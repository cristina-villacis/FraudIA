"""
Módulo de carga, validación y limpieza de datos.
Soporta carga desde CSV, Excel y upload web.
"""
import os
import re
import unicodedata
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd


from src.ingestion.schema import EXPECTED_COLUMNS, REQUIRED_COLUMNS, SKIP_SHEETS

TABLE_KEY_COLUMNS = {
    "siniestros": "id_siniestro",
    "polizas": "id_poliza",
    "asegurados": "id_asegurado",
    "vehiculos": "id_vehiculo",
    "proveedores": "id_proveedor",
    "documentos": "id_documento",
}

from src.ingestion.insurer_mapping import (
    is_insurer_workbook,
    remap_insurer_dataframe,
    resolve_insurer_sheet_name,
)

NAME_ALIASES = {
    "siniestro": "siniestros",
    "sin": "siniestros",
    "claims": "siniestros",
    "claim": "siniestros",
    "reclamos": "siniestros",
    "poliza": "polizas",
    "polizas": "polizas",
    "asegurado": "asegurados",
    "vehiculo": "vehiculos",
    "proveedor": "proveedores",
    "documento": "documentos",
    "plantilla_dataset_fraudia": "siniestros",
}


def _normalize_name(raw: str) -> str:
    text = unicodedata.normalize("NFKD", raw or "")
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = text.lower().strip()
    text = re.sub(r"[^a-z0-9]+", "_", text)
    return text.strip("_")


def resolve_table_name(raw_name: str, df: pd.DataFrame) -> str:
    """Nombre canónico de tabla a partir de hoja/archivo o columnas del DataFrame."""
    normalized = _normalize_name(raw_name)
    if normalized in NAME_ALIASES:
        normalized = NAME_ALIASES[normalized]
    if normalized in EXPECTED_COLUMNS:
        return normalized

    cols = {str(c).lower().strip() for c in df.columns}
    for table in TABLE_KEY_COLUMNS:
        key = TABLE_KEY_COLUMNS[table]
        if key in cols:
            return table
    return normalized


def load_csv(filepath: str, encoding: str = "utf-8-sig") -> pd.DataFrame:
    try:
        df = pd.read_csv(filepath, encoding=encoding)
    except UnicodeDecodeError:
        df = pd.read_csv(filepath, encoding="latin-1")
    return df


def load_excel(filepath: str, sheet_name: Optional[str] = None) -> Dict[str, pd.DataFrame]:
    xls = pd.ExcelFile(filepath)
    if sheet_name:
        return {sheet_name: pd.read_excel(xls, sheet_name=sheet_name)}
    return {name: pd.read_excel(xls, sheet_name=name) for name in xls.sheet_names}


def validate_dataframe(df: pd.DataFrame, table_name: str) -> Tuple[bool, list]:
    required = REQUIRED_COLUMNS.get(table_name)
    if not required:
        return True, []
    missing = [col for col in required if col not in df.columns]
    return len(missing) == 0, missing


def clean_dataframe(df: pd.DataFrame, table_name: str) -> pd.DataFrame:
    df = df.copy()
    df.columns = df.columns.str.strip().str.lower().str.replace(" ", "_")

    for col in df.select_dtypes(include=["object"]).columns:
        df[col] = df[col].str.strip()

    date_cols = [c for c in df.columns if "fecha" in c]
    for col in date_cols:
        df[col] = pd.to_datetime(df[col], errors="coerce")

    numeric_cols = [c for c in df.columns if any(k in c for k in ["monto", "prima", "suma", "deducible", "score"])]
    for col in numeric_cols:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    if table_name == "siniestros":
        df = _clean_siniestros(df)
    elif table_name == "polizas":
        df = _clean_polizas(df)

    return df


def _clean_siniestros(df: pd.DataFrame) -> pd.DataFrame:
    if "descripción" in df.columns and "descripcion" not in df.columns:
        df["descripcion"] = df["descripción"]

    # Campos opcionales para mantener trazabilidad sin exigirlos en la carga mínima.
    if "id_conductor" not in df.columns and "id_asegurado" in df.columns:
        df["id_conductor"] = df["id_asegurado"]
    if "id_proveedor" not in df.columns:
        df["id_proveedor"] = None

    if "monto_reclamado" in df.columns:
        df["monto_reclamado"] = df["monto_reclamado"].fillna(0).clip(lower=0)
    if "monto_estimado" in df.columns:
        df["monto_estimado"] = df["monto_estimado"].fillna(0).clip(lower=0)
    if "monto_pagado" in df.columns:
        df["monto_pagado"] = df["monto_pagado"].fillna(0).clip(lower=0)
    if "documentos_completos" in df.columns:
        df["documentos_completos"] = df["documentos_completos"].fillna("No")
    if "descripcion" in df.columns:
        df["descripcion"] = df["descripcion"].fillna("")
    if "dias_entre_ocurrencia_reporte" in df.columns:
        df["dias_entre_ocurrencia_reporte"] = df["dias_entre_ocurrencia_reporte"].fillna(0).clip(lower=0)
    if "dias_desde_inicio_poliza" in df.columns:
        df["dias_desde_inicio_poliza"] = df["dias_desde_inicio_poliza"].fillna(0).clip(lower=0)
    return df


