"""Reporte de evaluación antifraude por siniestro (UI + PDF)."""
from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Dict, List, Optional

import pandas as pd

from src.explainability.explain_score import explain_single_case
from src.risk.classification import get_risk_metadata, score_range_label
from src.rules.fraud_rules import MAX_SCORE_RULES, SIGNAL_CONFIG

_MESES_ES = (
    "enero", "febrero", "marzo", "abril", "mayo", "junio",
    "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
)


def _fecha_pie_es() -> str:
    now = datetime.now()
    return f"{now.day} de {_MESES_ES[now.month - 1].capitalize()} de {now.year}"


SCORE_BAR_LABELS = {
    "borde_vigencia": "Vigencia",
    "demora_denuncia_robo": "Demora robo",
    "frecuencia_asegurado": "Hist. Aseg.",
    "frecuencia_vehiculo": "Hist. Veh.",
    "frecuencia_conductor": "Hist. Cond.",
    "frecuencia_rc": "Solo RC",
    "proveedor_recurrente": "Proveedor",
    "documentos_incompletos": "Docs inc.",
    "dinamica_sospechosa": "Dinámica",
    "sin_tercero_identificado": "Sin tercero",
    "documentos_inconsistentes": "Docs inco.",
    "reporte_tardio": "Rep. Tardío",
    "narrativa_similar": "Narrativa",
    "monto_cercano_suma": "Monto",
}


def _pts_severity(pts: int) -> str:
    if pts >= 6:
        return "ALTA"
    if pts >= 4:
        return "MEDIA"
    return "BAJA"


def _parse_detalle(row: pd.Series) -> Dict[str, int]:
    raw = row.get("detalle_reglas")
    if isinstance(raw, dict):
        return {str(k): int(v or 0) for k, v in raw.items()}
    if isinstance(raw, str) and raw.strip().startswith("{"):
        try:
            import json
            d = json.loads(raw.replace("'", '"'))
            return {str(k): int(v or 0) for k, v in d.items()}
        except Exception:
            pass
    return {}


def _infer_umbral(descripcion: str, detalle: Dict[str, int]) -> str:
    d = descripcion.lower()
    if "≤10" in descripcion or "10 días" in d or "10 dias" in d:
        return "≤10 días"
    if "≥3" in descripcion or "11 siniestros" in d:
        return "≥3"
    if ">2" in descripcion or "casos observados" in d:
        return ">2"
    if ">7 días" in descripcion or "26 días" in descripcion:
        return ">7 días"
    if "inconsistencia" in d:
        return "Detectada"
    if "incomplet" in d or "documentación" in d:
        return "Falta doc. oblig."
    if "suma asegurada" in d or "promedio" in d:
        return "Umbral sup."
    if "similitud" in d:
        return "≥88%"
    return "—"


def _build_alertas_tabla(alertas: List[str], detalle: Dict[str, int]) -> List[Dict[str, Any]]:
    rows = []
    for i, msg in enumerate(alertas, 1):
        m = re.search(r"\((\d+)\s*pts?\)", msg, re.I)
        pts = int(m.group(1)) if m else 0
        desc = re.sub(r"\s*\[\w+-\d+\]\s*", "", msg)
        desc = re.sub(r"\s*\(\d+\s*pts?\)\s*", "", desc, flags=re.I).strip()
        desc = re.sub(r"\s*→\s*Rojo.*$", "", desc, flags=re.I).strip()
        if not desc:
            continue
        rows.append({
            "num": len(rows) + 1,
            "descripcion": desc,
            "umbral": _infer_umbral(desc, detalle),
            "puntos": pts,
            "severidad": _pts_severity(pts),
        })
    return rows


def _build_score_bars(detalle: Dict[str, int]) -> List[Dict[str, Any]]:
    bars = []
    order = list(SIGNAL_CONFIG.keys()) + ["narrativa_similar"]
    for key in order:
        pts = int(detalle.get(key, 0) or 0)
        if pts <= 0:
            continue
        label = SCORE_BAR_LABELS.get(key, key.replace("_", " ").title()[:12])
        bars.append({"key": key, "label": label, "puntos": pts})
    docs_pts = int(detalle.get("documentos_incompletos", 0) or 0) + int(
        detalle.get("documentos_inconsistentes", 0) or 0
    )
    if docs_pts > 0 and not any(b["key"] == "documentos_inconsistentes" for b in bars):
        bars.append({"key": "docs_total", "label": "Docs", "puntos": docs_pts})
    return bars


