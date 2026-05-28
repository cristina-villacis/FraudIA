"""
Mapeo del dataset oficial de la aseguradora (Evento Datasets_Sinteticos_Fraude_500_v2.xlsx)
a las tablas canónicas del proyecto.
"""
from __future__ import annotations

import os
import re
import unicodedata
from typing import Dict, Optional

import numpy as np
import pandas as pd

# Hojas del Excel de la aseguradora → tablas internas
INSURER_SHEET_ALIASES: Dict[str, str] = {
    "1_siniestros": "siniestros",
    "2_polizas": "polizas",
    "3_asegurados": "asegurados",
    "4_proveedores": "proveedores",
    "5_documentos": "documentos",
    "readme": "readme",
    "6_indice_documentos": "indice_documentos",
}

# Renombre explícito: columna normalizada (sin acentos) → columna canónica
COLUMN_RENAMES: Dict[str, Dict[str, str]] = {
    "siniestros": {
        "id_siniestro": "id_siniestro",
        "id_poliza": "id_poliza",
        "id_asegurado": "id_asegurado",
        "ramo": "ramo",
        "placa_vehiculo_asegurado": "placa_vehiculo",
        "cobertura": "cobertura",
        "fecha_ocurrencia": "fecha_ocurrencia",
        "fecha_reporte": "fecha_reporte",
        "dias_ocurr_reporte": "dias_entre_ocurrencia_reporte",
        "dias_ocurr_a_reporte": "dias_entre_ocurrencia_reporte",
        "monto_reclamado": "monto_reclamado",
        "monto_reclamado_": "monto_reclamado",
        "monto_estimado": "monto_estimado",
        "monto_estimado_": "monto_estimado",
        "monto_pagado": "monto_pagado",
        "monto_pagado_": "monto_pagado",
        "estado": "estado",
        "sucursal": "sucursal",
        "id_proveedor": "id_proveedor",
        "descripcion_del_evento": "descripcion",
        "docs_completos": "documentos_completos",
        "prov_lista_restrictiva": "prov_en_lista_restrictiva",
        "prov._lista_restrictiva": "prov_en_lista_restrictiva",
        "dias_desde_inicio_poliza": "dias_desde_inicio_poliza",
        "dias_hasta_fin_poliza": "dias_desde_fin_poliza",
        "n_reclamos_previos_asegurado": "historial_siniestros_asegurado",
        "suma_asegurada": "suma_asegurada",
        "suma_asegurada_": "suma_asegurada",
        "similitud_narrativa_max": "similitud_narrativa_max",
        "similitud_narrativa_max.": "similitud_narrativa_max",
        "numero_parte_policial": "numero_parte_policial",
        "etiqueta_fraude_simulada": "etiqueta_fraude_simulada",
    },
    "polizas": {
        "id_poliza": "id_poliza",
        "id_asegurado": "id_asegurado",
        "ramo": "ramo",
        "fecha_inicio": "fecha_inicio",
        "fecha_fin": "fecha_fin",
        "suma_asegurada": "suma_asegurada",
        "suma_asegurada_": "suma_asegurada",
        "prima_anual": "prima",
        "prima_anual_": "prima",
        "canal_venta": "canal_venta",
        "estado_poliza": "estado_poliza",
    },
    "asegurados": {
        "id_asegurado": "id_asegurado",
        "nombres_asegurado": "nombres_asegurado",
        "segmento": "segmento",
        "ciudad": "ciudad",
        "antiguedad_anos": "antiguedad_anos",
        "antiguedad_aos": "antiguedad_anos",
        "n_polizas_activas": "numero_polizas",
        "n_reclamos_ultimos_12_meses": "reclamos_ultimos_12m",
        "n_reclamos_historico_total": "reclamos_historico_total",
        "reclamos_rc_sin_tercero": "reclamos_rc_sin_tercero",
        "perfil_riesgo_historico": "perfil_riesgo_historico",
    },
    "proveedores": {
        "id_proveedor": "id_proveedor",
        "nombre_proveedor": "nombre_proveedor",
        "tipo": "tipo",
        "ciudad": "ciudad",
        "n_siniestros_asociados": "reclamos_asociados",
        "en_lista_restrictiva": "en_lista_restrictiva",
        "motivo_restriccion": "motivo_restriccion",
        "promedio_monto": "monto_promedio_reclamado",
        "promedio_monto_": "monto_promedio_reclamado",
    },
    "documentos": {
        "id_documento": "id_documento",
        "id_siniestro": "id_siniestro",
        "tipo_documento": "tipo_documento",
        "nombre_archivo_pdf": "nombre_archivo_pdf",
    },
}