def _clean_polizas(df: pd.DataFrame) -> pd.DataFrame:
    if "prima" in df.columns:
        df["prima"] = df["prima"].fillna(0).clip(lower=0)
    if "suma_asegurada" in df.columns:
        df["suma_asegurada"] = df["suma_asegurada"].fillna(0).clip(lower=0)
    return df


def tables_from_sheets(sheets: Dict[str, pd.DataFrame]) -> Dict[str, pd.DataFrame]:
    """Convierte hojas/archivos crudos en tablas con nombres canónicos."""
    insurer_mode = is_insurer_workbook(sheets.keys())
    datasets: Dict[str, pd.DataFrame] = {}
    for sheet_name, df in sheets.items():
        if df is None or df.empty:
            continue
        if insurer_mode:
            table_name = resolve_insurer_sheet_name(sheet_name)
            if table_name in SKIP_SHEETS:
                continue
            df = remap_insurer_dataframe(df, table_name)
        else:
            table_name = resolve_table_name(sheet_name, df)
        cleaned = clean_dataframe(df, table_name)
        if table_name in datasets:
            combined = pd.concat([datasets[table_name], cleaned], ignore_index=True)
            datasets[table_name] = _dedupe_table(combined, table_name)
        else:
            datasets[table_name] = cleaned
    _enrich_siniestros_beneficiario(datasets)
    return datasets


def _enrich_siniestros_beneficiario(datasets: Dict[str, pd.DataFrame]) -> None:
    """beneficiario = nombre del proveedor según especificación del reto."""
    sin = datasets.get("siniestros")
    prov = datasets.get("proveedores")
    if sin is None or prov is None or "id_proveedor" not in sin.columns:
        return
    if "nombre_proveedor" not in prov.columns or "id_proveedor" not in prov.columns:
        return
    lookup = prov.set_index("id_proveedor")["nombre_proveedor"].astype(str).to_dict()
    sin["beneficiario"] = sin["id_proveedor"].astype(str).map(lookup).fillna(
        sin["id_proveedor"].astype(str)
    )


def _dedupe_table(df: pd.DataFrame, table_name: str) -> pd.DataFrame:
    key = TABLE_KEY_COLUMNS.get(table_name)
    if key and key in df.columns:
        return df.drop_duplicates(subset=[key], keep="last").reset_index(drop=True)
    return df


def load_all_from_directory(directory: str) -> Dict[str, pd.DataFrame]:
    datasets = {}
    csv_files = [f for f in os.listdir(directory) if f.endswith(".csv")]
    for f in csv_files:
        raw_name = os.path.splitext(f)[0]
        filepath = os.path.join(directory, f)
        df = load_csv(filepath)
        table_name = resolve_table_name(raw_name, df)
        df = clean_dataframe(df, table_name)
        valid, missing = validate_dataframe(df, table_name)
        if not valid:
            print(f"  ADVERTENCIA: {table_name} faltan columnas: {missing}")
        if table_name in datasets:
            datasets[table_name] = pd.concat([datasets[table_name], df], ignore_index=True)
        else:
            datasets[table_name] = df
    return datasets


def load_file_to_tables(filepath: str, filename: str) -> Dict[str, pd.DataFrame]:
    """Carga un archivo del disco y devuelve tablas canónicas."""
    if filename.endswith(".csv"):
        raw_name = os.path.splitext(filename)[0]
        df = load_csv(filepath)
        table_name = resolve_table_name(raw_name, df)
        return {table_name: clean_dataframe(df, table_name)}
    if filename.endswith((".xlsx", ".xls")):
        sheets = load_excel(filepath)
        return tables_from_sheets(sheets)
    raise ValueError(f"Formato no soportado: {filename}")


def validate_datasets(datasets: Dict[str, pd.DataFrame]) -> Dict:
    """Validación agregada para respuesta de API."""
    warnings: List[str] = []
    has_siniestros = "siniestros" in datasets and datasets["siniestros"] is not None and len(datasets["siniestros"]) > 0

    if not has_siniestros:
        warnings.append(
            "No se detectó la tabla 'siniestros'. Use la plantilla Excel o un archivo con columna id_siniestro."
        )
    else:
        valid, missing = validate_dataframe(datasets["siniestros"], "siniestros")
        if not valid:
            warnings.append(f"Tabla siniestros: faltan columnas recomendadas: {', '.join(missing)}")

    return {
        "has_siniestros": has_siniestros,
        "warnings": warnings,
        "tables": list(datasets.keys()),
    }


_SKIP_EXCEL_SHEETS = frozenset(
    {"readme", "read me", "instrucciones", "guia", "guía", "help", "ayuda", "metadata"}
)


def load_from_upload(file_storage, filename: str) -> Dict[str, pd.DataFrame]:
    """Carga archivo desde upload HTTP (BytesIO / FileStorage)."""
    if filename.endswith(".csv"):
        df = pd.read_csv(file_storage, encoding="utf-8-sig")
        raw_name = os.path.splitext(filename)[0]
        table_name = resolve_table_name(raw_name, df)
        return {table_name: clean_dataframe(df, table_name)}
    if filename.endswith((".xlsx", ".xls")):
        all_sheets = pd.read_excel(file_storage, sheet_name=None)
        sheets = {
            name: df
            for name, df in all_sheets.items()
            if str(name).strip().lower() not in _SKIP_EXCEL_SHEETS and df is not None and len(df) > 0
        }
        return tables_from_sheets(sheets)
    raise ValueError(f"Formato no soportado: {filename}")
