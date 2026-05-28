"""Estado compartido y utilidades de la aplicación (sin Flask)."""
from __future__ import annotations

import os
import threading

UPLOAD_FOLDER = os.path.join("data", "raw")
try:
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
except OSError:
    pass

APP_DIR = os.path.dirname(os.path.abspath(__file__))

app_state: dict = {
    "datasets": {},
    "df_features": None,
    "df_scored": None,
    "model_results": None,
    "anomaly_results": None,
    "nlp_results": None,
    "agent": None,
    "dashboard_snapshot": None,
    "model_snapshot": None,
    "dashboard_last_payload": None,
    "pipeline_status": "idle",
}

_db_save_lock = threading.Lock()


def reset_pipeline_state() -> None:
    app_state["df_features"] = None
    app_state["df_scored"] = None
    app_state["model_results"] = None
    app_state["anomaly_results"] = None
    app_state["nlp_results"] = None
    app_state["agent"] = None
    app_state["dashboard_snapshot"] = None
    app_state["model_snapshot"] = None
    app_state["dashboard_last_payload"] = None
    app_state["pipeline_status"] = "idle"


def build_agent_context() -> dict:
    return {
        "dashboard_snapshot": app_state.get("dashboard_snapshot"),
        "model_snapshot": app_state.get("model_snapshot"),
        "dashboard_last_payload": app_state.get("dashboard_last_payload"),
    }


def merge_uploaded_tables(new_tables: dict) -> None:
    if not new_tables:
        return
    known = {"siniestros", "polizas", "asegurados", "vehiculos", "proveedores", "documentos"}
    known_in_file = set(new_tables.keys()) & known
    is_full_workbook = "siniestros" in new_tables and len(known_in_file) >= 3
    if is_full_workbook:
        app_state["datasets"] = new_tables
        return
    if not app_state.get("datasets"):
        app_state["datasets"] = {}
    for name, df in new_tables.items():
        app_state["datasets"][name] = df
