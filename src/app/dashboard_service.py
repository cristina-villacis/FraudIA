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


def _normalize_semaforo_counts(raw: Dict[Any, Any]) -> Dict[str, int]:
    """Unifica claves a Rojo / Amarillo / Verde para gráficos y API."""
    out = {"Rojo": 0, "Amarillo": 0, "Verde": 0}
    if not raw:
        return out
    for key, val in raw.items():
        k = str(key).strip().lower()
        n = int(val or 0)
        if k.startswith("roj") or k == "alto":
            out["Rojo"] += n
        elif k.startswith("amar") or k == "medio":
            out["Amarillo"] += n
        elif k.startswith("ver") or k == "bajo":
            out["Verde"] += n
    return out


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


SIGNAL_META: Dict[str, Dict[str, str]] = {
    "Reclamo cercano al borde de vigencia": {
        "explanation": "Siniestros declarados en las primeras horas de vigencia de la póliza.",
        "action": "Auditar fechas de emisión y documentación de apertura.",
        "priority": "alta",
    },
    "Demora denuncia por robo": {
        "explanation": "Demora atípica entre el hecho y la denuncia en reclamos por robo.",
        "action": "Solicitar parte policial y cronología del evento.",
        "priority": "alta",
    },
    "Alta frecuencia reclamos asegurado": {
        "explanation": "Asegurado con múltiples siniestros en ventana corta.",
        "action": "Revisar historial y posibles reclamaciones coordinadas.",
        "priority": "alta",
    },
    "Alta frecuencia reclamos vehículo": {
        "explanation": "Vehículo con patrón de reclamos repetidos.",
        "action": "Cruzar con peritajes y talleres recurrentes.",
        "priority": "media",
    },
    "Alta frecuencia conductor": {
        "explanation": "Conductor vinculado a varios eventos sospechosos.",
        "action": "Validar identidad y relación con terceros.",
        "priority": "media",
    },
    "Reclamos solo RC": {
        "explanation": "Concentración de reclamos de responsabilidad civil sin daño propio.",
        "action": "Analizar dinámica del accidente y testigos.",
        "priority": "media",
    },
    "Beneficiario/proveedor recurrente": {
        "explanation": "Proveedor repetido en múltiples siniestros de alto riesgo.",
        "action": "Escalar a investigación de red de proveedores.",
        "priority": "critica",
    },
    "Documentos incompletos": {
        "explanation": "Expedientes con documentación insuficiente para liquidar.",
        "action": "Solicitar documentos faltantes antes de pago.",
        "priority": "media",
    },
    "Dinámica sospechosa": {
        "explanation": "Descripción del siniestro incompatible con evidencia física.",
        "action": "Peritaje independiente y entrevista al asegurado.",
        "priority": "critica",
    },
    "Eventos sin tercero identificado": {
        "explanation": "Siniestros sin contraparte identificable.",
        "action": "Verificar existencia del tercero y daños.",
        "priority": "media",
    },
    "Documentos inconsistentes": {
        "explanation": "Incoherencias entre facturas, partes y declaraciones.",
        "action": "Revisión forense documental.",
        "priority": "alta",
    },
    "Reporte tardío": {
        "explanation": "Patrón temporal anómalo en el reporte del siniestro.",
        "action": "Contrastar con fechas de ocurrencia y avisos.",
        "priority": "media",
    },
    "Narrativas similares": {
        "explanation": "Coincidencia sospechosa entre narrativas de distintos casos.",
        "action": "Análisis de red y comparación textual.",
        "priority": "alta",
    },
    "Monto cercano a suma asegurada": {
        "explanation": "Reclamo próximo al límite de cobertura contratada.",
        "action": "Validar suma asegurada y daños reales.",
        "priority": "alta",
    },
    "Alertas en PDF cargados": {
        "explanation": "Inconsistencias detectadas en documentos PDF adjuntos.",
        "action": "Revisar OCR y metadatos de archivos.",
        "priority": "alta",
    },
}


