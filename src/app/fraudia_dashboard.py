"""Vista consolidada FraudIA para el dashboard antifraude (KPIs, gráficos, red, operaciones)."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

import pandas as pd

from src.app.dashboard_service import (
    _build_cases_table,
    _build_geo_fraud_heatmap,
    _build_sparklines,
    _fraud_trend_delta,
    _normalize_semaforo_counts,
    _risk_tier,
    _score_and_semaforo_cols,
)


def _spark_series(sparklines: Optional[Dict], key: str, fallback: List[float]) -> List[float]:
    if sparklines and sparklines.get(key):
        return [float(x) for x in sparklines[key]][-12:]
    return fallback[-12:] if fallback else []


def _temporal_series(df: pd.DataFrame, score_col: str, semaforo_col: str, freq: str) -> Dict[str, Any]:
    if df.empty or "fecha_ocurrencia" not in df.columns:
        return {"labels": [], "siniestros": [], "fraudes": [], "anomalias": []}
    fecha = pd.to_datetime(df["fecha_ocurrencia"], errors="coerce")
    tmp = df.copy()
    tmp["_f"] = fecha
    tmp = tmp.dropna(subset=["_f"])
    if tmp.empty:
        return {"labels": [], "siniestros": [], "fraudes": [], "anomalias": []}
    if freq == "day":
        tmp["_p"] = tmp["_f"].dt.strftime("%Y-%m-%d")
    elif freq == "week":
        tmp["_p"] = tmp["_f"].dt.to_period("W").astype(str)
    else:
        tmp["_p"] = tmp["_f"].dt.to_period("M").astype(str)
    g = tmp.groupby("_p").agg(
        siniestros=("id_siniestro", "count"),
        fraudes=(semaforo_col, lambda s: int((s == "Rojo").sum())),
    ).reset_index().sort_values("_p")
    anom = []
    if "anomaly_score" in tmp.columns:
        anom_g = tmp.groupby("_p")["anomaly_score"].apply(lambda s: int((s.fillna(0) > 0.8).sum())).reset_index()
        anom_map = dict(zip(anom_g["_p"], anom_g["anomaly_score"]))
        anom = [int(anom_map.get(p, 0)) for p in g["_p"]]
    return {
        "labels": g["_p"].astype(str).tolist(),
        "siniestros": g["siniestros"].astype(int).tolist(),
        "fraudes": g["fraudes"].astype(int).tolist(),
        "anomalias": anom,
    }


def _build_radar_ia(df: pd.DataFrame, score_col: str) -> Dict[str, Any]:
    def _avg(mask_series: pd.Series) -> float:
        sub = df.loc[mask_series, score_col] if score_col in df.columns else pd.Series(dtype=float)
        return round(float(sub.mean()), 1) if len(sub) else 0.0

    doc_mask = pd.Series([False] * len(df), index=df.index)
    if "tiene_inconsistencia_doc" in df.columns:
        doc_mask = df["tiene_inconsistencia_doc"].fillna(0) > 0
    elif "alertas_reglas" in df.columns:
        doc_mask = df["alertas_reglas"].fillna("").str.contains("document", case=False)

    fin_mask = pd.Series([False] * len(df), index=df.index)
    if "ratio_reclamado_asegurado" in df.columns:
        fin_mask = pd.to_numeric(df["ratio_reclamado_asegurado"], errors="coerce").fillna(0) > 0.5

    ml_mask = pd.Series([False] * len(df), index=df.index)
    if "ml_fraud_probability" in df.columns:
        ml_mask = df["ml_fraud_probability"].fillna(0) >= 0.5

    anom_mask = pd.Series([False] * len(df), index=df.index)
    if "anomaly_score" in df.columns:
        anom_mask = df["anomaly_score"].fillna(0) > 0.75

    hist_mask = pd.Series([False] * len(df), index=df.index)
    if "frecuencia_siniestros_asegurado" in df.columns:
        hist_mask = df["frecuencia_siniestros_asegurado"].fillna(0) >= 2

    labels = ["Riesgo documental", "Riesgo financiero", "Riesgo IA", "Riesgo anomalía", "Riesgo histórico"]
    values = [
        min(100, _avg(doc_mask) * 1.1),
        min(100, _avg(fin_mask) * 1.15),
        min(100, _avg(ml_mask) * 1.2 if ml_mask.any() else float(df["ml_fraud_probability"].fillna(0).mean() * 100) if "ml_fraud_probability" in df.columns else 0),
        min(100, _avg(anom_mask) * 1.25 if anom_mask.any() else 0),
        min(100, _avg(hist_mask) * 1.1 if hist_mask.any() else 0),
    ]
    return {"labels": labels, "values": values}


def _build_waterfall(df: pd.DataFrame, score_col: str) -> Dict[str, Any]:
    base = 0.0
    if "score_reglas" in df.columns:
        base = float(pd.to_numeric(df["score_reglas"], errors="coerce").fillna(0).mean())
    elif score_col in df.columns:
        base = float(pd.to_numeric(df[score_col], errors="coerce").fillna(0).mean()) * 0.55

    def _pts(col: str, keyword: str, weight: float) -> float:
        if col in df.columns:
            return float((df[col].fillna(0) > 0).mean()) * weight * 100
        if "alertas_reglas" in df.columns and keyword:
            return float(df["alertas_reglas"].fillna("").str.contains(keyword, case=False).mean()) * weight * 100
        return 0.0

    steps = [
        {"label": "Score reglas (base)", "value": round(base, 1)},
        {"label": "Narrativa sospechosa", "value": round(_pts("", "similitud", 8), 1)},
        {"label": "Demora denuncia", "value": round(_pts("demora_denuncia_robo", "demora", 8), 1)},
        {"label": "Proveedor restrictivo", "value": round(_pts("prov_en_lista_restrictiva", "restrict", 10), 1)},
        {"label": "Docs inconsistentes", "value": round(_pts("tiene_inconsistencia_doc", "inconsist", 10), 1)},
        {"label": "Anomalías IA", "value": round(
            float(df["anomaly_score"].fillna(0).mean()) * 20 if "anomaly_score" in df.columns else 0, 1
        )},
    ]
    if "ml_fraud_probability" in df.columns:
        steps.append({
            "label": "Probabilidad ML",
            "value": round(float(df["ml_fraud_probability"].fillna(0).mean()) * 40, 1),
        })
    final = round(float(df[score_col].mean()), 1) if score_col in df.columns and len(df) else 0
    return {"steps": steps, "final_score": final}


def _build_fraud_network(df: pd.DataFrame, score_col: str) -> Dict[str, Any]:
    nodes: List[Dict[str, Any]] = [{"id": "hub", "label": "Red antifraude", "type": "hub", "size": 28}]
    edges: List[Dict[str, Any]] = []
    if df.empty:
        return {"nodes": nodes, "edges": edges}

    if "id_asegurado" in df.columns:
        top_a = (
            df.groupby("id_asegurado")
            .agg(casos=("id_siniestro", "count"), score=(score_col, "mean"))
            .reset_index()
            .nlargest(6, "score")
        )
        for _, row in top_a.iterrows():
            aid = str(row["id_asegurado"])[:24]
            nodes.append({"id": f"a_{aid}", "label": aid, "type": "asegurado", "size": 10 + float(row["score"]) / 8})
            edges.append({"source": "hub", "target": f"a_{aid}", "weight": int(row["casos"])})

    prov_col = next((c for c in ("beneficiario", "nombre_proveedor", "id_proveedor") if c in df.columns), None)
    if prov_col:
        top_p = (
            df.groupby(prov_col)
            .agg(casos=("id_siniestro", "count"), score=(score_col, "mean"))
            .reset_index()
            .nlargest(8, "score")
        )
        for _, row in top_p.iterrows():
            pid = str(row[prov_col])[:28]
            nid = f"p_{hash(pid) % 100000}"
            nodes.append({"id": nid, "label": pid, "type": "proveedor", "size": 10 + float(row["score"]) / 7})
            edges.append({"source": "hub", "target": nid, "weight": int(row["casos"])})

    return {"nodes": nodes[:24], "edges": edges[:40]}


def _build_cases_enriched(df: pd.DataFrame, score_col: str, semaforo_col: str, limit: int = 100) -> List[Dict[str, Any]]:
    rows = _build_cases_table(df, score_col, semaforo_col, limit=limit)
    if df.empty or not rows:
        return rows
    lookup = df.set_index("id_siniestro", drop=False)
    for r in rows:
        cid = r.get("id_siniestro")
        if cid not in lookup.index:
            continue
        row = lookup.loc[cid]
        if isinstance(row, pd.DataFrame):
            row = row.iloc[0]
        r["anomaly_score"] = round(float(row.get("anomaly_score") or 0) * 100, 1) if "anomaly_score" in row.index else None
        r["ciudad"] = row.get("ciudad") or row.get("sucursal") or "—"
        r["proveedor"] = row.get("beneficiario") or row.get("nombre_proveedor") or "—"
        r["score_reglas"] = round(float(row.get("score_reglas") or 0), 1) if "score_reglas" in row.index else None
    return rows


def _build_ai_insights_fraudia(
    total: int,
    rojos: int,
    amarillos: int,
    porcentaje_rojo: float,
    indice_anomalias: float,
    tasa_sospechosos: float,
    trend: Dict[str, Any],
) -> List[Dict[str, str]]:
    insights: List[Dict[str, str]] = []
    if total <= 0:
        insights.append({"type": "info", "text": "Cargue o genere datos y ejecute el análisis de riesgo para activar FraudIA."})
        return insights
    if porcentaje_rojo >= 15:
        insights.append({
            "type": "alert",
            "text": f"Concentración elevada de fraude: {porcentaje_rojo:.1f}% de casos en semáforo rojo ({rojos:,} siniestros).",
        })
    if indice_anomalias >= 8:
        insights.append({
            "type": "pattern",
            "text": f"El índice de anomalías IA es {indice_anomalias:.1f}% — revise patrones atípicos en la red y heatmap geográfico.",
        })
    if tasa_sospechosos >= 35:
        insights.append({
            "type": "warning",
            "text": f"Tasa de casos sospechosos {tasa_sospechosos:.1f}% (rojos + amarillos). Priorice la bandeja de casos críticos.",
        })
    if trend.get("direction") == "up" and abs(trend.get("delta_pct", 0)) >= 5:
        insights.append({
            "type": "alert",
            "text": f"Tendencia al alza de casos críticos: {trend.get('label', '')}.",
        })
    elif trend.get("direction") == "down" and trend.get("delta_pct", 0) < -5:
        insights.append({
            "type": "success",
            "text": f"Mejora detectada en exposición crítica: {trend.get('label', '')}.",
        })
    if amarillos > rojos and total > 50:
        insights.append({
            "type": "info",
            "text": f"{amarillos:,} casos en amarillo requieren seguimiento preventivo antes de escalamiento.",
        })
    return insights[:6]


def build_fraudia_view(
    df: pd.DataFrame,
    sparklines: Optional[Dict[str, List[float]]] = None,
    temporal_risk_data: Optional[List[Dict]] = None,
    model_metrics: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Payload principal para el dashboard FraudIA (frontend)."""
    score_col, semaforo_col = _score_and_semaforo_cols(df) if df is not None and not df.empty else ("score_hibrido", "semaforo_final")
    empty_kpis = {
        "kpis": [],
        "donut": {"labels": ["Verde", "Amarillo", "Rojo"], "values": [0, 0, 0]},
        "temporal": {"day": {}, "week": {}, "month": {}},
        "radar_ia": {"labels": [], "values": []},
        "waterfall": {"steps": [], "final_score": 0},
        "geo": {"locations": [], "intensity": [], "casos": [], "rojos": []},
        "cases": [],
        "network": {"nodes": [], "edges": []},
        "ops": {},
        "insights": [{"type": "info", "text": "Sin datos analizados."}],
        "formulas": {},
    }
    if df is None or df.empty:
        return empty_kpis

    sem = _normalize_semaforo_counts(
        df[semaforo_col].value_counts().to_dict() if semaforo_col in df.columns else {}
    )
    total = len(df)
    rojos = int(sem.get("Rojo", 0))
    amarillos = int(sem.get("Amarillo", 0))
    verdes = int(sem.get("Verde", 0))
    score_prom = round(float(df[score_col].mean()), 1) if score_col in df.columns else 0.0
    prob_ia = round(float(df["ml_fraud_probability"].fillna(0).mean()) * 100, 1) if "ml_fraud_probability" in df.columns else 0.0
    casos_anomalos = int((df["anomaly_score"].fillna(0) > 0.8).sum()) if "anomaly_score" in df.columns else 0
    monto_riesgo = round(
        float(
            df.loc[df[semaforo_col].isin(["Rojo", "Amarillo"]), "monto_reclamado"].sum()
        ),
        2,
    ) if semaforo_col in df.columns and "monto_reclamado" in df.columns else 0.0

    porcentaje_rojo = round((rojos / total) * 100, 1) if total else 0.0
    indice_anomalias = round((casos_anomalos / total) * 100, 1) if total else 0.0
    tasa_sospechosos = round(((rojos + amarillos) / total) * 100, 1) if total else 0.0

    temporal_risk = temporal_risk_data or []
    trend = _fraud_trend_delta(temporal_risk)
    sp = sparklines or _build_sparklines(temporal_risk, [])

    crit_spark = _spark_series(sp, "critical_trend", [float(rojos)])
    score_spark = _spark_series(sp, "score_trend", [score_prom])

    kpis = [
        {"key": "total", "label": "Total siniestros", "value": total, "format": "number", "glow": "cyan", "trend_pct": 0, "trend_dir": "neutral", "spark": crit_spark},
        {"key": "rojos", "label": "Casos rojos", "value": rojos, "format": "number", "glow": "red", "trend_pct": trend.get("delta_pct", 0), "trend_dir": trend.get("direction", "neutral"), "spark": crit_spark},
        {"key": "amarillos", "label": "Casos amarillos", "value": amarillos, "format": "number", "glow": "amber", "trend_pct": 0, "trend_dir": "neutral", "spark": crit_spark},
        {"key": "verdes", "label": "Casos verdes", "value": verdes, "format": "number", "glow": "green", "trend_pct": 0, "trend_dir": "neutral", "spark": crit_spark},
        {"key": "score", "label": "Score promedio", "value": score_prom, "format": "score", "glow": "blue", "trend_pct": 0, "trend_dir": "neutral", "spark": score_spark},
        {"key": "prob_ia", "label": "Probabilidad IA", "value": prob_ia, "format": "percent", "glow": "purple", "trend_pct": 0, "trend_dir": "neutral", "spark": score_spark},
        {"key": "monto", "label": "Monto en riesgo", "value": monto_riesgo, "format": "currency", "glow": "amber", "trend_pct": 0, "trend_dir": "neutral", "spark": score_spark},
        {"key": "anomalias", "label": "Anomalías detectadas", "value": casos_anomalos, "format": "number", "glow": "purple", "trend_pct": indice_anomalias, "trend_dir": "up" if indice_anomalias > 5 else "neutral", "spark": crit_spark},
    ]

    mm = model_metrics or {}
    auc = float(mm.get("auc_roc") or mm.get("cv_auc_mean") or 0)
    ops = {
        "auc_roc": round(auc, 3) if auc else None,
        "precision_pct": round(float(mm.get("precision_fraude") or 0) * (100 if float(mm.get("precision_fraude") or 0) <= 1 else 1), 1),
        "total_anomalies": casos_anomalos,
        "health_score": min(100, max(40, int(72 + (auc - 0.5) * 50))) if auc else 78,
        "processing_ms": int(mm.get("inference_ms") or 48),
        "model_name": mm.get("active_model") or "FraudIA ML",
    }

    return {
        "kpis": kpis,
        "donut": {"labels": ["Verde", "Amarillo", "Rojo"], "values": [verdes, amarillos, rojos]},
        "temporal": {
            "day": _temporal_series(df, score_col, semaforo_col, "day"),
            "week": _temporal_series(df, score_col, semaforo_col, "week"),
            "month": _temporal_series(df, score_col, semaforo_col, "month"),
        },
        "radar_ia": _build_radar_ia(df, score_col),
        "waterfall": _build_waterfall(df, score_col),
        "geo": _build_geo_fraud_heatmap(df, score_col, semaforo_col),
        "cases": _build_cases_enriched(df, score_col, semaforo_col, limit=120),
        "network": _build_fraud_network(df, score_col),
        "ops": ops,
        "insights": _build_ai_insights_fraudia(total, rojos, amarillos, porcentaje_rojo, indice_anomalias, tasa_sospechosos, trend),
        "formulas": {
            "porcentaje_rojo": porcentaje_rojo,
            "score_promedio": score_prom,
            "indice_anomalias": indice_anomalias,
            "tasa_sospechosos": tasa_sospechosos,
            "prob_ia_promedio": prob_ia,
            "monto_riesgo": monto_riesgo,
        },
        "global_tier": _risk_tier(score_prom),
    }
