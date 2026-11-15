"""export_outputs_05.py: Genera snapshots compactos de BTC para análisis con IA."""

from __future__ import annotations

import argparse
import io
import logging
import os
import re
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

LOGGER = logging.getLogger("binance_orquestador.export_outputs")
ZONA_HORARIA = ZoneInfo("America/Mexico_City")

SIMBOLO_EXPORTACION = "BTCUSDT"
TIMEFRAMES_POR_DEFECTO = ["5m", "15m", "12h"]
MINUTOS_POR_TF = {"5m": 5, "15m": 15, "12h": 720}
# 5m: 12 h de cobertura; 15m: 24 h; 12h: 14 días.
LIMITE_FILAS_POR_TF = {"5m": 144, "15m": 96, "12h": 28}
VENTANA_INICIAL_BYTES = 1 << 20
PATRON_SNAPSHOT = re.compile(r"^data_\d{6}_(5|15|720)\.csv$")

COLUMNAS_COMPACTAS = [
    "fecha_local", "open", "high", "low", "close", "volume", "quote_asset_volume",
    "number_of_trades", "taker_buy_quote_asset_volume", "retorno_pct", "rango_hl_pct",
    "oi_value_usd", "global_ls_ratio", "top_accounts_ratio", "top_positions_ratio",
    "taker_buy_sell_ratio", "fundingRate",
]


def _leer_cola(archivo: Path, filas: int) -> pd.DataFrame:
    """Lee solo el encabezado y las últimas `filas` líneas del CSV."""
    tamano = archivo.stat().st_size
    if tamano == 0:
        return pd.DataFrame()

    with archivo.open("rb") as f:
        encabezado = f.readline()
        if not encabezado:
            return pd.DataFrame()

        ventana = VENTANA_INICIAL_BYTES
        while True:
            inicio = max(0, tamano - ventana)
            if inicio == 0:
                f.seek(len(encabezado))
                lineas = f.read().splitlines(keepends=True)
            else:
                f.seek(inicio - 1)
                lineas = f.read().splitlines(keepends=True)[1:]
            if len(lineas) >= filas or inicio == 0:
                break
            ventana *= 2

    if not lineas:
        return pd.DataFrame()

    texto = (encabezado + b"".join(lineas[-filas:])).decode("utf-8", errors="replace")
    try:
        try:
            return pd.read_csv(io.StringIO(texto), engine="pyarrow")
        except ImportError:
            return pd.read_csv(io.StringIO(texto), low_memory=False)
    except pd.errors.EmptyDataError:
        return pd.DataFrame()


def _limpiar_snapshots(salida_dir: Path) -> list[str]:
    """Elimina los snapshots previos de los tres timeframes."""
    if not salida_dir.is_dir():
        return []
    eliminados: list[str] = []
    for archivo in sorted(salida_dir.iterdir()):
        if not archivo.is_file() or not PATRON_SNAPSHOT.match(archivo.name):
            continue
        try:
            archivo.unlink()
            eliminados.append(archivo.name)
            LOGGER.info("Snapshot previo eliminado: %s", archivo)
        except OSError as e:
            LOGGER.warning("No se pudo eliminar %s: %s", archivo, e)
    return eliminados


def minutos_timeframe(tf: str) -> int:
    if tf not in MINUTOS_POR_TF:
        raise ValueError(f"Timeframe sin equivalencia en minutos: {tf}")
    return MINUTOS_POR_TF[tf]


def nombre_snapshot(tf: str, ahora_ms: int) -> str:
    fecha = datetime.fromtimestamp(ahora_ms / 1000, tz=ZONA_HORARIA)
    return f"data_{fecha:%d%m%y}_{minutos_timeframe(tf)}.csv"


def _escribir_atomico(df: pd.DataFrame, archivo: Path) -> int:
    archivo.parent.mkdir(parents=True, exist_ok=True)
    temporal = archivo.with_name(f".{archivo.name}.tmp")
    df.to_csv(temporal, index=False)
    os.replace(temporal, archivo)
    return archivo.stat().st_size