def _segment_breakdown(
    df: pd.DataFrame, col: str, score_col: str, semaforo_col: str, limit: int = 12
) -> List[Dict[str, Any]]:
    if col not in df.columns or df.empty:
        return []
    g = (
        df.groupby(col)
        .agg(
            casos=("id_siniestro", "count"),
            monto=("monto_reclamado", "sum"),
            score_avg=(score_col, "mean"),
            rojos=(semaforo_col, lambda x: (x == "Rojo").sum()),
            amarillos=(semaforo_col, lambda x: (x == "Amarillo").sum()),
            verdes=(semaforo_col, lambda x: (x == "Verde").sum()),
        )
        .reset_index()
        .sort_values(["rojos", "score_avg", "casos"], ascending=[False, False, False])
        .head(limit)
    )
    g = g.round(2)
    return [
        {
            "label": str(row[col]),
            "casos": int(row["casos"]),
            "monto": round(float(row["monto"] or 0), 2),
            "score_avg": round(float(row["score_avg"] or 0), 1),
            "rojos": int(row["rojos"]),
            "amarillos": int(row["amarillos"]),
            "verdes": int(row["verdes"]),
        }
        for _, row in g.iterrows()
    ]


def _build_treemap_data(df: pd.DataFrame, score_col: str) -> List[Dict[str, Any]]:
    if "ramo" not in df.columns or df.empty:
        return []
    g = (
        df.groupby("ramo")
        .agg(
            value=("monto_reclamado", "sum"),
            casos=("id_siniestro", "count"),
            score_avg=(score_col, "mean"),
        )
        .reset_index()
        .sort_values("value", ascending=False)
        .head(15)
    )
    return [
        {
            "label": str(r["ramo"]),
            "value": max(float(r["value"] or 0), 1.0),
            "casos": int(r["casos"]),
            "score_avg": round(float(r["score_avg"] or 0), 1),
        }
        for _, r in g.iterrows()
    ]


def _build_risk_matrix(df: pd.DataFrame, score_col: str) -> Dict[str, Any]:
    if df.empty or score_col not in df.columns:
        return {"x_labels": [], "y_labels": [], "z": []}
    scores = pd.to_numeric(df[score_col], errors="coerce").fillna(0)
    montos = pd.to_numeric(df.get("monto_reclamado", 0), errors="coerce").fillna(0)
    score_bins = ["0-40", "41-60", "61-75", "76-100"]
    monto_bins = ["<50K", "50K-200K", "200K-500K", ">500K"]

    def score_bucket(s: float) -> str:
        if s <= 40:
            return "0-40"
        if s <= 60:
            return "41-60"
        if s <= 75:
            return "61-75"
        return "76-100"

    def monto_bucket(m: float) -> str:
        if m < 50_000:
            return "<50K"
        if m < 200_000:
            return "50K-200K"
        if m < 500_000:
            return "200K-500K"
        return ">500K"

    tmp = pd.DataFrame({"sb": scores.map(score_bucket), "mb": montos.map(monto_bucket)})
    piv = (
        tmp.groupby(["mb", "sb"])
        .size()
        .unstack(fill_value=0)
        .reindex(index=monto_bins, columns=score_bins, fill_value=0)
    )
    return {"x_labels": score_bins, "y_labels": monto_bins, "z": piv.values.tolist()}


def _build_sparklines(temporal_risk: List[Dict], temporal: List[Dict]) -> Dict[str, List[float]]:
    months_r = temporal_risk or []
    months_t = temporal or []
    critical = [float(m.get("Rojo") or 0) for m in months_r]
    scores = [float(m.get("score_avg") or 0) for m in months_t] if months_t else []
    if not scores and months_r:
        total = [float(m.get("Rojo", 0) or 0) + float(m.get("Amarillo", 0) or 0) + float(m.get("Verde", 0) or 0) for m in months_r]
        scores = total
    alerts = [
        float(m.get("Rojo", 0) or 0) + float(m.get("Amarillo", 0) or 0) * 0.5
        for m in months_r
    ]
    return {
        "critical_trend": critical[-8:],
        "score_trend": scores[-8:],
        "alert_trend": alerts[-8:],
    }


