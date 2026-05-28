"""
Pipeline completo: datos → features → NLP → reglas → ML → anomalías → score híbrido.
Usado por Flask (local), script de build Vercel y empaquetado para el agente IA.
"""
from __future__ import annotations

import json
import os
import time
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

from src.app.dashboard_service import build_dashboard_payload
from src.explainability.explain_score import generate_executive_summary
from src.features.build_features import build_all_features, get_feature_columns
from src.models.fraud_model import (
    compute_hybrid_score,
    get_model_metrics_summary,
    predict_fraud_probability,
    train_anomaly_model,
    train_supervised_model,
)
from src.nlp.text_analysis import generate_text_summary, get_similarity_scores_by_id
from src.rules.fraud_rules import apply_rules, get_rules_summary
from src.utils.dataframe_columns import normalize_datasets_columns

BUNDLE_DIR = os.path.join("data", "processed", "vercel_bundle")


def _is_vercel_runtime() -> bool:
    return bool(
        os.getenv("VERCEL")
        or os.getenv("VERCEL_DEPLOYMENT_ID")
        or os.getenv("VERCEL_ENV")
    )


def _default_scored_csv_path() -> str:
    if _is_vercel_runtime():
        return "/tmp/fraudia_processed/siniestros_scored.csv"
    return os.path.join("data", "processed", "siniestros_scored.csv")


class NumpyJSONEncoder(json.JSONEncoder):
    def default(self, o):
        if isinstance(o, (np.integer,)):
            return int(o)
        if isinstance(o, (np.floating,)):
            return float(o)
        if isinstance(o, np.ndarray):
            return o.tolist()
        if isinstance(o, (pd.Timestamp,)):
            return o.isoformat()
        return super().default(o)


def _json_safe(data: Any) -> Any:
    return json.loads(json.dumps(data, cls=NumpyJSONEncoder))


def build_dashboard_snapshot(dashboard_payload: Dict[str, Any]) -> Dict[str, Any]:
    kpis = dashboard_payload.get("kpis", {}) if isinstance(dashboard_payload, dict) else {}
    return {
        "records_considered": int(dashboard_payload.get("records_considered", 0)),
        "active_filters_count": len(dashboard_payload.get("active_filters", [])),
        "score_promedio": float(kpis.get("score_promedio", 0.0)),
        "monto_total": float(kpis.get("monto_total", 0.0)),
        "semaforo_counts": {
            "Rojo": int(kpis.get("casos_rojos", 0)),
            "Amarillo": int(kpis.get("casos_amarillos", 0)),
            "Verde": int(kpis.get("casos_verdes", 0)),
        },
    }


