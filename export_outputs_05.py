"""Exporta una ventana reciente de los datasets analíticos para análisis con IA."""
from __future__ import annotations

import argparse
import csv
import logging
import math
import os
import time
from pathlib import Path

LOGGER = logging.getLogger("binance_orquestador.export_outputs")

TIMEFRAMES_POR_DEFECTO = ["5m", "15m", "12h"]
TOKEN_LIMIT_POR_DEFECTO = 16_000
CHARS_POR_TOKEN_POR_DEFECTO = 3.0
MARGEN_POR_DEFECTO = 0.95
BYTES_COLA_POR_DEFECTO = 2 * 1024 * 1024

PRESET_POR_DEFECTO = "compact"
SHARE_RECIENTE_POR_DEFECTO = 0.6
SHARE_MAX_DENSO_POR_DEFECTO = 0.85

COLUMNAS_COMPACTAS = [
    "fecha_local", "open", "high", "low", "close", "volume", "quote_asset_volume",
    "number_of_trades", "taker_buy_quote_asset_volume", "retorno_pct", "rango_hl_pct",
    "oi_value_usd", "global_ls_ratio", "top_accounts_ratio", "top_positions_ratio",
    "taker_buy_sell_ratio", "fundingRate",
]

VENTANA_RECIENTE_HORAS_POR_TF = {"5m": 8.0}
BUCKET_VIEJO_POR_TF = {"5m": 12, "15m": 4, "12h": 1}

def estimar_tokens(texto: str, chars_por_token: float) -> int:
    if not texto: return 0
    return math.ceil(len(texto) / chars_por_token)

def construir_texto(header: str, filas: list[str]) -> str:
    if not filas: return header + "\n"
    return header + "\n" + "\n".join(filas) + "\n"

def leer_encabezado_y_cola(archivo: Path, max_bytes: int = BYTES_COLA_POR_DEFECTO):
    tam = archivo.stat().st_size
    if tam == 0: return "", []
    with archivo.open("rb") as f:
        header = f.readline().decode("utf-8").rstrip("\r\n")
        if not header: return "", []
        inicio = max(0, tam - max_bytes)
        if inicio > 0:
            f.seek(inicio)
            f.readline()
        resto = f.read().decode("utf-8")
    filas = [linea for linea in resto.splitlines() if linea.strip()]
    return header, filas

def _columnas_header(header: str) -> list[str]:
    try: return next(csv.reader([header]))
    except (csv.Error, StopIteration): return []

def _indice_columna(header: str, nombre: str) -> int | None:
    columnas = _columnas_header(header)
    try: return columnas.index(nombre)
    except ValueError: return None

def _valor_columna(fila: str, indice: int | None) -> str | None:
    if indice is None: return None
    try: return next(csv.reader([fila]))[indice]
    except (csv.Error, StopIteration, IndexError): return None

def _close_time_ms(fila: str, indice: int | None) -> int | None:
    valor = _valor_columna(fila, indice)
    if valor is None: return None
    try: return int(float(valor))
    except ValueError: return None

def _open_time_ms(fila: str, indice: int | None) -> int | None:
    return _close_time_ms(fila, indice)

def excluir_vela_en_formacion(header: str, filas: list[str], ahora_ms: int) -> list[str]:
    if not filas: return filas
    indice = _indice_columna(header, "close_time_ms")
    close_ms = _close_time_ms(filas[-1], indice)
    if close_ms is not None and close_ms > ahora_ms:
        return filas[:-1]
    return filas

def proyectar_columnas(header: str, filas: list[str], columnas: list[str]):
    disponibles = _columnas_header(header)
    indices, nombres = [], []
    for nombre in columnas:
        if nombre in disponibles:
            indices.append(disponibles.index(nombre))
            nombres.append(nombre)
    header_out = ",".join(nombres)
    filas_out = []
    for fila in filas:
        try: valores = next(csv.reader([fila]))
        except (csv.Error, StopIteration): continue
        filas_out.append(",".join(valores[i] if i < len(valores) else "" for i in indices))
    return header_out, filas_out

def _tokens_fila(fila: str, chars_por_token: float) -> int:
    return estimar_tokens(fila + "\n", chars_por_token)

def _tomar_cola_por_presupuesto(filas: list[str], max_tokens: int, chars_por_token: float) -> list[str]:
    if not filas: return []
    acc = 0
    inicio = len(filas)
    for i in range(len(filas) - 1, -1, -1):
        tokens = _tokens_fila(filas[i], chars_por_token)
        if inicio < len(filas) and acc + tokens > max_tokens: break
        acc += tokens
        inicio = i
    if inicio == len(filas): return filas[-1:]
    return filas[inicio:]

def _inicio_ventana(timestamps: list[int | None], cutoff_ms: int) -> int:
    inicio = len(timestamps)
    for i in range(len(timestamps) - 1, -1, -1):
        ts = timestamps[i]
        if ts is not None and ts >= cutoff_ms: inicio = i
        else: break
    return inicio