def _build_conclusion(case: Dict[str, Any]) -> str:
    cid = case.get("id_siniestro", "")
    score = float(case.get("score_hibrido") or 0)
    sem = str(case.get("semaforo", "")).upper()
    n_alert = len(case.get("alertas_tabla") or [])
    ml = case.get("ml_fraud_probability")
    anom = case.get("anomaly_score")
    parts = [
        f"El siniestro {cid} presenta un score de riesgo de {score:.1f}/100, "
        f"classificado como {sem} — Nivel {case.get('nivel_riesgo', '')} "
        f"(rango {case.get('rango_score', '')}).",
    ]
    if n_alert:
        parts.append(
            f"Se identificaron {n_alert} señales de alerta mediante reglas de negocio "
            "y modelos de aprendizaje automatizado."
        )
    if ml is not None and not (isinstance(ml, float) and pd.isna(ml)):
        parts.append(
            f"El modelo ML supervisado asigna una probabilidad de fraude del {float(ml)*100:.1f}%, "
        )
        if anom is not None and not (isinstance(anom, float) and pd.isna(anom)):
            parts.append(
                f"mientras que el score de anomalía alcanza el {float(anom)*100:.1f}%, "
                "indicando un patrón altamente atípico."
            )
        else:
            parts.append("reforzando la necesidad de revisión.")
    parts.append(
        f"Se recomienda {str(case.get('accion_sugerida') or case.get('recomendacion', '')).lower()} "
        "antes de proceder con cualquier liquidación."
    )
    return " ".join(parts)


def build_case_report(row: pd.Series, extra: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Payload estructurado para previsualización HTML y PDF."""
    case = explain_single_case(row)
    detalle = _parse_detalle(row)
    alertas_tabla = _build_alertas_tabla(case.get("alertas") or [], detalle)
    score_bars = _build_score_bars(detalle)
    raw_pts = sum(int(v or 0) for v in detalle.values())

    score_reglas = row.get("score_reglas")
    if pd.isna(score_reglas):
        score_reglas = None
    else:
        score_reglas = float(score_reglas)

    ml_prob = row.get("ml_fraud_probability")
    if pd.notna(ml_prob):
        case["ml_fraud_probability"] = float(ml_prob)

    anom = row.get("anomaly_score")
    if pd.notna(anom):
        case["anomaly_score"] = float(anom)

    poliza = row.get("id_poliza", "")
    dias_rep = row.get("dias_entre_ocurrencia_reporte")
    reporte_tardio_txt = ""
    if pd.notna(dias_rep):
        reporte_tardio_txt = f"{int(dias_rep)} días después del evento"

    generated = datetime.now().strftime("%d/%m/%Y")
    sem_meta = get_risk_metadata(case.get("semaforo", "Verde"))

    report = {
        **case,
        "titulo": "REPORTE DE EVALUACIÓN ANTIFRAUDE",
        "subtitulo": "Análisis automatizado con modelo ML supervisado + reglas de negocio",
        "generado": generated,
        "confidencial": "DOCUMENTO CONFIDENCIAL — USO EXCLUSIVO UNIDAD ANTIFRAUDE",
        "id_poliza": poliza,
        "reporte_tardio": reporte_tardio_txt,
        "nombre_asegurado": extra.get("nombre_asegurado") if extra else row.get("nombres_asegurado"),
        "alertas_tabla": alertas_tabla,
        "num_alertas": len(alertas_tabla),
        "score_bars": score_bars,
        "score_reglas_detalle": score_reglas,
        "puntos_brutos_reglas": raw_pts,
        "max_puntos_reglas": MAX_SCORE_RULES,
        "factores_evaluacion": [
            {
                "factor": "Reglas de negocio (score ponderado)",
                "valor": f"{score_reglas:.1f} / 100" if score_reglas is not None else "—",
            },
            {
                "factor": "Modelo ML supervisado (probabilidad)",
                "valor": f"{float(ml_prob)*100:.1f} %" if pd.notna(ml_prob) else "—",
            },
            {
                "factor": "Score de anomalía (isolation forest)",
                "valor": f"{float(anom)*100:.1f} %" if pd.notna(anom) else "—",
            },
        ],
        "distribucion_nota": (
            f"Total acumulado por reglas de negocio: {raw_pts} puntos brutos"
            + (f" → score normalizado {score_reglas:.1f}/100" if score_reglas is not None else "")
        ),
        "accion_destacada": case.get("accion_sugerida") or sem_meta.get("accion", ""),
        "conclusion": "",
        "pie": f"Generado por FXecure — Agente IA Antifraude · Aseguradora del Sur",
        "pie_fecha": _fecha_pie_es(),
    }
    report["conclusion"] = _build_conclusion(report)
    if not report.get("nombre_asegurado"):
        report["nombre_asegurado"] = row.get("beneficiario") or row.get("id_asegurado", "—")
    return report
