"""Estado compartido y utilidades de la aplicación (sin Flask)."""
from __future__ import annotations

import contextvars
import os
import threading
import uuid

UPLOAD_FOLDER = os.path.join("data", "raw")
DOCUMENTS_UPLOAD_FOLDER = os.path.join("data", "uploads", "documents")
for _folder in (UPLOAD_FOLDER, DOCUMENTS_UPLOAD_FOLDER):
    try:
        os.makedirs(_folder, exist_ok=True)
    except OSError:
        pass

APP_DIR = os.path.dirname(os.path.abspath(__file__))

app_state: dict = {
    "datasets": {},
    "source_row_counts": {},
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
    "documentos_subidos": [],
    "executive_summary": None,
}

_db_save_lock = threading.Lock()

_request_session: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "fraudia_session", default=None
)


def get_request_session_id() -> str | None:
    return _request_session.get()


def set_request_session_id(session_id: str | None):
    return _request_session.set(session_id)


def reset_request_session_id(token) -> None:
    _request_session.reset(token)


def ensure_request_session_id() -> str:
    """ID de sesión para /tmp en Vercel (header X-FraudIA-Session o nuevo UUID)."""
    sid = get_request_session_id()
    if sid:
        return sid
    sid = uuid.uuid4().hex[:16]
    set_request_session_id(sid)
    return sid


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
    app_state["executive_summary"] = None


def build_agent_context() -> dict:
    from src.documents.dataset_integration import build_documents_agent_summary

    docs = app_state.get("documentos_subidos") or []
    doc_summary = build_documents_agent_summary(docs)
    return {
        "dashboard_snapshot": app_state.get("dashboard_snapshot"),
        "model_snapshot": app_state.get("model_snapshot"),
        "model_results": app_state.get("model_results"),
        "anomaly_results": app_state.get("anomaly_results"),
        "nlp_results": app_state.get("nlp_results"),
        "dashboard_last_payload": app_state.get("dashboard_last_payload"),
        "documentos_subidos": doc_summary,
        "executive_summary": app_state.get("executive_summary"),
        "source_row_counts": app_state.get("source_row_counts"),
        "total_pdfs_cargados": doc_summary.get("total", 0),
    }


STANDARD_TABLES = frozenset(
    {"siniestros", "polizas", "asegurados", "vehiculos", "proveedores", "documentos"}
)


def is_standard_workbook(tables: dict) -> bool:
    """Workbook completo (plantilla aseguradora): reemplaza todo el estado, no mezcla."""
    if not tables or "siniestros" not in tables:
        return False
    return len(set(tables.keys()) & STANDARD_TABLES) >= 2


def record_source_row_counts(datasets: dict) -> None:
    """Totales del archivo cargado (referencia para dashboard y validación)."""
    app_state["source_row_counts"] = {
        name: len(df) for name, df in (datasets or {}).items() if df is not None
    }


def apply_loaded_datasets(new_tables: dict) -> None:
    """
    Asigna tablas cargadas sin duplicar datasets previos.
    Workbooks con siniestros + tablas relacionadas reemplazan el estado completo.
    """
    if not new_tables:
        return
    filtered = {k: v for k, v in new_tables.items() if k in STANDARD_TABLES}
    if is_standard_workbook(filtered):
        app_state["datasets"] = filtered
        record_source_row_counts(filtered)
        return
    if not app_state.get("datasets"):
        app_state["datasets"] = {}
    for name, df in filtered.items():
        app_state["datasets"][name] = df
    record_source_row_counts(app_state["datasets"])


def merge_uploaded_tables(new_tables: dict) -> None:
    """Compatibilidad: delega en apply_loaded_datasets."""
    apply_loaded_datasets(new_tables)
