"""Normalización de nombres de columnas (MySQL/SQLAlchemy → pandas/sklearn)."""
from typing import Dict, Optional, Set

import pandas as pd


def normalize_id_value(value) -> Optional[str]:
    """Unifica IDs entre hojas Excel/CSV (espacios, .0, mayúsculas)."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    s = str(value).strip()
    if not s or s.lower() in ("nan", "none", "null"):
        return None
    if s.endswith(".0") and s[:-2].isdigit():
        s = s[:-2]
    return s.upper()


def normalize_id_column(series: pd.Series) -> pd.Series:
    return series.map(normalize_id_value)


def normalize_dataset_ids(datasets: Dict[str, pd.DataFrame]) -> Dict[str, pd.DataFrame]:
    """Normaliza columnas de clave foránea en todas las tablas del workbook."""
    id_cols_by_table = {
        "asegurados": ["id_asegurado"],
        "vehiculos": ["id_vehiculo", "id_asegurado"],
        "polizas": ["id_poliza", "id_asegurado"],
        "proveedores": ["id_proveedor"],
        "siniestros": [
            "id_siniestro", "id_poliza", "id_asegurado", "id_vehiculo",
            "id_proveedor", "id_conductor",
        ],
        "documentos": ["id_documento", "id_siniestro"],
    }
    out = {}
    for name, df in datasets.items():
        frame = ensure_str_columns(df.copy())
        for col in id_cols_by_table.get(name, []):
            if col in frame.columns:
                frame[col] = normalize_id_column(frame[col])
        out[name] = frame
    return out


def id_set_from_column(df: pd.DataFrame, col: str) -> Set[str]:
    if df is None or col not in df.columns:
        return set()
    return {x for x in normalize_id_column(df[col]) if x}


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
