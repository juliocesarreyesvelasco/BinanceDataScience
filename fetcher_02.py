import time
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


def _get_sentimiento_con_reintentos(session: requests.Session, url: str, params: dict, headers: dict, logger, max_intentos: int = 3):
    espera = 1
    for intento in range(1, max_intentos + 1):
        try:
            res = session.get(url, params=params, headers=headers, timeout=10)
            if res.status_code == 200:
                return res, intento
            if res.status_code in (418, 429):
                try:
                    pausa = float(res.headers.get("Retry-After", espera))
                except (TypeError, ValueError):
                    pausa = espera
                logger.warning(f"[api_rest_sentimiento] HTTP {res.status_code}. Reintento {intento}/{max_intentos} en {pausa}s")
                time.sleep(pausa)
                espera *= 2
                continue
            return res, intento
        except Exception as e:
            logger.error(f"[api_rest_sentimiento] Error: {e}. Reintento {intento}/{max_intentos}")
            if intento < max_intentos:
                time.sleep(espera)
                espera *= 2
    return None, max_intentos


def obtener_metricas_sentimiento(session: requests.Session, api_key: str, symbol: str, tf: str, start_ms: int, end_ms: int, logger):
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
    peticiones = 0
    for clave, url in endpoints.items():
        res, intentos = _get_sentimiento_con_reintentos(session, url, params, headers, logger)
        peticiones += intentos
        if res is None:
            continue
        if res.status_code == 200:
            try:
                data = res.json()
            except ValueError:
                logger.error(f"[api_rest_sentimiento] {clave} respuesta no JSON")
                continue
            if isinstance(data, list):
                metricas[clave] = data
        elif res.status_code != 400:
            logger.warning(f"[api_rest_sentimiento] {clave} HTTP {res.status_code}: {res.text}")

    return metricas, peticiones