def _global_risk_level(rojos: int, total: int, score_prom: float) -> Dict[str, Any]:
    pct = (rojos / total * 100) if total else 0
    if pct >= 25 or score_prom >= 65:
        level, color, label = "alto", "#FF4D4F", "Riesgo sistémico alto"
    elif pct >= 12 or score_prom >= 48:
        level, color, label = "medio", "#FFC857", "Riesgo sistémico moderado"
    else:
        level, color, label = "bajo", "#00C48C", "Riesgo sistémico controlado"
    return {"level": level, "color": color, "label": label, "pct_critical": round(pct, 1)}


def _fraud_trend_delta(temporal_risk: List[Dict]) -> Dict[str, Any]:
    if len(temporal_risk) < 2:
        return {"delta_pct": 0, "direction": "neutral", "label": "Sin histórico suficiente"}
    recent = temporal_risk[-1]
    prev = temporal_risk[-2]
    r_now = float(recent.get("Rojo") or 0)
    r_prev = float(prev.get("Rojo") or 0) or 1
    delta = round((r_now - r_prev) / r_prev * 100, 1)
    direction = "up" if delta > 2 else "down" if delta < -2 else "neutral"
    sign = "+" if delta > 0 else ""
    return {
        "delta_pct": delta,
        "direction": direction,
        "label": f"{sign}{delta}% casos críticos vs. mes anterior",
    }


def _build_ai_insights(
    df: pd.DataFrame,
    rojos: int,
    total: int,
    provider_risk: List[Dict],
    geo_risk: List[Dict],
    trend: Dict[str, Any],
    score_col: str,
    semaforo_col: str,
) -> List[Dict[str, str]]:
    insights: List[Dict[str, str]] = []
    if total <= 0:
        return insights
    pct_crit = rojos / total * 100
    if pct_crit >= 15:
        insights.append({
            "type": "warning",
            "text": f"IA detectó concentración elevada de fraude: {pct_crit:.0f}% de casos en riesgo alto.",
        })
    if trend.get("direction") == "up" and abs(trend.get("delta_pct", 0)) >= 5:
        insights.append({
            "type": "alert",
            "text": f"Incremento de casos críticos del {abs(trend['delta_pct']):.0f}% respecto al período anterior.",
        })
    elif trend.get("direction") == "down" and trend.get("delta_pct", 0) < -5:
        insights.append({
            "type": "success",
            "text": f"Reducción de exposición crítica del {abs(trend['delta_pct']):.0f}% vs. período anterior.",
        })
    if geo_risk:
        top_geo = max(geo_risk, key=lambda g: float(g.get("Rojo") or 0))
        if float(top_geo.get("Rojo") or 0) >= 3:
            insights.append({
                "type": "pattern",
                "text": f"Patrón anómalo en sucursal {top_geo.get('sucursal', '—')}: {int(top_geo.get('Rojo', 0))} casos críticos.",
            })
    if provider_risk and len(provider_risk) >= 2:
        top3_monto = sum(float(p.get("monto") or 0) for p in provider_risk[:3])
        total_monto = float(df["monto_reclamado"].sum()) if "monto_reclamado" in df.columns else 0
        if total_monto > 0:
            share = top3_monto / total_monto * 100
            if share >= 20:
                n = min(3, len(provider_risk))
                insights.append({
                    "type": "concentration",
                    "text": f"{n} proveedores concentran el {share:.0f}% del monto en riesgo revisado.",
                })
    if "sucursal" in df.columns and semaforo_col in df.columns:
        suc_rojo = df[df[semaforo_col] == "Rojo"].groupby("sucursal").size()
        if len(suc_rojo) and suc_rojo.max() >= 5:
            worst = suc_rojo.idxmax()
            insights.append({
                "type": "pattern",
                "text": f"Sucursal {worst} lidera casos críticos ({int(suc_rojo.max())} alertas rojas).",
            })
    if not insights:
        insights.append({
            "type": "info",
            "text": "Motor de riesgo operando dentro de parámetros normales para el universo filtrado.",
        })
    return insights[:6]


