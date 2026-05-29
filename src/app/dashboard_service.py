"""Agregación y filtrado de datos para el dashboard ejecutivo."""
from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional, Tuple, Union

import pandas as pd

from src.risk.classification import (
    SCORE_AMARILLO_MAX,
    SCORE_AMARILLO_MIN,
    SCORE_ROJO_MIN,
    SCORE_VERDE_MAX,
)


def _score_and_semaforo_cols(df: pd.DataFrame) -> Tuple[str, str]:
    score_col = "score_hibrido" if "score_hibrido" in df.columns else "score_reglas"
    semaforo_col = "semaforo_final" if "semaforo_final" in df.columns else "semaforo_reglas"
    return score_col, semaforo_col


# Bandas alineadas con classify_risk() y parámetros de fraude (score híbrido)
RISK_BANDS = [
    {
        "key": "verde",
        "semaforo": "Verde",
        "nivel": "Bajo",
        "label": f"Verde — Bajo (0-{SCORE_VERDE_MAX})",
        "min": 0,
        "max": SCORE_VERDE_MAX,
        "color": "#00C48C",
    },
    {
        "key": "amarillo",
        "semaforo": "Amarillo",
        "nivel": "Medio",
        "label": f"Amarillo — Medio ({SCORE_AMARILLO_MIN}-{SCORE_AMARILLO_MAX})",
        "min": SCORE_AMARILLO_MIN,
        "max": SCORE_AMARILLO_MAX,
        "color": "#FFC857",
    },
    {
        "key": "rojo",
        "semaforo": "Rojo",
        "nivel": "Alto",
        "label": f"Rojo — Alto ({SCORE_ROJO_MIN}-100)",
        "min": SCORE_ROJO_MIN,
        "max": 100,
        "color": "#FF4D4F",
    },
]


def _build_score_distribution_by_risk(df: pd.DataFrame, score_col: str) -> Dict[str, Any]:
    """Distribución por nivel de riesgo según score (parámetros de fraude)."""
    if score_col not in df.columns:
        return {
            "bins": [],
            "counts": [],
            "colors": [],
            "labels": [],
            "click_ranges": [],
            "total": 0,
        }

    scores = pd.to_numeric(df[score_col], errors="coerce").fillna(0)
    bins = []
    counts = []
    colors = []
    labels = []
    click_ranges = []

    for band in RISK_BANDS:
        mask = (scores >= band["min"]) & (scores <= band["max"])
        count = int(mask.sum())
        bins.append(f"{band['min']}-{band['max']}")
        counts.append(count)
        colors.append(band["color"])
        labels.append(band["label"])
        click_ranges.append({
            "min": band["min"],
            "max": band["max"],
            "key": band["key"],
            "label": band["label"],
            "semaforo": band["semaforo"],
        })

    return {
        "bins": bins,
        "counts": counts,
        "colors": colors,
        "labels": labels,
        "click_ranges": click_ranges,
        "total": int(len(scores)),
    }


