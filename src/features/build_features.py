"""
Módulo de ingeniería de features para detección de fraude.
Construye variables derivadas a partir de las tablas base.
"""
from typing import Dict

import numpy as np
import pandas as pd

from src.utils.dataframe_columns import ensure_str_columns, normalize_datasets_columns


def build_all_features(datasets: Dict[str, pd.DataFrame]) -> pd.DataFrame:
    datasets = normalize_datasets_columns(datasets)
    siniestros = datasets.get("siniestros")
    if siniestros is None:
        raise ValueError("Se requiere la tabla 'siniestros'")

    df = siniestros.copy()
    polizas = datasets.get("polizas")
    asegurados = datasets.get("asegurados")
    proveedores = datasets.get("proveedores")
    vehiculos = datasets.get("vehiculos")
    documentos = datasets.get("documentos")

    if polizas is not None:
        df = _merge_poliza_features(df, polizas)
    if asegurados is not None:
        df = _merge_asegurado_features(df, asegurados)
    if proveedores is not None:
        df = _merge_proveedor_features(df, proveedores)
    if vehiculos is not None:
        df = _merge_vehiculo_features(df, vehiculos)
    if documentos is not None:
        df = _merge_documento_features(df, documentos)

    df = _build_temporal_features(df)
    df = _build_frequency_features(df)
    df = _build_amount_features(df)
    df = _build_critical_rule_features(df)

    return ensure_str_columns(df)


def _merge_poliza_features(df: pd.DataFrame, polizas: pd.DataFrame) -> pd.DataFrame:
    poliza_cols = ["id_poliza"]
    for col in ["suma_asegurada", "prima", "deducible", "canal_venta", "estado_poliza"]:
        if col in polizas.columns and col not in df.columns:
            poliza_cols.append(col)

    if len(poliza_cols) > 1:
        df = df.merge(polizas[poliza_cols], on="id_poliza", how="left")

    if "suma_asegurada" in df.columns and "monto_reclamado" in df.columns:
        df["ratio_reclamado_asegurado"] = np.where(
            df["suma_asegurada"] > 0,
            df["monto_reclamado"] / df["suma_asegurada"],
            0
        )
    return df


def _merge_asegurado_features(df: pd.DataFrame, asegurados: pd.DataFrame) -> pd.DataFrame:
    aseg_cols = ["id_asegurado"]
    for col in ["segmento", "antiguedad_anos", "score_cliente", "mora_actual", "en_lista_restrictiva"]:
        if col in asegurados.columns and col not in df.columns:
            aseg_cols.append(col)

    if len(aseg_cols) > 1:
        rename = {c: f"aseg_{c}" if c != "id_asegurado" else c for c in aseg_cols}
        df = df.merge(asegurados[aseg_cols].rename(columns=rename), on="id_asegurado", how="left")
    return df


def _merge_proveedor_features(df: pd.DataFrame, proveedores: pd.DataFrame) -> pd.DataFrame:
    if "id_proveedor" not in df.columns:
        return df

    prov_cols = ["id_proveedor"]
    for col in ["casos_observados", "porcentaje_casos_observados", "en_lista_restrictiva", "monto_promedio_reclamado"]:
        if col in proveedores.columns:
            prov_cols.append(col)

    if len(prov_cols) > 1:
        prov_rename = {c: f"prov_{c}" if c != "id_proveedor" else c for c in prov_cols}
        prov_data = proveedores[prov_cols].rename(columns=prov_rename)
        df = df.merge(prov_data, on="id_proveedor", how="left")
    return df


def _merge_vehiculo_features(df: pd.DataFrame, vehiculos: pd.DataFrame) -> pd.DataFrame:
    if "id_vehiculo" not in df.columns:
        return df

    veh_cols = ["id_vehiculo"]
    for col in ["marca", "ano", "tipo"]:
        if col in vehiculos.columns and col not in df.columns:
            veh_cols.append(col)

    if len(veh_cols) > 1:
        df = df.merge(vehiculos[veh_cols], on="id_vehiculo", how="left")

    if "ano" in df.columns:
        df["vehiculo_antiguedad"] = 2025 - df["ano"].fillna(2020)
    return df