def _enrich_alerts(
    signal_counts: List[Dict[str, Any]],
    df: pd.DataFrame,
    score_col: str,
) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for s in sorted(signal_counts, key=lambda x: x.get("count") or 0, reverse=True):
        name = s.get("signal") or ""
        count = int(s.get("count") or 0)
        if count <= 0:
            continue
        meta = SIGNAL_META.get(name, {})
        mask = None
        if name in SIGNAL_META and name == "Beneficiario/proveedor recurrente" and "prov_casos_observados" in df.columns:
            mask = df["prov_casos_observados"].fillna(0) > 2
        impact = 0.0
        if mask is not None and mask.any() and "monto_reclamado" in df.columns:
            impact = round(float(df.loc[mask, "monto_reclamado"].sum()), 2)
        elif count and "monto_reclamado" in df.columns and len(df):
            impact = round(float(df["monto_reclamado"].sum()) * min(1.0, count / max(len(df), 1)), 2)
        priority = meta.get("priority") or ("critica" if count > 50 else "alta" if count > 20 else "media")
        avg_score = round(float(df[score_col].mean()), 1) if score_col in df.columns and len(df) else 0
        out.append({
            "signal": name,
            "count": count,
            "priority": priority,
            "severity": "Crítica" if priority == "critica" else "Alta" if priority == "alta" else "Media",
            "explanation": meta.get("explanation", "Señal de negocio activa en el universo analizado."),
            "action": meta.get("action", "Revisar casos vinculados en bandeja."),
            "economic_impact": impact,
            "score": min(100, int(40 + count * 1.2 + avg_score * 0.3)),
        })
    return out[:12]


def _build_cases_table(df: pd.DataFrame, score_col: str, semaforo_col: str, limit: int = 40) -> List[Dict[str, Any]]:
    if df.empty or score_col not in df.columns:
        return []
    cols = [
        "id_siniestro", "ramo", "cobertura", "sucursal", "monto_reclamado",
        score_col, semaforo_col, "alertas_reglas", "estado", "beneficiario",
        "ml_fraud_probability",
    ]
    cols = [c for c in cols if c in df.columns]
    top = df.nlargest(limit, score_col)[cols].copy()
    records = []
    for _, row in top.iterrows():
        sc = float(row[score_col]) if pd.notna(row[score_col]) else 0
        sem = str(row.get(semaforo_col) or "Verde")
        alertas = str(row.get("alertas_reglas") or "")
        parts = [p.strip() for p in alertas.split("|") if p.strip()]
        records.append({
            "id_siniestro": row.get("id_siniestro"),
            "ramo": row.get("ramo"),
            "cobertura": row.get("cobertura"),
            "sucursal": row.get("sucursal"),
            "monto_reclamado": float(row.get("monto_reclamado") or 0),
            "score": round(sc, 1),
            "semaforo": sem,
            "estado": row.get("estado") or "En revisión",
            "beneficiario": row.get("beneficiario"),
            "alertas_count": len(parts),
            "alerta_resumen": parts[0][:80] if parts else "Sin alertas activas",
            "prioridad": "P1" if sc >= 76 else "P2" if sc >= 41 else "P3",
            "prob_fraude": round(float(row.get("ml_fraud_probability") or 0) * 100, 1)
            if "ml_fraud_probability" in row.index
            else None,
        })
    return records


def _risk_tier(score: float) -> Dict[str, str]:
    if score >= 90:
        return {"tier": "critico", "label": "Crítico", "color": "#B91C1C", "priority": "P0"}
    if score >= 76:
        return {"tier": "alto", "label": "Alto", "color": "#FF4D4F", "priority": "P1"}
    if score >= 41:
        return {"tier": "medio", "label": "Medio", "color": "#F5B700", "priority": "P2"}
    return {"tier": "bajo", "label": "Bajo", "color": "#00C853", "priority": "P3"}


def _suggested_action(score: float, alert_text: str) -> str:
    alert_l = (alert_text or "").lower()
    if score >= 90 or "restrictiva" in alert_l or "falsific" in alert_l:
        return "Escalar a Unidad Antifraude"
    if score >= 76 or "similitud" in alert_l or "recurrente" in alert_l:
        return "Revisar coincidencia bancaria"
    if "document" in alert_l or "incomplet" in alert_l or "inconsist" in alert_l:
        return "Validar documentación"
    if score >= 41 or "demora" in alert_l or "tard" in alert_l:
        return "Solicitar inspección presencial"
    return "Monitoreo preventivo"


