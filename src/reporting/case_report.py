"""Reporte de evaluación antifraude por siniestro (UI + PDF)."""
from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any, Dict, List, Optional

import pandas as pd

from src.explainability.explain_score import explain_single_case
from src.risk.classification import get_risk_metadata, score_range_label
from src.rules.fraud_rules import MAX_SCORE_RULES, SIGNAL_CONFIG, apply_rules

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
        return {str(k): int(v or 0) for k, v in raw.items() if int(v or 0) > 0}
    if isinstance(raw, str) and raw.strip():
        text = raw.strip()
        if text.startswith("{"):
            try:
                d = json.loads(text.replace("'", '"'))
                return {str(k): int(v or 0) for k, v in d.items() if int(v or 0) > 0}
            except Exception:
                pass
    return {}


_ALERT_SIGNAL_HINTS = (
    ("borde de vigencia", "borde_vigencia"),
    ("denuncia de robo", "demora_denuncia_robo"),
    ("demora de", "demora_denuncia_robo"),
    ("asegurado con", "frecuencia_asegurado"),
    ("vehículo con", "frecuencia_vehiculo"),
    ("vehiculo con", "frecuencia_vehiculo"),
    ("conductor presente", "frecuencia_conductor"),
    ("conductor en", "frecuencia_conductor"),
    ("solo rc", "frecuencia_rc"),
    ("proveedor", "proveedor_recurrente"),
    ("documentos incompletos", "documentos_incompletos"),
    ("inconsistencias detectadas", "documentos_inconsistentes"),
    ("dinámica del siniestro", "dinamica_sospechosa"),
    ("dinamica del siniestro", "dinamica_sospechosa"),
    ("sin tercero", "sin_tercero_identificado"),
    ("reporte tardío", "reporte_tardio"),
    ("reporte tardio", "reporte_tardio"),
    ("monto reclamado", "monto_cercano_suma"),
    ("similitud textual", "narrativa_similar"),
)


def _reconstruct_detalle_from_alertas(row: pd.Series) -> Dict[str, int]:
    raw = row.get("alertas_reglas", "")
    if not isinstance(raw, str) or not raw.strip() or raw.strip() == "Sin alertas":
        return {}
    detalle: Dict[str, int] = {}
    for part in raw.split("|"):
        msg = part.strip()
        if not msg or msg.startswith("["):
            continue
        m = re.search(r"\((\d+)\s*pts?\)", msg, re.I)
        pts = int(m.group(1)) if m else 0
        if pts <= 0:
            continue
        low = msg.lower()
        matched = False
        for hint, key in _ALERT_SIGNAL_HINTS:
            if hint in low:
                detalle[key] = detalle.get(key, 0) + pts
                matched = True
                break
        if not matched:
            detalle["otros"] = detalle.get("otros", 0) + pts
    return detalle


def _similarity_map_for_row(row: pd.Series) -> Optional[Dict[str, float]]:
    sid = row.get("id_siniestro")
    if sid is None or (isinstance(sid, float) and pd.isna(sid)):
        return None
    sim = row.get("similitud_narrativa_max")
    if pd.isna(sim):
        return None
    return {str(sid): float(sim)}


def resolve_detalle_reglas(row: pd.Series) -> Dict[str, int]:
    detalle = _parse_detalle(row)
    if detalle and sum(detalle.values()) > 0:
        return detalle
    try:
        sub = pd.DataFrame([row])
        scored = apply_rules(sub, similarity_scores=_similarity_map_for_row(row))
        raw = scored.iloc[0].get("detalle_reglas")
        if isinstance(raw, dict):
            rebuilt = {str(k): int(v or 0) for k, v in raw.items() if int(v or 0) > 0}
            if rebuilt:
                return rebuilt
    except Exception:
        pass
    return _reconstruct_detalle_from_alertas(row)


def _lookup_by_id(
    df: Optional[pd.DataFrame],
    id_col: str,
    key: Any,
) -> Optional[pd.Series]:
    if df is None or getattr(df, "empty", True) or key is None:
        return None
    if isinstance(key, float) and pd.isna(key):
        return None
    key_s = str(key).strip().upper()
    if not key_s or id_col not in df.columns:
        return None
    col = df[id_col].astype(str).str.strip().str.upper()
    match = df[col == key_s]
    return match.iloc[0] if not match.empty else None


