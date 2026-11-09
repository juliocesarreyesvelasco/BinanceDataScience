import logging
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

import storage

ZONA_HORARIA = ZoneInfo("America/Mexico_City")

COLUMNAS_KLINES = [
    "open_time_ms", "open", "high", "low", "close", "volume",
    "close_time_ms", "quote_asset_volume", "number_of_trades",
    "taker_buy_base_asset_volume", "taker_buy_quote_asset_volume",
]
COLUMNAS_KLINES_ESTADO = COLUMNAS_KLINES + ["fecha_procesamiento"]

INTERVALO_MS = {"5m": 300_000, "15m": 900_000, "12h": 43_200_000}

RENOMBRES_SENTIMIENTO = {
    "open_interest": {
        "sumOpenInterest": "oi_sum_open_interest",
        "sumOpenInterestValue": "oi_value_usd",
        "CMCCirculatingSupply": "oi_cmc_circulating_supply",
    },
    "global_ls": {
        "longAccount": "global_ls_long_account",
        "shortAccount": "global_ls_short_account",
        "longShortRatio": "global_ls_ratio",
    },
    "top_ls_accounts": {
        "longAccount": "top_accounts_long_account",
        "shortAccount": "top_accounts_short_account",
        "longShortRatio": "top_accounts_ratio",
    },
    "top_ls_positions": {
        "longAccount": "top_positions_long_account",
        "shortAccount": "top_positions_short_account",
        "longShortRatio": "top_positions_ratio",
    },
    "taker_vol": {
        "buySellRatio": "taker_buy_sell_ratio",
        "sellVol": "taker_sell_vol",
        "buyVol": "taker_buy_vol",
    },
}

COLUMNAS_SENTIMIENTO_DATASET = [
    "oi_sum_open_interest", "oi_value_usd", "oi_cmc_circulating_supply",
    "global_ls_long_account", "global_ls_ratio", "global_ls_short_account",
    "top_accounts_long_account", "top_accounts_ratio", "top_accounts_short_account",
    "top_positions_long_account", "top_positions_ratio", "top_positions_short_account",
    "taker_buy_sell_ratio", "taker_sell_vol", "taker_buy_vol",
]

COLUMNAS_SENTIMIENTO_MASTER = [
    "symbol", "fecha_utc", "fecha_local",
    "oi_sum_open_interest", "oi_value_usd", "oi_cmc_circulating_supply",
    "timestamp",
    "global_ls_long_account", "global_ls_ratio", "global_ls_short_account",
    "top_accounts_long_account", "top_accounts_ratio", "top_accounts_short_account",
    "top_positions_long_account", "top_positions_ratio", "top_positions_short_account",
    "taker_buy_sell_ratio", "taker_sell_vol", "taker_buy_vol",
    "origen_datos", "fecha_procesamiento",
]

COLUMNAS_FUNDING_MASTER = [
    "symbol", "fecha_utc", "fecha_local", "fundingTime", "fundingRate",
    "markPrice", "rateType", "origen_datos", "fecha_procesamiento",
]

COLUMNAS_DATASET = [
    "symbol", "fecha_utc", "fecha_local",
    "open_time_ms", "open", "high", "low", "close", "volume",
    "close_time_ms", "quote_asset_volume", "number_of_trades",
    "taker_buy_base_asset_volume", "taker_buy_quote_asset_volume",
    "origen_datos", "fecha_procesamiento",
    "retorno_pct", "rango_hl_pct", "taker_sell_quote_asset_volume",
    "delta_vol_total_usd", "delta_vol_comprador_usd", "delta_vol_vendedor_usd",
    *COLUMNAS_SENTIMIENTO_DATASET,
    "fundingRate",
]


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


def _fecha_local_desde_ms(serie_ms: pd.Series) -> pd.Series:
    return pd.to_datetime(serie_ms, unit="ms", utc=True).dt.tz_convert(ZONA_HORARIA)


def _leer_csv(archivo: Path) -> pd.DataFrame:
    try:
        return pd.read_csv(archivo, low_memory=False)
    except pd.errors.EmptyDataError:
        return pd.DataFrame()


