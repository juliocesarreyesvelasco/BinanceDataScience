import json
import os
from pathlib import Path

import pandas as pd


def _ruta_temporal(archivo: Path) -> Path:
    return archivo.with_name(f".{archivo.name}.tmp")


def escribir_json(datos, archivo: Path):
    temporal = _ruta_temporal(archivo)
    with open(temporal, "w", encoding="utf-8") as f:
        json.dump(datos, f, indent=4)
    os.replace(temporal, archivo)


def escribir_csv(df: pd.DataFrame, archivo: Path):
    temporal = _ruta_temporal(archivo)
    df.to_csv(temporal, index=False)
    os.replace(temporal, archivo)


def archivo_bloqueado(archivo: Path) -> bool:
    return (archivo.parent / f".~lock.{archivo.name}#").exists()


def obtener_ruta_raw(base_symbol_dir: Path, fuente: str) -> Path:
    ruta = base_symbol_dir / "raw" / fuente
    ruta.mkdir(parents=True, exist_ok=True)
    return ruta


def obtener_ruta_checkpoints(base_symbol_dir: Path) -> Path:
    ruta = base_symbol_dir / "checkpoints"
    ruta.mkdir(parents=True, exist_ok=True)
    return ruta


def leer_checkpoint(base_symbol_dir: Path, nombre_proceso: str) -> dict:
    archivo = obtener_ruta_checkpoints(base_symbol_dir) / f"checkpoint_{nombre_proceso}.json"
    if archivo.exists():
        try:
            with open(archivo, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def actualizar_checkpoint(base_symbol_dir: Path, nombre_proceso: str, backfill_completo: bool, ultimo_ms: int, mas_antiguo_ms: int = None):
    archivo = obtener_ruta_checkpoints(base_symbol_dir) / f"checkpoint_{nombre_proceso}.json"
    estado_previo = leer_checkpoint(base_symbol_dir, nombre_proceso)

    payload = {
        "backfill_completado": backfill_completo,
        "ultimo_timestamp_reciente_ms": max(ultimo_ms, estado_previo.get("ultimo_timestamp_reciente_ms", 0)),
        "timestamp_mas_antiguo_ms": mas_antiguo_ms if mas_antiguo_ms else estado_previo.get("timestamp_mas_antiguo_ms", ultimo_ms)
    }
    escribir_json(payload, archivo)


def guardar_coleccion_raw(base_symbol_dir: Path, fuente: str, nombre_archivo: str, nuevos_datos: list, campo_clave: str, logger):
    if not nuevos_datos:
        return 0

    target_dir = obtener_ruta_raw(base_symbol_dir, fuente)
    archivo_csv = target_dir / f"{nombre_archivo}.csv"
    archivo_json = target_dir / f"{nombre_archivo}.json"

    if archivo_bloqueado(archivo_json) or archivo_bloqueado(archivo_csv):
        logger.warning(f"[{fuente}] {nombre_archivo}: archivo bloqueado por otro programa. Se omite esta escritura.")
        return 0

    historico = []
    if archivo_json.exists():
        try:
            with open(archivo_json, "r", encoding="utf-8") as f:
                historico = json.load(f)
                if not isinstance(historico, list):
                    historico = []
        except Exception as e:
            logger.warning(f"Error leyendo {archivo_json.name}: {e}. Reiniciando respaldo.")
            historico = []

    vistos = {h.get(campo_clave) for h in historico if h.get(campo_clave) is not None}
    agregados = 0

    for dato in nuevos_datos:
        clave_val = dato.get(campo_clave)
        if clave_val is not None and clave_val not in vistos:
            historico.append(dato)
            vistos.add(clave_val)
            agregados += 1

    historico.sort(key=lambda x: x.get(campo_clave, 0))

    escribir_json(historico, archivo_json)

    # Si el proceso murió entre la escritura del JSON y la del CSV, el CSV queda
    # desactualizado. Comparar mtimes permite repararlo incluso sin filas nuevas.
    csv_desactualizado = (not archivo_csv.exists()) or (archivo_json.stat().st_mtime > archivo_csv.stat().st_mtime)
    if agregados > 0 or csv_desactualizado:
        df = pd.DataFrame(historico)
        escribir_csv(df, archivo_csv)
        logger.info(f"[{fuente}] {nombre_archivo}: +{agregados} nuevos registros. Total: {len(historico)} filas.")

    return agregados
