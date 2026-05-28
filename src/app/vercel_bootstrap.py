"""
Carga automática del demo en Vercel (sin SQLite ni pipeline pesado en frío).
Usa datos pre-calculados incluidos en el repositorio.
"""
from __future__ import annotations

import os
from typing import Any, Dict

import pandas as pd

from src.ai_agent.claims_agent import ClaimsAgent
from src.app.dashboard_service import build_dashboard_payload
from src.ingestion.load_data import load_all_from_directory
from src.models.fraud_model import get_model_metrics_summary
from src.utils.dataframe_columns import normalize_datasets_columns


def is_vercel_runtime() -> bool:
    return bool(
        os.getenv("VERCEL")
        or os.getenv("VERCEL_DEPLOYMENT_ID")
        or os.getenv("VERCEL_ENV")
    )


def _project_root() -> str:
    return os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


def _load_scored_dataframe() -> pd.DataFrame:
    root = _project_root()
    candidates = [
        os.path.join(root, "data", "processed", "siniestros_scored.csv"),
        os.path.join(root, "data", "processed", "dataset_completo_scored.xlsx"),
    ]
    for path in candidates:
        if not os.path.exists(path):
            continue
        if path.endswith(".csv"):
            return pd.read_csv(path)
        return pd.read_excel(path, sheet_name="siniestros")
    raise FileNotFoundError(
        "No se encontró data/processed/siniestros_scored.csv. "
        "Ejecute el pipeline localmente antes de desplegar."
    )


def _build_model_results_stub(df: pd.DataFrame) -> Dict[str, Any]:
    """Métricas mínimas para la pestaña Modelo ML usando columnas ya calculadas."""
    stub: Dict[str, Any] = {
        "mode": "precomputed",
        "model": None,
        "note": "Modelo entrenado en entorno local; métricas derivadas del dataset desplegado.",
    }
    if "etiqueta_fraude_simulada" in df.columns and "ml_fraud_probability" in df.columns:
        try:
            from sklearn.metrics import accuracy_score, roc_auc_score

            y = df["etiqueta_fraude_simulada"].fillna(0).astype(int)
            proba = df["ml_fraud_probability"].fillna(0).astype(float)
            pred = (proba >= 0.5).astype(int)
            if y.nunique() >= 2:
                stub["auc_roc"] = round(float(roc_auc_score(y, proba)), 4)
            stub["accuracy"] = round(float(accuracy_score(y, pred)), 4)
        except Exception:
            pass
    if "score_hibrido" in df.columns:
        stub["score_promedio"] = round(float(df["score_hibrido"].mean()), 2)
    return stub


def bootstrap_vercel_demo(app_state: Dict[str, Any]) -> Dict[str, Any]:
    """Inicializa memoria de la app con datos del repo (idempotente)."""
    if app_state.get("df_scored") is not None and app_state.get("agent") is not None:
        return {"status": "already_loaded", "records": len(app_state["df_scored"])}

    root = _project_root()
    df_scored = _load_scored_dataframe()

    synthetic_dir = os.path.join(root, "data", "synthetic")
    datasets: Dict[str, pd.DataFrame] = {}
    if os.path.isdir(synthetic_dir):
        try:
            datasets = normalize_datasets_columns(load_all_from_directory(synthetic_dir))
        except Exception:
            datasets = {}

    if not datasets:
        datasets = {"siniestros": df_scored.copy()}

    app_state["datasets"] = datasets
    app_state["df_features"] = df_scored.copy()
    app_state["df_scored"] = df_scored
    app_state["model_results"] = _build_model_results_stub(df_scored)
    app_state["nlp_results"] = {"mode": "precomputed", "message": "NLP incluido en dataset desplegado"}
    app_state["pipeline_status"] = "completed"

    payload = build_dashboard_payload(df_scored, total_unfiltered=len(df_scored), active_filters=[])
    kpis = payload.get("kpis", {}) if isinstance(payload, dict) else {}
    app_state["dashboard_snapshot"] = {
        "records_considered": int(payload.get("records_considered", len(df_scored))),
        "active_filters_count": 0,
        "score_promedio": float(kpis.get("score_promedio", 0.0)),
        "monto_total": float(kpis.get("monto_total", 0.0)),
        "semaforo_counts": {
            "Rojo": int(kpis.get("casos_rojos", 0)),
            "Amarillo": int(kpis.get("casos_amarillos", 0)),
            "Verde": int(kpis.get("casos_verdes", 0)),
        },
    }
    app_state["dashboard_last_payload"] = payload
    app_state["model_snapshot"] = get_model_metrics_summary(app_state["model_results"])

    extra = {
        "dashboard_snapshot": app_state["dashboard_snapshot"],
        "model_snapshot": app_state["model_snapshot"],
        "dashboard_last_payload": app_state["dashboard_last_payload"],
        "deployment": "vercel",
    }
    app_state["agent"] = ClaimsAgent(df_scored, extra_context=extra)

    return {
        "status": "loaded",
        "records": len(df_scored),
        "vercel": True,
        "openai_required": True,
    }