def _coerce_klines(df: pd.DataFrame) -> pd.DataFrame:
    df["open_time_ms"] = pd.to_numeric(df["open_time_ms"], errors="coerce")
    df = df.dropna(subset=["open_time_ms"])
    df["open_time_ms"] = df["open_time_ms"].astype("int64")
    for columna in [
        "open", "high", "low", "close", "volume", "quote_asset_volume",
        "taker_buy_base_asset_volume", "taker_buy_quote_asset_volume",
    ]:
        if columna in df.columns:
            df[columna] = pd.to_numeric(df[columna], errors="coerce")
    for columna in ["close_time_ms", "number_of_trades"]:
        if columna in df.columns:
            df[columna] = pd.to_numeric(df[columna], errors="coerce")
            if df[columna].notna().all():
                df[columna] = df[columna].astype("int64")
    return df


def normalizar_klines(datos: list) -> pd.DataFrame:
    if not datos:
        return pd.DataFrame(columns=COLUMNAS_KLINES)
    df = pd.DataFrame(datos)
    if "open_time_ms" not in df.columns:
        return pd.DataFrame(columns=COLUMNAS_KLINES)
    df = _coerce_klines(df)
    df = df.drop_duplicates(subset=["open_time_ms"], keep="last")
    df = df.sort_values("open_time_ms").reset_index(drop=True)
    return df.reindex(columns=COLUMNAS_KLINES)


def cargar_estado_klines(archivo: Path) -> pd.DataFrame:
    if not archivo.exists():
        return pd.DataFrame(columns=COLUMNAS_KLINES_ESTADO)
    try:
        columnas = pd.read_csv(archivo, nrows=0).columns
    except pd.errors.EmptyDataError:
        return pd.DataFrame(columns=COLUMNAS_KLINES_ESTADO)
    usecols = [c for c in COLUMNAS_KLINES_ESTADO if c in columnas]
    df = pd.read_csv(archivo, usecols=usecols, low_memory=False)
    if "open_time_ms" not in df.columns:
        return pd.DataFrame(columns=COLUMNAS_KLINES_ESTADO)
    df = _coerce_klines(df)
    df = df.drop_duplicates(subset=["open_time_ms"], keep="last")
    df = df.sort_values("open_time_ms").reset_index(drop=True)
    df = df.reindex(columns=COLUMNAS_KLINES_ESTADO)
    return df


def detectar_huecos(df: pd.DataFrame, tf: str) -> list[tuple[int, int]]:
    intervalo = INTERVALO_MS.get(tf)
    if intervalo is None or df is None or len(df) < 2:
        return []
    tiempos = df["open_time_ms"].astype("int64").sort_values().reset_index(drop=True)
    diferencias = tiempos.diff()
    huecos = []
    for indice in diferencias[diferencias > intervalo].index:
        anterior = int(tiempos.iloc[indice - 1])
        actual = int(tiempos.iloc[indice])
        inicio = anterior + intervalo
        if inicio < actual:
            huecos.append((inicio, actual))
    return huecos


def detectar_huecos_timestamps(df: pd.DataFrame, tf: str, desde_ms=None, hasta_ms=None) -> list[tuple[int, int]]:
    intervalo = INTERVALO_MS.get(tf)
    if intervalo is None or df is None or len(df) == 0 or "timestamp" not in df.columns:
        return []
    tiempos = df["timestamp"].astype("int64").sort_values().reset_index(drop=True)
    huecos = []

    if len(tiempos) >= 2:
        diferencias = tiempos.diff()
        for indice in diferencias[diferencias > intervalo].index:
            anterior = int(tiempos.iloc[indice - 1])
            actual = int(tiempos.iloc[indice])
            inicio = anterior + intervalo
            if inicio >= actual:
                continue
            inicio_recortado = max(inicio, int(desde_ms)) if desde_ms is not None else inicio
            fin_recortado = min(actual, int(hasta_ms)) if hasta_ms is not None else actual
            if inicio_recortado < fin_recortado:
                huecos.append((inicio_recortado, fin_recortado))

    if desde_ms is not None:
        primero = int(tiempos.iloc[0])
        if primero > int(desde_ms) + intervalo:
            fin = min(primero, int(hasta_ms)) if hasta_ms is not None else primero
            if int(desde_ms) < fin:
                huecos.append((int(desde_ms), fin))
    return huecos