def serialize_model_results(ml_results: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Métricas serializables (sin objetos sklearn)."""
    if not ml_results or "model" not in ml_results:
        return {"error": ml_results.get("error") if ml_results else "Modelo no entrenado"}
    summary = get_model_metrics_summary(ml_results)
    summary["feature_importance"] = ml_results.get("feature_importance", [])[:15]
    summary["confusion_matrix"] = ml_results.get("confusion_matrix")
    summary["trained"] = True
    return _json_safe(summary)


def execute_full_pipeline(
    datasets: Dict[str, pd.DataFrame],
    *,
    persist_csv: bool = True,
    csv_path: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Ejecuta el análisis completo sobre datasets normalizados.
    Retorna estado listo para app_state / bundle Vercel.
    """
    if not datasets or "siniestros" not in datasets:
        raise ValueError("Se requiere la tabla 'siniestros' en los datasets.")

    datasets = normalize_datasets_columns(datasets)
    t_start = time.time()
    steps: List[Dict[str, Any]] = []

    df_feat = build_all_features(datasets)
    steps.append({"step": "Feature Engineering", "status": "ok", "features": len(df_feat.columns)})

    similarity_scores: Dict[str, float] = {}
    nlp_results: Optional[Dict[str, Any]] = None
    if "descripcion" in df_feat.columns:
        similarity_scores = get_similarity_scores_by_id(df_feat)
        nlp_results = generate_text_summary(df_feat)
        steps.append({
            "step": "Analisis NLP",
            "status": "ok",
            "pairs_detected": sum(1 for v in similarity_scores.values() if v >= 0.70),
        })

    df_rules = apply_rules(df_feat, similarity_scores)
    rules_summary = get_rules_summary(df_rules)
    steps.append({"step": "Reglas de Negocio", "status": "ok", "summary": _json_safe(rules_summary)})

    if "etiqueta_fraude_simulada" not in df_rules.columns:
        raise ValueError(
            "El modelo supervisado requiere 'etiqueta_fraude_simulada' en siniestros."
        )

    feature_cols = get_feature_columns(df_rules)
    if not feature_cols:
        raise ValueError("No hay variables numéricas válidas para entrenar el modelo.")

    ml_results = train_supervised_model(df_rules, feature_cols)
    if "model" not in ml_results:
        raise ValueError(ml_results.get("error", "No fue posible entrenar el modelo supervisado."))

    df_rules["ml_fraud_probability"] = predict_fraud_probability(
        df_rules, ml_results["model"], ml_results["scaler"], ml_results["feature_cols"]
    )
    steps.append({
        "step": "Modelo Supervisado (Random Forest)",
        "status": "ok",
        "metrics": serialize_model_results(ml_results),
    })

    anomaly_results = None
    n_anomalies = None
    if feature_cols:
        anomaly_results = train_anomaly_model(df_rules, feature_cols)
        df_rules["anomaly_score"] = anomaly_results["anomaly_scores"]
        n_anomalies = anomaly_results["n_anomalies"]
        steps.append({
            "step": "Deteccion de Anomalias (Isolation Forest)",
            "status": "ok",
            "anomalies_detected": n_anomalies,
        })

    df_scored = compute_hybrid_score(df_rules)

    if persist_csv:
        out = csv_path or _default_scored_csv_path()
        try:
            os.makedirs(os.path.dirname(out), exist_ok=True)
            df_scored.to_csv(out, index=False)
        except OSError:
            # En serverless solo /tmp es escribible; el estado vive en memoria del request.
            pass

    dashboard_payload = build_dashboard_payload(
        df_scored, total_unfiltered=len(df_scored), active_filters=[]
    )
    dashboard_snapshot = build_dashboard_snapshot(dashboard_payload)
    model_snapshot = serialize_model_results(ml_results)
    executive_summary = generate_executive_summary(df_scored)

    sem_counts = df_scored["semaforo_final"].value_counts()

    return {
        "datasets": datasets,
        "df_features": df_feat,
        "df_scored": df_scored,
        "model_results": ml_results,
        "model_snapshot": model_snapshot,
        "anomaly_results": anomaly_results,
        "nlp_results": nlp_results,
        "dashboard_snapshot": dashboard_snapshot,
        "dashboard_last_payload": dashboard_payload,
        "executive_summary": executive_summary,
        "steps": steps,
        "duration_seconds": round(time.time() - t_start, 2),
        "total_records": len(df_scored),
        "semaforo_counts": {
            "Rojo": int(sem_counts.get("Rojo", 0)),
            "Amarillo": int(sem_counts.get("Amarillo", 0)),
            "Verde": int(sem_counts.get("Verde", 0)),
        },
        "auc_roc": ml_results.get("auc_roc"),
        "status": "success",
    }


def save_vercel_bundle(pipeline_result: Dict[str, Any], root: Optional[str] = None) -> str:
    """Guarda CSV + JSON de contexto para runtime Vercel (agente + dashboard)."""
    root = root or os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    bundle_dir = os.path.join(root, BUNDLE_DIR)
    os.makedirs(bundle_dir, exist_ok=True)

    df_scored = pipeline_result["df_scored"]
    csv_path = os.path.join(root, "data", "processed", "siniestros_scored.csv")
    os.makedirs(os.path.dirname(csv_path), exist_ok=True)
    df_scored.to_csv(csv_path, index=False)

    files = {
        "manifest.json": {
            "version": 1,
            "source": pipeline_result.get("data_source", "pipeline"),
            "seed": pipeline_result.get("seed"),
            "total_records": pipeline_result["total_records"],
            "duration_seconds": pipeline_result["duration_seconds"],
            "semaforo_counts": pipeline_result["semaforo_counts"],
            "auc_roc": pipeline_result.get("auc_roc"),
            "steps": pipeline_result.get("steps", []),
        },
        "dashboard_snapshot.json": pipeline_result["dashboard_snapshot"],
        "dashboard_payload.json": _json_safe(pipeline_result["dashboard_last_payload"]),
        "model_snapshot.json": pipeline_result["model_snapshot"],
        "nlp_summary.json": _json_safe(pipeline_result.get("nlp_results") or {}),
        "executive_summary.json": {"text": pipeline_result.get("executive_summary", "")},
        "rules_summary.json": _json_safe(
            next((s.get("summary") for s in pipeline_result.get("steps", []) if s["step"] == "Reglas de Negocio"), {})
        ),
    }

    for name, content in files.items():
        path = os.path.join(bundle_dir, name)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(content, f, ensure_ascii=False, indent=2, cls=NumpyJSONEncoder)

    return bundle_dir


def load_vercel_bundle(root: Optional[str] = None) -> Dict[str, Any]:
    """Carga el bundle generado en build (para runtime Vercel)."""
    root = root or os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    bundle_dir = os.path.join(root, BUNDLE_DIR)
    if not os.path.isdir(bundle_dir):
        return {}

    loaded: Dict[str, Any] = {}
    for name in os.listdir(bundle_dir):
        if not name.endswith(".json"):
            continue
        key = name.replace(".json", "")
        with open(os.path.join(bundle_dir, name), encoding="utf-8") as f:
            loaded[key] = json.load(f)
    return loaded
