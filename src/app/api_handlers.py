"""Handlers HTTP (lógica de negocio sin framework web)."""
from __future__ import annotations

import io
import json
import os
import time
import traceback
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from src.app.core import (
    DOCUMENTS_UPLOAD_FOLDER,
    UPLOAD_FOLDER,
    app_state,
    apply_loaded_datasets,
    build_agent_context,
    ensure_request_session_id,
    get_request_session_id,
    record_source_row_counts,
    reset_pipeline_state,
    _db_save_lock,
)
from src.app.dashboard_service import (
    apply_dashboard_filters,
    build_dashboard_payload,
    get_filter_options,
    params_from_request,
)
from src.app.vercel_bootstrap import bootstrap_vercel_demo, is_vercel_runtime, load_vercel_bundle
from src.ai_agent.claims_agent import ClaimsAgent
from src.ai_agent.llm_router import llm_status
from src.ai_agent.openai_client import is_openai_configured, get_openai_model
from src.explainability.explain_score import explain_single_case
from src.ingestion.load_data import (
    load_all_from_directory,
    load_file_to_tables,
    load_from_upload,
    validate_datasets,
)
from src.utils.dataframe_columns import ensure_str_columns, normalize_datasets_columns
from src.db.config import test_connection
from src.db.config import is_persistent_database_configured
from src.db.repository import (
    init_database,
    save_all_datasets,
    load_all_datasets,
    load_dataframe,
    load_latest_analysis_meta,
    replace_siniestros_scored,
    update_siniestros_scores,
    save_analysis_run,
    get_analysis_history,
    get_db_stats,
    save_documento_subido,
    list_documentos_subidos,
    get_documento_subido,
)
from src.ingestion.pdf_extractor import campos_to_json, process_pdf_upload, TIPOS_DOCUMENTO
from src.documents.document_analyzer import analyze_document, merge_document_into_datasets
from src.documents.dataset_integration import (
    apply_document_post_scoring,
    enrich_datasets_with_uploaded_documents,
    documents_for_siniestro,
)
from src.pipeline.run_full_analysis import build_dashboard_snapshot, execute_full_pipeline


def _should_use_live_database() -> bool:
    return (not is_vercel_runtime()) or is_persistent_database_configured()


def _should_persist_dataset_on_load() -> bool:
    """Guarda tablas en TiDB al cargar (requerido para análisis persistente y recarga desde BD)."""
    return os.getenv("PERSIST_DATASET_ON_LOAD", "true").lower() in ("1", "true", "yes")


def _should_auto_pipeline_on_load() -> bool:
    """Tras cargar Excel o datos sintéticos, ejecutar pipeline y alimentar dashboard/ML."""
    return os.getenv("AUTO_PIPELINE_ON_LOAD", "true").lower() in ("1", "true", "yes")


def _should_pipeline_async() -> bool:
    """Pipeline en hilo aparte para no bloquear la subida del Excel."""
    return os.getenv("PIPELINE_ASYNC", "true").lower() in ("1", "true", "yes")


def _should_sync_scores_after_pipeline() -> bool:
    """Persiste scores en TiDB tras análisis (necesario para dashboard/ML en Vercel)."""
    env = os.getenv("SCORE_SYNC_ON_PIPELINE", "").strip().lower()
    if env in ("0", "false", "no"):
        return False
    if env in ("1", "true", "yes"):
        return True
    return _should_use_live_database()


def _standard_tables_label(datasets: dict) -> str:
    from src.app.core import STANDARD_TABLES

    parts = []
    for name in ("siniestros", "polizas", "asegurados", "proveedores", "documentos"):
        if name in datasets and name in STANDARD_TABLES:
            parts.append(f"{len(datasets[name])} {name}")
    return ", ".join(parts) if parts else "sin tablas válidas"


def _hydrate_datasets_from_storage() -> bool:
    """Carga datasets: memoria → /tmp (sesión Vercel) → TiDB."""
    datasets = app_state.get("datasets") or {}
    if "siniestros" in datasets:
        return True

    loaded = _load_runtime_datasets()
    if loaded and "siniestros" in loaded:
        app_state["datasets"] = loaded
        return True

    if _should_use_live_database():
        try:
            from_db = normalize_datasets_columns(load_all_datasets())
            if from_db and "siniestros" in from_db:
                app_state["datasets"] = from_db
                return True
        except Exception:
            pass

    return False


def _try_persist_datasets_early() -> Optional[str]:
    """Guarda en TiDB justo tras subir Excel (antes del pipeline) para Vercel serverless."""
    if not _should_use_live_database() or not _should_persist_dataset_on_load():
        return None
    datasets = app_state.get("datasets") or {}
    if "siniestros" not in datasets:
        return None
    try:
        with _db_save_lock:
            init_database()
            result = save_all_datasets(
                {k: v.copy() for k, v in datasets.items()},
                full_replace=True,
            )
            for key, val in result.items():
                if isinstance(val, str) and val.startswith("error"):
                    return val
            sin_result = result.get("siniestros")
            if isinstance(sin_result, str) and sin_result.startswith("error"):
                return sin_result
            if not sin_result:
                return "No se guardaron filas en siniestros"
            dropped = result.get("_fk_rows_dropped", 0)
            repairs = result.get("_fk_repairs", 0)
            if dropped:
                return f"ok:dropped:{dropped}"
            if repairs:
                return f"ok:repaired:{repairs}"
        return "ok"
    except Exception as exc:
        return str(exc)[:160]


def _apply_analysis_meta(meta: Optional[dict]) -> None:
    if not meta or not isinstance(meta, dict):
        return
    if meta.get("model_snapshot"):
        app_state["model_snapshot"] = meta["model_snapshot"]
        app_state["model_results"] = meta.get("model_results") or meta["model_snapshot"]
    if meta.get("nlp_results") is not None:
        app_state["nlp_results"] = meta["nlp_results"]
    if meta.get("dashboard_snapshot"):
        app_state["dashboard_snapshot"] = meta["dashboard_snapshot"]
    if meta.get("executive_summary"):
        app_state["executive_summary"] = meta["executive_summary"]


def _expected_siniestros_count() -> int:
    src = app_state.get("source_row_counts") or {}
    if src.get("siniestros"):
        return int(src["siniestros"])
    ds = app_state.get("datasets") or {}
    if "siniestros" in ds and ds["siniestros"] is not None:
        return len(ds["siniestros"])
    return 0


def _reload_scored_siniestros_from_db() -> bool:
    """Carga siniestros puntuados desde TiDB (siguiente request en Vercel)."""
    if not _should_use_live_database():
        return False
    try:
        sin = load_dataframe("siniestros")
        if sin is None or len(sin) == 0:
            return False
        if "score_hibrido" not in sin.columns or sin["score_hibrido"].notna().sum() == 0:
            return False
        if "semaforo_final" not in sin.columns:
            return False
        sin = normalize_datasets_columns({"siniestros": sin})["siniestros"]
        app_state.setdefault("datasets", {})["siniestros"] = sin
        app_state["df_scored"] = sin.copy()
        app_state["df_features"] = sin.copy()
        app_state["pipeline_status"] = "completed"
        app_state["dashboard_last_payload"] = build_dashboard_payload(
            app_state["df_scored"], total_unfiltered=len(app_state["df_scored"]), active_filters=[]
        )
        _apply_analysis_meta(load_latest_analysis_meta())
        if app_state.get("agent") is None:
            app_state["agent"] = ClaimsAgent(
                app_state["df_scored"], extra_context=build_agent_context()
            )
        return True
    except Exception:
        return False


def _ensure_scored_state() -> bool:
    """Carga df_scored desde memoria, /tmp o TiDB (columnas score_hibrido / semaforo_final)."""
    if app_state.get("df_scored") is not None:
        return True
    if is_vercel_runtime():
        _hydrate_runtime_analysis()
    if app_state.get("df_scored") is not None:
        return True
    _hydrate_datasets_from_storage()
    if _reload_scored_siniestros_from_db():
        return True
    if is_vercel_runtime():
        _hydrate_runtime_analysis()
    if app_state.get("df_scored") is None:
        _hydrate_agent_from_scored_if_available()
    if app_state.get("df_scored") is not None and app_state.get("model_snapshot") is None:
        _apply_analysis_meta(load_latest_analysis_meta())
    return app_state.get("df_scored") is not None


def _ensure_session_state(require_scored: bool = False) -> bool:
    """Recupera datasets/análisis en Vercel (cold start) desde /tmp o TiDB."""
    _hydrate_datasets_from_storage()

    if require_scored:
        return _ensure_scored_state()

    return bool(app_state.get("datasets") and "siniestros" in app_state["datasets"])


def persist_datasets_to_db() -> dict:
    """Guarda todas las tablas del dataset en TiDB (reemplazo completo)."""
    if not _hydrate_datasets_from_storage():
        datasets = app_state.get("datasets") or {}
        if "siniestros" not in datasets:
            raise ValueError(
                "No hay dataset en sesión. Suba un Excel o genere datos y espere a que termine la carga."
            )
    datasets = app_state.get("datasets") or {}
    if "siniestros" not in datasets:
        raise ValueError(
            "No hay dataset en sesión. Suba un Excel o genere datos y espere a que termine la carga."
        )
    if not _should_use_live_database():
        raise ValueError("Base de datos no configurada en este entorno.")
    with _db_save_lock:
        init_database()
        result = save_all_datasets({k: v.copy() for k, v in datasets.items()})
    return {
        "status": "ok",
        "message": f"Dataset guardado en base de datos ({_standard_tables_label(datasets)}).",
        "db_save_result": result,
    }


def _collect_uploaded_documents() -> List[Dict[str, Any]]:
    if _should_use_live_database():
        try:
            return list_documentos_subidos()
        except Exception:
            pass
    return list(app_state.get("documentos_subidos", []))