def combinar_klines(df_old: pd.DataFrame, df_nuevos: pd.DataFrame) -> pd.DataFrame:
    partes = [d for d in (df_old, df_nuevos) if d is not None and not d.empty]
    if not partes:
        return pd.DataFrame(columns=COLUMNAS_KLINES_ESTADO)
    df = pd.concat(partes, ignore_index=True, sort=False)
    df = _coerce_klines(df)
    df = df.drop_duplicates(subset=["open_time_ms"], keep="last")
    df = df.sort_values("open_time_ms").reset_index(drop=True)
    return df.reindex(columns=COLUMNAS_KLINES_ESTADO)


def _normalizar_funding(symbol: str, datos: list, fecha_procesamiento: str) -> pd.DataFrame:
    if not datos:
        return pd.DataFrame(columns=COLUMNAS_FUNDING_MASTER)
    df = pd.DataFrame(datos)
    if "fundingTime" not in df.columns:
        return pd.DataFrame(columns=COLUMNAS_FUNDING_MASTER)
    df["fundingTime"] = pd.to_numeric(df["fundingTime"], errors="coerce")
    df = df.dropna(subset=["fundingTime"])
    df["fundingTime"] = df["fundingTime"].astype("int64")
    df = df.drop_duplicates(subset=["fundingTime"], keep="last")
    df = df.sort_values("fundingTime").reset_index(drop=True)
    df["symbol"] = symbol.upper()
    df["fecha_utc"] = pd.to_datetime(df["fundingTime"], unit="ms")
    df["fecha_local"] = _fecha_local_desde_ms(df["fundingTime"])
    for columna in ["fundingRate", "markPrice"]:
        if columna in df.columns:
            df[columna] = pd.to_numeric(df[columna], errors="coerce")
    if "rateType" not in df.columns:
        df["rateType"] = None
    df["origen_datos"] = "api_funding"
    df["fecha_procesamiento"] = fecha_procesamiento
    return df.reindex(columns=COLUMNAS_FUNDING_MASTER)


def cargar_funding_master(out_dir: Path) -> pd.DataFrame:
    archivo = out_dir / "funding_rates_master.csv"
    if not archivo.exists():
        return pd.DataFrame(columns=COLUMNAS_FUNDING_MASTER)
    df = _leer_csv(archivo)
    if "fundingTime" not in df.columns:
        return pd.DataFrame(columns=COLUMNAS_FUNDING_MASTER)
    df["fundingTime"] = pd.to_numeric(df["fundingTime"], errors="coerce")
    df = df.dropna(subset=["fundingTime"])
    df["fundingTime"] = df["fundingTime"].astype("int64")
    df = df.drop_duplicates(subset=["fundingTime"], keep="last")
    df = df.sort_values("fundingTime").reset_index(drop=True)
    return df.reindex(columns=COLUMNAS_FUNDING_MASTER)


def actualizar_master_funding(symbol: str, nuevos: list, out_dir: Path, logger, fecha_procesamiento: str) -> pd.DataFrame:
    archivo = out_dir / "funding_rates_master.csv"
    df_old = cargar_funding_master(out_dir)
    df_new = _normalizar_funding(symbol, nuevos, fecha_procesamiento)
    if df_new.empty:
        return df_old
    if df_old.empty:
        df_final = df_new
    else:
        df_old_idx = df_old.drop_duplicates(subset=["fundingTime"], keep="last").set_index("fundingTime")
        df_new_idx = df_new.set_index("fundingTime")
        df_final = df_new_idx.combine_first(df_old_idx).reset_index()
        df_final = df_final.sort_values("fundingTime").reset_index(drop=True)
        df_final = df_final.reindex(columns=COLUMNAS_FUNDING_MASTER)
    storage.escribir_csv(df_final, archivo)
    logger.info(f"[funding] {symbol}: +{len(df_new)} nuevos. Total: {len(df_final)} filas.")
    return df_final


