import io
import zipfile
import requests
import pandas as pd
from datetime import datetime
from dateutil.relativedelta import relativedelta
from pathlib import Path

COLUMNAS_KLINES = [
    "open_time_ms", "open", "high", "low", "close", "volume",
    "close_time_ms", "quote_asset_volume", "number_of_trades",
    "taker_buy_base_asset_volume", "taker_buy_quote_asset_volume", "ignore"
]

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

    if dataframes:
        df_master = pd.concat(dataframes, ignore_index=True)
        if df_master.shape[1] == 12:
            df_master.columns = COLUMNAS_KLINES
        
        df_master["open_time_ms"] = pd.to_numeric(df_master["open_time_ms"], errors="coerce")
        df_master.dropna(subset=["open_time_ms"], inplace=True)
        df_master["open_time_ms"] = df_master["open_time_ms"].astype("int64")
        df_master.drop_duplicates(subset=["open_time_ms"], keep="last", inplace=True)
        df_master.sort_values("open_time_ms", inplace=True)

        archivo_csv = out_dir / f"binance_vision_klines_{tf}.csv"
        df_master.to_csv(archivo_csv, index=False)
        logger.info(f"[binance_vision] Archivo consolidado guardado: {archivo_csv.name} ({len(df_master)} filas)")
        return len(df_master)
    return 0

def obtener_klines_api(client, symbol: str, tf: str, start_ms: int, end_ms: int, logger) -> list:
    try:
        klines = client.futures_historical_klines(
            symbol=symbol,
            interval=tf,
            start_str=start_ms,
            end_str=end_ms
        )
        return [{
            "open_time_ms": k[0],
            "open": k[1],
            "high": k[2],
            "low": k[3],
            "close": k[4],
            "volume": k[5],
            "close_time_ms": k[6],
            "quote_asset_volume": k[7],
            "number_of_trades": k[8],
            "taker_buy_base_asset_volume": k[9],
            "taker_buy_quote_asset_volume": k[10]
        } for k in klines]
    except Exception as e:
        logger.error(f"[api_rest_klines_{tf}] Error: {e}")
        return []

def obtener_funding_rates(client, symbol: str, start_ms: int, end_ms: int, logger) -> list:
    try:
        data = client.futures_funding_rate(symbol=symbol, startTime=start_ms, endTime=end_ms, limit=1000)
        return data or []
    except Exception as e:
        logger.error(f"[api_rest_funding] Error: {e}")
        return []

def obtener_liquidaciones(client, symbol: str, start_ms: int, end_ms: int, logger) -> list:
    try:
        data = client.futures_liquidation_orders(symbol=symbol, startTime=start_ms, endTime=end_ms, limit=100)
        return data or []
    except Exception as e:
        logger.error(f"[api_rest_liquidaciones] Error: {e}")
        return []

def obtener_metricas_sentimiento(api_key: str, symbol: str, tf: str, start_ms: int, end_ms: int, logger) -> dict:
    metricas = {
        "open_interest": [],
        "global_ls": [],
        "top_ls_accounts": [],
        "top_ls_positions": [],
        "taker_vol": []
    }
    headers = {"X-MBX-APIKEY": api_key} if api_key else {}
    endpoints = {
        "open_interest": "https://fapi.binance.com/futures/data/openInterestHist",
        "global_ls": "https://fapi.binance.com/futures/data/globalLongShortAccountRatio",
        "top_ls_accounts": "https://fapi.binance.com/futures/data/topLongShortAccountRatio",
        "top_ls_positions": "https://fapi.binance.com/futures/data/topLongShortPositionRatio",
        "taker_vol": "https://fapi.binance.com/futures/data/takerlongshortRatio"
    }
    params = {
        "symbol": symbol.upper(),
        "period": tf,
        "startTime": start_ms,
        "endTime": end_ms,
        "limit": 500
    }
    for clave, url in endpoints.items():
        try:
            res = requests.get(url, params=params, headers=headers, timeout=10)
            if res.status_code == 200:
                data = res.json()
                if isinstance(data, list):
                    metricas[clave] = data
            elif res.status_code != 400:
                logger.warning(f"[api_rest_sentimiento] {clave} HTTP {res.status_code}: {res.text}")
        except Exception as e:
            logger.error(f"[api_rest_sentimiento] {clave} Error: {e}")

    return metricas