def _normalize_col_name(raw: str) -> str:
    text = unicodedata.normalize("NFKD", str(raw or ""))
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = text.lower().strip()
    text = text.replace("→", "_").replace("(", "").replace(")", "")
    text = text.replace("$", "").replace(".", "")
    text = re.sub(r"[^a-z0-9]+", "_", text)
    return text.strip("_")


def resolve_insurer_sheet_name(sheet_name: str) -> str:
    key = _normalize_col_name(sheet_name)
    return INSURER_SHEET_ALIASES.get(key, key)


def remap_insurer_dataframe(df: pd.DataFrame, table_name: str) -> pd.DataFrame:
    """Renombra columnas del Excel de la aseguradora al esquema interno."""
    if df is None or df.empty:
        return df
    out = df.copy()
    out.columns = [_normalize_col_name(c) for c in out.columns]
    out = out.loc[:, ~out.columns.str.startswith("unnamed")]

    mapping = COLUMN_RENAMES.get(table_name, {})
    rename = {}
    for col in out.columns:
        if col in mapping:
            rename[col] = mapping[col]
    out = out.rename(columns=rename)

    if table_name == "siniestros":
        out = _postprocess_siniestros(out)
    elif table_name == "polizas":
        out = _postprocess_polizas(out)
    elif table_name == "asegurados":
        out = _postprocess_asegurados(out)
    elif table_name == "proveedores":
        out = _postprocess_proveedores(out)
    elif table_name == "documentos":
        out = _postprocess_documentos(out)

    return out


def _yes_no_to_int(series: pd.Series) -> pd.Series:
    s = series.astype(str).str.strip().str.lower()
    return s.isin(["si", "sí", "1", "true", "yes", "y"]).astype(int)


def _postprocess_siniestros(df: pd.DataFrame) -> pd.DataFrame:
    if "documentos_completos" in df.columns:
        dc = df["documentos_completos"].astype(str).str.strip().str.lower()
        df["documentos_completos"] = np.where(dc.str.startswith("s"), "Si", "No")
    if "prov_en_lista_restrictiva" in df.columns:
        df["prov_en_lista_restrictiva"] = _yes_no_to_int(df["prov_en_lista_restrictiva"])
    if "similitud_narrativa_max" in df.columns:
        df["similitud_narrativa_max"] = pd.to_numeric(df["similitud_narrativa_max"], errors="coerce").fillna(0)
    if "beneficiario" not in df.columns and "id_proveedor" in df.columns:
        df["beneficiario"] = df["id_proveedor"]
    if "etiqueta_fraude_simulada" not in df.columns:
        df["etiqueta_fraude_simulada"] = derive_fraud_label(df)
    return df


def _postprocess_polizas(df: pd.DataFrame) -> pd.DataFrame:
    for col in ("prima", "suma_asegurada"):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)
    if "deducible" not in df.columns:
        df["deducible"] = 0
    if "ciudad" not in df.columns:
        df["ciudad"] = ""
    return df


