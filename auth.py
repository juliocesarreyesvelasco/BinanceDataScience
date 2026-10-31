import os
import time
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path
from binance.client import Client

import fetcher
import storage
import consolidator

import os
from dotenv import load_dotenv

# Carga las variables definidas en el archivo .env al entorno del sistema
load_dotenv()

# --- PARÁMETROS GLOBALES ---
API_KEY = os.getenv("BINANCE_API_KEY")
API_SECRET = os.getenv("BINANCE_API_SECRET")

if not API_KEY or not API_SECRET:
    raise ValueError("Error: Faltan las credenciales BINANCE_API_KEY o BINANCE_API_SECRET en el archivo .env")

PARES = ["BNBUSDT", "BTCUSDT", "ETHUSDT", "XRPUSDT", "SOLUSDT"]
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
    logger.info("=== INICIANDO ORQUESTADOR DE INGESTA TOTAL ===")
    client = Client(API_KEY, API_SECRET)

    ahora_utc = datetime.now(timezone.utc)
    fecha_fin_ms = int(ahora_utc.timestamp() * 1000)
    fecha_inicio_global = ahora_utc - timedelta(days=365 * ANOS_HISTORIA)
    fecha_inicio_global_ms = int(fecha_inicio_global.timestamp() * 1000)

    for symbol in PARES:
        symbol_dir = DATA_DIR / symbol.lower()
        symbol_dir.mkdir(parents=True, exist_ok=True)

        # 1. BINANCE VISION
        for tf in TIMEFRAMES:
            nombre_proc = f"binance_vision_klines_{tf}"
            ckpt = storage.leer_checkpoint(symbol_dir, nombre_proc)
            dir_vision = storage.obtener_ruta_raw(symbol_dir, "binance_vision")
            archivo_vision = dir_vision / f"binance_vision_klines_{tf}.csv"

            if not ckpt.get("backfill_completado") or not archivo_vision.exists():
                logger.info(f"[{symbol}] Ejecutando descarga de Binance Vision: {tf}...")
                fetcher.descargar_zips_vision(symbol, tf, fecha_inicio_global, ahora_utc, dir_vision, logger)
                storage.actualizar_checkpoint(symbol_dir, nombre_proc, backfill_completo=True, ultimo_ms=fecha_fin_ms, mas_antiguo_ms=fecha_inicio_global_ms)
            else:
                logger.info(f"[{symbol}] Binance Vision {tf} ya completado previamente.")

        # 2. API REST: KLINES
        for tf in TIMEFRAMES:
            nombre_proc = f"api_rest_klines_{tf}"
            ckpt = storage.leer_checkpoint(symbol_dir, nombre_proc)
            dias_paso = 30 if tf == "15m" else 180

            if not ckpt.get("backfill_completado"):
                logger.info(f"[{symbol}] Ejecutando Backfill API Klines {tf}...")
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

        # 3. API REST: FUNDING RATES
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

        # 4. API REST: LIQUIDACIONES
        nombre_proc_liq = "api_rest_liquidaciones"
        ckpt_liq = storage.leer_checkpoint(symbol_dir, nombre_proc_liq)
        if not ckpt_liq.get("backfill_completado"):
            logger.info(f"[{symbol}] Ejecutando Backfill de Liquidaciones...")
            cursor = ahora_utc
            while cursor > fecha_inicio_global:
                inicio_lote = cursor - timedelta(days=7)
                datos = fetcher.obtener_liquidaciones(client, symbol, int(inicio_lote.timestamp() * 1000), int(cursor.timestamp() * 1000), logger)
                if datos:
                    storage.guardar_coleccion_raw(symbol_dir, "api_rest", nombre_proc_liq, datos, "time", logger)
                cursor = inicio_lote
                time.sleep(PAUSA_SEGUNDOS)
            storage.actualizar_checkpoint(symbol_dir, nombre_proc_liq, backfill_completo=True, ultimo_ms=fecha_fin_ms, mas_antiguo_ms=fecha_inicio_global_ms)
        else:
            desde_ms = ckpt_liq.get("ultimo_timestamp_reciente_ms", fecha_fin_ms - (7 * 86400000))
            logger.info(f"[{symbol}] Actualización incremental de Liquidaciones...")
            datos = fetcher.obtener_liquidaciones(client, symbol, desde_ms, fecha_fin_ms, logger)
            if datos:
                storage.guardar_coleccion_raw(symbol_dir, "api_rest", nombre_proc_liq, datos, "time", logger)
            storage.actualizar_checkpoint(symbol_dir, nombre_proc_liq, backfill_completo=True, ultimo_ms=fecha_fin_ms)

        # 5. API REST: SENTIMIENTO (Ventana fija 28 días)
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

        # 6. CONSOLIDACIÓN
        logger.info(f"[{symbol}] FASE 6: Consolidando y generando los 8 archivos maestros...")
        consolidator.consolidar_symbol(symbol, DATA_DIR, LOG_DIR)

    logger.info("=== FLUJO DE EJECUCIÓN COMPLETADO ===")

if __name__ == "__main__":
    main()
