> **Obsoleto:** esta es una propuesta de referencia y no refleja el estado implementado. El proyecto final descarta liquidaciones, archiva Binance Vision, usa nombres de master alineados, columnas de sentimiento con prefijos y hora local de Ciudad de México. Ver `Proceso Arquitectura Binance.md`.

Los modelos Flash son absolutamente suficientes para programar, depurar y analizar los logs de tu pipeline, aunque vale aclarar que la nomenclatura oficial actual en Google AI Studio corresponde a la familia Gemini 1.5 y al reciente Gemini 2.0, no existiendo en producción las versiones 2.5, 3.6 o 3.8.

**Eficiencia de la arquitectura Flash**
Estos modelos utilizan una estructura de menor peso paramétrico optimizada para baja latencia, lo que permite inyectar y procesar de forma casi instantánea ventanas de contexto gigantes. Son ideales para tareas con reglas estructuradas y patrones predecibles, como depurar la sintaxis de Python, refactorizar scripts o escanear tus logs de ejecución en busca de advertencias.

**Necesidad de modelos Pro para datos**
Al introducir un CSV de 106,000 filas, la tarea cambia de reconocimiento de texto a razonamiento complejo. Los modelos Pro poseen una mayor densidad de parámetros y entrenamiento avanzado en lógica matemática, lo que les permite inferir correlaciones, entender distribuciones y mantener la coherencia analítica en datasets masivos, tareas donde un modelo Flash suele perder el hilo estadístico o alucinar datos.

**Impacto en costos**
Esta capacidad computacional define el modelo de precios: procesar código y logs con Flash cuesta apenas centavos por millón de tokens, mientras que el análisis estadístico profundo con modelos Pro es significativamente más caro por la energía y hardware necesarios para su razonamiento avanzado.



auth.py


import os
import time
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path
from binance.client import Client

import fetcher
import storage
import consolidator

# --- PARÁMETROS GLOBALES ---
API_KEY = os.getenv("BINANCE_API_KEY", "TU_API_KEY")
API_SECRET = os.getenv("BINANCE_API_SECRET", "TU_API_SECRET")
PARES = ["BTCUSDT", "ETHUSDT", "BNBUSDT", "XRPUSDT", "SOLUSDT"]
TIMEFRAMES = ["15m", "12h"]
PAUSA_SEGUNDOS = 1
ANOS_HISTORIA = 3

BASE_DIR = Path(os.path.dirname(os.path.abspath(__file__)))
LOG_DIR = BASE_DIR / "logs"
LOG_DIR.mkdir(exist_ok=True)
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)

def setup_logger():
    logger = logging.getLogger("binance_orquestador")
    if not logger.handlers:
        logger.setLevel(logging.INFO)
        fh = logging.FileHandler(LOG_DIR / "proceso.log", encoding="utf-8")
        formatter = logging.Formatter("%(asctime)s - %(levelname)s - [%(module)s] - %(message)s")
        fh.setFormatter(formatter)
        ch = logging.StreamHandler()
        ch.setFormatter(formatter)
        logger.addHandler(fh)
        logger.addHandler(ch)
    return logger

logger = setup_logger()