def apply_dashboard_filters(df: pd.DataFrame, params: Dict[str, Any]) -> Tuple[pd.DataFrame, List[Dict[str, str]]]:
    """Aplica filtros desde query params. Retorna (df_filtrado, filtros_activos)."""
    if df is None or df.empty:
        return df, []

    filtered = df.copy()
    active: List[Dict[str, str]] = []
    score_col, semaforo_col = _score_and_semaforo_cols(filtered)

    semaforo = (params.get("semaforo") or "").strip()
    if semaforo and semaforo.lower() != "all" and semaforo_col in filtered.columns:
        values = [v.strip() for v in semaforo.split(",") if v.strip()]
        if values:
            filtered = filtered[filtered[semaforo_col].isin(values)]
            active.append({"key": "semaforo", "label": "Semáforo", "value": ", ".join(values)})

    ramo = (params.get("ramo") or "").strip()
    if ramo and ramo.lower() != "all" and "ramo" in filtered.columns:
        filtered = filtered[filtered["ramo"] == ramo]
        active.append({"key": "ramo", "label": "Ramo", "value": ramo})

    cobertura = (params.get("cobertura") or "").strip()
    if cobertura and cobertura.lower() != "all" and "cobertura" in filtered.columns:
        filtered = filtered[filtered["cobertura"] == cobertura]
        active.append({"key": "cobertura", "label": "Cobertura", "value": cobertura})

    sucursal = (params.get("sucursal") or "").strip()
    if sucursal and sucursal.lower() != "all" and "sucursal" in filtered.columns:
        filtered = filtered[filtered["sucursal"] == sucursal]
        active.append({"key": "sucursal", "label": "Sucursal", "value": sucursal})

    estado = (params.get("estado") or "").strip()
    if estado and estado.lower() != "all" and "estado" in filtered.columns:
        filtered = filtered[filtered["estado"] == estado]
        active.append({"key": "estado", "label": "Estado", "value": estado})

    search = (params.get("search") or "").strip()
    if search and "id_siniestro" in filtered.columns:
        mask = filtered["id_siniestro"].astype(str).str.contains(search, case=False, na=False)
        filtered = filtered[mask]
        active.append({"key": "search", "label": "Búsqueda", "value": search})

    if score_col in filtered.columns:
        score_min = params.get("score_min")
        score_max = params.get("score_max")
        if score_min not in (None, ""):
            lo = float(score_min)
            filtered = filtered[filtered[score_col] >= lo]
            active.append({"key": "score_min", "label": "Score mín.", "value": str(int(lo))})
        if score_max not in (None, ""):
            hi = float(score_max)
            filtered = filtered[filtered[score_col] <= hi]
            active.append({"key": "score_max", "label": "Score máx.", "value": str(int(hi))})

    if "fecha_ocurrencia" in filtered.columns:
        fecha = pd.to_datetime(filtered["fecha_ocurrencia"], errors="coerce")
        fd = (params.get("fecha_desde") or "").strip()
        fh = (params.get("fecha_hasta") or "").strip()
        if fd:
            filtered = filtered[fecha >= pd.to_datetime(fd)]
            active.append({"key": "fecha_desde", "label": "Desde", "value": fd})
        if fh:
            filtered = filtered[fecha <= pd.to_datetime(fh)]
            active.append({"key": "fecha_hasta", "label": "Hasta", "value": fh})

    return filtered, active


def params_from_request(req: Union[Mapping[str, str], Any]) -> Dict[str, Any]:
    """Acepta Flask request.args o FastAPI query_params / dict."""
    if hasattr(req, "args"):
        return {k: req.args.get(k, "") for k in req.args}
    if hasattr(req, "items"):
        return {k: v for k, v in req.items()}
    return {}


def get_filter_options(df: pd.DataFrame) -> Dict[str, Any]:
    if df is None or df.empty:
        return {"error": "Sin datos"}

    score_col, semaforo_col = _score_and_semaforo_cols(df)
    fecha_min, fecha_max = None, None
    if "fecha_ocurrencia" in df.columns:
        fechas = pd.to_datetime(df["fecha_ocurrencia"], errors="coerce").dropna()
        if len(fechas):
            fecha_min = fechas.min().strftime("%Y-%m-%d")
            fecha_max = fechas.max().strftime("%Y-%m-%d")

    def _sorted_unique(col: str) -> List[str]:
        if col not in df.columns:
            return []
        return sorted(df[col].dropna().astype(str).unique().tolist())

    return {
        "ramos": _sorted_unique("ramo"),
        "coberturas": _sorted_unique("cobertura"),
        "sucursales": _sorted_unique("sucursal"),
        "estados": _sorted_unique("estado"),
        "semaforos": ["Verde", "Amarillo", "Rojo"],
        "fecha_min": fecha_min,
        "fecha_max": fecha_max,
        "score_min": int(df[score_col].min()) if score_col in df.columns else 0,
        "score_max": int(df[score_col].max()) if score_col in df.columns else 100,
        "total_records": len(df),
    }


