"""
Runtime Vercel: carga bundle generado en build (sin importar módulos pesados de ML).
"""
from __future__ import annotations

import os
from typing import Any, Dict

import pandas as pd

from src.ai_agent.claims_agent import ClaimsAgent
from src.app.dashboard_service import build_dashboard_payload

BUNDLE_DIR = os.path.join("data", "processed", "vercel_bundle")


def is_vercel_runtime() -> bool:
    return bool(os.getenv("VERCEL_ENV") or os.getenv("VERCEL_DEPLOYMENT_ID"))


def _project_root() -> str:
    return os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


def _load_scored_dataframe(root: str) -> pd.DataFrame:
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
    raise FileNotFoundError("No hay CSV/Excel scored en data/processed")


def load_vercel_bundle(root: str | None = None) -> Dict[str, Any]:
    import json

    root = root or _project_root()
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


def _build_dashboard_snapshot(payload: Dict[str, Any]) -> Dict[str, Any]:
    kpis = payload.get("kpis", {}) if isinstance(payload, dict) else {}
    return {
        "records_considered": int(payload.get("records_considered", 0)),
        "active_filters_count": len(payload.get("active_filters", [])),
        "score_promedio": float(kpis.get("score_promedio", 0.0)),
        "monto_total": float(kpis.get("monto_total", 0.0)),
        "semaforo_counts": {
            "Rojo": int(kpis.get("casos_rojos", 0)),
            "Amarillo": int(kpis.get("casos_amarillos", 0)),
            "Verde": int(kpis.get("casos_verdes", 0)),
        },
    }


def bootstrap_vercel_demo(app_state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Carga resultados del pipeline ejecutado en build/deploy:
    datos puntuados + contexto de dashboard y modelo ML para el agente.
    """
    if app_state.get("df_scored") is not None and app_state.get("agent") is not None:
        return {"status": "already_loaded", "records": len(app_state["df_scored"])}

    root = _project_root()
    bundle = load_vercel_bundle(root)
    df_scored = _load_scored_dataframe(root)

    manifest = bundle.get("manifest", {})
    dashboard_snapshot = bundle.get("dashboard_snapshot")
    dashboard_payload = bundle.get("dashboard_payload")
    model_snapshot = bundle.get("model_snapshot", {})
    nlp_results = bundle.get("nlp_summary")

    if not dashboard_payload:
        dashboard_payload = build_dashboard_payload(
            df_scored, total_unfiltered=len(df_scored), active_filters=[]
        )
    if not dashboard_snapshot:
        dashboard_snapshot = _build_dashboard_snapshot(dashboard_payload)

    app_state["datasets"] = {"siniestros": df_scored.copy()}
    app_state["df_features"] = df_scored.copy()
    app_state["df_scored"] = df_scored
    app_state["model_results"] = model_snapshot
    app_state["nlp_results"] = nlp_results or {}
    app_state["pipeline_status"] = "completed"
    app_state["dashboard_snapshot"] = dashboard_snapshot
    app_state["dashboard_last_payload"] = dashboard_payload
    app_state["model_snapshot"] = model_snapshot

    extra = {
        "dashboard_snapshot": dashboard_snapshot,
        "model_snapshot": model_snapshot,
        "dashboard_last_payload": dashboard_payload,
        "deployment": "vercel",
        "data_source": manifest.get("source", "vercel_bundle"),
        "pipeline_steps": manifest.get("steps", []),
        "executive_summary": bundle.get("executive_summary", {}).get("text", ""),
        "rules_summary": bundle.get("rules_summary", {}),
        "manifest": manifest,
    }
    app_state["agent"] = ClaimsAgent(df_scored, extra_context=extra)

    return {
        "status": "loaded",
        "records": len(df_scored),
        "vercel": True,
        "data_source": manifest.get("source"),
        "seed": manifest.get("seed"),
        "auc_roc": manifest.get("auc_roc"),
        "analysis_at": "build",
        "message": "Análisis cargado desde bundle (runtime liviano).",
    }