def _merge_documento_features(df: pd.DataFrame, documentos: pd.DataFrame) -> pd.DataFrame:
    if "id_siniestro" not in documentos.columns:
        return df

    doc_agg = documentos.groupby("id_siniestro").agg(
        total_documentos=("id_documento", "count"),
        docs_entregados=("entregado", lambda x: (x == "Sí").sum()),
        docs_legibles=("legible", lambda x: (x == "Sí").sum() if "legible" in documentos.columns else 0),
        docs_con_inconsistencia=("inconsistencia_detectada", lambda x: (x.fillna("") != "").sum()),
    ).reset_index()

    doc_agg["ratio_docs_entregados"] = np.where(
        doc_agg["total_documentos"] > 0,
        doc_agg["docs_entregados"] / doc_agg["total_documentos"],
        1
    )
    doc_agg["tiene_inconsistencia_doc"] = (doc_agg["docs_con_inconsistencia"] > 0).astype(int)

    df = df.merge(doc_agg, on="id_siniestro", how="left")
    return df


def _build_temporal_features(df: pd.DataFrame) -> pd.DataFrame:
    if "dias_desde_inicio_poliza" in df.columns:
        df["borde_inicio_vigencia"] = (df["dias_desde_inicio_poliza"] <= 30).astype(int)
        df["borde_inicio_extremo"] = (df["dias_desde_inicio_poliza"] <= 10).astype(int)

    if "dias_desde_fin_poliza" in df.columns:
        df["borde_fin_vigencia"] = (df["dias_desde_fin_poliza"] <= 30).astype(int)

    if "dias_entre_ocurrencia_reporte" in df.columns:
        df["reporte_tardio"] = (df["dias_entre_ocurrencia_reporte"] > 7).astype(int)
        df["demora_denuncia_robo"] = 0
        mask_robo = df["cobertura"].str.contains("Robo", case=False, na=False)
        df.loc[mask_robo, "demora_denuncia_robo"] = (
            df.loc[mask_robo, "dias_entre_ocurrencia_reporte"] > 2
        ).astype(int)

    if "fecha_ocurrencia" in df.columns:
        fecha = pd.to_datetime(df["fecha_ocurrencia"], errors="coerce")
        df["dia_semana_ocurrencia"] = fecha.dt.dayofweek
        df["es_fin_semana"] = (fecha.dt.dayofweek >= 5).astype(int)
        df["hora_estimada_madrugada"] = 0

    if "dias_desde_inicio_poliza" in df.columns and "dias_desde_fin_poliza" in df.columns:
        min_dias = df[["dias_desde_inicio_poliza", "dias_desde_fin_poliza"]].min(axis=1)
        df["horas_borde_vigencia"] = min_dias.clip(lower=0) * 24
        df["borde_vigencia_48h"] = (df["horas_borde_vigencia"] < 48).astype(int)

    return df


def _build_critical_rule_features(df: pd.DataFrame) -> pd.DataFrame:
    """Features para reglas críticas RF-02, RF-03 y RF-04."""
    if "aseg_en_lista_restrictiva" in df.columns:
        df["aseg_en_lista_restrictiva"] = df["aseg_en_lista_restrictiva"].fillna(0).astype(int)
    else:
        df["aseg_en_lista_restrictiva"] = 0

    if "prov_en_lista_restrictiva" in df.columns:
        df["beneficiario_en_lista_restrictiva"] = df["prov_en_lista_restrictiva"].fillna(0).astype(int)
    else:
        df["beneficiario_en_lista_restrictiva"] = 0

    if "id_conductor" in df.columns and "id_asegurado" in df.columns:
        df["conductor_en_lista_restrictiva"] = np.where(
            (df["id_conductor"] == df["id_asegurado"]) & (df["aseg_en_lista_restrictiva"] == 1),
            1,
            0,
        )
    else:
        df["conductor_en_lista_restrictiva"] = 0

    if "descripcion" in df.columns:
        desc = df["descripcion"].fillna("").astype(str).str.lower()
        dinamica_kw = (
            "físicamente imposible|fisicamente imposible|dinámica imposible|dinamica imposible"
            "|volcadura en vía recta|volcadura en via recta|relatos contradictorios|fotos no coinciden"
        )
        dinamica_sospechosa_kw = (
            "frontal.*posterior|posterior.*frontal|impacto múltiple|impacto multiple|trayectorias imposibles"
            "|minucias cruzadas|versiones incompatibles"
        )
        sin_tercero_kw = (
            "sin tercero identificado|vehículo no identificado|vehiculo no identificado|huyó el tercero"
            "|huyo el tercero|no hay testigos ni cámaras|no hay testigos ni camaras"
        )
        fals_kw = "falsific|adulter|documento alterado|documento falso"
        df["flag_dinamica_imposible"] = desc.str.contains(dinamica_kw, regex=True, na=False).astype(int)
        df["flag_dinamica_sospechosa"] = desc.str.contains(dinamica_sospechosa_kw, regex=True, na=False).astype(int)
        df["flag_sin_tercero_identificado"] = desc.str.contains(sin_tercero_kw, regex=True, na=False).astype(int)
        df["flag_falsificacion_doc"] = desc.str.contains(fals_kw, regex=True, na=False).astype(int)
    else:
        df["flag_dinamica_imposible"] = 0
        df["flag_dinamica_sospechosa"] = 0
        df["flag_sin_tercero_identificado"] = 0
        df["flag_falsificacion_doc"] = 0

    if "tiene_inconsistencia_doc" in df.columns:
        df["flag_falsificacion_doc"] = (
            (df["flag_falsificacion_doc"] == 1) | (df["tiene_inconsistencia_doc"].fillna(0) > 0)
        ).astype(int)

    return df


