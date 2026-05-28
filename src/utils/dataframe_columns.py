"""Normalización de nombres de columnas (MySQL/SQLAlchemy → pandas/sklearn)."""
from typing import Dict

import pandas as pd


def ensure_str_columns(df: pd.DataFrame) -> pd.DataFrame:
    """
    Convierte todos los nombres de columna a str.
    Evita errores de sklearn cuando read_sql devuelve quoted_name mezclado con str.
    """
    if df is None or df.empty:
        return df
    out = df.copy()
    out.columns = [str(c) for c in out.columns]
    return out


def normalize_datasets_columns(datasets: Dict[str, pd.DataFrame]) -> Dict[str, pd.DataFrame]:
    return {name: ensure_str_columns(df) for name, df in datasets.items()}