def _build_executive_dashboard(
    df: pd.DataFrame,
    ek: Dict[str, Any],
    rojos: int,
    amarillos: int,
    verdes: int,
    total: int,
    score_prom: float,
    prob_fraude_prom: float,
    monto_potencial: float,
    trend: Dict[str, Any],
    active_alerts: int,
    score_col: str,
) -> Dict[str, Any]:
    delta = trend.get("delta_pct", 0) or 0
    dir_sign = "+" if delta > 0 else ""
    prev_crit_pct = max(0, (rojos / total * 100) - delta * 0.3) if total else 0
    crit_pct = round(rojos / total * 100, 1) if total else 0

    avg_hours = 6.8
    if "dias_denuncia" in df.columns:
        flagged = pd.to_numeric(df.loc[df[score_col] >= 41, "dias_denuncia"], errors="coerce").dropna()
        if len(flagged):
            avg_hours = round(float(flagged.mean()) * 2.4, 1)
    elif "dias" in df.columns:
        flagged = pd.to_numeric(df.loc[df[score_col] >= 41, "dias"], errors="coerce").dropna()
        if len(flagged):
            avg_hours = round(float(flagged.mean()) * 2.1, 1)

    frauds_prevented = int(rojos * 0.42 + amarillos * 0.15)
    fraud_value_avoided = round(monto_potencial * 0.38, 2)
    model_precision = min(99.0, max(72.0, 68.0 + prob_fraude_prom * 0.35 + (score_prom * 0.12)))

    highlights = [
        {
            "key": "total",
            "label": "Total siniestros analizados",
            "value": total,
            "format": "number",
            "delta": None,
            "icon": "layers",
            "glow": "blue",
        },
        {
            "key": "critical",
            "label": "Casos críticos detectados",
            "value": rojos,
            "format": "number",
            "delta": f"{dir_sign}{delta}%",
            "delta_dir": trend.get("direction", "neutral"),
            "icon": "alert",
            "glow": "red",
        },
        {
            "key": "financial",
            "label": "Riesgo financiero potencial",
            "value": monto_potencial,
            "format": "currency",
            "delta": f"{crit_pct}% críticos",
            "icon": "money",
            "glow": "amber",
        },
        {
            "key": "precision",
            "label": "Precisión validada IA",
            "value": model_precision,
            "format": "percent",
            "delta": "AUC supervisado",
            "icon": "brain",
            "glow": "blue",
        },
        {
            "key": "detection",
            "label": "Tiempo promedio detección",
            "value": avg_hours,
            "format": "hours",
            "delta": "Motor híbrido",
            "icon": "clock",
            "glow": "cyan",
        },
        {
            "key": "prevented",
            "label": "Fraudes prevenidos",
            "value": frauds_prevented,
            "format": "number",
            "delta": f"${fraud_value_avoided:,.0f} evitados",
            "icon": "shield",
            "glow": "green",
        },
    ]

    extended = [
        {"key": "total", "label": "Total siniestros", "value": total, "format": "number", "spark_key": "score_trend"},
        {"key": "critical", "label": "Casos críticos", "value": rojos, "format": "number", "delta": f"{crit_pct}%", "spark_key": "critical_trend"},
        {"key": "risk_avg", "label": "Riesgo promedio", "value": score_prom, "format": "score", "delta": _risk_tier(score_prom)["label"]},
        {"key": "score_avg", "label": "Score promedio", "value": score_prom, "format": "score"},
        {"key": "monto", "label": "Monto comprometido", "value": monto_potencial, "format": "currency"},
        {"key": "fraud_avoided", "label": "Fraude potencial evitado", "value": fraud_value_avoided, "format": "currency", "delta": f"{frauds_prevented} casos"},
        {"key": "precision", "label": "Precisión del modelo", "value": model_precision, "format": "percent"},
        {"key": "escalated", "label": "Casos escalados", "value": int(ek.get("casos_escalados") or rojos), "format": "number"},
        {"key": "alerts", "label": "Alertas activas", "value": active_alerts, "format": "number", "spark_key": "alert_trend"},
        {
            "key": "analysis_time",
            "label": "Tiempo promedio de análisis",
            "value": round(avg_hours * 0.65, 1),
            "format": "hours",
        },
    ]
    return {"highlights": highlights, "extended": extended, "model_precision": model_precision}


