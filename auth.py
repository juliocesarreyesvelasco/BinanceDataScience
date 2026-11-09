import argparse
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

# Carga las variables definidas en el archivo .env al entorno del sistema
load_dotenv()

# --- PARÁMETROS GLOBALES ---
API_KEY = os.getenv("BINANCE_API_KEY")
API_SECRET = os.getenv("BINANCE_API_SECRET")

if not API_KEY or not API_SECRET:
    raise ValueError("Error: Faltan las credenciales BINANCE_API_KEY o BINANCE_API_SECRET en el archivo .env")

PARES = ["BNBUSDT", "BTCUSDT", "ETHUSDT", "XRPUSDT", "SOLUSDT"]
TIMEFRAMES = ["5m", "15m", "12h"]
DIAS_LOTE_KLINES = {"5m": 30, "15m": 30, "12h": 180}
RETENCION_DIAS_SENTIMIENTO = 28
PUNTOS_POR_LOTE_SENTIMIENTO = 480
SOLAPE_PERIODOS_SENTIMIENTO = 2
PAUSA_ENTRE_LOTES = 0.25
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


def _obtener_klines_rango(client, symbol: str, tf: str, start_ms: int, end_ms: int, logger) -> list:
    todos = []
    paso = DIAS_LOTE_KLINES.get(tf, 30) * 86400000
    cursor = int(start_ms)
    while cursor < end_ms:
        fin = min(cursor + paso, int(end_ms))
        todos.extend(fetcher.obtener_klines_api(client, symbol, tf, cursor, fin, logger))
        if fin <= cursor:
            break
        cursor = fin
        time.sleep(PAUSA_SEGUNDOS)
    return todos


def _obtener_funding_rango(client, symbol: str, start_ms: int, end_ms: int, logger) -> list:
    todos = []
    paso = 300 * 86400000
    cursor = int(start_ms)
    while cursor < end_ms:
        fin = min(cursor + paso, int(end_ms))
        todos.extend(fetcher.obtener_funding_rates(client, symbol, cursor, fin, logger))
        if fin <= cursor:
            break
        cursor = fin
        time.sleep(PAUSA_SEGUNDOS)
    return todos


def _fusionar_rangos(rangos: list) -> list:
    if not rangos:
        return []
    ordenados = sorted((int(inicio), int(fin)) for inicio, fin in rangos)
    fusionados = [list(ordenados[0])]
    for inicio, fin in ordenados[1:]:
        if inicio <= fusionados[-1][1]:
            fusionados[-1][1] = max(fusionados[-1][1], fin)
        else:
            fusionados.append([inicio, fin])
    return [(int(inicio), int(fin)) for inicio, fin in fusionados]


def _inicio_dia_ms(ahora_utc: datetime) -> int:
    fecha_local = ahora_utc.astimezone(consolidator.ZONA_HORARIA).date()
    inicio_local = datetime(fecha_local.year, fecha_local.month, fecha_local.day, tzinfo=consolidator.ZONA_HORARIA)
    return int(inicio_local.timestamp() * 1000)


def _requiere_reconciliacion(df_master, inicio_dia_ms: int) -> bool:
    if df_master is None or df_master.empty or "timestamp" not in df_master.columns:
        return True
    return int(df_master["timestamp"].max()) < inicio_dia_ms


def _planificar_rangos_sentimiento(symbol: str, tf: str, df_master, ahora_utc: datetime, inicio_dia_ms: int, logger):
    intervalo = consolidator.INTERVALO_MS[tf]
    ahora_ms = int(ahora_utc.timestamp() * 1000)
    piso = ahora_ms - RETENCION_DIAS_SENTIMIENTO * 86400000
    solape = SOLAPE_PERIODOS_SENTIMIENTO * intervalo

    if df_master is None or df_master.empty or "timestamp" not in df_master.columns:
        return [(piso, ahora_ms)], True

    ultimo = int(df_master["timestamp"].max())
    if ultimo < piso:
        logger.warning(
            f"[{symbol.upper()}] {tf}: maestro de sentimiento desactualizado "
            f"(último {ultimo} < piso {piso}); posible pérdida por retención de {RETENCION_DIAS_SENTIMIENTO} días."
        )

    if _requiere_reconciliacion(df_master, inicio_dia_ms):
        return [(piso, ahora_ms)], True

    rangos = [(max(ultimo - solape, piso), ahora_ms)]
    for inicio_hueco, fin_hueco in consolidator.detectar_huecos_timestamps(
        df_master, tf, desde_ms=piso, hasta_ms=ahora_ms
    ):
        if fin_hueco - inicio_hueco > 2 * intervalo:
            rangos.append((inicio_hueco, fin_hueco))

    return _fusionar_rangos(rangos), False


def _obtener_sentimiento(symbol: str, tf: str, rangos: list, logger):
    acumulado = {metrica: [] for metrica in consolidator.RENOMBRES_SENTIMIENTO}
    intervalo = consolidator.INTERVALO_MS[tf]
    lote_ms = PUNTOS_POR_LOTE_SENTIMIENTO * intervalo
    peticiones = 0
    for inicio_ms, fin_ms in rangos:
        cursor = int(inicio_ms)
        while cursor < int(fin_ms):
            fin = min(cursor + lote_ms, int(fin_ms))
            datos, intentos = fetcher.obtener_metricas_sentimiento(API_KEY, symbol, tf, cursor, fin, logger)
            peticiones += intentos
            for metrica, lista in datos.items():
                if metrica in acumulado:
                    acumulado[metrica].extend(lista)
            if fin <= cursor:
                break
            cursor = fin
            time.sleep(PAUSA_ENTRE_LOTES)
    return acumulado, peticiones