def enrich_case_row(
    row: pd.Series,
    datasets: Optional[Dict[str, pd.DataFrame]] = None,
) -> pd.Series:
    if not datasets:
        return row
    data = row.to_dict()
    sid = str(row.get("id_siniestro", "")).strip().upper()
    sin_df = datasets.get("siniestros")
    if sin_df is not None and sid:
        base = _lookup_by_id(sin_df, "id_siniestro", sid)
        if base is not None:
            for c in base.index:
                if c not in data or pd.isna(data.get(c)):
                    data[c] = base[c]
    pol = _lookup_by_id(datasets.get("polizas"), "id_poliza", row.get("id_poliza") or data.get("id_poliza"))
    if pol is not None:
        for field in ("fecha_inicio_vigencia", "fecha_fin_vigencia", "suma_asegurada", "estado_poliza"):
            if field in pol.index and (field not in data or pd.isna(data.get(field))):
                data[field] = pol[field]
    aseg = _lookup_by_id(
        datasets.get("asegurados"),
        "id_asegurado",
        row.get("id_asegurado") or data.get("id_asegurado"),
    )
    if aseg is not None:
        for field in ("nombres_asegurado", "nombre", "nombres", "nombre_completo", "documento", "telefono"):
            if field in aseg.index and (field not in data or pd.isna(data.get(field))):
                data[field] = aseg[field]
    veh = _lookup_by_id(
        datasets.get("vehiculos"),
        "id_vehiculo",
        row.get("id_vehiculo") or data.get("id_vehiculo"),
    )
    if veh is not None:
        for field in ("placa", "marca", "modelo", "anio"):
            if field in veh.index and (field not in data or pd.isna(data.get(field))):
                data[field] = veh[field]
        if "placa" in veh.index and (not data.get("placa_vehiculo") or pd.isna(data.get("placa_vehiculo"))):
            data["placa_vehiculo"] = veh["placa"]
    return pd.Series(data)


def build_case_report_extra(
    row: pd.Series,
    datasets: Optional[Dict[str, pd.DataFrame]] = None,
) -> Dict[str, Any]:
    extra: Dict[str, Any] = {}
    enriched = enrich_case_row(row, datasets) if datasets else row
    for field in ("nombres_asegurado", "nombre", "nombres", "nombre_completo"):
        if field in enriched.index and pd.notna(enriched.get(field)):
            extra["nombre_asegurado"] = str(enriched[field]).strip()
            break
    placa = enriched.get("placa_vehiculo") or enriched.get("placa")
    if pd.notna(placa):
        extra["placa_vehiculo"] = str(placa).strip()
    return extra


def _format_fecha(val: Any) -> str:
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return ""
    if hasattr(val, "strftime"):
        return val.strftime("%d/%m/%Y")
    s = str(val).strip()
    if not s or s.lower() == "nan":
        return ""
    return s[:10] if len(s) > 10 else s


def _build_justificacion(row: pd.Series, case: Dict[str, Any]) -> str:
    existing = row.get("justificacion_ia")
    if isinstance(existing, str) and existing.strip():
        return existing.strip()
    parts = []
    sc = case.get("score_hibrido")
    if sc is not None:
        parts.append(f"Score de riesgo {float(sc):.1f}/100")
    sem = case.get("semaforo")
    if sem:
        parts.append(f"Semáforo {sem}")
    alertas = case.get("alertas") or []
    if alertas:
        parts.append("; ".join(str(a) for a in alertas[:4])[:450])
    return ". ".join(parts) if parts else "Sin alertas destacadas en este caso."


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
    detalle = resolve_detalle_reglas(row)
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

    extra = extra or {}
    report = {
        **case,
        "titulo": "REPORTE DE EVALUACIÓN ANTIFRAUDE",
        "subtitulo": "Análisis automatizado con modelo ML supervisado + reglas de negocio",
        "generado": generated,
        "confidencial": "DOCUMENTO CONFIDENCIAL — USO EXCLUSIVO UNIDAD ANTIFRAUDE",
        "id_poliza": poliza,
        "reporte_tardio": reporte_tardio_txt,
        "nombre_asegurado": extra.get("nombre_asegurado") or row.get("nombres_asegurado"),
        "placa_vehiculo": extra.get("placa_vehiculo") or row.get("placa_vehiculo") or row.get("placa"),
        "estado": row.get("estado"),
        "sucursal": row.get("sucursal"),
        "beneficiario": row.get("beneficiario"),
        "fecha_ocurrencia": _format_fecha(row.get("fecha_ocurrencia")),
        "fecha_reporte": _format_fecha(row.get("fecha_reporte")),
        "monto_estimado": row.get("monto_estimado") if pd.notna(row.get("monto_estimado")) else None,
        "reglas_criticas": row.get("reglas_criticas") or "",
        "num_alertas_dataset": row.get("num_alertas"),
        "justificacion_ia": _build_justificacion(row, case),
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
