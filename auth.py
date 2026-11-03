import fcntl
import logging
import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from binance.client import Client
from dotenv import load_dotenv

import consolidator
import fetcher
import storage

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
    # Evita dos ejecuciones simultáneas del pipeline sobre los mismos archivos
    lock_file = open(LOG_DIR / "pipeline.lock", "w", encoding="utf-8")
    try:
        fcntl.flock(lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        logger.error("Ya hay otra ejecución del pipeline en curso. Se aborta esta corrida.")
        lock_file.close()
        return

    logger.info("=== INICIANDO ORQUESTADOR DE INGESTA TOTAL ===")
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

        # 3. API REST: SENTIMIENTO (Ventana fija 28 días)
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

        # 4. CONSOLIDACIÓN
        logger.info(f"[{symbol}] FASE 4: Consolidando y generando los 7 archivos maestros...")
        consolidator.consolidar_symbol(symbol, DATA_DIR, LOG_DIR)

    logger.info("=== FLUJO DE EJECUCIÓN COMPLETADO ===")
    lock_file.close()


if __name__ == "__main__":
    main()