def main():
    logger.info("=== INICIANDO ORQUESTADOR DE INGESTA (API REST ONLY) ===")
    client = Client(API_KEY, API_SECRET)

    ahora_utc = datetime.now(timezone.utc)
    fecha_fin_ms = int(ahora_utc.timestamp() * 1000)
    fecha_inicio_global = ahora_utc - timedelta(days=365 * ANOS_HISTORIA)
    fecha_inicio_global_ms = int(fecha_inicio_global.timestamp() * 1000)

    for symbol in PARES:
        symbol_dir = DATA_DIR / symbol.lower()
        symbol_dir.mkdir(parents=True, exist_ok=True)

        # 1. API REST: KLINES
        for tf in TIMEFRAMES:
            nombre_proc = f"api_rest_klines_{tf}"
            ckpt = storage.leer_checkpoint(symbol_dir, nombre_proc)
            dias_paso = 30 if tf == "15m" else 180

            if not ckpt.get("backfill_completado"):
                logger.info(f"[{symbol}] Ejecutando Backfill histórico API Klines {tf}...")
                cursor = ahora_utc
                while cursor > fecha_inicio_global:
                    inicio_lote = cursor - timedelta(days=dias_paso)
                    datos = fetcher.obtener_klines_api(client, symbol, tf, int(inicio_lote.timestamp() * 1000), int(cursor.timestamp() * 1000), logger)
                    storage.guardar_coleccion_raw(symbol_dir, "api_rest", nombre_proc, datos, "open_time_ms", logger)
                    cursor = inicio_lote
                    time.sleep(PAUSA_SEGUNDOS)
                storage.actualizar_checkpoint(symbol_dir, nombre_proc, backfill_completo=True, ultimo_ms=fecha_fin_ms, mas_antiguo_ms=fecha_inicio_global_ms)
            else:
                desde_ms = ckpt.get("ultimo_timestamp_reciente_ms", fecha_fin_ms - 86400000)
                if fecha_fin_ms - desde_ms > 60000:
                    logger.info(f"[{symbol}] Sincronizando Klines recientes {tf}...")
                    datos = fetcher.obtener_klines_api(client, symbol, tf, desde_ms, fecha_fin_ms, logger)
                    storage.guardar_coleccion_raw(symbol_dir, "api_rest", nombre_proc, datos, "open_time_ms", logger)
                    storage.actualizar_checkpoint(symbol_dir, nombre_proc, backfill_completo=True, ultimo_ms=fecha_fin_ms)

        # 2. API REST: FUNDING RATES
        nombre_proc_funding = "api_rest_funding_rate"
        ckpt_funding = storage.leer_checkpoint(symbol_dir, nombre_proc_funding)
        if not ckpt_funding.get("backfill_completado"):
            logger.info(f"[{symbol}] Ejecutando Backfill histórico de Funding Rates...")
            cursor = ahora_utc
            while cursor > fecha_inicio_global:
                inicio_lote = cursor - timedelta(days=120)
                datos = fetcher.obtener_funding_rates(client, symbol, int(inicio_lote.timestamp() * 1000), int(cursor.timestamp() * 1000), logger)
                storage.guardar_coleccion_raw(symbol_dir, "api_rest", nombre_proc_funding, datos, "fundingTime", logger)
                cursor = inicio_lote
                time.sleep(PAUSA_SEGUNDOS)
            storage.actualizar_checkpoint(symbol_dir, nombre_proc_funding, backfill_completo=True, ultimo_ms=fecha_fin_ms, mas_antiguo_ms=fecha_inicio_global_ms)
        else:
            desde_ms = ckpt_funding.get("ultimo_timestamp_reciente_ms", fecha_fin_ms - 86400000)
            if fecha_fin_ms - desde_ms > 60000:
                logger.info(f"[{symbol}] Sincronizando Funding Rates recientes...")
                datos = fetcher.obtener_funding_rates(client, symbol, desde_ms, fecha_fin_ms, logger)
                storage.guardar_coleccion_raw(symbol_dir, "api_rest", nombre_proc_funding, datos, "fundingTime", logger)
                storage.actualizar_checkpoint(symbol_dir, nombre_proc_funding, backfill_completo=True, ultimo_ms=fecha_fin_ms)

        # 3. API REST: LIQUIDACIONES (Captura estricta de últimos 7 días y luego incremental)
        nombre_proc_liq = "api_rest_liquidaciones"
        ckpt_liq = storage.leer_checkpoint(symbol_dir, nombre_proc_liq)
        if not ckpt_liq.get("backfill_completado"):
            logger.info(f"[{symbol}] Extrayendo lote inicial de Liquidaciones (últimos 7 días)...")
            inicio_lote = ahora_utc - timedelta(days=7)
            datos = fetcher.obtener_liquidaciones(client, symbol, int(inicio_lote.timestamp() * 1000), fecha_fin_ms, logger)
            if datos:
                storage.guardar_coleccion_raw(symbol_dir, "api_rest", nombre_proc_liq, datos, "time", logger)
            storage.actualizar_checkpoint(symbol_dir, nombre_proc_liq, backfill_completo=True, ultimo_ms=fecha_fin_ms)
        else:
            desde_ms = ckpt_liq.get("ultimo_timestamp_reciente_ms", fecha_fin_ms - (7 * 86400000))
            if fecha_fin_ms - desde_ms > 60000:
                logger.info(f"[{symbol}] Actualización incremental de Liquidaciones...")
                datos = fetcher.obtener_liquidaciones(client, symbol, desde_ms, fecha_fin_ms, logger)
                if datos:
                    storage.guardar_coleccion_raw(symbol_dir, "api_rest", nombre_proc_liq, datos, "time", logger)
                storage.actualizar_checkpoint(symbol_dir, nombre_proc_liq, backfill_completo=True, ultimo_ms=fecha_fin_ms)

        # 4. API REST: SENTIMIENTO (Ventana fija 28 días)
        fecha_inicio_sentimiento = ahora_utc - timedelta(days=28)
        for tf in TIMEFRAMES:
            logger.info(f"[{symbol}] Extrayendo Sentimiento reciente {tf}...")
            cursor = ahora_utc
            while cursor > fecha_inicio_sentimiento:
                inicio_lote = cursor - timedelta(days=7)
                datos_dic = fetcher.obtener_metricas_sentimiento(
                    API_KEY, symbol, tf,
                    int(inicio_lote.timestamp() * 1000),
                    int(cursor.timestamp() * 1000),
                    logger
                )
                for metrica_nombre, lista in datos_dic.items():
                    if lista:
                        storage.guardar_coleccion_raw(
                            symbol_dir, "api_rest",
                            f"api_rest_{metrica_nombre}_{tf}", lista, "timestamp", logger
                        )
                cursor = inicio_lote
                time.sleep(PAUSA_SEGUNDOS)

        # 5. CONSOLIDACIÓN
        logger.info(f"[{symbol}] FASE 5: Consolidando y generando archivos maestros...")
        consolidator.consolidar_symbol(symbol, DATA_DIR, LOG_DIR)

    logger.info("=== FLUJO DE EJECUCIÓN COMPLETADO ===")

