import requests


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