def _build_frequency_features(df: pd.DataFrame) -> pd.DataFrame:
    if "id_asegurado" in df.columns:
        freq_aseg = df.groupby("id_asegurado")["id_siniestro"].transform("count")
        df["frecuencia_siniestros_asegurado"] = freq_aseg

    if "id_vehiculo" in df.columns:
        freq_veh = df.groupby("id_vehiculo")["id_siniestro"].transform("count")
        df["frecuencia_siniestros_vehiculo"] = freq_veh.fillna(0)

    if "id_conductor" in df.columns:
        freq_cond = df.groupby("id_conductor")["id_siniestro"].transform("count")
        df["frecuencia_siniestros_conductor"] = freq_cond.fillna(0)

    if "id_proveedor" in df.columns:
        freq_prov = df.groupby("id_proveedor")["id_siniestro"].transform("count")
        df["frecuencia_proveedor"] = freq_prov.fillna(0)

    if "cobertura" in df.columns and "id_asegurado" in df.columns:
        mask_rc = df["cobertura"].str.contains("Responsabilidad Civil", case=False, na=False)
        rc_count = df[mask_rc].groupby("id_asegurado")["id_siniestro"].transform("count")
        df["frecuencia_solo_rc"] = 0
        df.loc[mask_rc, "frecuencia_solo_rc"] = rc_count

    return df


def _build_amount_features(df: pd.DataFrame) -> pd.DataFrame:
    if "monto_reclamado" in df.columns:
        mean_by_ramo = df.groupby("ramo")["monto_reclamado"].transform("mean")
        std_by_ramo = df.groupby("ramo")["monto_reclamado"].transform("std").replace(0, 1)
        df["monto_zscore_ramo"] = (df["monto_reclamado"] - mean_by_ramo) / std_by_ramo

        mean_by_cob = df.groupby("cobertura")["monto_reclamado"].transform("mean")
        df["ratio_monto_vs_promedio_cobertura"] = np.where(
            mean_by_cob > 0,
            df["monto_reclamado"] / mean_by_cob,
            1
        )

    if "monto_reclamado" in df.columns and "monto_estimado" in df.columns:
        df["diferencia_reclamado_estimado"] = df["monto_reclamado"] - df["monto_estimado"]
        df["ratio_reclamado_estimado"] = np.where(
            df["monto_estimado"] > 0,
            df["monto_reclamado"] / df["monto_estimado"],
            1
        )

    return df


def get_feature_columns(df: pd.DataFrame) -> list:
    df = ensure_str_columns(df)
    exclude_cols = [
        "id_siniestro", "id_poliza", "id_asegurado", "id_vehiculo",
        "id_conductor", "id_proveedor", "id_documento",
        "descripcion", "beneficiario", "nombre_proveedor", "observacion",
        "fecha_ocurrencia", "fecha_reporte", "fecha_inicio", "fecha_fin",
        "fecha_emision", "etiqueta_fraude_simulada",
        "estado", "sucursal", "ciudad",
    ]
    numeric_cols = [str(c) for c in df.select_dtypes(include=[np.number]).columns]
    return [c for c in numeric_cols if c not in exclude_cols]