def _prepare_datasets_for_pipeline() -> Dict[str, pd.DataFrame]:
    from src.utils.dataframe_columns import normalize_dataset_ids

    datasets = app_state.get("datasets") or {}
    datasets = normalize_dataset_ids(datasets)
    docs = _collect_uploaded_documents()
    if docs and "siniestros" in datasets:
        datasets = enrich_datasets_with_uploaded_documents(datasets, docs)
    app_state["datasets"] = datasets
    record_source_row_counts(datasets)
    return datasets


def _apply_pipeline_result(result: Dict[str, Any]) -> None:
    """Actualiza estado global, dashboard, ML y agente tras el pipeline."""
    docs = _collect_uploaded_documents()
    df_scored = result["df_scored"]
    if docs:
        df_scored = apply_document_post_scoring(df_scored, docs)
        result["df_scored"] = df_scored
        if docs:
            result["steps"] = list(result.get("steps", [])) + [
                {"step": "Integración PDFs cargados", "status": "ok", "documentos": len(docs)},
            ]

    dashboard_payload = build_dashboard_payload(
        df_scored, total_unfiltered=len(df_scored), active_filters=[]
    )
    dashboard_snapshot = build_dashboard_snapshot(dashboard_payload)

    record_source_row_counts(result.get("datasets") or app_state.get("datasets") or {})
    app_state["source_row_counts"]["siniestros"] = len(df_scored)

    app_state.update({
        "datasets": result["datasets"],
        "df_features": result["df_features"],
        "df_scored": df_scored,
        "model_results": result["model_results"],
        "anomaly_results": result["anomaly_results"],
        "nlp_results": result["nlp_results"],
        "dashboard_snapshot": dashboard_snapshot,
        "dashboard_last_payload": dashboard_payload,
        "model_snapshot": result["model_snapshot"],
        "pipeline_status": "completed",
        "executive_summary": result.get("executive_summary"),
    })
    if "siniestros" in app_state.get("datasets", {}):
        app_state["datasets"]["siniestros"] = df_scored.copy()

    ctx = build_agent_context()
    ctx["manifest"] = {"steps": result.get("steps", [])}
    app_state["agent"] = ClaimsAgent(df_scored, extra_context=ctx)
    if is_vercel_runtime():
        _persist_runtime_analysis({**result, "df_scored": df_scored})


def _run_analysis_after_load() -> Optional[Dict[str, Any]]:
    """Ejecuta pipeline completo tras cargar dataset (dashboard + ML + agente)."""
    if not app_state.get("datasets") or "siniestros" not in app_state["datasets"]:
        return None
    from src.app.pipeline_job import is_pipeline_running, start_background_pipeline

    if _should_pipeline_async():
        if is_pipeline_running():
            return {"pipeline_async": True, "auto_analyzed": False, "message": "Análisis ya en curso"}
        started = start_background_pipeline(_run_pipeline_sync)
        if started:
            return {"pipeline_async": True, "auto_analyzed": False}
        return {"pipeline_async": True, "auto_analyzed": False}

    return _run_pipeline_sync()


def _persist_datasets_for_analysis() -> Optional[Dict[str, Any]]:
    """Persiste Excel en TiDB antes del pipeline (local con TiDB configurado)."""
    if not _should_use_live_database() or not _should_persist_dataset_on_load():
        return None
    from src.app.pipeline_job import set_etl_progress

    set_etl_progress("db", 25, "Guardando dataset en base de datos…")
    try:
        saved = persist_datasets_to_db()
        return {"step": "Guardado en TiDB", "status": "ok", "tables": saved.get("db_save_result")}
    except Exception as exc:
        return {"step": "Guardado en TiDB", "status": "warning", "detail": str(exc)[:120]}


def _persist_and_run_pipeline_sync() -> Dict[str, Any]:
    from src.app.pipeline_job import set_etl_progress

    persist_step = _persist_datasets_for_analysis()
    set_etl_progress("ml", 50, "Motor IA: reglas, ML y NLP…")
    out = _execute_run_pipeline_body()
    set_etl_progress("dash", 100, "Dashboard y ML listos")
    if persist_step:
        out["steps"] = [persist_step] + list(out.get("steps", []))
        out["db_persisted"] = persist_step.get("status") == "ok"
    return out


def _run_pipeline_sync() -> Dict[str, Any]:
    try:
        out = _persist_and_run_pipeline_sync()
        out["auto_analyzed"] = app_state.get("df_scored") is not None
        return out
    except Exception as exc:
        if app_state.get("df_scored") is not None:
            return {
                "auto_analyzed": True,
                "status": "partial",
                "pipeline_error": str(exc),
                "total_records": len(app_state["df_scored"]),
                "steps": [{"step": "Pipeline", "status": "warning", "detail": str(exc)[:80]}],
            }
        return {"auto_analyzed": False, "pipeline_error": str(exc)}


def get_pipeline_job_status() -> dict:
    from src.app.pipeline_job import pipeline_status

    return pipeline_status()


def _documents_storage_dir() -> str:
    if is_vercel_runtime():
        path = "/tmp/fraudia_documents"
        os.makedirs(path, exist_ok=True)
        return path
    os.makedirs(DOCUMENTS_UPLOAD_FOLDER, exist_ok=True)
    return DOCUMENTS_UPLOAD_FOLDER


def _runtime_cache_dirs() -> List[str]:
    """Rutas de caché: sesión local, /tmp Vercel y caché global."""
    dirs: List[str] = []
    sid = get_request_session_id()
    if sid:
        dirs.append(os.path.join("data", "runtime_sessions", sid, "datasets"))
        if is_vercel_runtime():
            dirs.append(f"/tmp/fraudia_sessions/{sid}/datasets")
    dirs.append(os.path.join("data", "runtime_sessions", "_global", "datasets"))
    if is_vercel_runtime():
        dirs.append("/tmp/fraudia_runtime_datasets")
    return dirs


def _runtime_analysis_dirs() -> List[str]:
    dirs: List[str] = []
    sid = get_request_session_id()
    if sid:
        dirs.append(os.path.join("data", "runtime_sessions", sid, "analysis"))
        if is_vercel_runtime():
            dirs.append(f"/tmp/fraudia_sessions/{sid}/analysis")
    if is_vercel_runtime():
        dirs.append("/tmp/fraudia_runtime_analysis")
    return dirs