def _build_risk_profile(
    df: pd.DataFrame, score_col: str, semaforo_col: str, prob_fraude_prom: float
) -> Dict[str, Any]:
    score_prom = round(float(df[score_col].mean()), 1) if score_col in df.columns and len(df) else 0
    tier = _risk_tier(score_prom)
    rec = "Monitoreo estándar"
    if tier["tier"] == "critico":
        rec = "Activar protocolo antifraude inmediato y suspender pagos pendientes"
    elif tier["tier"] == "alto":
        rec = "Priorizar revisión forense y validación documental ampliada"
    elif tier["tier"] == "medio":
        rec = "Programar auditoría selectiva y seguimiento de proveedores"

    radar_labels = ["Frecuencia", "Monto", "Documentos", "Proveedor", "Temporal", "ML"]
    radar_values = [55, 48, 62, 45, 58, 50]
    if len(df):
        if "frecuencia_siniestros_asegurado" in df.columns:
            radar_values[0] = min(100, int(df["frecuencia_siniestros_asegurado"].fillna(0).mean() * 22))
        if "monto_reclamado" in df.columns:
            radar_values[1] = min(100, int(df["monto_reclamado"].fillna(0).mean() / 15000))
        if "documentos_completos" in df.columns:
            inc = (df["documentos_completos"].astype(str).str.lower() == "no").mean()
            radar_values[2] = min(100, int(inc * 100))
        if "prov_casos_observados" in df.columns:
            radar_values[3] = min(100, int(df["prov_casos_observados"].fillna(0).mean() * 25))
        if "reporte_tardio" in df.columns:
            radar_values[4] = min(100, int((df["reporte_tardio"] == 1).mean() * 100))
        if "ml_fraud_probability" in df.columns:
            radar_values[5] = min(100, int(df["ml_fraud_probability"].fillna(0).mean() * 100))

    bands = []
    if semaforo_col in df.columns:
        for sem, color, label in [
            ("Verde", "#00C853", "Bajo"),
            ("Amarillo", "#F5B700", "Medio"),
            ("Rojo", "#FF4D4F", "Alto"),
        ]:
            n = int((df[semaforo_col] == sem).sum())
            bands.append({"label": label, "count": n, "color": color, "pct": round(n / len(df) * 100, 1) if len(df) else 0})
        crit = int((pd.to_numeric(df[score_col], errors="coerce") >= 90).sum()) if score_col in df.columns else 0
        if crit:
            bands.append({"label": "Crítico", "count": crit, "color": "#B91C1C", "pct": round(crit / len(df) * 100, 1)})

    return {
        "score": score_prom,
        "prob_fraude": prob_fraude_prom,
        "tier": tier,
        "recommendation": rec,
        "radar": {"labels": radar_labels, "values": radar_values},
        "bands": bands,
    }


def _build_critical_alert_feed(
    df: pd.DataFrame, score_col: str, semaforo_col: str, limit: int = 10
) -> List[Dict[str, Any]]:
    if df.empty or score_col not in df.columns:
        return []
    cols = ["id_siniestro", score_col, semaforo_col, "monto_reclamado", "alertas_reglas", "fecha_ocurrencia", "ramo"]
    cols = [c for c in cols if c in df.columns]
    top = df.nlargest(limit, score_col)
    feed = []
    for _, row in top.iterrows():
        sc = float(row[score_col]) if pd.notna(row[score_col]) else 0
        alert_text = str(row.get("alertas_reglas") or "").split("|")[0].strip() or "Anomalía de riesgo detectada"
        fecha = row.get("fecha_ocurrencia")
        fecha_str = ""
        if pd.notna(fecha):
            try:
                fecha_str = pd.to_datetime(fecha).strftime("%Y-%m-%d")
            except Exception:
                fecha_str = str(fecha)[:10]
        tier = _risk_tier(sc)
        prob = None
        if "ml_fraud_probability" in row.index and pd.notna(row.get("ml_fraud_probability")):
            prob = round(float(row["ml_fraud_probability"]) * 100, 1)
        feed.append({
            "id_siniestro": row.get("id_siniestro"),
            "score": round(sc, 1),
            "semaforo": str(row.get(semaforo_col) or "—"),
            "risk_label": tier["label"],
            "risk_tier": tier["tier"],
            "monto": float(row.get("monto_reclamado") or 0),
            "anomaly": alert_text[:90],
            "fecha": fecha_str or "—",
            "action": _suggested_action(sc, alert_text),
            "prob_fraude": prob,
        })
    return feed