if __name__ == "__main__":
    main()




fetcher.py

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


    consolidator.py

    import logging
from pathlib import Path
from datetime import datetime
import pandas as pd

def setup_consolidator_logger(log_dir: Path):
    c_logger = logging.getLogger("consolidator_audit")
    if not c_logger.handlers:
        c_logger.setLevel(logging.INFO)
        fh = logging.FileHandler(log_dir / "consolidacion.log", encoding="utf-8")
        formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
        fh.setFormatter(formatter)
        ch = logging.StreamHandler()
        ch.setFormatter(formatter)
        c_logger.addHandler(fh)
        c_logger.addHandler(ch)
    return c_logger

def consolidar_symbol(symbol: str, data_dir: Path, log_dir: Path):
    logger = setup_consolidator_logger(log_dir)
    symbol_dir = data_dir / symbol.lower()
    raw_dir = symbol_dir / "raw"
    out_dir = symbol_dir / "consolidado"
    out_dir.mkdir(parents=True, exist_ok=True)

    fecha_procesamiento = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    logger.info("=========================================================================================")
    logger.info(f"INICIANDO CONSOLIDACIÓN AUDITADA PARA: {symbol.upper()}")
    logger.info("=========================================================================================")

    resumen_salidas = []

    def log_transformacion(archivo_nombre, origen_desc, filas_origen, filas_duplicadas, filas_finales, df_resultado):
        rango_fechas = "N/A"
        if not df_resultado.empty and "fecha_utc" in df_resultado.columns:
            rango_fechas = f"{df_resultado['fecha_utc'].min()} -> {df_resultado['fecha_utc'].max()}"
        
        logger.info(f"[PROCESADO] {archivo_nombre}")
        logger.info(f"  • Archivo(s) Fuente: {origen_desc}")
        logger.info(f"  • Filas brutas leídas: {filas_origen} | Duplicadas descartadas: {filas_duplicadas} | Consolidadas: {filas_finales}")
        logger.info(f"  • Rango Temporal: {rango_fechas}")

        resumen_salidas.append({
            "Archivo Consolidado": archivo_nombre,
            "Filas": filas_finales,
            "Columnas": len(df_resultado.columns),
            "Rango Fechas": rango_fechas
        })

    # 1. Klines Maestras
    def procesar_klines(tf):
        f_api = raw_dir / "api_rest" / f"api_rest_klines_{tf}.csv"
        archivo_nombre = f"api_rest_klines_{tf}_master.csv"

        if not f_api.exists():
            vacio = pd.DataFrame()
            vacio.to_csv(out_dir / archivo_nombre, index=False)
            log_transformacion(archivo_nombre, "Sin archivos fuente", 0, 0, 0, vacio)
            return vacio

        df = pd.read_csv(f_api, low_memory=False)
        filas_brutas = len(df)
        df["origen_datos"] = "api_rest"
        
        df["open_time_ms"] = pd.to_numeric(df["open_time_ms"], errors="coerce")
        df.dropna(subset=["open_time_ms"], inplace=True)
        df["open_time_ms"] = df["open_time_ms"].astype("int64")

        duplicados = df.duplicated(subset=["open_time_ms"]).sum()
        df.drop_duplicates(subset=["open_time_ms"], keep="last", inplace=True)
        df.sort_values("open_time_ms", inplace=True)

        df.insert(0, "symbol", symbol.upper())
        df.insert(1, "fecha_utc", pd.to_datetime(df["open_time_ms"], unit="ms"))
        df["fecha_procesamiento"] = fecha_procesamiento

        for c in ["open", "high", "low", "close", "volume", "quote_asset_volume", "taker_buy_base_asset_volume", "taker_buy_quote_asset_volume"]:
            if c in df.columns:
                df[c] = pd.to_numeric(df[c], errors="coerce")

        archivo_final = out_dir / archivo_nombre
        df.to_csv(archivo_final, index=False)
        log_transformacion(archivo_nombre, f"api_rest_klines_{tf}.csv", filas_brutas, duplicados, len(df), df)
        return df

    df_k15 = procesar_klines("15m")
    df_k12 = procesar_klines("12h")

    # 2. Funding Rates Master
    f_fund = raw_dir / "api_rest" / "api_rest_funding_rate.csv"
    archivo_fund_nombre = "api_rest_funding_rates_master.csv"
    df_fund = pd.DataFrame()
    if f_fund.exists():
        df_fund = pd.read_csv(f_fund, low_memory=False)
        filas_brutas = len(df_fund)
        df_fund["fundingTime"] = pd.to_numeric(df_fund["fundingTime"], errors="coerce")
        df_fund.dropna(subset=["fundingTime"], inplace=True)
        df_fund["fundingTime"] = df_fund["fundingTime"].astype("int64")

        dups = df_fund.duplicated(subset=["fundingTime"]).sum()
        df_fund.drop_duplicates(subset=["fundingTime"], keep="last", inplace=True)
        df_fund.sort_values("fundingTime", inplace=True)

        df_fund.insert(1, "fecha_utc", pd.to_datetime(df_fund["fundingTime"], unit="ms"))
        df_fund["fundingRate"] = pd.to_numeric(df_fund["fundingRate"], errors="coerce")
        df_fund["origen_datos"] = "api_funding"
        df_fund["fecha_procesamiento"] = fecha_procesamiento

        df_fund.to_csv(out_dir / archivo_fund_nombre, index=False)
        log_transformacion(archivo_fund_nombre, f_fund.name, filas_brutas, dups, len(df_fund), df_fund)
    else:
        df_fund.to_csv(out_dir / archivo_fund_nombre, index=False)
        log_transformacion(archivo_fund_nombre, "No encontrado", 0, 0, 0, df_fund)

    # 3. Liquidaciones Master
    f_liq = raw_dir / "api_rest" / "api_rest_liquidaciones.csv"
    archivo_liq_nombre = "api_rest_liquidaciones_master.csv"
    df_liq = pd.DataFrame()
    if f_liq.exists():
        df_liq = pd.read_csv(f_liq, low_memory=False)
        filas_brutas = len(df_liq)
        df_liq["time"] = pd.to_numeric(df_liq["time"], errors="coerce")
        df_liq.dropna(subset=["time"], inplace=True)
        df_liq["time"] = df_liq["time"].astype("int64")

        dups = df_liq.duplicated(subset=["time", "side", "price", "origQty"]).sum() if "side" in df_liq.columns else 0
        df_liq.drop_duplicates(subset=["time", "side", "price", "origQty"], keep="last", inplace=True)
        df_liq.sort_values("time", inplace=True)

        df_liq.insert(1, "fecha_utc", pd.to_datetime(df_liq["time"], unit="ms"))
        df_liq["origQty"] = pd.to_numeric(df_liq["origQty"], errors="coerce")
        df_liq["price"] = pd.to_numeric(df_liq["price"], errors="coerce")
        df_liq["volumen_usd"] = df_liq["origQty"] * df_liq["price"]
        df_liq["origen_datos"] = "api_liquidaciones"
        df_liq["fecha_procesamiento"] = fecha_procesamiento

        df_liq.to_csv(out_dir / archivo_liq_nombre, index=False)
        log_transformacion(archivo_liq_nombre, f_liq.name, filas_brutas, dups, len(df_liq), df_liq)
    else:
        df_liq.to_csv(out_dir / archivo_liq_nombre, index=False)
        log_transformacion(archivo_liq_nombre, "No encontrado", 0, 0, 0, df_liq)

    # 4 & 5. Sentimiento Master
    def procesar_sentimiento(tf):
        metricas = ["open_interest", "global_ls", "top_ls_accounts", "top_ls_positions", "taker_vol"]
        df_sent = pd.DataFrame()
        filas_brutas_total = 0
        fuentes = []
        archivo_sent_nombre = f"api_rest_sentimiento_{tf}_master.csv"

        for m in metricas:
            f_m = raw_dir / "api_rest" / f"api_rest_{m}_{tf}.csv"
            if f_m.exists():
                df_temp = pd.read_csv(f_m, low_memory=False)
                filas_brutas_total += len(df_temp)
                fuentes.append(f_m.name)
                df_temp["timestamp"] = pd.to_numeric(df_temp["timestamp"], errors="coerce")
                df_temp.dropna(subset=["timestamp"], inplace=True)
                df_temp["timestamp"] = df_temp["timestamp"].astype("int64")
                df_temp.drop_duplicates(subset=["timestamp"], keep="last", inplace=True)

                if "symbol" in df_temp.columns:
                    df_temp.drop(columns=["symbol"], inplace=True)

                if df_sent.empty:
                    df_sent = df_temp
                else:
                    df_sent = pd.merge(df_sent, df_temp, on=["timestamp"], how="outer")

        if not df_sent.empty:
            df_sent.sort_values("timestamp", inplace=True)
            df_sent.insert(0, "symbol", symbol.upper())
            df_sent.insert(1, "fecha_utc", pd.to_datetime(df_sent["timestamp"], unit="ms"))
            df_sent["origen_datos"] = "api_sentimiento"
            df_sent["fecha_procesamiento"] = fecha_procesamiento

            df_sent.to_csv(out_dir / archivo_sent_nombre, index=False)
            log_transformacion(archivo_sent_nombre, ", ".join(fuentes), filas_brutas_total, 0, len(df_sent), df_sent)
        else:
            df_sent.to_csv(out_dir / archivo_sent_nombre, index=False)
            log_transformacion(archivo_sent_nombre, "Sin archivos fuente", 0, 0, 0, df_sent)

        return df_sent

    df_s15 = procesar_sentimiento("15m")
    df_s12 = procesar_sentimiento("12h")

    # 6 & 7. Datasets Analíticos Finales
    def crear_dataset_analisis(df_k, df_s, tf):
        archivo_nombre = f"dataset_analisis_{tf}.csv"
        if df_k.empty:
            vacio = pd.DataFrame()
            vacio.to_csv(out_dir / archivo_nombre, index=False)
            log_transformacion(archivo_nombre, "Sin Klines base", 0, 0, 0, vacio)
            return

        df_master = df_k.copy()

        df_master["retorno_pct"] = (df_master["close"] / df_master["open"] - 1) * 100
        df_master["rango_hl_pct"] = (df_master["high"] / df_master["low"] - 1) * 100

        if "quote_asset_volume" in df_master.columns and "taker_buy_quote_asset_volume" in df_master.columns:
            df_master["taker_sell_quote_asset_volume"] = df_master["quote_asset_volume"] - df_master["taker_buy_quote_asset_volume"]
            df_master["delta_vol_total_usd"] = df_master["quote_asset_volume"].diff()
            df_master["delta_vol_comprador_usd"] = df_master["taker_buy_quote_asset_volume"].diff()
            df_master["delta_vol_vendedor_usd"] = df_master["taker_sell_quote_asset_volume"].diff()

        if not df_s.empty:
            df_s_clean = df_s.drop(columns=["fecha_utc", "symbol", "origen_datos", "fecha_procesamiento"], errors="ignore")
            df_master = pd.merge(df_master, df_s_clean, left_on="open_time_ms", right_on="timestamp", how="left")
            df_master.drop(columns=["timestamp"], inplace=True, errors="ignore")

        if not df_fund.empty:
            df_f = df_fund[["fundingTime", "fundingRate"]].dropna().sort_values("fundingTime")
            df_master = pd.merge_asof(
                df_master.sort_values("open_time_ms"),
                df_f,
                left_on="open_time_ms",
                right_on="fundingTime",
                direction="backward"
            )
            df_master.drop(columns=["fundingTime"], inplace=True, errors="ignore")

        if not df_liq.empty:
            interval_ms = 900000 if tf == "15m" else 43200000
            df_liq_copy = df_liq.copy()
            df_liq_copy["open_time_ms"] = (df_liq_copy["time"] // interval_ms) * interval_ms

            liq_agg = df_liq_copy.groupby(["open_time_ms", "side"])["volumen_usd"].sum().unstack(fill_value=0).reset_index()
            liq_agg.rename(columns={"BUY": "liq_shorts_usd", "SELL": "liq_longs_usd"}, inplace=True)

            for col in ["liq_shorts_usd", "liq_longs_usd"]:
                if col not in liq_agg.columns:
                    liq_agg[col] = 0.0

            df_master = pd.merge(df_master, liq_agg[["open_time_ms", "liq_shorts_usd", "liq_longs_usd"]], on="open_time_ms", how="left")
            df_master["liq_shorts_usd"] = df_master["liq_shorts_usd"].fillna(0.0)
            df_master["liq_longs_usd"] = df_master["liq_longs_usd"].fillna(0.0)

        df_master["fecha_procesamiento"] = fecha_procesamiento
        archivo_final = out_dir / archivo_nombre
        df_master.to_csv(archivo_final, index=False)
        log_transformacion(archivo_nombre, f"Fusión total {tf}", len(df_k), 0, len(df_master), df_master)

    crear_dataset_analisis(df_k15, df_s15, "15m")
    crear_dataset_analisis(df_k12, df_s12, "12h")

    # Resumen general en log
    logger.info("=========================================================================================")
    logger.info("RESUMEN GENERAL AUDITADO (8 ARCHIVOS SALIDA)")
    logger.info("=========================================================================================")
    resumen_df = pd.DataFrame(resumen_salidas)
    logger.info("\n" + resumen_df.to_string(index=False))
    logger.info("=========================================================================================")