def cargar_master_sentimiento(out_dir: Path, tf: str) -> pd.DataFrame:
    archivo = out_dir / f"sentimiento_{tf}_master.csv"
    if not archivo.exists():
        return pd.DataFrame(columns=COLUMNAS_SENTIMIENTO_MASTER)
    df = _leer_csv(archivo)
    if df.empty or "timestamp" not in df.columns:
        return pd.DataFrame(columns=COLUMNAS_SENTIMIENTO_MASTER)
    df["timestamp"] = pd.to_numeric(df["timestamp"], errors="coerce")
    df = df.dropna(subset=["timestamp"])
    df["timestamp"] = df["timestamp"].astype("int64")
    df = df.drop_duplicates(subset=["timestamp"], keep="last")
    df = df.sort_values("timestamp").reset_index(drop=True)
    for columna in COLUMNAS_SENTIMIENTO_DATASET:
        if columna in df.columns:
            df[columna] = pd.to_numeric(df[columna], errors="coerce")
    return df.reindex(columns=COLUMNAS_SENTIMIENTO_MASTER)


def _normalizar_metricas_sentimiento(metricas: dict) -> pd.DataFrame:
    df_sent = pd.DataFrame()
    for metrica, renombres in RENOMBRES_SENTIMIENTO.items():
        datos = metricas.get(metrica) or []
        if not datos:
            continue
        df_temp = pd.DataFrame(datos)
        if "timestamp" not in df_temp.columns:
            continue
        df_temp["timestamp"] = pd.to_numeric(df_temp["timestamp"], errors="coerce")
        df_temp = df_temp.dropna(subset=["timestamp"])
        df_temp["timestamp"] = df_temp["timestamp"].astype("int64")
        df_temp = df_temp.drop_duplicates(subset=["timestamp"], keep="last")
        df_temp = df_temp.rename(columns={v: n for v, n in renombres.items() if v in df_temp.columns})
        columnas = ["timestamp"] + [n for n in renombres.values() if n in df_temp.columns]
        df_temp = df_temp.reindex(columns=columnas)
        for columna in columnas[1:]:
            df_temp[columna] = pd.to_numeric(df_temp[columna], errors="coerce")
        if df_sent.empty:
            df_sent = df_temp
        else:
            df_sent = pd.merge(df_sent, df_temp, on=["timestamp"], how="outer")
    if df_sent.empty:
        return df_sent
    df_sent = df_sent.drop_duplicates(subset=["timestamp"], keep="last")
    return df_sent.sort_values("timestamp").reset_index(drop=True)


def _preparar_master_sentimiento(df: pd.DataFrame, symbol: str, fecha_procesamiento: str) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame(columns=COLUMNAS_SENTIMIENTO_MASTER)
    df["timestamp"] = pd.to_numeric(df["timestamp"], errors="coerce")
    df = df.dropna(subset=["timestamp"])
    df["timestamp"] = df["timestamp"].astype("int64")
    df = df.drop_duplicates(subset=["timestamp"], keep="last")
    df = df.sort_values("timestamp").reset_index(drop=True)
    df["symbol"] = symbol.upper()
    df["fecha_utc"] = pd.to_datetime(df["timestamp"], unit="ms")
    df["fecha_local"] = _fecha_local_desde_ms(df["timestamp"])
    for columna in COLUMNAS_SENTIMIENTO_DATASET:
        if columna in df.columns:
            df[columna] = pd.to_numeric(df[columna], errors="coerce")
    if "origen_datos" not in df.columns:
        df["origen_datos"] = "api_sentimiento"
    if "fecha_procesamiento" not in df.columns:
        df["fecha_procesamiento"] = fecha_procesamiento
    return df.reindex(columns=COLUMNAS_SENTIMIENTO_MASTER)