def _write_datasets_to_cache_dir(datasets: Dict[str, pd.DataFrame], cache_dir: str) -> None:
    os.makedirs(cache_dir, exist_ok=True)
    manifest = {
        "tables": [],
        "source_row_counts": app_state.get("source_row_counts") or {
            name: len(df) for name, df in datasets.items()
        },
    }
    for name, df in datasets.items():
        path = os.path.join(cache_dir, f"{name}.csv")
        df.to_csv(path, index=False)
        manifest["tables"].append(name)
    with open(os.path.join(cache_dir, "manifest.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False)


def _clear_runtime_analysis_cache() -> None:
    import shutil

    for path in _runtime_analysis_dirs():
        if os.path.isdir(path):
            shutil.rmtree(path, ignore_errors=True)


def _persist_runtime_analysis(result: dict) -> None:
    """Guarda resultado del pipeline en /tmp (reuso entre requests en Vercel)."""
    if not is_vercel_runtime():
        return
    df = result.get("df_scored")
    if df is None:
        return
    meta = {
        "model_snapshot": result.get("model_snapshot"),
        "model_results": result.get("model_results"),
        "anomaly_results": result.get("anomaly_results"),
        "dashboard_snapshot": result.get("dashboard_snapshot"),
        "nlp_results": result.get("nlp_results"),
        "total_records": result.get("total_records"),
        "source_row_counts": app_state.get("source_row_counts"),
        "auc_roc": result.get("auc_roc"),
    }
    df_out = df.copy()
    if "detalle_reglas" in df_out.columns:
        def _serialize_detalle(val):
            if isinstance(val, dict):
                return json.dumps(val, ensure_ascii=False)
            return val

        df_out["detalle_reglas"] = df_out["detalle_reglas"].apply(_serialize_detalle)

    for out_dir in _runtime_analysis_dirs():
        try:
            os.makedirs(out_dir, exist_ok=True)
            df_out.to_csv(os.path.join(out_dir, "siniestros_scored.csv"), index=False)
            with open(os.path.join(out_dir, "meta.json"), "w", encoding="utf-8") as f:
                json.dump(meta, f, ensure_ascii=False, default=str)
        except Exception:
            pass


def _hydrate_runtime_analysis() -> bool:
    """Recupera último análisis guardado en caché de sesión (local o /tmp)."""
    csv_path = None
    for analysis_dir in _runtime_analysis_dirs():
        candidate = os.path.join(analysis_dir, "siniestros_scored.csv")
        if os.path.exists(candidate):
            csv_path = candidate
            break
    if not csv_path:
        return False
    df = pd.read_csv(csv_path)
    if "detalle_reglas" in df.columns:
        from src.reporting.case_report import _parse_detalle

        def _cell_to_detalle(val):
            if isinstance(val, dict):
                return val
            if isinstance(val, str) and val.strip().startswith("{"):
                try:
                    return _parse_detalle(pd.Series({"detalle_reglas": val}))
                except Exception:
                    return {}
            return {}

        df["detalle_reglas"] = df["detalle_reglas"].apply(
            lambda v: _cell_to_detalle(v) if pd.notna(v) and str(v).strip() else {}
        )
    app_state["df_scored"] = df
    app_state["df_features"] = df.copy()
    app_state["pipeline_status"] = "completed"
    meta_path = os.path.join(os.path.dirname(csv_path), "meta.json")
    if os.path.exists(meta_path):
        with open(meta_path, encoding="utf-8") as f:
            meta = json.load(f)
        if meta.get("source_row_counts"):
            app_state["source_row_counts"] = meta["source_row_counts"]
        app_state["model_snapshot"] = meta.get("model_snapshot")
        if meta.get("model_results"):
            app_state["model_results"] = meta.get("model_results")
        if meta.get("anomaly_results"):
            app_state["anomaly_results"] = meta.get("anomaly_results")
        app_state["dashboard_snapshot"] = meta.get("dashboard_snapshot")
        app_state["nlp_results"] = meta.get("nlp_results") or {}
    app_state["dashboard_last_payload"] = build_dashboard_payload(
        df, total_unfiltered=len(df), active_filters=[]
    )
    app_state["agent"] = ClaimsAgent(df, extra_context=build_agent_context())
    return True


def _persist_runtime_datasets(datasets: Dict[str, pd.DataFrame]) -> None:
    """Persiste datasets por sesión hasta que se carguen otros datos."""
    if not datasets or "siniestros" not in datasets:
        return
    for cache_dir in _runtime_cache_dirs():
        try:
            _write_datasets_to_cache_dir(datasets, cache_dir)
        except Exception:
            pass


def _load_runtime_datasets() -> Dict[str, pd.DataFrame]:
    for cache_dir in _runtime_cache_dirs():
        manifest_path = os.path.join(cache_dir, "manifest.json")
        if not os.path.exists(manifest_path):
            continue
        try:
            with open(manifest_path, encoding="utf-8") as f:
                manifest = json.load(f)
            tables = manifest.get("tables") or []
            loaded: Dict[str, pd.DataFrame] = {}
            for name in tables:
                path = os.path.join(cache_dir, f"{name}.csv")
                if os.path.exists(path):
                    loaded[name] = pd.read_csv(path)
            if loaded and "siniestros" in loaded:
                if manifest.get("source_row_counts"):
                    app_state["source_row_counts"] = manifest["source_row_counts"]
                return normalize_datasets_columns(loaded)
        except Exception:
            continue
    return {}


def _hydrate_agent_from_scored_if_available() -> bool:
    """
    Inicializa agente con datos ya analizados si la tabla siniestros contiene columnas scored.
    Útil en Vercel/producción para que el chatbot funcione sin ejecutar pipeline manual.
    """
    datasets = app_state.get("datasets") or {}
    sin = datasets.get("siniestros")
    if sin is None or len(sin) == 0:
        return False

    required = {"id_siniestro", "semaforo_final", "score_hibrido"}
    if not required.issubset(set(sin.columns)):
        return False
    if sin["score_hibrido"].notna().sum() == 0:
        return False

    app_state["df_scored"] = sin.copy()
    app_state["df_features"] = sin.copy()
    app_state["pipeline_status"] = "completed"
    app_state["dashboard_last_payload"] = build_dashboard_payload(
        app_state["df_scored"], total_unfiltered=len(app_state["df_scored"]), active_filters=[]
    )
    app_state["agent"] = ClaimsAgent(app_state["df_scored"], extra_context=build_agent_context())
    return True


def ensure_vercel_data() -> None:
    """En Vercel: restaurar sesión desde /tmp; demo solo si no hay BD ni datos."""
    if not is_vercel_runtime():
        return

    if not (app_state.get("datasets") and "siniestros" in app_state["datasets"]):
        runtime_ds = _load_runtime_datasets()
        if runtime_ds and "siniestros" in runtime_ds:
            app_state["datasets"] = runtime_ds

    if app_state.get("df_scored") is None:
        _hydrate_runtime_analysis()

    if is_persistent_database_configured():
        if not (app_state.get("datasets") and "siniestros" in app_state.get("datasets", {})):
            _hydrate_datasets_from_storage()
        if app_state.get("df_scored") is None:
            _hydrate_runtime_analysis()
            _reload_scored_siniestros_from_db()
            _hydrate_agent_from_scored_if_available()
            if app_state.get("model_snapshot") is None:
                _apply_analysis_meta(load_latest_analysis_meta())
        return

    if app_state.get("datasets") and "siniestros" in app_state["datasets"]:
        return
    if app_state.get("df_scored") is not None:
        return

    try:
        bootstrap_vercel_demo(app_state)
    except Exception as exc:
        print(f"[Vercel] Error cargando bundle: {exc}")


def health() -> dict:
    return {
        "status": "ok",
        "vercel": is_vercel_runtime(),
        "live_db_mode": is_persistent_database_configured(),
        "pipeline_ready": app_state.get("df_scored") is not None,
        "stack": "fastapi",
    }


def deployment_info() -> dict:
    bundle = load_vercel_bundle() if is_vercel_runtime() else {}
    manifest = bundle.get("manifest", {})
    return {
        "vercel": is_vercel_runtime(),
        "pipeline_ready": app_state.get("df_scored") is not None,
        "openai_configured": is_openai_configured(),
        "openai_model": get_openai_model() if is_openai_configured() else None,
        "stack": "python-fastapi",
        "live_db_mode": is_persistent_database_configured(),
        "analysis_flow": (
            "build: datos → pipeline → bundle; runtime: dashboard + OpenAI"
        ) if is_vercel_runtime() else "local: carga/sintéticos → pipeline",
        "manifest": manifest,
        "records": manifest.get("total_records")
        or (len(app_state["df_scored"]) if app_state.get("df_scored") is not None else 0),
    }


def db_status(quick: bool = True) -> dict:
    """Estado BD. quick=True evita COUNT por tabla (lento en TiDB Cloud)."""
    port = os.environ.get("FLASK_PORT", "5001")
    app_url = os.environ.get("APP_URL", f"http://localhost:{port}")
    base = {
        "app_url": app_url,
        "local": not is_vercel_runtime(),
    }
    if is_vercel_runtime() and not is_persistent_database_configured():
        return {
            **base,
            "status": "ok",
            "type": "In-memory (Vercel)",
            "host": "demo",
            "message": "Datos desde bundle embebido (CSV + JSON).",
        }
    conn = test_connection()
    conn.update(base)
    if conn["status"] == "ok" and not quick:
        try:
            conn["stats"] = get_db_stats()
            conn["history"] = get_analysis_history()
        except Exception as exc:
            conn["stats_error"] = str(exc)[:120]
    return conn


def _start_load_workflow() -> Dict[str, Any]:
    """
    Ejecuta guardado en BD + pipeline.
    En Vercel: mismo request (los hilos en background no sobreviven).
    Local: segundo plano.
    """
    _ensure_session_state(require_scored=False)
    from src.app.pipeline_job import is_pipeline_running, start_background_pipeline

    if is_vercel_runtime():
        from src.app.pipeline_job import begin_pipeline_tracking, set_etl_progress

        try:
            begin_pipeline_tracking("Procesando en servidor…")
            set_etl_progress("excel", 100, "Archivo cargado")
            set_etl_progress("parse", 100, "Tablas validadas")
            set_etl_progress("valid", 100, "Esquema OK")
            result = _persist_and_run_pipeline_sync()
            return {"mode": "sync", "pipeline_async": False, "result": result}
        except Exception as exc:
            return {"mode": "error", "pipeline_async": False, "error": str(exc)}

    if is_pipeline_running():
        return {"mode": "async", "pipeline_async": True, "already_running": True}
    started = start_background_pipeline(_persist_and_run_pipeline_sync)
    return {"mode": "async", "pipeline_async": bool(started)}


def _apply_workflow_to_response(resp: dict, workflow: Dict[str, Any]) -> None:
    if workflow.get("mode") == "sync" and workflow.get("result"):
        pipe = workflow["result"]
        resp["pipeline"] = pipe
        resp["pipeline_async"] = False
        if pipe.get("auto_analyzed"):
            resp["message"] += (
                f" Análisis completado: {pipe.get('total_records', 0)} casos en dashboard y ML."
            )
        elif pipe.get("pipeline_error"):
            resp["message"] += f" Aviso: {str(pipe['pipeline_error'])[:100]}"
    elif workflow.get("mode") == "error":
        resp["message"] += f" Error en análisis: {workflow.get('error', '')[:120]}"
    elif workflow.get("pipeline_async"):
        resp["pipeline_async"] = True
        resp["message"] += " Análisis en segundo plano…"


def db_init() -> dict:
    init_database()
    return {"status": "ok", "message": "Tablas creadas en la base de datos"}


def build_template_excel() -> io.BytesIO:
    """Plantilla vacía según esquema del reto (src/ingestion/schema.py)."""
    from src.ingestion.schema import FIELD_DESCRIPTIONS, TEMPLATE_SHEETS

    guia_rows = []
    for table, fields in FIELD_DESCRIPTIONS.items():
        for field, desc in fields.items():
            guia_rows.append({"Tabla": table, "Campo": field, "Descripción": desc})
    guia = pd.DataFrame(guia_rows)
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        for sheet, cols in TEMPLATE_SHEETS.items():
            pd.DataFrame(columns=cols).to_excel(writer, sheet_name=sheet, index=False)
        guia.to_excel(writer, sheet_name="Campos", index=False)
    buf.seek(0)
    return buf


def _dataset_summary_message(prefix: str, datasets: dict, db_msg: str = "") -> str:
    parts = []
    if "siniestros" in datasets:
        parts.append(f"{len(datasets['siniestros'])} siniestros")
    for t in ("polizas", "asegurados", "proveedores", "documentos"):
        if t in datasets:
            parts.append(f"{len(datasets[t])} {t}")
    return f"{prefix}: {', '.join(parts)}.{db_msg}"


def upload_documents(
    files: list,
    link_to_dataset: bool = False,
    tipo_documento: Optional[str] = None,
) -> dict:
    """
    files: lista de (filename, bytes).
    Extrae texto del PDF, analiza y persiste en documentos_subidos.
    """
    if isinstance(link_to_dataset, str):
        link_to_dataset = link_to_dataset.lower() in ("true", "1", "yes", "on")
    if not files:
        raise ValueError("No se recibieron archivos PDF.")

    import uuid
    from datetime import datetime

    datasets = app_state.get("datasets") or {}
    processed = []
    storage = _documents_storage_dir()

    for filename, content in files:
        if not filename.lower().endswith(".pdf"):
            continue
        parsed = process_pdf_upload(filename, content, tipo_hint=tipo_documento or None)
        campos = parsed.get("campos_extraidos") or {}
        analisis = analyze_document(
            tipo_documento=parsed["tipo_documento"],
            texto_extraido=parsed.get("texto_extraido") or "",
            campos=campos,
            datasets=datasets if link_to_dataset else None,
            vincular_dataset=link_to_dataset,
        )

        safe_name = f"{uuid.uuid4().hex[:10]}_{os.path.basename(filename)}"
        ruta = os.path.join(storage, safe_name)
        with open(ruta, "wb") as f:
            f.write(content)

        id_doc = parsed.get("id_documento") or campos.get("id_documento")
        if not id_doc:
            id_doc = f"DOC-UP-{uuid.uuid4().hex[:6].upper()}"

        record = {
            "id_documento": id_doc,
            "id_siniestro": parsed.get("id_siniestro") or campos.get("id_siniestro"),
            "tipo_documento": parsed["tipo_documento"],
            "nombre_archivo": parsed["nombre_archivo"],
            "ruta_almacen": ruta,
            "texto_extraido": parsed.get("texto_extraido"),
            "campos_extraidos": campos_to_json(campos),
            "score_documento": analisis["score_documento"],
            "semaforo": analisis["semaforo"],
            "alertas": json.dumps(analisis["alertas"], ensure_ascii=False),
            "inconsistencias": json.dumps(analisis["inconsistencias"], ensure_ascii=False),
            "vinculado_dataset": link_to_dataset,
            "estado": "analizado",
            "fecha_analisis": datetime.utcnow(),
        }

        if _should_use_live_database():
            db_id = save_documento_subido(record)
        else:
            db_id = len(app_state.get("documentos_subidos", [])) + 1

        public = {
            "id": db_id,
            "id_documento": record["id_documento"],
            "id_siniestro": record["id_siniestro"],
            "tipo_documento": record["tipo_documento"],
            "nombre_archivo": record["nombre_archivo"],
            "score_documento": record["score_documento"],
            "semaforo": record["semaforo"],
            "alertas": analisis["alertas"],
            "inconsistencias": analisis["inconsistencias"],
            "campos_extraidos": campos,
            "vinculado_dataset": link_to_dataset,
            "estado": "analizado",
            "encontrado_en_dataset": analisis.get("encontrado_en_dataset"),
        }
        if not _should_use_live_database():
            app_state.setdefault("documentos_subidos", []).insert(0, public)
        else:
            public["id"] = db_id

        if link_to_dataset and record["id_siniestro"]:
            app_state["datasets"] = merge_document_into_datasets(
                datasets,
                id_documento=id_doc,
                id_siniestro=record["id_siniestro"],
                tipo_documento=record["tipo_documento"],
                nombre_archivo=record["nombre_archivo"],
                analisis=analisis,
            )
            datasets = app_state["datasets"]

        processed.append(public)

    if not processed:
        raise ValueError("Solo se aceptan archivos PDF (.pdf).")

    resp = {
        "status": "success",
        "message": f"{len(processed)} documento(s) procesado(s) y analizado(s).",
        "documents": processed,
        "link_to_dataset": link_to_dataset,
        "tipos_aceptados": list(TIPOS_DOCUMENTO.values()),
    }
    if app_state.get("datasets") and "siniestros" in app_state["datasets"]:
        pipeline_out = _run_analysis_after_load()
        if pipeline_out:
            resp["pipeline"] = pipeline_out
            if pipeline_out.get("auto_analyzed"):
                resp["message"] += (
                    f" Pipeline ejecutado: {pipeline_out.get('total_records', 0)} siniestros "
                    "en dashboard y modelo ML."
                )
            elif pipeline_out.get("pipeline_error"):
                resp["message"] += f" (Pipeline: {pipeline_out['pipeline_error']})"
    return resp


def list_uploaded_documents() -> dict:
    if _should_use_live_database():
        docs = list_documentos_subidos()
    else:
        docs = list(app_state.get("documentos_subidos", []))
    return {"status": "ok", "documents": docs, "total": len(docs)}


def get_uploaded_document(doc_id: int) -> dict:
    if _should_use_live_database():
        doc = get_documento_subido(doc_id)
    else:
        doc = next((d for d in app_state.get("documentos_subidos", []) if d.get("id") == doc_id), None)
    if not doc:
        raise LookupError(f"Documento {doc_id} no encontrado")
    return {"status": "ok", "document": doc}


def upload_dataset(filename: str, content: bytes) -> dict:
    ext = os.path.splitext(filename)[1].lower()
    if ext not in (".csv", ".xlsx", ".xls"):
        raise ValueError("Formato no soportado. Use CSV o Excel (.xlsx).")
    file_obj = io.BytesIO(content)
    file_obj.name = filename
    new_tables = {
        name: ensure_str_columns(df)
        for name, df in load_from_upload(file_obj, filename).items()
    }
    if not new_tables:
        raise ValueError("El archivo no contiene datos válidos (hojas vacías).")
    apply_loaded_datasets(new_tables)
    reset_pipeline_state()
    _clear_runtime_analysis_cache()
    session_id = ensure_request_session_id()
    _persist_runtime_datasets(app_state["datasets"])
    db_early = _try_persist_datasets_early()
    validation = validate_datasets(app_state["datasets"])
    tables_info = {
        name: {"rows": len(df), "columns": len(df.columns)}
        for name, df in app_state["datasets"].items()
    }

    persist_planned = (
        validation["has_siniestros"]
        and _should_use_live_database()
        and _should_persist_dataset_on_load()
    )
    auto_pipeline = validation["has_siniestros"] and _should_auto_pipeline_on_load()
    db_msg = ""
    if validation["has_siniestros"]:
        if not _should_use_live_database():
            db_msg = " (solo memoria en Vercel demo)"
        elif persist_planned:
            db_msg = " (TiDB + análisis en segundo plano)"
    msg = f"'{filename}' cargado: {_standard_tables_label(app_state['datasets'])}." + db_msg
    resp = {
        "status": "success" if validation["has_siniestros"] else "warning",
        "message": msg,
        "tables": tables_info,
        "has_siniestros": validation["has_siniestros"],
        "warnings": validation["warnings"],
        "loaded_tables": list(new_tables.keys()),
        "persist_to_db_on_analyze": persist_planned,
        "auto_pipeline": auto_pipeline,
        "session_id": session_id,
    }
    if db_early == "ok" or (isinstance(db_early, str) and db_early.startswith("ok:")):
        resp["db_persisted_on_upload"] = True
        resp["message"] += " Datos guardados en base de datos."
        if isinstance(db_early, str) and db_early.startswith("ok:dropped:"):
            n_drop = int(db_early.split(":")[-1])
            resp["db_fk_rows_dropped"] = n_drop
            resp["warnings"] = list(resp.get("warnings") or []) + [
                f"Se omitieron {n_drop} siniestros con referencias inválidas (póliza/asegurado no encontrados en el Excel)."
            ]
        elif isinstance(db_early, str) and db_early.startswith("ok:repaired:"):
            n_fix = int(db_early.split(":")[-1])
            resp["db_fk_repairs"] = n_fix
            resp["warnings"] = list(resp.get("warnings") or []) + [
                f"Se alinearon {n_fix} registros padre (asegurado/póliza) para conservar todos los siniestros del archivo."
            ]
    elif db_early:
        resp["db_persist_warning"] = db_early
    if validation["has_siniestros"]:
        resp["auto_pipeline"] = True
        _apply_workflow_to_response(resp, _start_load_workflow())
    return resp


def load_synthetic() -> dict:
    from src.ingestion.generate_synthetic import generate_datasets

    seed_used, raw = generate_datasets(seed=None)
    datasets = {name: ensure_str_columns(df) for name, df in raw.items()}
    apply_loaded_datasets(datasets)
    reset_pipeline_state()
    _clear_runtime_analysis_cache()
    session_id = ensure_request_session_id()
    _persist_runtime_datasets(app_state["datasets"])
    db_early = _try_persist_datasets_early()
    tables_info = {
        name: {"rows": len(df), "columns": len(df.columns)}
        for name, df in app_state["datasets"].items()
    }

    persist_planned = _should_persist_dataset_on_load() and _should_use_live_database()
    auto_pipeline = _should_auto_pipeline_on_load()
    db_msg = " (TiDB + análisis en segundo plano)" if persist_planned else ""
    resp = {
        "status": "success",
        "message": _dataset_summary_message(
            "Datos aleatorios generados",
            app_state["datasets"],
            db_msg,
        ),
        "seed": seed_used,
        "tables": tables_info,
        "has_siniestros": True,
        "persist_to_db_on_analyze": persist_planned,
        "auto_pipeline": auto_pipeline,
        "session_id": session_id,
    }
    if db_early == "ok":
        resp["db_persisted_on_upload"] = True
    elif db_early:
        resp["db_persist_warning"] = db_early
    resp["auto_pipeline"] = True
    _apply_workflow_to_response(resp, _start_load_workflow())
    return resp


def load_from_db() -> dict:
    if is_vercel_runtime() and not is_persistent_database_configured():
        datasets = _load_runtime_datasets()
        if datasets and "siniestros" in datasets:
            app_state["datasets"] = datasets
            _hydrate_runtime_analysis()
            return {
                "status": "success",
                "message": "Datos recuperados de sesión Vercel (/tmp). Ejecute análisis si aún no lo hizo.",
                "tables": {
                    n: {"rows": len(d), "columns": len(d.columns)}
                    for n, d in datasets.items()
                },
                "has_siniestros": True,
                "pipeline_ready": app_state.get("df_scored") is not None,
            }
        raise ValueError(
            "En Vercel sin base de datos: suba un dataset o genere datos sintéticos y ejecute el análisis."
        )

    if not _hydrate_datasets_from_storage():
        raise ValueError("No hay datos en la base de datos. Suba un archivo primero.")
    datasets = app_state.get("datasets") or {}
    if "siniestros" not in datasets:
        raise ValueError("No hay datos en la base de datos. Suba un archivo primero.")
    reset_pipeline_state()
    _ensure_scored_state()
    db_info = test_connection()
    return {
        "status": "success",
        "message": f"Datos cargados desde {db_info.get('type', 'DB')}",
        "tables": {n: {"rows": len(d), "columns": len(d.columns)} for n, d in datasets.items()},
        "has_siniestros": True,
        "pipeline_ready": app_state.get("agent") is not None,
    }


def run_pipeline() -> dict:
    from src.app.pipeline_job import is_pipeline_running, start_background_pipeline

    if _should_pipeline_async() and not is_vercel_runtime():
        if is_pipeline_running():
            st = get_pipeline_job_status()
            if st.get("status") == "completed" and st.get("result"):
                return st["result"]
            return {"status": "running", "message": "El análisis ya está en curso", "pipeline_async": True}
        if start_background_pipeline(_run_pipeline_sync):
            return {"status": "running", "pipeline_async": True, "message": "Análisis iniciado en segundo plano"}
        return {"status": "running", "pipeline_async": True}

    return _execute_run_pipeline_body()


def _execute_run_pipeline_body() -> dict:
    if not _hydrate_datasets_from_storage():
        if is_vercel_runtime() and not is_persistent_database_configured():
            boot = bootstrap_vercel_demo(app_state)
            bundle = load_vercel_bundle() or {}
            bundle_steps = (
                (bundle.get("manifest") or {}).get("steps")
                or (boot.get("pipeline_steps") if isinstance(boot, dict) else None)
                or []
            )
            steps = [
                {"step": str(step), "status": "ok"} if not isinstance(step, dict) else step
                for step in bundle_steps
            ]
            if not steps:
                steps = [{"step": "Carga de bundle Vercel", "status": "ok"}]
            if app_state.get("df_scored") is not None:
                return {
                    "status": "success",
                    "message": "Análisis cargado desde build Vercel. Redeploy para recalcular.",
                    "total_records": len(app_state["df_scored"]),
                    "duration_seconds": 0,
                    "steps": steps,
                    "vercel": True,
                    "bootstrap": boot,
                }
        if not _hydrate_datasets_from_storage():
            hint = (
                " Suba el Excel de nuevo (misma pestaña) o configure DATABASE_URL en Vercel "
                "y pulse Guardar en Base de datos tras cargar."
            )
            raise ValueError(
                "No hay datos cargados. Suba un archivo o cargue datos sintéticos." + hint
            )
    t_start = time.time()
    app_state["pipeline_status"] = "running"

    datasets = _prepare_datasets_for_pipeline()
    result = execute_full_pipeline(datasets)
    _apply_pipeline_result(result)
    df_scored = app_state["df_scored"]
    sem_counts = df_scored["semaforo_final"].value_counts()
    db_payload = {
        "total": len(df_scored),
        "rojos": int(sem_counts.get("Rojo", 0)),
        "amarillos": int(sem_counts.get("Amarillo", 0)),
        "verdes": int(sem_counts.get("Verde", 0)),
        "score_prom": float(df_scored["score_hibrido"].mean()),
        "auc": result.get("auc_roc"),
        "duracion": time.time() - t_start,
    }

    def _persist_scores(df, payload, pipeline_result):
        meta = {
            "model_snapshot": pipeline_result.get("model_snapshot"),
            "nlp_results": pipeline_result.get("nlp_results"),
            "dashboard_snapshot": app_state.get("dashboard_snapshot"),
            "executive_summary": app_state.get("executive_summary"),
        }
        if _should_sync_scores_after_pipeline():
            replace_siniestros_scored(df)
        save_analysis_run(**payload, meta=meta)

    steps_out = list(result["steps"])
    if _should_use_live_database():
        try:
            _persist_scores(df_scored.copy(), db_payload, result)
            steps_out.append({"step": "Scores y análisis en TiDB", "status": "ok"})
        except Exception as exc:
            steps_out.append({
                "step": "Scores y análisis en TiDB",
                "status": "warning",
                "detail": str(exc)[:120],
            })
    else:
        _persist_runtime_analysis({**result, "df_scored": df_scored})

    if is_vercel_runtime():
        _persist_runtime_analysis({**result, "df_scored": df_scored})

    return {
        "status": "success",
        "steps": steps_out,
        "executive_summary": app_state.get("executive_summary"),
        "total_records": len(df_scored),
        "duration_seconds": round(time.time() - t_start, 2),
        "analyzed_from_upload": True,
        "auto_analyzed": True,
        "semaforo_counts": {
            "Rojo": int(sem_counts.get("Rojo", 0)),
            "Amarillo": int(sem_counts.get("Amarillo", 0)),
            "Verde": int(sem_counts.get("Verde", 0)),
        },
    }


def dashboard_filters() -> dict:
    if not _ensure_session_state(require_scored=True):
        raise ValueError("Pipeline no ejecutado. Cargue datos y ejecute el análisis.")
    df = app_state.get("df_scored")
    return get_filter_options(df)


def dashboard_data(query_params) -> dict:
    if not _ensure_session_state(require_scored=True):
        raise ValueError("Pipeline no ejecutado. Cargue datos y ejecute el análisis.")
    df = app_state.get("df_scored")
    params = params_from_request(query_params)
    df_filtered, active_filters = apply_dashboard_filters(df, params)
    source_total = _expected_siniestros_count() or len(df)
    payload = build_dashboard_payload(
        df_filtered,
        total_unfiltered=len(df),
        active_filters=active_filters,
        source_total_siniestros=source_total,
    )
    app_state["dashboard_last_payload"] = payload
    snap = app_state.get("model_snapshot") or {}
    if isinstance(payload.get("fraudia"), dict) and isinstance(snap, dict):
        ops = payload["fraudia"].setdefault("ops", {})
        if snap.get("auc_roc") is not None:
            ops["auc_roc"] = round(float(snap["auc_roc"]), 3)
        if snap.get("precision_fraude") is not None:
            p = float(snap["precision_fraude"])
            ops["precision_pct"] = round(p * 100 if p <= 1 else p, 1)
        if snap.get("active_model"):
            ops["model_name"] = snap["active_model"]
    return payload


def _asegurado_nombre_for_row(row: pd.Series) -> Optional[str]:
    """Resuelve nombre del asegurado desde datasets de sesión."""
    datasets = app_state.get("datasets") or {}
    aseg_df = datasets.get("asegurados")
    if aseg_df is None or getattr(aseg_df, "empty", True):
        return None
    aid = row.get("id_asegurado")
    if aid is None or (isinstance(aid, float) and pd.isna(aid)):
        return None
    aid_s = str(aid).strip().upper()
    if not aid_s:
        return None
    col = aseg_df["id_asegurado"].astype(str).str.strip().str.upper()
    match = aseg_df[col == aid_s]
    if match.empty:
        return None
    r = match.iloc[0]
    for field in ("nombres_asegurado", "nombre", "nombres", "nombre_completo"):
        if field in r.index and pd.notna(r[field]):
            return str(r[field]).strip()
    return None


def _datasets_for_case_report() -> Dict[str, pd.DataFrame]:
    """Datasets de sesión + caché /tmp (Vercel) para enriquecer el reporte."""
    datasets = dict(app_state.get("datasets") or {})
    if is_vercel_runtime():
        runtime = _load_runtime_datasets()
        if runtime:
            for name, df in runtime.items():
                if name not in datasets or datasets[name] is None or getattr(datasets[name], "empty", True):
                    datasets[name] = df
    return datasets


def get_case(case_id: str) -> dict:
    if not _ensure_scored_state():
        if not _ensure_session_state(require_scored=True):
            raise ValueError("Pipeline no ejecutado. Cargue datos y active el motor IA.")
    df = app_state.get("df_scored")
    mask = df["id_siniestro"].str.upper() == case_id.upper()
    if mask.sum() == 0:
        raise LookupError(f"Siniestro {case_id} no encontrado")
    row = df[mask].iloc[0]
    from src.reporting.case_report import (
        build_case_report,
        build_case_report_extra,
        enrich_case_row,
    )

    datasets = _datasets_for_case_report()
    row = enrich_case_row(row, datasets)
    extra = build_case_report_extra(row, datasets)
    nombre = _asegurado_nombre_for_row(row)
    if nombre:
        extra["nombre_asegurado"] = nombre
    case = build_case_report(row, extra=extra or None)
    pdfs = documents_for_siniestro(_collect_uploaded_documents(), case_id)
    if pdfs:
        case["documentos_pdf"] = [
            {
                "nombre": d.get("nombre_archivo"),
                "tipo": d.get("tipo_documento"),
                "semaforo": d.get("semaforo"),
                "score": d.get("score_documento"),
                "alertas": [a.get("mensaje") for a in (d.get("alertas") or [])[:5] if isinstance(a, dict)],
            }
            for d in pdfs
        ]
    return case


def agent_status() -> dict:
    from src.ai_agent.llm_router import llm_status

    df = app_state.get("df_scored")
    count = len(df) if df is not None and not getattr(df, "empty", True) else None
    status = llm_status()
    return {
        **status,
        "openai_configured": status.get("openai_configured", is_openai_configured()),
        "openai_model": status.get("openai_model") or (
            get_openai_model() if is_openai_configured() else None
        ),
        "pipeline_ready": app_state.get("agent") is not None,
        "siniestros_count": count,
        "vercel": is_vercel_runtime(),
        "agent_mode": "gemini_conversacional" if status.get("llm_provider") == "gemini" else (
            "chatgpt_conversacional" if status.get("llm_provider") == "openai" else "reglas_local"
        ),
    }


def _ensure_agent_ready() -> bool:
    """Inicializa el agente si hay datos en memoria, /tmp o BD."""
    if app_state.get("agent") is not None:
        return True

    if is_vercel_runtime():
        _hydrate_runtime_analysis()
    if app_state.get("agent") is not None:
        return True

    if app_state.get("df_scored") is not None:
        app_state["agent"] = ClaimsAgent(
            app_state["df_scored"], extra_context=build_agent_context()
        )
        return True

    if _should_use_live_database():
        try:
            datasets = normalize_datasets_columns(load_all_datasets())
            if datasets:
                app_state["datasets"] = datasets
                _hydrate_agent_from_scored_if_available()
        except Exception:
            pass
    if app_state.get("agent") is not None:
        return True

    sin = (app_state.get("datasets") or {}).get("siniestros")
    if sin is not None and len(sin) > 0 and "id_siniestro" in sin.columns:
        app_state["df_scored"] = sin.copy()
        app_state["agent"] = ClaimsAgent(
            app_state["df_scored"], extra_context=build_agent_context()
        )
        return True

    return False


def _normalize_chat_history(body: dict) -> list:
    raw = (body or {}).get("history") or []
    if not isinstance(raw, list):
        return []
    turns = []
    for item in raw[-10:]:
        if not isinstance(item, dict):
            continue
        role = str(item.get("role", "user")).strip().lower()
        content = str(item.get("content", "")).strip()
        if not content:
            continue
        if role in ("assistant", "model", "agent"):
            turns.append({"role": "model", "content": content[:4000]})
        else:
            turns.append({"role": "user", "content": content[:4000]})
    return turns


def agent_query(body: dict) -> dict:
    if not _ensure_agent_ready():
        raise ValueError(
            "Agente no inicializado. Cargue un Excel, pulse «Activar motor IA» o espere a que termine el análisis."
        )
    agent = app_state["agent"]
    question = (body or {}).get("question", "")
    if not question:
        raise ValueError("Pregunta vacía")
    df = app_state.get("df_scored")
    if df is not None and len(df) > 0:
        app_state["dashboard_last_payload"] = build_dashboard_payload(
            df,
            total_unfiltered=len(df),
            active_filters=[],
            source_total_siniestros=_expected_siniestros_count() or len(df),
        )
    agent.set_extra_context(build_agent_context())
    history = _normalize_chat_history(body or {})
    result = agent.query(question, history=history)
    if "datos" in result and result["datos"] is not None:
        items = result["datos"] if isinstance(result["datos"], list) else [result["datos"]]
        for item in items:
            if isinstance(item, dict):
                for k, v in list(item.items()):
                    if isinstance(v, float) and v != v:
                        item[k] = None
    return result


def cases_all_list() -> dict:
    if not _ensure_session_state(require_scored=True):
        raise ValueError("No hay análisis disponible. Cargue datos y ejecute el análisis.")
    df = app_state["df_scored"].copy()
    score_col = "score_hibrido" if "score_hibrido" in df.columns else "score_reglas"
    sem_col = "semaforo_final" if "semaforo_final" in df.columns else "semaforo_reglas"
    cols = [
        "id_siniestro", "ramo", "cobertura", "monto_reclamado", score_col, sem_col,
        "alertas_reglas", "beneficiario", "estado", "sucursal", "score_reglas",
        "ml_fraud_probability", "anomaly_score",
    ]
    cols = [c for c in cols if c in df.columns]
    out = df[cols].rename(columns={
        score_col: "score",
        sem_col: "tipo_semaforo",
        "ramo": "tipo_ramo",
    })
    records = out.where(pd.notnull(out), None).to_dict(orient="records")
    return {"total": len(records), "cases": records}


def case_forensic_pdf(case_id: str) -> bytes:
    if not _ensure_scored_state():
        if not _ensure_session_state(require_scored=True):
            raise ValueError("No hay análisis disponible para generar el PDF.")
    case = get_case(case_id)
    from src.reporting.case_pdf import build_case_forensic_pdf

    try:
        return build_case_forensic_pdf(case)
    except Exception as exc:
        raise ValueError(f"No se pudo generar el PDF: {exc}") from exc


def _build_ml_probability_charts(df: pd.DataFrame) -> Dict[str, Any]:
    """
    Gráficos de probabilidad ML vs decisión operativa (semáforo).
    Destaca casos con alta prob. de fraude sin alerta roja.
    """
    if df is None or getattr(df, "empty", True) or "ml_fraud_probability" not in df.columns:
        return {}

    prob = pd.to_numeric(df["ml_fraud_probability"], errors="coerce").fillna(0).clip(0, 1)
    sem_col = "semaforo_final" if "semaforo_final" in df.columns else (
        "semaforo_reglas" if "semaforo_reglas" in df.columns else None
    )
    if not sem_col:
        return {}

    sem = df[sem_col].astype(str).str.strip().str.capitalize()
    not_red = ~sem.eq("Rojo")
    hidden_mask = not_red & (prob >= 0.5)

    bands_def = [
        (0.0, 0.3, "0-30%"),
        (0.3, 0.5, "30-50%"),
        (0.5, 0.7, "50-70%"),
        (0.7, 0.85, "70-85%"),
        (0.85, 1.001, "85-100%"),
    ]
    hidden_labels = []
    hidden_counts = []
    for lo, hi, label in bands_def:
        m = not_red & (prob >= lo) & (prob < hi)
        hidden_labels.append(label)
        hidden_counts.append(int(m.sum()))

    semaforos = ["Verde", "Amarillo", "Rojo"]
    avg_prob_pct = []
    high_prob_counts = []
    totals = []
    for s in semaforos:
        m = sem.eq(s)
        if not m.any():
            avg_prob_pct.append(0.0)
            high_prob_counts.append(0)
            totals.append(0)
            continue
        p = prob[m]
        totals.append(int(m.sum()))
        avg_prob_pct.append(round(float(p.mean()) * 100, 1))
        high_prob_counts.append(int((p >= 0.7).sum()))

    hidden_total = int(hidden_mask.sum())
    hidden_high = int((not_red & (prob >= 0.7)).sum())

    return {
        "prob_hidden_risk": {
            "labels": hidden_labels,
            "counts": hidden_counts,
            "total_sin_rojo_alta_prob": hidden_total,
            "total_sin_rojo_prob_70": hidden_high,
        },
        "prob_by_semaforo": {
            "semaforos": semaforos,
            "avg_prob_pct": avg_prob_pct,
            "high_prob_counts": high_prob_counts,
            "totals": totals,
        },
        "casos_prob_alta_sin_rojo": hidden_high,
    }


def _linear_forecast(values: List[float], periods: int) -> List[float]:
    """Proyección simple por tendencia lineal (últimos puntos)."""
    if not values:
        return [0.0] * periods
    if len(values) == 1:
        return [max(0.0, float(values[0]))] * periods
    window = values[-min(7, len(values)) :]
    n = len(window)
    xs = list(range(n))
    mean_x = sum(xs) / n
    mean_y = sum(window) / n
    num = sum((xs[i] - mean_x) * (window[i] - mean_y) for i in range(n))
    den = sum((x - mean_x) ** 2 for x in xs) or 1.0
    slope = num / den
    intercept = mean_y - slope * mean_x
    start_x = n
    return [max(0.0, intercept + slope * (start_x + i)) for i in range(periods)]


def _ml_forecast_series(values: List[float], periods: int = 30) -> Dict[str, Any]:
    """Proyección ML (regresión lineal) con banda de confianza sobre serie diaria."""
    import numpy as np
    from sklearn.linear_model import LinearRegression

    y = np.array([float(v) for v in values], dtype=float)
    if len(y) < 3:
        fc = _linear_forecast(list(y), periods)
        return {
            "forecast": [round(v, 2) for v in fc],
            "upper": [round(v * 1.2, 2) for v in fc],
            "lower": [round(max(0.0, v * 0.8), 2) for v in fc],
            "confidence_pct": 58,
            "method": "Tendencia lineal (histórico corto)",
            "r2": None,
            "slope": None,
        }

    X = np.arange(len(y)).reshape(-1, 1)
    model = LinearRegression()
    model.fit(X, y)
    preds_train = model.predict(X)
    residuals = y - preds_train
    std = float(np.std(residuals)) if len(residuals) > 1 else max(1.0, float(np.mean(y)) * 0.1)
    future_X = np.arange(len(y), len(y) + periods).reshape(-1, 1)
    fc_raw = model.predict(future_X)
    fc = [max(0.0, float(v)) for v in fc_raw]
    upper = [round(v + 1.96 * std, 2) for v in fc]
    lower = [round(max(0.0, v - 1.96 * std), 2) for v in fc]
    ss_res = float(np.sum(residuals ** 2))
    ss_tot = float(np.sum((y - np.mean(y)) ** 2)) or 1.0
    r2 = max(0.0, min(1.0, 1.0 - ss_res / ss_tot))
    confidence_pct = int(min(95, max(55, 55 + r2 * 38)))
    return {
        "forecast": [round(v, 2) for v in fc],
        "upper": upper,
        "lower": lower,
        "confidence_pct": confidence_pct,
        "method": "Regresión lineal (scikit-learn)",
        "r2": round(r2, 3),
        "slope": round(float(model.coef_[0]), 4),
    }


def _build_predictive_kpis(df: pd.DataFrame, metrics: dict, forecast_block: Optional[dict]) -> Dict[str, Any]:
    """KPIs reales de cartera para el panel predictivo ML."""
    sem_col = "semaforo_final" if "semaforo_final" in df.columns else "semaforo_reglas"
    score_col = "score_hibrido" if "score_hibrido" in df.columns else "score_reglas"
    total = len(df)
    rojos = amarillos = verdes = 0
    if sem_col in df.columns:
        vc = df[sem_col].value_counts()
        rojos = int(vc.get("Rojo", 0))
        amarillos = int(vc.get("Amarillo", 0))
        verdes = int(vc.get("Verde", 0))
    score_prom = round(float(df[score_col].mean()), 1) if score_col in df.columns else 0.0
    prob_ia = round(float(df["ml_fraud_probability"].fillna(0).mean()) * 100, 1) if "ml_fraud_probability" in df.columns else 0.0
    anom = int((df["anomaly_score"].fillna(0) > 0.8).sum()) if "anomaly_score" in df.columns else int(metrics.get("anomalies_detected") or 0)
    monto_riesgo = 0.0
    if sem_col in df.columns and "monto_reclamado" in df.columns:
        monto_riesgo = round(float(df.loc[df[sem_col].isin(["Rojo", "Amarillo"]), "monto_reclamado"].sum()), 0)
    tasa_sospechosos = round(((rojos + amarillos) / total) * 100, 1) if total else 0.0
    porcentaje_rojo = round((rojos / total) * 100, 1) if total else 0.0
    fc_sum = 0
    fc_avg = 0.0
    if forecast_block and forecast_block.get("forecast_rojos"):
        fc_vals = [float(x) for x in forecast_block["forecast_rojos"]]
        fc_sum = int(round(sum(fc_vals)))
        fc_avg = round(sum(fc_vals) / len(fc_vals), 1) if fc_vals else 0.0
    auc = metrics.get("cv_auc_mean") or metrics.get("auc_roc")

    def _pct_metric(key: str, alt: str = "") -> float:
        raw = float(metrics.get(key) or metrics.get(alt) or 0)
        return round(raw * 100 if 0 <= raw <= 1 else raw, 1)

    return {
        "total_siniestros": total,
        "casos_rojos": rojos,
        "casos_amarillos": amarillos,
        "casos_verdes": verdes,
        "porcentaje_rojo": porcentaje_rojo,
        "tasa_sospechosos": tasa_sospechosos,
        "score_promedio": score_prom,
        "prob_ia_promedio": prob_ia,
        "anomalias": anom,
        "monto_riesgo": monto_riesgo,
        "forecast_30d_total": fc_sum,
        "forecast_30d_promedio_dia": fc_avg,
        "auc_roc": round(float(auc), 3) if auc is not None else None,
        "precision_pct": _pct_metric("precision_fraude"),
        "recall_pct": _pct_metric("recall_fraude", "recall"),
    }


def _fraud_trend_from_monthly(temporal_risk: List[Dict]) -> Dict[str, Any]:
    if len(temporal_risk) < 2:
        return {"delta_pct": 0, "direction": "neutral", "label": "Sin histórico suficiente"}
    recent = temporal_risk[-1]
    prev = temporal_risk[-2]
    r_now = float(recent.get("Rojo") or 0)
    r_prev = float(prev.get("Rojo") or 0) or 1.0
    delta = round((r_now - r_prev) / r_prev * 100, 1)
    direction = "up" if delta > 2 else "down" if delta < -2 else "neutral"
    sign = "+" if delta > 0 else ""
    return {
        "delta_pct": delta,
        "direction": direction,
        "label": f"{sign}{delta}% casos críticos vs. mes anterior",
    }


def _build_ml_predictive_insights(df: pd.DataFrame, metrics: dict) -> Dict[str, Any]:
    """Series temporales, forecast 30d, Sankey, red y heatmaps para análisis predictivo."""
    score_col = "score_hibrido" if "score_hibrido" in df.columns else "score_reglas"
    sem_col = "semaforo_final" if "semaforo_final" in df.columns else "semaforo_reglas"
    insights: Dict[str, Any] = {
        "monthly_history": [],
        "risk_evolution": [],
        "fraud_trend": {"delta_pct": 0, "direction": "neutral", "label": "Cargue datos para tendencia"},
        "forecast_30d": None,
        "forecast_ia": None,
        "sankey": {"labels": [], "source": [], "target": [], "value": []},
        "risk_network": {"nodes": [], "edges": []},
        "risk_heatmap": {"x_labels": [], "y_labels": [], "z": []},
        "anomaly_heatmap": {"x": [], "y": [], "z": []},
    }

    temporal_risk: List[Dict] = []
    if "fecha_ocurrencia" in df.columns and sem_col in df.columns:
        fecha = pd.to_datetime(df["fecha_ocurrencia"], errors="coerce")
        tmp = df.copy()
        tmp["_fecha"] = fecha
        tmp = tmp.dropna(subset=["_fecha"])
        if not tmp.empty:
            tmp["mes"] = tmp["_fecha"].dt.to_period("M").astype(str)
            piv = (
                tmp.pivot_table(
                    index="mes",
                    columns=sem_col,
                    values="id_siniestro",
                    aggfunc="count",
                    fill_value=0,
                )
                .reindex(columns=["Rojo", "Amarillo", "Verde"], fill_value=0)
                .reset_index()
            )
            temporal_risk = piv.to_dict("records")
            insights["monthly_history"] = temporal_risk
            insights["fraud_trend"] = _fraud_trend_from_monthly(temporal_risk)

            if score_col in tmp.columns:
                risk_evo = (
                    tmp.groupby("mes")
                    .agg(
                        score_avg=(score_col, "mean"),
                        casos=("id_siniestro", "count"),
                        rojos=(sem_col, lambda s: int((s == "Rojo").sum())),
                    )
                    .reset_index()
                    .round(2)
                )
                insights["risk_evolution"] = risk_evo.to_dict("records")

            tmp["dia"] = tmp["_fecha"].dt.strftime("%Y-%m-%d")
            daily = (
                tmp.groupby("dia")
                .agg(
                    casos=("id_siniestro", "count"),
                    rojos=(sem_col, lambda s: int((s == "Rojo").sum())),
                    score_avg=(score_col, "mean") if score_col in tmp.columns else ("id_siniestro", "count"),
                )
                .reset_index()
                .sort_values("dia")
                .tail(60)
            )
            if not daily.empty:
                hist_labels = daily["dia"].astype(str).tolist()
                hist_rojos = [float(x) for x in daily["rojos"].tolist()]
                hist_score = [round(float(x), 2) for x in daily["score_avg"].tolist()]
                ml_fc = _ml_forecast_series(hist_rojos, 30)
                fc_rojos = ml_fc["forecast"]
                fc_score = _linear_forecast(hist_score, 30)
                last_dt = pd.to_datetime(hist_labels[-1])
                fc_labels = [
                    (last_dt + pd.Timedelta(days=i + 1)).strftime("%Y-%m-%d")
                    for i in range(30)
                ]
                block = {
                    "historical_labels": hist_labels,
                    "historical_rojos": hist_rojos,
                    "historical_score": hist_score,
                    "forecast_labels": fc_labels,
                    "forecast_rojos": fc_rojos,
                    "forecast_score": [round(v, 2) for v in fc_score],
                    "forecast_upper": ml_fc["upper"],
                    "forecast_lower": ml_fc["lower"],
                    "confidence_pct": ml_fc["confidence_pct"],
                    "method": ml_fc["method"],
                    "r2": ml_fc.get("r2"),
                    "slope": ml_fc.get("slope"),
                }
                insights["forecast_30d"] = block
                hist_tail = min(21, len(hist_rojos))
                tail_labels = hist_labels[-hist_tail:]
                tail_actual = hist_rojos[-hist_tail:]
                ia_labels = tail_labels + fc_labels
                ia_actual = tail_actual + [None] * 30
                ia_predicted = [None] * (hist_tail - 1) + [tail_actual[-1]] + fc_rojos
                ia_upper = [None] * (hist_tail - 1) + [tail_actual[-1]] + ml_fc["upper"]
                ia_lower = [None] * (hist_tail - 1) + [tail_actual[-1]] + ml_fc["lower"]
                insights["forecast_ia"] = {
                    "labels": ia_labels,
                    "actual": ia_actual,
                    "predicted": ia_predicted,
                    "upper": ia_upper,
                    "lower": ia_lower,
                    "method": ml_fc["method"],
                    "model_note": (
                        f"Forecast ML: {ml_fc['method']}"
                        + (f" · R²={ml_fc['r2']}" if ml_fc.get("r2") is not None else "")
                        + f" · confianza {ml_fc['confidence_pct']}%"
                    ),
                }

    sem_counts = metrics.get("semaforo_counts") or {}
    if sem_counts:
        insights["donut_semaforo"] = {
            "labels": ["Verde", "Amarillo", "Rojo"],
            "values": [
                int(sem_counts.get("Verde", 0)),
                int(sem_counts.get("Amarillo", 0)),
                int(sem_counts.get("Rojo", 0)),
            ],
        }

    if "ramo" in df.columns and sem_col in df.columns:
        labels: List[str] = []
        sources: List[int] = []
        targets: List[int] = []
        values: List[int] = []
        ramos = df["ramo"].fillna("Sin ramo").astype(str).value_counts().head(6).index.tolist()
        sem_order = ["Verde", "Amarillo", "Rojo"]
        label_idx: Dict[str, int] = {}

        def _idx(name: str) -> int:
            if name not in label_idx:
                label_idx[name] = len(labels)
                labels.append(name)
            return label_idx[name]

        for ramo in ramos:
            sub = df[df["ramo"].fillna("Sin ramo").astype(str) == ramo]
            r_i = _idx(str(ramo))
            for sem in sem_order:
                cnt = int((sub[sem_col] == sem).sum())
                if cnt <= 0:
                    continue
                s_i = _idx(f"Semáforo {sem}")
                sources.append(r_i)
                targets.append(s_i)
                values.append(cnt)
        insights["sankey"] = {
            "labels": labels,
            "source": sources,
            "target": targets,
            "value": values,
        }

    prov_col = next(
        (c for c in ("nombre_proveedor", "proveedor", "id_proveedor") if c in df.columns),
        None,
    )
    if prov_col and score_col in df.columns:
        top = (
            df.groupby(prov_col)
            .agg(casos=("id_siniestro", "count"), score=(score_col, "mean"))
            .reset_index()
            .nlargest(8, "score")
        )
        nodes = [{"id": "Cartera", "label": "Cartera", "size": 24}]
        edges: List[Dict] = []
        for _, row in top.iterrows():
            pid = str(row[prov_col])[:28]
            nodes.append({"id": pid, "label": pid, "size": max(8, min(22, float(row["score"]) / 4))})
            edges.append({
                "source": "Cartera",
                "target": pid,
                "weight": int(row["casos"]),
                "risk": round(float(row["score"]), 1),
            })
        insights["risk_network"] = {"nodes": nodes, "edges": edges}

    if score_col in df.columns and "monto_reclamado" in df.columns:
        scores = pd.to_numeric(df[score_col], errors="coerce").fillna(0)
        montos = pd.to_numeric(df["monto_reclamado"], errors="coerce").fillna(0)
        score_bins = ["0-40", "41-60", "61-75", "76-100"]
        monto_bins = ["<50K", "50K-200K", "200K-500K", ">500K"]

        def _sb(s: float) -> str:
            if s <= 40:
                return "0-40"
            if s <= 60:
                return "41-60"
            if s <= 75:
                return "61-75"
            return "76-100"

        def _mb(m: float) -> str:
            if m < 50_000:
                return "<50K"
            if m < 200_000:
                return "50K-200K"
            if m < 500_000:
                return "200K-500K"
            return ">500K"

        tmp_h = pd.DataFrame({"sb": scores.map(_sb), "mb": montos.map(_mb)})
        piv_h = (
            tmp_h.groupby(["mb", "sb"])
            .size()
            .unstack(fill_value=0)
            .reindex(index=monto_bins, columns=score_bins, fill_value=0)
        )
        insights["risk_heatmap"] = {
            "x_labels": score_bins,
            "y_labels": monto_bins,
            "z": piv_h.values.tolist(),
        }

        if "fecha_ocurrencia" in df.columns:
            fechas = pd.to_datetime(df["fecha_ocurrencia"], errors="coerce")
            dow = fechas.dt.dayofweek.fillna(0).astype(int).clip(0, 6)
            week = fechas.dt.isocalendar().week.fillna(1).astype(int) % 5
            tmp_a = pd.DataFrame({"w": week, "d": dow, "s": scores})
            ah = tmp_a.groupby(["w", "d"])["s"].mean().unstack(fill_value=0)
            insights["anomaly_heatmap"] = {
                "x": ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"],
                "y": [f"S{i+1}" for i in range(ah.shape[0])],
                "z": ah.values.tolist(),
            }

    auc = float(metrics.get("cv_auc_mean") or metrics.get("auc_roc") or 0)
    def _pct(v: float) -> float:
        return v * 100 if 0 <= v <= 1 else v

    prec = _pct(float(metrics.get("precision_fraude") or 0))
    rec = _pct(float(metrics.get("recall_fraude") or metrics.get("recall") or 0))
    f1 = _pct(float(metrics.get("f1_fraude") or metrics.get("f1_score") or 0))
    anom = min(100, float(metrics.get("anomalies_detected") or 0) * 3)
    alta = min(100, float(metrics.get("casos_alta_prob_ml") or 0) * 2)
    insights["feature_radar"] = {
        "labels": ["AUC", "Precisión", "Recall", "F1", "Anomalías", "Alta prob."],
        "values": [round(auc * 100, 1), round(prec, 1), round(rec, 1), round(f1, 1), round(anom, 1), round(alta, 1)],
    }
    if score_col in df.columns:
        insights["risk_gauge_score"] = round(float(df[score_col].mean()), 1)
    insights["kpi_summary"] = _build_predictive_kpis(df, metrics, insights.get("forecast_30d"))
    return insights


def _enrich_ml_metrics(metrics: dict) -> dict:
    """Campos extra para la pantalla AI / ML Engine."""
    ar = app_state.get("anomaly_results")
    if isinstance(ar, dict) and ar.get("n_anomalies") is not None:
        metrics["anomalies_detected"] = int(ar["n_anomalies"])
    metrics.setdefault("active_model", "Random Forest")
    metrics.setdefault("model_version", "fraudia-ml-1.0")
    metrics.setdefault("inference_ms", 48)
    nlp = app_state.get("nlp_results")
    if isinstance(nlp, dict):
        pairs = nlp.get("high_similarity_pairs") or []
        metrics["nlp_pairs"] = len(pairs)
    df = app_state.get("df_scored")
    if df is not None and not getattr(df, "empty", True):
        cols = [
            c
            for c in (
                "id_siniestro",
                "score_hibrido",
                "anomaly_score",
                "ml_fraud_probability",
                "monto_reclamado",
                "semaforo_final",
            )
            if c in df.columns
        ]
        if cols and "score_hibrido" in df.columns:
            sample = df.nlargest(120, "score_hibrido")[cols]
            metrics["anomaly_scatter"] = sample.to_dict("records")
        if "score_hibrido" in df.columns:
            scores = df["score_hibrido"].dropna()
            metrics["score_histogram"] = {
                "bins": ["0-40", "41-75", "76-100"],
                "counts": [
                    int(((scores >= 0) & (scores <= 40)).sum()),
                    int(((scores >= 41) & (scores <= 75)).sum()),
                    int((scores >= 76).sum()),
                ],
            }
        metrics.update(_build_ml_probability_charts(df))
        metrics["predictive"] = _build_ml_predictive_insights(df, metrics)
    return metrics


def _build_metrics_from_scored_df() -> dict:
    """Métricas derivadas del dataset procesado cuando no hay snapshot ML persistido."""
    df = app_state.get("df_scored")
    if df is None or getattr(df, "empty", True):
        return {"trained": False}

    has_ml = "ml_fraud_probability" in df.columns and df["ml_fraud_probability"].notna().any()
    has_anom = "anomaly_score" in df.columns and df["anomaly_score"].notna().any()
    has_score = "score_hibrido" in df.columns

    metrics: dict = {
        "trained": bool(has_ml or has_score),
        "active_model": "Random Forest" if has_ml else "Reglas + score híbrido",
        "model_version": "fxecure-ml-1.0",
        "total_records": int(len(df)),
    }

    if has_score:
        scores = df["score_hibrido"].dropna()
        metrics["score_promedio"] = round(float(scores.mean()), 2)

    if "semaforo_final" in df.columns:
        sem = df["semaforo_final"].value_counts()
        metrics["semaforo_counts"] = {
            "Rojo": int(sem.get("Rojo", 0)),
            "Amarillo": int(sem.get("Amarillo", 0)),
            "Verde": int(sem.get("Verde", 0)),
        }

    if has_ml:
        prob = df["ml_fraud_probability"].dropna()
        if len(prob):
            metrics["ml_prob_promedio"] = round(float(prob.mean()), 4)
            metrics["casos_alta_prob_ml"] = int((prob >= 0.7).sum())

    if has_anom:
        anom = df["anomaly_score"].dropna()
        if len(anom):
            metrics["anomalies_detected"] = int((anom >= 0.75).sum())

    snapshot = app_state.get("model_snapshot")
    if isinstance(snapshot, dict):
        for key in (
            "auc_roc", "cv_auc_mean", "precision_fraude", "recall_fraude", "f1_fraude",
            "top_features", "feature_importance", "confusion_matrix",
        ):
            if snapshot.get(key) is not None and metrics.get(key) is None:
                metrics[key] = snapshot.get(key)

    return metrics


def _resolve_model_metrics_payload() -> dict:
    """Payload JSON-safe para /api/model-metrics."""
    from src.models.fraud_model import get_model_metrics_summary
    from src.pipeline.run_full_analysis import serialize_model_results

    snapshot = app_state.get("model_snapshot")
    if isinstance(snapshot, dict) and snapshot.get("error"):
        metrics = _build_metrics_from_scored_df()
        metrics["warning"] = str(snapshot.get("error"))
        return metrics

    if isinstance(snapshot, dict) and snapshot.get("trained") is not False and (
        snapshot.get("auc_roc") is not None or snapshot.get("top_features") or snapshot.get("feature_importance")
    ):
        metrics = dict(snapshot)
        metrics.setdefault("top_features", metrics.get("feature_importance", [])[:10])
        return metrics

    results = app_state.get("model_results")
    if isinstance(results, dict) and results.get("model") is not None:
        return serialize_model_results(results)

    if isinstance(results, dict) and not results.get("model") and (
        results.get("auc_roc") is not None or results.get("top_features")
    ):
        metrics = dict(results)
        metrics.setdefault("trained", True)
        metrics.setdefault("top_features", metrics.get("feature_importance", [])[:10])
        return metrics

    metrics = _build_metrics_from_scored_df()
    if not metrics.get("trained"):
        raise ValueError(
            "Modelo no entrenado. Cargue un Excel en «Carga Inteligente de Datos» y pulse «Activar motor IA»."
        )
    return metrics


def model_metrics() -> dict:
    if not _ensure_session_state(require_scored=True):
        raise ValueError(
            "Pipeline no ejecutado. Cargue datos en «Carga Inteligente de Datos» y active el motor IA."
        )
    metrics = _resolve_model_metrics_payload()
    return _enrich_ml_metrics(metrics)


def nlp_summary() -> dict:
    results = app_state.get("nlp_results")
    if results is None:
        raise ValueError("Análisis NLP no ejecutado")
    return results


def session_bootstrap() -> dict:
    """
    Recupera dataset y análisis desde TiDB o /tmp (petición nueva en Vercel).
    El frontend puede llamarlo al abrir la app o tras subir Excel.
    """
    has_datasets = _hydrate_datasets_from_storage()
    has_scored = _ensure_scored_state()
    ds = app_state.get("datasets") or {}
    n_sin = len(ds["siniestros"]) if "siniestros" in ds else 0
    return {
        "status": "ok",
        "session_id": get_request_session_id(),
        "datasets_ready": has_datasets and n_sin > 0,
        "pipeline_ready": has_scored,
        "siniestros_rows": n_sin,
        "tables": list(ds.keys()),
        "message": (
            "Datos y análisis listos."
            if has_scored
            else (
                "Hay datos en base de datos pero falta ejecutar el motor IA."
                if n_sin > 0
                else "No hay siniestros cargados. Suba un Excel."
            )
        ),
    }


def get_status() -> dict:
    if is_vercel_runtime():
        _hydrate_datasets_from_storage()
        _ensure_scored_state()
    db_info = (
        {"status": "ok", "type": "In-memory (Vercel)", "host": "demo"}
        if is_vercel_runtime() and not is_persistent_database_configured()
        else test_connection()
    )
    return {
        "pipeline_status": app_state["pipeline_status"],
        "datasets_loaded": list((app_state.get("datasets") or {}).keys()),
        "has_scored_data": app_state["df_scored"] is not None,
        "has_model": app_state["model_results"] is not None,
        "has_agent": app_state["agent"] is not None,
        "database": db_info,
        "vercel": is_vercel_runtime(),
        "openai_configured": is_openai_configured(),
        "stack": "python-fastapi",
    }

