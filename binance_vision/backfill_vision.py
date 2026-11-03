"""Descarga manual de Klines históricas desde Binance Vision.

Este script quedó fuera del pipeline diario. Se conserva como herramienta de
recuperación para reconstruir el histórico de Klines si se pierde el archivo
crudo de la API REST o si se necesita un respaldo independiente.

Uso:
    ./binance_env/bin/python binance_vision/backfill_vision.py --years 3
"""

import argparse
import io
import logging
import os
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import requests
from dateutil.relativedelta import relativedelta

COLUMNAS_KLINES = [
    "open_time_ms", "open", "high", "low", "close", "volume",
    "close_time_ms", "quote_asset_volume", "number_of_trades",
    "taker_buy_base_asset_volume", "taker_buy_quote_asset_volume", "ignore"
]

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR_POR_DEFECTO = BASE_DIR / "data"


def descargar_zips_vision(symbol: str, tf: str, start_date: datetime, end_date: datetime, out_dir: Path, logger):
    current_date = start_date
    dataframes = []

    while current_date < end_date:
        mes_str = current_date.strftime("%Y-%m")
        url = f"https://data.binance.vision/data/futures/um/monthly/klines/{symbol}/{tf}/{symbol}-{tf}-{mes_str}.zip"

        try:
            res = requests.get(url, timeout=20)
            if res.status_code == 200:
                logger.info(f"[binance_vision] {symbol} {tf}: Descargando {mes_str}...")
                with zipfile.ZipFile(io.BytesIO(res.content)) as z:
                    for filename in z.namelist():
                        with z.open(filename) as f:
                            df = pd.read_csv(f, header=None)
                            dataframes.append(df)
            else:
                logger.warning(f"[binance_vision] {symbol} {tf}: No disponible {mes_str} (HTTP {res.status_code})")
        except Exception as e:
            logger.error(f"[binance_vision] Error descargando {mes_str}: {e}")

        current_date += relativedelta(months=1)

    if not dataframes:
        return 0

    df_master = pd.concat(dataframes, ignore_index=True)
    if df_master.shape[1] == 12:
        df_master.columns = COLUMNAS_KLINES

    df_master["open_time_ms"] = pd.to_numeric(df_master["open_time_ms"], errors="coerce")
    df_master.dropna(subset=["open_time_ms"], inplace=True)
    df_master["open_time_ms"] = df_master["open_time_ms"].astype("int64")
    df_master.drop_duplicates(subset=["open_time_ms"], keep="last", inplace=True)
    df_master.sort_values("open_time_ms", inplace=True)

    archivo_csv = out_dir / f"binance_vision_klines_{tf}.csv"
    temporal = archivo_csv.with_name(f".{archivo_csv.name}.tmp")
    df_master.to_csv(temporal, index=False)
    os.replace(temporal, archivo_csv)
    logger.info(f"[binance_vision] Archivo consolidado guardado: {archivo_csv.name} ({len(df_master)} filas)")
    return len(df_master)


def main():
    parser = argparse.ArgumentParser(description="Descarga manual de Klines desde Binance Vision")
    parser.add_argument("--symbols", nargs="+", default=["BNBUSDT", "BTCUSDT", "ETHUSDT", "XRPUSDT", "SOLUSDT"])
    parser.add_argument("--timeframes", nargs="+", default=["15m", "12h"])
    parser.add_argument("--years", type=int, default=3)
    parser.add_argument("--data-dir", type=Path, default=DATA_DIR_POR_DEFECTO)
    parser.add_argument("--pause", type=float, default=0.0, help="Segundos de pausa entre símbolos/timeframes")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
    logger = logging.getLogger("binance_vision_backfill")

    ahora_utc = datetime.now(timezone.utc)
    fecha_inicio = ahora_utc - timedelta(days=365 * args.years)

    for symbol in args.symbols:
        out_dir = args.data_dir / symbol.lower() / "raw" / "binance_vision"
        out_dir.mkdir(parents=True, exist_ok=True)
        for tf in args.timeframes:
            logger.info(f"=== {symbol} {tf}: {fecha_inicio.date()} -> {ahora_utc.date()} ===")
            descargar_zips_vision(symbol, tf, fecha_inicio, ahora_utc, out_dir, logger)
            if args.pause:
                import time
                time.sleep(args.pause)


if __name__ == "__main__":
    main()
