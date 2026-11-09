import os
from pathlib import Path

import pandas as pd


def _ruta_temporal(archivo: Path) -> Path:
    return archivo.with_name(f".{archivo.name}.tmp")


def escribir_csv(df: pd.DataFrame, archivo: Path):
    temporal = _ruta_temporal(archivo)
    df.to_csv(temporal, index=False)
    os.replace(temporal, archivo)


def archivo_bloqueado(archivo: Path) -> bool:
    return (archivo.parent / f".~lock.{archivo.name}#").exists()