def seleccionar_hibrido(header: str, filas: list[str], timestamps: list[int | None], ahora_ms: int, token_objetivo: int, chars_por_token: float, share_reciente: float, ventana_reciente_h: float | None, stride_viejo: int) -> tuple[list[str], dict]:
    if not filas: return [], {"filas_recientes": 0, "filas_muestreadas": 0, "stride": stride_viejo}
    tokens_header = estimar_tokens(header + "\n", chars_por_token)
    presupuesto_filas = max(0, token_objetivo - tokens_header)
    if ventana_reciente_h is not None:
        ultimo_ts = next((ts for ts in reversed(timestamps) if ts is not None), None)
        referencia_ms = ultimo_ts if ultimo_ts is not None else ahora_ms
        cutoff_ms = referencia_ms - int(ventana_reciente_h * 3600 * 1000)
        inicio_ventana = _inicio_ventana(timestamps, cutoff_ms)
        candidatas_densas = filas[inicio_ventana:]
        max_denso = int(presupuesto_filas * SHARE_MAX_DENSO_POR_DEFECTO)
    else:
        candidatas_densas = filas
        max_denso = int(presupuesto_filas * share_reciente)
    densas = _tomar_cola_por_presupuesto(candidatas_densas, max_denso, chars_por_token)
    if not densas and filas: densas = filas[-1:]
    tokens_densas = sum(_tokens_fila(fila, chars_por_token) for fila in densas)
    tokens_restantes = presupuesto_filas - tokens_densas
    n_densas = len(densas)
    antiguas = filas[: len(filas) - n_densas]
    muestreadas: list[str] = []
    if antiguas and tokens_restantes > 0 and stride_viejo >= 1:
        acc = 0
        for i in range(len(antiguas) - 1, -1, -stride_viejo):
            tokens = _tokens_fila(antiguas[i], chars_por_token)
            if muestreadas and acc + tokens > tokens_restantes: break
            muestreadas.append(antiguas[i])
            acc += tokens
        muestreadas.reverse()
    seleccion = muestreadas + densas
    meta = {"filas_recientes": n_densas, "filas_muestreadas": len(muestreadas), "stride": stride_viejo}
    return seleccion, meta

def escribir_texto_atomico(texto: str, archivo: Path) -> None:
    archivo.parent.mkdir(parents=True, exist_ok=True)
    temporal = archivo.with_name(f".{archivo.name}.tmp")
    with temporal.open("w", encoding="utf-8", newline="") as f: f.write(texto)
    os.replace(temporal, archivo)

def _rango_fechas(header: str, filas: list[str]) -> tuple[str, str]:
    indice = _indice_columna(header, "fecha_local") or _indice_columna(header, "fecha_utc")
    if indice is None or not filas: return "N/A", "N/A"
    return _valor_columna(filas[0], indice) or "N/A", _valor_columna(filas[-1], indice) or "N/A"

def resolver_columnas(preset: str, columnas_personalizadas: list[str] | None) -> list[str] | None:
    if columnas_personalizadas: return columnas_personalizadas
    if preset == "full": return None
    return COLUMNAS_COMPACTAS

def exportar_archivo(archivo_origen: Path, archivo_salida: Path, token_limit: int, chars_por_token: float, margen: float, incluir_vela_en_formacion: bool, ahora_ms: int, preset: str = PRESET_POR_DEFECTO, columnas_personalizadas: list[str] | None = None, share_reciente: float = SHARE_RECIENTE_POR_DEFECTO, ventana_reciente_h: float | None = None, stride_viejo: int = 1, bytes_cola: int = BYTES_COLA_POR_DEFECTO) -> dict | None:
    if not archivo_origen.exists(): return None
    header_raw, filas_raw = leer_encabezado_y_cola(archivo_origen, bytes_cola)
    if not header_raw or not filas_raw: return None
    if not incluir_vela_en_formacion:
        filas_raw = excluir_vela_en_formacion(header_raw, filas_raw, ahora_ms)
        if not filas_raw: return None
    indice_ts = _indice_columna(header_raw, "open_time_ms")
    timestamps = [_open_time_ms(fila, indice_ts) for fila in filas_raw]
    columnas = resolver_columnas(preset, columnas_personalizadas)
    if columnas is None: header, filas = header_raw, filas_raw
    else:
        header, filas = proyectar_columnas(header_raw, filas_raw, columnas)
        if not header: return None
    token_objetivo = max(1, int(token_limit * margen))
    seleccion, meta = seleccionar_hibrido(header=header, filas=filas, timestamps=timestamps, ahora_ms=ahora_ms, token_objetivo=token_objetivo, chars_por_token=chars_por_token, share_reciente=share_reciente, ventana_reciente_h=ventana_reciente_h, stride_viejo=stride_viejo)
    if not seleccion: return None
    texto = construir_texto(header, seleccion)
    tokens = estimar_tokens(texto, chars_por_token)
    escribir_texto_atomico(texto, archivo_salida)
    inicio, fin = _rango_fechas(header, seleccion)
    return {"filas": len(seleccion), "caracteres": len(texto), "tokens": tokens, "inicio": inicio, "fin": fin, "filas_recientes": meta["filas_recientes"], "filas_muestreadas": meta["filas_muestreadas"], "bucket": meta["stride"]}