def build_dashboard_payload(
    df: pd.DataFrame,
    total_unfiltered: int,
    active_filters: Optional[List[Dict[str, str]]] = None,
    source_total_siniestros: Optional[int] = None,
) -> Dict[str, Any]:
    active_filters = active_filters or []
    source_total = source_total_siniestros or total_unfiltered
    if df is None or df.empty:
        return {
            "semaforo": {"Rojo": 0, "Amarillo": 0, "Verde": 0},
            "total": 0,
            "total_unfiltered": total_unfiltered,
            "source_total_siniestros": source_total,
            "score_promedio": 0,
            "monto_total": 0,
            "ramo_data": [],
            "top_cases": [],
            "score_distribution": {
                "bins": [],
                "counts": [],
                "colors": [],
                "labels": [],
                "click_ranges": [],
                "total": 0,
            },
            "temporal_data": [],
            "active_filters": active_filters,
            "filtered": len(active_filters) > 0,
        }

    score_col, semaforo_col = _score_and_semaforo_cols(df)
    semaforo_counts = df[semaforo_col].value_counts().to_dict() if semaforo_col in df.columns else {}

    ramo_data = []
    if "ramo" in df.columns:
        ramo_stats = df.groupby("ramo").agg(
            count=("id_siniestro", "count"),
            monto_total=("monto_reclamado", "sum"),
            score_avg=(score_col, "mean"),
            rojos=(semaforo_col, lambda x: (x == "Rojo").sum()),
            amarillos=(semaforo_col, lambda x: (x == "Amarillo").sum()),
            verdes=(semaforo_col, lambda x: (x == "Verde").sum()),
        ).reset_index().round(2)
        ramo_data = ramo_stats.to_dict("records")

    cols_top = ["id_siniestro", "ramo", "cobertura", "monto_reclamado", score_col, semaforo_col, "alertas_reglas"]
    for extra in ("beneficiario", "estado", "id_asegurado"):
        if extra in df.columns and extra not in cols_top:
            cols_top.append(extra)
    cols_top = [c for c in cols_top if c in df.columns]
    top_cases = df.nlargest(20, score_col)[cols_top].to_dict("records") if score_col in df.columns else []

    score_distribution = (
        _build_score_distribution_by_risk(df, score_col)
        if score_col in df.columns
        else {"bins": [], "counts": [], "colors": [], "labels": [], "click_ranges": [], "total": 0}
    )

    temporal_data = []
    if "fecha_ocurrencia" in df.columns:
        fecha = pd.to_datetime(df["fecha_ocurrencia"], errors="coerce")
        df_temp = df.copy()
        df_temp["mes"] = fecha.dt.to_period("M").astype(str)
        temporal = df_temp.groupby("mes").agg(
            count=("id_siniestro", "count"),
            monto=("monto_reclamado", "sum"),
            score_avg=(score_col, "mean"),
        ).reset_index().round(2)
        temporal_data = temporal.to_dict("records")

    temporal_risk_data = []
    if "fecha_ocurrencia" in df.columns and semaforo_col in df.columns:
        fecha = pd.to_datetime(df["fecha_ocurrencia"], errors="coerce")
        df_temp_risk = df.copy()
        df_temp_risk["mes"] = fecha.dt.to_period("M").astype(str)
        piv_tmp = (
            df_temp_risk.pivot_table(
                index="mes",
                columns=semaforo_col,
                values="id_siniestro",
                aggfunc="count",
                fill_value=0,
            )
            .reindex(columns=["Rojo", "Amarillo", "Verde"], fill_value=0)
            .reset_index()
        )
        temporal_risk_data = piv_tmp.to_dict("records")

    rojos = int(semaforo_counts.get("Rojo", 0))
    amarillos = int(semaforo_counts.get("Amarillo", 0))
    verdes = int(semaforo_counts.get("Verde", 0))

    prob_fraude_prom = round(df["ml_fraud_probability"].fillna(0).mean() * 100, 1) if "ml_fraud_probability" in df.columns else 0
    monto_total = round(df["monto_reclamado"].sum(), 2) if "monto_reclamado" in df.columns else 0
    monto_rojo = round(
        df.loc[df[semaforo_col] == "Rojo", "monto_reclamado"].sum(), 2
    ) if semaforo_col in df.columns and "monto_reclamado" in df.columns else 0
    monto_amarillo = round(
        df.loc[df[semaforo_col] == "Amarillo", "monto_reclamado"].sum(), 2
    ) if semaforo_col in df.columns and "monto_reclamado" in df.columns else 0
    monto_potencial_riesgo = round(monto_rojo + (monto_amarillo * 0.5), 2)

    casos_sospechosos = int(((df[score_col] >= 41).sum())) if score_col in df.columns else 0
    casos_escalados = int(((df[semaforo_col] == "Rojo").sum())) if semaforo_col in df.columns else 0
    casos_observados = int((df["prov_casos_observados"].fillna(0) > 0).sum()) if "prov_casos_observados" in df.columns else 0
    if "id_proveedor" in df.columns and "prov_en_lista_restrictiva" in df.columns:
        proveedores_sospechosos = int(df.loc[df["prov_en_lista_restrictiva"].fillna(0) == 1, "id_proveedor"].nunique())
    else:
        proveedores_sospechosos = 0
    narrativas_clonadas = int(df["alertas_reglas"].fillna("").str.contains("Similitud textual", case=False).sum()) if "alertas_reglas" in df.columns else 0
    alertas_pdf_count = int((df.get("tiene_alerta_pdf", 0) == 1).sum()) if "tiene_alerta_pdf" in df.columns else 0
    if alertas_pdf_count == 0 and "alertas_reglas" in df.columns:
        alertas_pdf_count = int(df["alertas_reglas"].fillna("").str.contains("[PDF]", case=False).sum())

    # Señales de fraude (conteo por lógica de negocio)
    signal_counts = [
        {"signal": "Reclamo cercano al borde de vigencia", "count": int((df.get("borde_inicio_vigencia", 0) == 1).sum()) if "borde_inicio_vigencia" in df.columns else 0},
        {"signal": "Demora denuncia por robo", "count": int((df.get("demora_denuncia_robo", 0) == 1).sum()) if "demora_denuncia_robo" in df.columns else 0},
        {"signal": "Alta frecuencia reclamos asegurado", "count": int((df.get("frecuencia_siniestros_asegurado", 0) >= 3).sum()) if "frecuencia_siniestros_asegurado" in df.columns else 0},
        {"signal": "Alta frecuencia reclamos vehículo", "count": int((df.get("frecuencia_siniestros_vehiculo", 0) >= 3).sum()) if "frecuencia_siniestros_vehiculo" in df.columns else 0},
        {"signal": "Alta frecuencia conductor", "count": int((df.get("frecuencia_siniestros_conductor", 0) >= 3).sum()) if "frecuencia_siniestros_conductor" in df.columns else 0},
        {"signal": "Reclamos solo RC", "count": int((df.get("frecuencia_solo_rc", 0) > 2).sum()) if "frecuencia_solo_rc" in df.columns else 0},
        {"signal": "Beneficiario/proveedor recurrente", "count": int((df.get("prov_casos_observados", 0) > 2).sum()) if "prov_casos_observados" in df.columns else 0},
        {"signal": "Documentos incompletos", "count": int(df.get("documentos_completos", pd.Series([""] * len(df))).astype(str).str.lower().eq("no").sum()) if "documentos_completos" in df.columns else 0},
        {"signal": "Dinámica sospechosa", "count": int((df.get("flag_dinamica_sospechosa", 0) == 1).sum()) if "flag_dinamica_sospechosa" in df.columns else 0},
        {"signal": "Eventos sin tercero identificado", "count": int((df.get("flag_sin_tercero_identificado", 0) == 1).sum()) if "flag_sin_tercero_identificado" in df.columns else 0},
        {"signal": "Documentos inconsistentes", "count": int((df.get("tiene_inconsistencia_doc", 0) > 0).sum()) if "tiene_inconsistencia_doc" in df.columns else 0},
        {"signal": "Reporte tardío", "count": int((df.get("reporte_tardio", 0) == 1).sum()) if "reporte_tardio" in df.columns else 0},
        {"signal": "Narrativas similares", "count": narrativas_clonadas},
        {"signal": "Monto cercano a suma asegurada", "count": int((df.get("ratio_reclamado_asegurado", 0) > 0.95).sum()) if "ratio_reclamado_asegurado" in df.columns else 0},
        {"signal": "Alertas en PDF cargados", "count": alertas_pdf_count},
    ]

    signal_masks = {
        "Reclamo cercano al borde de vigencia": (df.get("borde_inicio_vigencia", 0) == 1) if "borde_inicio_vigencia" in df.columns else pd.Series([False] * len(df), index=df.index),
        "Demora denuncia por robo": (df.get("demora_denuncia_robo", 0) == 1) if "demora_denuncia_robo" in df.columns else pd.Series([False] * len(df), index=df.index),
        "Alta frecuencia reclamos asegurado": (df.get("frecuencia_siniestros_asegurado", 0) >= 3) if "frecuencia_siniestros_asegurado" in df.columns else pd.Series([False] * len(df), index=df.index),
        "Alta frecuencia reclamos vehículo": (df.get("frecuencia_siniestros_vehiculo", 0) >= 3) if "frecuencia_siniestros_vehiculo" in df.columns else pd.Series([False] * len(df), index=df.index),
        "Alta frecuencia conductor": (df.get("frecuencia_siniestros_conductor", 0) >= 3) if "frecuencia_siniestros_conductor" in df.columns else pd.Series([False] * len(df), index=df.index),
        "Reclamos solo RC": (df.get("frecuencia_solo_rc", 0) > 2) if "frecuencia_solo_rc" in df.columns else pd.Series([False] * len(df), index=df.index),
        "Beneficiario/proveedor recurrente": (df.get("prov_casos_observados", 0) > 2) if "prov_casos_observados" in df.columns else pd.Series([False] * len(df), index=df.index),
        "Documentos incompletos": df.get("documentos_completos", pd.Series([""] * len(df), index=df.index)).astype(str).str.lower().eq("no") if "documentos_completos" in df.columns else pd.Series([False] * len(df), index=df.index),
        "Dinámica sospechosa": (df.get("flag_dinamica_sospechosa", 0) == 1) if "flag_dinamica_sospechosa" in df.columns else pd.Series([False] * len(df), index=df.index),
        "Eventos sin tercero identificado": (df.get("flag_sin_tercero_identificado", 0) == 1) if "flag_sin_tercero_identificado" in df.columns else pd.Series([False] * len(df), index=df.index),
        "Documentos inconsistentes": (df.get("tiene_inconsistencia_doc", 0) > 0) if "tiene_inconsistencia_doc" in df.columns else pd.Series([False] * len(df), index=df.index),
        "Reporte tardío": (df.get("reporte_tardio", 0) == 1) if "reporte_tardio" in df.columns else pd.Series([False] * len(df), index=df.index),
        "Narrativas similares": df.get("alertas_reglas", pd.Series([""] * len(df), index=df.index)).fillna("").astype(str).str.contains("Similitud textual", case=False),
        "Monto cercano a suma asegurada": (df.get("ratio_reclamado_asegurado", 0) > 0.95) if "ratio_reclamado_asegurado" in df.columns else pd.Series([False] * len(df), index=df.index),
        "Alertas en PDF cargados": (
            (df.get("tiene_alerta_pdf", 0) == 1)
            if "tiene_alerta_pdf" in df.columns
            else df.get("alertas_reglas", pd.Series([""] * len(df), index=df.index)).fillna("").astype(str).str.contains("[PDF]", case=False)
        ),
    }
    signal_case_cols = [
        c for c in ["id_siniestro", "ramo", "cobertura", score_col, semaforo_col, "monto_reclamado", "alertas_reglas"]
        if c in df.columns
    ]
    signal_cases_map: Dict[str, List[Dict[str, Any]]] = {}
    for signal_name, mask in signal_masks.items():
        try:
            subset = df.loc[mask, signal_case_cols]
        except Exception:
            subset = df.iloc[0:0][signal_case_cols]
        if score_col in subset.columns:
            subset = subset.sort_values(score_col, ascending=False)
        signal_cases_map[signal_name] = subset.head(50).to_dict("records")

    # Reglas críticas RF-01..RF-07
    critical_counts = {f"RF-0{i}": 0 for i in range(1, 8)}
    if "reglas_criticas" in df.columns:
        for raw in df["reglas_criticas"].fillna("").astype(str):
            codes = [c.strip() for c in raw.split(",") if c.strip()]
            for c in codes:
                if c in critical_counts:
                    critical_counts[c] += 1

    # Heatmap ramo x semáforo
    heatmap = {"ramos": [], "semaforos": ["Verde", "Amarillo", "Rojo"], "z": []}
    if "ramo" in df.columns and semaforo_col in df.columns:
        piv = (
            df.pivot_table(index="ramo", columns=semaforo_col, values="id_siniestro", aggfunc="count", fill_value=0)
            .reindex(columns=["Verde", "Amarillo", "Rojo"], fill_value=0)
        )
        heatmap["ramos"] = piv.index.astype(str).tolist()
        heatmap["z"] = piv.values.tolist()

    geo_data = []
    if "sucursal" in df.columns:
        geo_data = (
            df.groupby("sucursal")
            .agg(casos=("id_siniestro", "count"), monto=("monto_reclamado", "sum"))
            .reset_index()
            .sort_values("casos", ascending=False)
            .to_dict("records")
        )

    geo_risk_data = []
    if "sucursal" in df.columns and semaforo_col in df.columns:
        piv_geo = (
            df.pivot_table(
                index="sucursal",
                columns=semaforo_col,
                values="id_siniestro",
                aggfunc="count",
                fill_value=0,
            )
            .reindex(columns=["Rojo", "Amarillo", "Verde"], fill_value=0)
            .reset_index()
        )
        geo_risk_data = piv_geo.to_dict("records")

    provider_risk = []
    if "beneficiario" in df.columns:
        provider_risk = (
            df.groupby("beneficiario")
            .agg(casos=("id_siniestro", "count"), score_prom=(score_col, "mean"), monto=("monto_reclamado", "sum"))
            .reset_index()
            .sort_values(["score_prom", "casos"], ascending=[False, False])
            .head(10)
            .round(2)
            .to_dict("records")
        )

    return {
        "semaforo": semaforo_counts,
        "total": len(df),
        "total_unfiltered": total_unfiltered,
        "source_total_siniestros": source_total,
        "analysis_complete": len(df) >= source_total if source_total else True,
        "score_promedio": round(df[score_col].mean(), 1) if score_col in df.columns else 0,
        "monto_total": monto_total,
        "monto_rojo": monto_rojo,
        "ramo_data": ramo_data,
        "top_cases": top_cases,
        "score_distribution": score_distribution,
        "temporal_data": temporal_data,
        "active_filters": active_filters,
        "filtered": len(active_filters) > 0,
        "rojos": rojos,
        "executive_kpis": {
            "casos_sospechosos": casos_sospechosos,
            "riesgo_alto": rojos,
            "riesgo_medio": amarillos,
            "riesgo_bajo": verdes,
            "prob_fraude_promedio": prob_fraude_prom,
            "monto_potencial_riesgo": monto_potencial_riesgo,
            "casos_escalados": casos_escalados,
            "casos_observados": casos_observados,
            "proveedores_sospechosos": proveedores_sospechosos,
            "narrativas_clonadas": narrativas_clonadas,
        },
        "signals_summary": signal_counts,
        "signal_cases_map": signal_cases_map,
        "critical_rules_summary": critical_counts,
        "heatmap_ramo_riesgo": heatmap,
        "geo_data": geo_data,
        "provider_risk": provider_risk,
        "temporal_risk_data": temporal_risk_data,
        "geo_risk_data": geo_risk_data,
    }