def _contar_nuevos_sentimiento(df_old: pd.DataFrame, df_new: pd.DataFrame) -> int:
    if df_new is None or df_new.empty:
        return 0
    ts_new = set(df_new["timestamp"].tolist())
    if df_old is None or df_old.empty:
        return len(ts_new)
    ts_old = set(df_old["timestamp"].tolist())
    return len(ts_new - ts_old)


def _contar_actualizados_sentimiento(df_old: pd.DataFrame, df_final: pd.DataFrame) -> int:
    if df_old is None or df_old.empty or df_final is None or df_final.empty:
        return 0
    columnas = [c for c in COLUMNAS_SENTIMIENTO_DATASET if c in df_old.columns and c in df_final.columns]
    if not columnas:
        return 0
    viejo = df_old.drop_duplicates(subset=["timestamp"], keep="last").set_index("timestamp")
    final = df_final.drop_duplicates(subset=["timestamp"], keep="last").set_index("timestamp")
    comunes = final.index.intersection(viejo.index)
    if len(comunes) == 0:
        return 0
    matriz_vieja = viejo.loc[comunes, columnas].to_numpy(dtype=float)
    matriz_final = final.loc[comunes, columnas].to_numpy(dtype=float)
    with np.errstate(invalid="ignore"):
        distintos = ~np.isclose(matriz_vieja, matriz_final, rtol=0.0, atol=0.0, equal_nan=True)
    return int(distintos.any(axis=1).sum())


def actualizar_master_sentimiento(symbol: str, tf: str, metricas: dict, out_dir: Path, logger, fecha_procesamiento: str, df_old: pd.DataFrame = None):
    archivo = out_dir / f"sentimiento_{tf}_master.csv"
    if df_old is None:
        df_old = cargar_master_sentimiento(out_dir, tf)
    df_new = _normalizar_metricas_sentimiento(metricas)
    if df_new.empty:
        if df_old.empty:
            df_final = pd.DataFrame(columns=COLUMNAS_SENTIMIENTO_MASTER)
            stats = {"nuevos_reales": 0, "actualizados": 0, "total": 0, "written": False}
            return df_final, stats
        df_final = _preparar_master_sentimiento(df_old, symbol, fecha_procesamiento)
        stats = {"nuevos_reales": 0, "actualizados": 0, "total": len(df_final), "written": False}
        return df_final, stats

    nuevos_reales = _contar_nuevos_sentimiento(df_old, df_new)

    df_new["symbol"] = symbol.upper()
    df_new["fecha_utc"] = pd.to_datetime(df_new["timestamp"], unit="ms")
    df_new["fecha_local"] = _fecha_local_desde_ms(df_new["timestamp"])
    df_new["origen_datos"] = "api_sentimiento"
    df_new["fecha_procesamiento"] = fecha_procesamiento
    df_new = df_new.reindex(columns=COLUMNAS_SENTIMIENTO_MASTER)

    if df_old.empty:
        df_final = df_new
    else:
        df_old = _preparar_master_sentimiento(df_old, symbol, fecha_procesamiento)
        df_old_idx = df_old.drop_duplicates(subset=["timestamp"], keep="last").set_index("timestamp")
        df_new_idx = df_new.set_index("timestamp")
        df_final = df_new_idx.combine_first(df_old_idx).reset_index()
        df_final = df_final.sort_values("timestamp").reset_index(drop=True)
        df_final = df_final.reindex(columns=COLUMNAS_SENTIMIENTO_MASTER)

    actualizados = _contar_actualizados_sentimiento(df_old, df_final)
    stats = {"nuevos_reales": nuevos_reales, "actualizados": actualizados, "total": len(df_final), "written": False}
    if nuevos_reales > 0 or actualizados > 0:
        storage.escribir_csv(df_final, archivo)
        stats["written"] = True
        logger.info(f"[sentimiento] {symbol} {tf}: +{nuevos_reales} nuevos, {actualizados} actualizados. Total: {len(df_final)} filas.")
    else:
        logger.info(f"[sentimiento] {symbol} {tf}: sin cambios. Total: {len(df_final)} filas.")
    return df_final, stats