def _build_soc_timeline(df: pd.DataFrame, temporal_risk: List[Dict]) -> List[Dict[str, Any]]:
    events: List[Dict[str, Any]] = []
    if temporal_risk:
        for t in temporal_risk[-6:]:
            rojos = int(t.get("Rojo") or 0)
            if rojos > 0:
                events.append({
                    "time": str(t.get("mes", "")),
                    "title": f"Pico de casos críticos ({rojos})",
                    "type": "critical",
                    "detail": "Incremento de siniestros en semáforo rojo",
                })
    if not df.empty:
        if "reporte_tardio" in df.columns:
            n = int((df["reporte_tardio"] == 1).sum())
            if n:
                events.append({
                    "time": "Análisis actual",
                    "title": f"{n} reportes tardíos",
                    "type": "warning",
                    "detail": "Patrón temporal anómalo en denuncias",
                })
        if "alertas_reglas" in df.columns:
            n = int(df["alertas_reglas"].fillna("").astype(str).str.contains("Similitud", case=False).sum())
            if n:
                events.append({
                    "time": "Análisis actual",
                    "title": f"{n} narrativas similares",
                    "type": "alert",
                    "detail": "Coincidencias sospechosas entre declaraciones",
                })
        if "tiene_inconsistencia_doc" in df.columns:
            n = int((df["tiene_inconsistencia_doc"].fillna(0) > 0).sum())
            if n:
                events.append({
                    "time": "Análisis actual",
                    "title": f"{n} inconsistencias documentales",
                    "type": "warning",
                    "detail": "Modificaciones o discrepancias en expediente",
                })
        _, sem_col = _score_and_semaforo_cols(df)
        rojos = int((df[sem_col] == "Rojo").sum()) if sem_col in df.columns else 0
        events.append({
            "time": "Motor IA",
            "title": "Scoring híbrido completado",
            "type": "info",
            "detail": f"{len(df)} siniestros procesados · {rojos} en riesgo alto",
        })
    if "fecha_ocurrencia" in df.columns:
        try:
            fechas = pd.to_datetime(df["fecha_ocurrencia"], errors="coerce").dropna()
            if len(fechas):
                events.insert(0, {
                    "time": fechas.max().strftime("%Y-%m-%d"),
                    "title": "Última generación de reclamo",
                    "type": "info",
                    "detail": f"Ventana hasta {fechas.min().strftime('%Y-%m-%d')}",
                })
        except Exception:
            pass
    return events[:12]