def _descubrir_simbolos(data_dir: Path) -> list[str]:
    if not data_dir.exists(): return []
    return sorted(p.name for p in data_dir.iterdir() if p.is_dir() and (p / "consolidado").is_dir())

def _escribir_resumen(filas: list[dict], archivo: Path) -> None:
    archivo.parent.mkdir(parents=True, exist_ok=True)
    temporal = archivo.with_name(f".{archivo.name}.tmp")
    with temporal.open("w", encoding="utf-8", newline="") as f:
        escritor = csv.DictWriter(f, fieldnames=["symbol", "timeframe", "filas", "filas_recientes", "filas_muestreadas", "bucket", "tokens_estimados", "caracteres", "rango_inicio", "rango_fin", "archivo_salida"])
        escritor.writeheader()
        for fila in filas: escritor.writerow(fila)
    os.replace(temporal, archivo)

def ejecutar_exportacion(symbols: list[str] | None = None, data_dir: Path = Path("data"), out_dir: Path = Path("outputs"), timeframes: list[str] | None = None, token_limit: int = TOKEN_LIMIT_POR_DEFECTO, chars_por_token: float = CHARS_POR_TOKEN_POR_DEFECTO, margen: float = MARGEN_POR_DEFECTO, incluir_vela_en_formacion: bool = False, preset: str = PRESET_POR_DEFECTO, columnas_personalizadas: list[str] | None = None, share_reciente: float = SHARE_RECIENTE_POR_DEFECTO, ventana_reciente: float | None = None, bucket_viejo: int | None = None, bytes_cola: int = BYTES_COLA_POR_DEFECTO, ahora_ms: int | None = None) -> list[dict]:
    data_dir, out_dir = Path(data_dir), Path(out_dir)
    timeframes = TIMEFRAMES_POR_DEFECTO if timeframes is None else timeframes
    ahora_ms = int(time.time() * 1000) if ahora_ms is None else int(ahora_ms)
    symbols = [s.upper() for s in (symbols if symbols is not None else _descubrir_simbolos(data_dir))]
    resumen: list[dict] = []
    for symbol in symbols:
        for tf in timeframes:
            archivo_origen = data_dir / symbol.lower() / "consolidado" / f"dataset_analisis_{tf}.csv"
            archivo_salida = out_dir / symbol.lower() / f"dataset_analisis_{tf}.csv"
            ventana = ventana_reciente if ventana_reciente is not None else VENTANA_RECIENTE_HORAS_POR_TF.get(tf)
            stride = bucket_viejo if bucket_viejo is not None else BUCKET_VIEJO_POR_TF.get(tf, 1)
            stats = exportar_archivo(archivo_origen, archivo_salida, token_limit, chars_por_token, margen, incluir_vela_en_formacion, ahora_ms, preset, columnas_personalizadas, share_reciente, ventana, stride, bytes_cola)
            if stats is None: continue
            resumen.append({"symbol": symbol, "timeframe": tf, "filas": stats["filas"], "filas_recientes": stats["filas_recientes"], "filas_muestreadas": stats["filas_muestreadas"], "bucket": stats["bucket"], "tokens_estimados": stats["tokens"], "caracteres": stats["caracteres"], "rango_inicio": stats["inicio"], "rango_fin": stats["fin"], "archivo_salida": str(archivo_salida)})
    if resumen: _escribir_resumen(resumen, out_dir / "_resumen.csv")
    return resumen

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", type=Path, default=Path("data"))
    parser.add_argument("--out-dir", type=Path, default=Path("outputs"))
    parser.add_argument("--symbols", nargs="+", default=None)
    parser.add_argument("--timeframes", nargs="+", default=TIMEFRAMES_POR_DEFECTO)
    parser.add_argument("--token-limit", type=int, default=TOKEN_LIMIT_POR_DEFECTO)
    parser.add_argument("--chars-por-token", type=float, default=CHARS_POR_TOKEN_POR_DEFECTO)
    parser.add_argument("--margen", type=float, default=MARGEN_POR_DEFECTO)
    parser.add_argument("--preset", choices=["compact", "full"], default=PRESET_POR_DEFECTO)
    parser.add_argument("--columnas", nargs="+", default=None)
    parser.add_argument("--share-reciente", type=float, default=SHARE_RECIENTE_POR_DEFECTO)
    parser.add_argument("--ventana-reciente", type=float, default=None)
    parser.add_argument("--bucket-viejo", type=int, default=None)
    parser.add_argument("--bytes-cola", type=int, default=BYTES_COLA_POR_DEFECTO)
    parser.add_argument("--incluir-vela-en-formacion", action="store_true")
    args = parser.parse_args()
    ejecutar_exportacion(args.symbols, args.data_dir, args.out_dir, args.timeframes, args.token_limit, args.chars_por_token, args.margen, args.incluir_vela_en_formacion, args.preset, args.columnas, args.share_reciente, args.ventana_reciente, args.bucket_viejo, args.bytes_cola)

if __name__ == "__main__":
    main()