def _postprocess_asegurados(df: pd.DataFrame) -> pd.DataFrame:
    if "antiguedad_anos" in df.columns:
        df["antiguedad_anos"] = pd.to_numeric(df["antiguedad_anos"], errors="coerce").fillna(0).astype(int)
    if "reclamos_ultimos_12m" in df.columns:
        df["reclamos_ultimos_12m"] = pd.to_numeric(df["reclamos_ultimos_12m"], errors="coerce").fillna(0).astype(int)
    if "numero_polizas" in df.columns:
        df["numero_polizas"] = pd.to_numeric(df["numero_polizas"], errors="coerce").fillna(0).astype(int)
    if "mora_actual" not in df.columns:
        df["mora_actual"] = 0
    if "score_cliente" not in df.columns:
        df["score_cliente"] = 0.0
    return df


def _postprocess_proveedores(df: pd.DataFrame) -> pd.DataFrame:
    if "en_lista_restrictiva" in df.columns:
        df["en_lista_restrictiva"] = _yes_no_to_int(df["en_lista_restrictiva"])
    if "reclamos_asociados" in df.columns:
        df["reclamos_asociados"] = pd.to_numeric(df["reclamos_asociados"], errors="coerce").fillna(0).astype(int)
        df["casos_observados"] = df["reclamos_asociados"]
    if "monto_promedio_reclamado" in df.columns:
        df["monto_promedio_reclamado"] = pd.to_numeric(df["monto_promedio_reclamado"], errors="coerce").fillna(0)
    if "antiguedad_anos" not in df.columns:
        df["antiguedad_anos"] = 0
    if "porcentaje_casos_observados" not in df.columns:
        df["porcentaje_casos_observados"] = 0.0
    return df


def _postprocess_documentos(df: pd.DataFrame) -> pd.DataFrame:
    if "entregado" not in df.columns:
        df["entregado"] = "Si"
    if "legible" not in df.columns:
        df["legible"] = "Si"
    if "nombre_archivo_pdf" in df.columns:
        df["entregado"] = np.where(df["nombre_archivo_pdf"].notna(), "Si", "No")
    return df


def derive_fraud_label(df: pd.DataFrame) -> pd.Series:
    """
    El Excel de la aseguradora no trae etiqueta explícita.
    Proxy para entrenamiento supervisado (alineado a señales de fraude del dataset).
    """
    score = pd.Series(0.0, index=df.index)
    if "prov_en_lista_restrictiva" in df.columns:
        score += pd.to_numeric(df["prov_en_lista_restrictiva"], errors="coerce").fillna(0) * 3
    if "similitud_narrativa_max" in df.columns:
        sim = pd.to_numeric(df["similitud_narrativa_max"], errors="coerce").fillna(0)
        score += (sim >= 0.88).astype(float) * 2
    if "documentos_completos" in df.columns:
        dc = df["documentos_completos"].astype(str).str.lower()
        score += dc.str.startswith("n").astype(float)
    if "dias_entre_ocurrencia_reporte" in df.columns:
        dias = pd.to_numeric(df["dias_entre_ocurrencia_reporte"], errors="coerce").fillna(0)
        score += (dias > 14).astype(float)
    if "monto_reclamado" in df.columns and "suma_asegurada" in df.columns:
        ratio = np.where(
            df["suma_asegurada"] > 0,
            df["monto_reclamado"] / df["suma_asegurada"],
            0,
        )
        score += (ratio > 0.92).astype(float) * 2

    # Umbral dinámico para ~15–25% positivos si hay variación
    if score.max() > 0:
        thr = max(float(score.quantile(0.78)), 2.0)
        return (score >= thr).astype(int)
    return pd.Series(0, index=df.index, dtype=int)


def is_insurer_workbook(sheet_names) -> bool:
    names = {_normalize_col_name(k) for k in sheet_names}
    return "1_siniestros" in names


INSURER_DEFAULT_XLSX = os.path.join("data", "raw", "Evento_Datasets_Sinteticos_Fraude_500_v2.xlsx")