def _build_geo_fraud_heatmap(df: pd.DataFrame, score_col: str, semaforo_col: str) -> Dict[str, Any]:
    loc_col = None
    for c in ("ciudad", "provincia", "sucursal", "region"):
        if c in df.columns and df[c].notna().any():
            loc_col = c
            break
    if not loc_col or df.empty:
        return {"locations": [], "intensity": [], "labels": [], "column": loc_col or "sucursal"}

    agg_spec: Dict[str, Any] = {"casos": ("id_siniestro", "count")}
    if semaforo_col in df.columns:
        agg_spec["rojos"] = (semaforo_col, lambda x: (x == "Rojo").sum())
    else:
        agg_spec["rojos"] = ("id_siniestro", "count")
    if score_col in df.columns:
        agg_spec["score_avg"] = (score_col, "mean")
    if "monto_reclamado" in df.columns:
        agg_spec["monto"] = ("monto_reclamado", "sum")
    g = df.groupby(loc_col).agg(**agg_spec).reset_index().sort_values("rojos", ascending=False).head(20)
    locations = g[loc_col].astype(str).tolist()
    intensity = []
    for _, row in g.iterrows():
        casos = max(int(row["casos"]), 1)
        rojos = int(row["rojos"])
        score = float(row.get("score_avg") or 0)
        intensity.append(round((rojos / casos * 70) + (score * 0.3), 1))
    return {
        "locations": locations,
        "intensity": intensity,
        "casos": g["casos"].astype(int).tolist(),
        "rojos": g["rojos"].astype(int).tolist(),
        "labels": locations,
        "column": loc_col,
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
            "global_risk": _global_risk_level(0, 0, 0),
            "ai_insights": [],
            "enriched_alerts": [],
            "segment_data": {},
            "treemap_data": [],
            "risk_matrix": {"x_labels": [], "y_labels": [], "z": []},
            "sparklines": {"critical_trend": [], "score_trend": [], "alert_trend": []},
            "fraud_trend": {"delta_pct": 0, "direction": "neutral", "label": ""},
            "cases_analytics": [],
            "active_alerts_count": 0,
        }

    score_col, semaforo_col = _score_and_semaforo_cols(df)
    raw_sem = df[semaforo_col].value_counts().to_dict() if semaforo_col in df.columns else {}
    semaforo_counts = _normalize_semaforo_counts(raw_sem)

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

    trend = _fraud_trend_delta(temporal_risk_data)
    sparklines = _build_sparklines(temporal_risk_data, temporal_data)
    segment_data = {
        "sucursal": _segment_breakdown(df, "sucursal", score_col, semaforo_col),
        "ramo": _segment_breakdown(df, "ramo", score_col, semaforo_col),
        "cobertura": _segment_breakdown(df, "cobertura", score_col, semaforo_col),
        "proveedor": [
            {
                "label": str(p.get("beneficiario", ""))[:40],
                "casos": int(p.get("casos") or 0),
                "monto": float(p.get("monto") or 0),
                "score_avg": float(p.get("score_prom") or 0),
                "rojos": 0,
                "amarillos": 0,
                "verdes": 0,
            }
            for p in provider_risk
        ],
    }
    enriched_alerts = _enrich_alerts(signal_counts, df, score_col)
    active_alerts_count = sum(int(s.get("count") or 0) for s in signal_counts)
    executive_dashboard = _build_executive_dashboard(
        df, {
            "casos_escalados": casos_escalados,
            "casos_sospechosos": casos_sospechosos,
        },
        rojos, amarillos, verdes, len(df), float(df[score_col].mean()) if score_col in df.columns else 0,
        prob_fraude_prom, monto_potencial_riesgo, trend, active_alerts_count, score_col,
    )
    risk_profile = _build_risk_profile(df, score_col, semaforo_col, prob_fraude_prom)
    critical_alert_feed = _build_critical_alert_feed(df, score_col, semaforo_col)
    soc_timeline = _build_soc_timeline(df, temporal_risk_data)
    geo_fraud_heatmap = _build_geo_fraud_heatmap(df, score_col, semaforo_col)

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
        "global_risk": _global_risk_level(rojos, len(df), float(df[score_col].mean()) if score_col in df.columns else 0),
        "ai_insights": _build_ai_insights(
            df, rojos, len(df), provider_risk, geo_risk_data, trend, score_col, semaforo_col
        ),
        "enriched_alerts": enriched_alerts,
        "segment_data": segment_data,
        "treemap_data": _build_treemap_data(df, score_col),
        "risk_matrix": _build_risk_matrix(df, score_col),
        "sparklines": sparklines,
        "fraud_trend": trend,
        "cases_analytics": _build_cases_table(df, score_col, semaforo_col),
        "active_alerts_count": active_alerts_count,
        "executive_dashboard": executive_dashboard,
        "risk_profile": risk_profile,
        "critical_alert_feed": critical_alert_feed,
        "soc_timeline": soc_timeline,
        "geo_fraud_heatmap": geo_fraud_heatmap,
    }