def exportar_archivo(
    archivo_origen: Path,
    archivo_salida: Path,
    tf: str,
    incluir_vela_en_formacion: bool = False,
    ahora_ms: int | None = None,
) -> dict | None:
    if not archivo_origen.exists():
        LOGGER.warning("No existe el dataset de origen: %s", archivo_origen)
        return None

    limite = LIMITE_FILAS_POR_TF.get(tf)
    if limite is None:
        LOGGER.warning("Timeframe sin límite de filas definido: %s", tf)
        return None

    # Se piden dos filas extra para poder descartar la vela en formación.
    df = _leer_cola(archivo_origen, limite + 2)
    if df.empty:
        LOGGER.warning("Dataset vacío: %s", archivo_origen)
        return None

    if "open_time_ms" in df.columns:
        df = df.sort_values("open_time_ms")

    if not incluir_vela_en_formacion and "close_time_ms" in df.columns and ahora_ms is not None:
        ultimo_cierre = pd.to_numeric(df["close_time_ms"], errors="coerce").iloc[-1]
        if pd.notna(ultimo_cierre) and int(ultimo_cierre) > ahora_ms:
            df = df.iloc[:-1]

    df = df.tail(limite)

    columnas = [c for c in COLUMNAS_COMPACTAS if c in df.columns]
    faltantes = [c for c in COLUMNAS_COMPACTAS if c not in df.columns]
    if faltantes:
        LOGGER.warning("Columnas ausentes en %s: %s", archivo_origen.name, ", ".join(faltantes))
    if not columnas:
        return None

    df = df[columnas]
    caracteres = _escribir_atomico(df, archivo_salida)
    LOGGER.info("Snapshot BTC %s: %s filas -> %s", tf, len(df), archivo_salida)
    return {
        "symbol": SIMBOLO_EXPORTACION,
        "timeframe": tf,
        "filas": len(df),
        "columnas": len(columnas),
        "caracteres": caracteres,
        "archivo_salida": str(archivo_salida),
    }


def ejecutar_exportacion(
    data_dir: Path = Path("outputs/data"),
    out_dir: Path = Path("outputs"),
    timeframes: list[str] | None = None,
    incluir_vela_en_formacion: bool = False,
    ahora_ms: int | None = None,
) -> list[dict]:
    data_dir, out_dir = Path(data_dir), Path(out_dir)
    timeframes = TIMEFRAMES_POR_DEFECTO if timeframes is None else timeframes
    ahora_ms = int(time.time() * 1000) if ahora_ms is None else int(ahora_ms)

    origen_dir = data_dir / SIMBOLO_EXPORTACION.lower() / "consolidado"
    salida_dir = out_dir / SIMBOLO_EXPORTACION.lower()

    eliminados = _limpiar_snapshots(salida_dir)
    LOGGER.info("Limpieza de snapshots: %s archivo(s) eliminado(s).", len(eliminados))

    if not origen_dir.is_dir():
        LOGGER.warning("No hay datos de %s en %s; no se genera snapshot.", SIMBOLO_EXPORTACION, origen_dir)
        return []

    resultados: list[dict] = []
    for tf in timeframes:
        archivo_origen = origen_dir / f"dataset_analisis_{tf}.csv"
        archivo_salida = salida_dir / nombre_snapshot(tf, ahora_ms)
        stats = exportar_archivo(
            archivo_origen,
            archivo_salida,
            tf,
            incluir_vela_en_formacion=incluir_vela_en_formacion,
            ahora_ms=ahora_ms,
        )
        if stats is not None:
            resultados.append(stats)
    return resultados


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
    parser = argparse.ArgumentParser(description="Genera snapshots compactos de BTCUSDT.")
    parser.add_argument("--data-dir", type=Path, default=Path("outputs/data"))
    parser.add_argument("--out-dir", type=Path, default=Path("outputs"))
    parser.add_argument("--timeframes", nargs="+", default=TIMEFRAMES_POR_DEFECTO)
    parser.add_argument("--incluir-vela-en-formacion", action="store_true")
    args = parser.parse_args()
    ejecutar_exportacion(
        data_dir=args.data_dir,
        out_dir=args.out_dir,
        timeframes=args.timeframes,
        incluir_vela_en_formacion=args.incluir_vela_en_formacion,
    )


if __name__ == "__main__":
    main()