def main(symbols=None, data_dir=None):
    # Evita dos ejecuciones simultáneas del pipeline sobre los mismos archivos
    lock_file = open(LOG_DIR / "pipeline.lock", "w", encoding="utf-8")
    try:
        fcntl.flock(lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        logger.error("Ya hay otra ejecución del pipeline en curso. Se aborta esta corrida.")
        lock_file.close()
        return

    symbols = symbols or PARES
    base_data = Path(data_dir) if data_dir else DATA_DIR
    base_data.mkdir(parents=True, exist_ok=True)
    cons_logger = consolidator.setup_consolidator_logger(LOG_DIR)

    logger.info("=== INICIANDO ORQUESTADOR DE INGESTA DATASET-ONLY ===")
    client = Client(API_KEY, API_SECRET)

    ahora_utc = datetime.now(timezone.utc)
    fecha_fin_ms = int(ahora_utc.timestamp() * 1000)
    fecha_inicio_global_ms = int((ahora_utc - timedelta(days=365 * ANOS_HISTORIA)).timestamp() * 1000)
    inicio_dia_ms = _inicio_dia_ms(ahora_utc)

    for symbol in symbols:
        symbol_dir = base_data / symbol.lower()
        out_dir = symbol_dir / "consolidado"
        out_dir.mkdir(parents=True, exist_ok=True)

        bloqueos = sorted(out_dir.glob(".~lock.*#"))
        if bloqueos:
            nombres = ", ".join(p.name for p in bloqueos)
            logger.warning(f"[{symbol.upper()}] Se omite: archivos abiertos ({nombres}).")
            continue

        fecha_procesamiento = datetime.now(consolidator.ZONA_HORARIA).isoformat(timespec="seconds")
        cons_logger.info("=========================================================================================")
        cons_logger.info(f"CONSTRUYENDO DATASETS PARA: {symbol.upper()}")
        cons_logger.info("=========================================================================================")

        df_fund_old = consolidator.cargar_funding_master(out_dir)
        desde_fund = int(df_fund_old["fundingTime"].max()) if not df_fund_old.empty else fecha_inicio_global_ms
        nuevos_fund = _obtener_funding_rango(client, symbol, desde_fund, fecha_fin_ms, logger)
        df_fund = consolidator.actualizar_master_funding(symbol, nuevos_fund, out_dir, cons_logger, fecha_procesamiento)

        for tf in TIMEFRAMES:
            archivo_dataset = out_dir / f"dataset_analisis_{tf}.csv"
            df_old = consolidator.cargar_estado_klines(archivo_dataset)
            filas_previas = len(df_old)

            if df_old.empty:
                rangos = [(fecha_inicio_global_ms, fecha_fin_ms)]
            else:
                min_ms = int(df_old["open_time_ms"].min())
                max_ms = int(df_old["open_time_ms"].max())
                rangos = []
                if min_ms > fecha_inicio_global_ms + 86400000:
                    rangos.append((fecha_inicio_global_ms, min_ms))
                if fecha_fin_ms - max_ms > 60000:
                    rangos.append((max_ms, fecha_fin_ms))
                huecos = [
                    (inicio_hueco, fin_hueco)
                    for inicio_hueco, fin_hueco in consolidator.detectar_huecos(df_old, tf)
                    if inicio_hueco >= fecha_inicio_global_ms and fin_hueco <= fecha_fin_ms
                ]
                rangos.extend(huecos)
                if huecos:
                    logger.info(f"[{symbol.upper()}] {tf}: {len(huecos)} huecos internos detectados.")

            nuevos = []
            for inicio_ms, fin_ms in rangos:
                nuevos.extend(_obtener_klines_rango(client, symbol, tf, inicio_ms, fin_ms, logger))
            df_nuevos = consolidator.normalizar_klines(nuevos)
            filas_nuevas = len(df_nuevos)
            df_klines = consolidator.combinar_klines(df_old, df_nuevos)

            df_sent_old = consolidator.cargar_master_sentimiento(out_dir, tf)
            rangos_sent, recuperacion_sent = _planificar_rangos_sentimiento(
                symbol, tf, df_sent_old, ahora_utc, inicio_dia_ms, logger
            )
            metricas, peticiones_sent = _obtener_sentimiento(symbol, tf, rangos_sent, logger)
            df_sent, stats_sent = consolidator.actualizar_master_sentimiento(
                symbol, tf, metricas, out_dir, cons_logger, fecha_procesamiento, df_old=df_sent_old
            )
            cons_logger.info(
                f"[sentimiento] {symbol} {tf}: modo={'recuperacion' if recuperacion_sent else 'incremental'} "
                f"rangos={rangos_sent} peticiones={peticiones_sent} "
                f"nuevos={stats_sent['nuevos_reales']} actualizados={stats_sent['actualizados']} "
                f"escritura={'si' if stats_sent['written'] else 'no'}"
            )

            df_dataset = consolidator.construir_dataset(symbol, df_klines, df_sent, df_fund, fecha_procesamiento)
            if df_dataset.empty:
                logger.warning(f"[{symbol.upper()}] {tf}: sin datos para construir el dataset. Se omite escritura.")
                continue

            consolidator.guardar_dataset(df_dataset, out_dir, tf)
            consolidator.auditar_dataset(cons_logger, symbol, tf, filas_previas, filas_nuevas, df_dataset)

    logger.info("=== FLUJO DE EJECUCIÓN COMPLETADO ===")
    lock_file.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Orquestador de ingesta Binance dataset-only")
    parser.add_argument("--symbols", nargs="+", default=None, help="Símbolos a procesar (default: todos)")
    parser.add_argument("--data-dir", type=Path, default=None, help="Directorio de datos alternativo")
    args = parser.parse_args()
    main(args.symbols, args.data_dir)
