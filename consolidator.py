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

    # 1 & 2. Klines Maestras
    def procesar_klines(tf):
        f_vision = raw_dir / "binance_vision" / f"binance_vision_klines_{tf}.csv"
        f_api = raw_dir / "api_rest" / f"api_rest_klines_{tf}.csv"

        dfs = []
        filas_brutas = 0
        fuentes_usadas = []

        if f_vision.exists():
            df_v = pd.read_csv(f_vision, low_memory=False)
            df_v["origen_datos"] = "binance_vision"
            dfs.append(df_v)
            filas_brutas += len(df_v)
            fuentes_usadas.append(f"binance_vision_klines_{tf}.csv ({len(df_v)})")

        if f_api.exists():
            df_a = pd.read_csv(f_api, low_memory=False)
            df_a["origen_datos"] = "api_rest"
            dfs.append(df_a)
            filas_brutas += len(df_a)
            fuentes_usadas.append(f"api_rest_klines_{tf}.csv ({len(df_a)})")

        archivo_nombre = f"binance_vision_api_rest_klines_{tf}_master.csv"
        if not dfs:
            vacio = pd.DataFrame()
            vacio.to_csv(out_dir / archivo_nombre, index=False)
            log_transformacion(archivo_nombre, "Sin archivos fuente", 0, 0, 0, vacio)
            return vacio

        df = pd.concat(dfs, ignore_index=True)
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
        log_transformacion(archivo_nombre, " + ".join(fuentes_usadas), filas_brutas, duplicados, len(df), df)
        return df

    df_k15 = procesar_klines("15m")
    df_k12 = procesar_klines("12h")

    # 3. Funding Rates Master
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

    # 4. Liquidaciones Master
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

    # 5 & 6. Sentimiento Master
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

    # 7 & 8. Datasets Analíticos Finales
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
