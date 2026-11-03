import logging
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

import storage

ZONA_HORARIA = ZoneInfo("America/Mexico_City")

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


def consolidar_symbol(symbol: str, data_dir: Path, log_dir: Path):
    logger = setup_consolidator_logger(log_dir)
    symbol_dir = data_dir / symbol.lower()
    raw_dir = symbol_dir / "raw"
    out_dir = symbol_dir / "consolidado"
    out_dir.mkdir(parents=True, exist_ok=True)

    bloqueos = sorted(out_dir.glob(".~lock.*#"))
    if bloqueos:
        nombres = ", ".join(p.name for p in bloqueos)
        logger.warning(f"[{symbol.upper()}] Consolidación omitida: hay archivos abiertos ({nombres}).")
        return

    fecha_procesamiento = datetime.now(ZONA_HORARIA).isoformat(timespec="seconds")
    logger.info("=========================================================================================")
    logger.info(f"INICIANDO CONSOLIDACIÓN AUDITADA PARA: {symbol.upper()}")
    logger.info("=========================================================================================")

    resumen_salidas = []

    def log_transformacion(archivo_nombre, origen_desc, filas_origen, filas_duplicadas, filas_finales, df_resultado):
        rango_fechas = "N/A"
        columna_fecha = "fecha_local" if "fecha_local" in df_resultado.columns else "fecha_utc"
        if not df_resultado.empty and columna_fecha in df_resultado.columns:
            rango_fechas = f"{df_resultado[columna_fecha].min()} -> {df_resultado[columna_fecha].max()}"

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

    # 1 & 2. Klines Maestras (API REST)
    def procesar_klines(tf):
        f_api = raw_dir / "api_rest" / f"api_rest_klines_{tf}.csv"
        archivo_nombre = f"klines_{tf}_master.csv"

        if not f_api.exists():
            vacio = pd.DataFrame()
            storage.escribir_csv(vacio, out_dir / archivo_nombre)
            log_transformacion(archivo_nombre, "Sin archivo fuente", 0, 0, 0, vacio)
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
        df.insert(2, "fecha_local", _fecha_local_desde_ms(df["open_time_ms"]))
        df["fecha_procesamiento"] = fecha_procesamiento

        for c in ["open", "high", "low", "close", "volume", "quote_asset_volume", "taker_buy_base_asset_volume", "taker_buy_quote_asset_volume"]:
            if c in df.columns:
                df[c] = pd.to_numeric(df[c], errors="coerce")

        storage.escribir_csv(df, out_dir / archivo_nombre)
        log_transformacion(archivo_nombre, f_api.name, filas_brutas, duplicados, len(df), df)
        return df

    df_k15 = procesar_klines("15m")
    df_k12 = procesar_klines("12h")

    # 3. Funding Rates Master
    f_fund = raw_dir / "api_rest" / "api_rest_funding_rate.csv"
    archivo_fund_nombre = "funding_rates_master.csv"
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
        df_fund.insert(2, "fecha_local", _fecha_local_desde_ms(df_fund["fundingTime"]))
        df_fund["fundingRate"] = pd.to_numeric(df_fund["fundingRate"], errors="coerce")
        df_fund["origen_datos"] = "api_funding"
        df_fund["fecha_procesamiento"] = fecha_procesamiento

        storage.escribir_csv(df_fund, out_dir / archivo_fund_nombre)
        log_transformacion(archivo_fund_nombre, f_fund.name, filas_brutas, dups, len(df_fund), df_fund)
    else:
        storage.escribir_csv(df_fund, out_dir / archivo_fund_nombre)
        log_transformacion(archivo_fund_nombre, "No encontrado", 0, 0, 0, df_fund)

    # 4 & 5. Sentimiento Master
    def procesar_sentimiento(tf):
        metricas = ["open_interest", "global_ls", "top_ls_accounts", "top_ls_positions", "taker_vol"]
        df_sent = pd.DataFrame()
        filas_brutas_total = 0
        fuentes = []
        archivo_sent_nombre = f"sentimiento_{tf}_master.csv"

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

                renombres = {viejo: nuevo for viejo, nuevo in RENOMBRES_SENTIMIENTO[m].items() if viejo in df_temp.columns}
                df_temp.rename(columns=renombres, inplace=True)

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
            df_sent.insert(2, "fecha_local", _fecha_local_desde_ms(df_sent["timestamp"]))
            df_sent["origen_datos"] = "api_sentimiento"
            df_sent["fecha_procesamiento"] = fecha_procesamiento

            storage.escribir_csv(df_sent, out_dir / archivo_sent_nombre)
            log_transformacion(archivo_sent_nombre, ", ".join(fuentes), filas_brutas_total, 0, len(df_sent), df_sent)
        else:
            storage.escribir_csv(df_sent, out_dir / archivo_sent_nombre)
            log_transformacion(archivo_sent_nombre, "Sin archivos fuente", 0, 0, 0, df_sent)

        return df_sent

    df_s15 = procesar_sentimiento("15m")
    df_s12 = procesar_sentimiento("12h")

    # 6 & 7. Datasets Analíticos Finales
    def crear_dataset_analisis(df_k, df_s, tf):
        archivo_nombre = f"dataset_analisis_{tf}.csv"
        if df_k.empty:
            vacio = pd.DataFrame()
            storage.escribir_csv(vacio, out_dir / archivo_nombre)
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
            df_s_clean = df_s.drop(columns=["fecha_utc", "fecha_local", "symbol", "origen_datos", "fecha_procesamiento"], errors="ignore")
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

        df_master["fecha_procesamiento"] = fecha_procesamiento
        storage.escribir_csv(df_master, out_dir / archivo_nombre)
        log_transformacion(archivo_nombre, f"Fusión total {tf}", len(df_k), 0, len(df_master), df_master)

    crear_dataset_analisis(df_k15, df_s15, "15m")
    crear_dataset_analisis(df_k12, df_s12, "12h")

    # Resumen general en log
    logger.info("=========================================================================================")
    logger.info("RESUMEN GENERAL AUDITADO (7 ARCHIVOS SALIDA)")
    logger.info("=========================================================================================")
    resumen_df = pd.DataFrame(resumen_salidas)
    logger.info("\n" + resumen_df.to_string(index=False))
    logger.info("=========================================================================================")
