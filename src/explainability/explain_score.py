"""
Módulo de explicabilidad para scores de fraude.
Genera explicaciones en lenguaje natural para cada caso.
"""
from typing import Dict, List

import pandas as pd

from src.risk.classification import classify_risk, get_risk_metadata, score_range_label


def explain_single_case(row: pd.Series) -> Dict:
    score = row.get("score_hibrido", row.get("score_reglas", 0))
    semaforo = row.get("semaforo_final", row.get("semaforo_reglas", classify_risk(score)))
    meta = get_risk_metadata(semaforo)

    explanation = {
        "id_siniestro": row.get("id_siniestro", "N/A"),
        "score_hibrido": score,
        "semaforo": semaforo,
        "nivel_riesgo": row.get("nivel_riesgo", meta["nivel"]),
        "rango_score": score_range_label(semaforo),
        "emoji": meta["emoji"],
        "descripcion_riesgo": meta["descripcion"],
        "accion_sugerida": row.get("accion_sugerida", meta["accion"]),
        "alertas": [],
        "factores_principales": [],
        "recomendacion": meta["accion"],
        "resumen": "",
    }

    alertas_raw = row.get("alertas_reglas", "")
    if isinstance(alertas_raw, str) and alertas_raw != "Sin alertas":
        explanation["alertas"] = [a.strip() for a in alertas_raw.split("|") if a.strip()]

    factores = []

    score_reglas = row.get("score_reglas", 0)
    if not pd.isna(score_reglas) and score_reglas > 0:
        factores.append({"factor": "Reglas de negocio", "contribucion": f"{score_reglas:.1f}/100", "tipo": "reglas"})

    ml_prob = row.get("ml_fraud_probability", 0)
    if not pd.isna(ml_prob) and ml_prob > 0:
        factores.append({"factor": "Modelo ML supervisado", "contribucion": f"{ml_prob*100:.1f}%", "tipo": "ml"})

    anomaly = row.get("anomaly_score", 0)
    if not pd.isna(anomaly) and anomaly > 0:
        factores.append({"factor": "Score de anomalía", "contribucion": f"{anomaly*100:.1f}%", "tipo": "anomalia"})

    explanation["factores_principales"] = factores
    explanation["resumen"] = _generate_narrative_summary(row, explanation)

    for field in (
        "ramo", "cobertura", "monto_reclamado", "monto_estimado", "estado",
        "sucursal", "beneficiario", "fecha_ocurrencia", "fecha_reporte",
    ):
        if field in row.index and not pd.isna(row.get(field)):
            explanation[field] = row.get(field)

    return explanation


def _generate_narrative_summary(row: pd.Series, explanation: Dict) -> str:
    parts = []
    id_sin = row.get("id_siniestro", "N/A")
    score = explanation["score_hibrido"]
    semaforo = explanation["semaforo"]
    nivel = explanation["nivel_riesgo"]
    rango = explanation["rango_score"]

    parts.append(
        f"El siniestro {id_sin} tiene score de riesgo {score:.1f}/100 "
        f"(rango {rango}): {explanation['emoji']} {semaforo} — nivel {nivel}."
    )

    n_alertas = len(explanation["alertas"])
    if n_alertas > 0:
        parts.append(f"Se detectaron {n_alertas} señales de alerta:")
        for i, alerta in enumerate(explanation["alertas"][:5], 1):
            parts.append(f"  {i}. {alerta}")

    monto = row.get("monto_reclamado", 0)
    ramo = row.get("ramo", "N/A")
    cobertura = row.get("cobertura", "N/A")
    if not pd.isna(monto):
        parts.append(f"Ramo: {ramo} | Cobertura: {cobertura} | Monto reclamado: ${monto:,.2f}")

    parts.append(f"\nAcción sugerida: {explanation['accion_sugerida']}")

    return "\n".join(parts)


def explain_batch(df: pd.DataFrame) -> List[Dict]:
    return [explain_single_case(row) for _, row in df.iterrows()]


def generate_executive_summary(df: pd.DataFrame) -> Dict:
    total = len(df)
    semaforo_col = "semaforo_final" if "semaforo_final" in df.columns else "semaforo_reglas"
    score_col = "score_hibrido" if "score_hibrido" in df.columns else "score_reglas"

    if semaforo_col not in df.columns:
        return {"error": "No se encontraron scores calculados"}

    counts = df[semaforo_col].value_counts()
    rojo = counts.get("Rojo", 0)
    amarillo = counts.get("Amarillo", 0)
    verde = counts.get("Verde", 0)

    top_cases = df.nlargest(10, score_col)[
        ["id_siniestro", score_col, semaforo_col, "ramo", "monto_reclamado"]
    ].to_dict("records") if score_col in df.columns else []

    ramo_risk = {}
    if "ramo" in df.columns and score_col in df.columns:
        ramo_risk = df.groupby("ramo")[score_col].agg(["mean", "max", "count"]).round(1).to_dict("index")

    return {
        "total_siniestros": total,
        "distribucion_semaforo": {
            "Rojo": int(rojo),
            "Amarillo": int(amarillo),
            "Verde": int(verde),
        },
        "porcentajes": {
            "Rojo": round(rojo / total * 100, 1) if total else 0,
            "Amarillo": round(amarillo / total * 100, 1) if total else 0,
            "Verde": round(verde / total * 100, 1) if total else 0,
        },
        "score_promedio": round(df[score_col].mean(), 1) if score_col in df.columns else 0,
        "score_maximo": round(df[score_col].max(), 1) if score_col in df.columns else 0,
        "top_10_casos": top_cases,
        "riesgo_por_ramo": ramo_risk,
        "umbrales_score": {
            "Verde": "0-40 (Bajo)",
            "Amarillo": "41-75 (Medio)",
            "Rojo": "76-100 (Alto)",
        },
    }