def construir_dataset(symbol: str, df_klines: pd.DataFrame, df_sent: pd.DataFrame, df_fund: pd.DataFrame, fecha_procesamiento: str) -> pd.DataFrame:
    if df_klines is None or df_klines.empty:
        return pd.DataFrame(columns=COLUMNAS_DATASET)

    df = df_klines.copy()
    df = df.sort_values("open_time_ms").reset_index(drop=True)
    df["symbol"] = symbol.upper()
    df["fecha_utc"] = pd.to_datetime(df["open_time_ms"], unit="ms")
    df["fecha_local"] = _fecha_local_desde_ms(df["open_time_ms"])
    df["origen_datos"] = "api_rest"
    if "fecha_procesamiento" not in df.columns:
        df["fecha_procesamiento"] = None
    df["fecha_procesamiento"] = df["fecha_procesamiento"].fillna(fecha_procesamiento)

    df["retorno_pct"] = (df["close"] / df["open"] - 1) * 100
    df["rango_hl_pct"] = (df["high"] / df["low"] - 1) * 100
    if "quote_asset_volume" in df.columns and "taker_buy_quote_asset_volume" in df.columns:
        df["taker_sell_quote_asset_volume"] = df["quote_asset_volume"] - df["taker_buy_quote_asset_volume"]
        df["delta_vol_total_usd"] = df["quote_asset_volume"].diff()
        df["delta_vol_comprador_usd"] = df["taker_buy_quote_asset_volume"].diff()
        df["delta_vol_vendedor_usd"] = df["taker_sell_quote_asset_volume"].diff()

    if df_sent is not None and not df_sent.empty and "timestamp" in df_sent.columns:
        columnas = ["timestamp"] + [c for c in COLUMNAS_SENTIMIENTO_DATASET if c in df_sent.columns]
        df = pd.merge(df, df_sent[columnas], left_on="open_time_ms", right_on="timestamp", how="left")
        df = df.drop(columns=["timestamp"], errors="ignore")

    if df_fund is not None and not df_fund.empty and "fundingTime" in df_fund.columns:
        df_f = df_fund[["fundingTime", "fundingRate"]].dropna().sort_values("fundingTime")
        df = pd.merge_asof(
            df.sort_values("open_time_ms"),
            df_f,
            left_on="open_time_ms",
            right_on="fundingTime",
            direction="backward",
        )
        df = df.drop(columns=["fundingTime"], errors="ignore")

    return df.reindex(columns=COLUMNAS_DATASET)


def guardar_dataset(df: pd.DataFrame, out_dir: Path, tf: str) -> Path:
    archivo = out_dir / f"dataset_analisis_{tf}.csv"
    storage.escribir_csv(df, archivo)
    return archivo


def auditar_dataset(logger, symbol: str, tf: str, filas_previas: int, filas_nuevas: int, df_dataset: pd.DataFrame):
    filas = len(df_dataset)
    duplicados = max(0, filas_previas + filas_nuevas - filas)
    rango = "N/A"
    if filas and "fecha_local" in df_dataset.columns:
        rango = f"{df_dataset['fecha_local'].min()} -> {df_dataset['fecha_local'].max()}"
    cobertura_sent = int(df_dataset["oi_sum_open_interest"].notna().sum()) if "oi_sum_open_interest" in df_dataset.columns else 0
    cobertura_fund = int(df_dataset["fundingRate"].notna().sum()) if "fundingRate" in df_dataset.columns else 0
    logger.info(f"[DATASET] {symbol} {tf}")
    logger.info(f"  • Filas previas: {filas_previas} | Nuevas: {filas_nuevas} | Duplicadas/traslapadas: {duplicados} | Finales: {filas}")
    logger.info(f"  • Columnas: {len(df_dataset.columns)} | Rango: {rango}")
    logger.info(f"  • Cobertura sentimiento: {cobertura_sent} filas | Cobertura funding: {cobertura_fund} filas")
