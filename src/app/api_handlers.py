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
from src.app.powerbi_export import export_to_powerbi, export_csv_for_powerbi
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
    """El análisis se dispara desde el frontend tras /api/upload (respuesta rápida)."""
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

    if is_vercel_runtime():
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
        expected = _expected_siniestros_count()
        if expected > 0 and len(sin) < expected:
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
    """Rutas /tmp: primero sesión (header), luego caché global."""
    dirs: List[str] = []
    sid = get_request_session_id()
    if sid:
        dirs.append(f"/tmp/fraudia_sessions/{sid}/datasets")
    dirs.append("/tmp/fraudia_runtime_datasets")
    return dirs


def _runtime_analysis_dirs() -> List[str]:
    dirs: List[str] = []
    sid = get_request_session_id()
    if sid:
        dirs.append(f"/tmp/fraudia_sessions/{sid}/analysis")
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
    if not is_vercel_runtime():
        return
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
    for out_dir in _runtime_analysis_dirs():
        try:
            os.makedirs(out_dir, exist_ok=True)
            df.to_csv(os.path.join(out_dir, "siniestros_scored.csv"), index=False)
            with open(os.path.join(out_dir, "meta.json"), "w", encoding="utf-8") as f:
                json.dump(meta, f, ensure_ascii=False, default=str)
        except Exception:
            pass


def _hydrate_runtime_analysis() -> bool:
    """Recupera último análisis guardado en /tmp (si existe)."""
    if not is_vercel_runtime():
        return False
    csv_path = None
    for analysis_dir in _runtime_analysis_dirs():
        candidate = os.path.join(analysis_dir, "siniestros_scored.csv")
        if os.path.exists(candidate):
            csv_path = candidate
            break
    if not csv_path:
        return False
    df = pd.read_csv(csv_path)
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
    """En Vercel guarda datasets en /tmp (sesión + caché global)."""
    if not is_vercel_runtime():
        return
    if not datasets or "siniestros" not in datasets:
        return
    for cache_dir in _runtime_cache_dirs():
        try:
            _write_datasets_to_cache_dir(datasets, cache_dir)
        except Exception:
            pass


def _load_runtime_datasets() -> Dict[str, pd.DataFrame]:
    if not is_vercel_runtime():
        return {}
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
        if auto_pipeline:
            _apply_workflow_to_response(resp, _start_load_workflow())
        else:
            resp["message"] += " Pulse «Activar motor IA» para el análisis."
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
    if auto_pipeline:
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
    return payload


def get_case(case_id: str) -> dict:
    if not _ensure_session_state(require_scored=True):
        raise ValueError("Pipeline no ejecutado")
    df = app_state.get("df_scored")
    mask = df["id_siniestro"].str.upper() == case_id.upper()
    if mask.sum() == 0:
        raise LookupError(f"Siniestro {case_id} no encontrado")
    case = explain_single_case(df[mask].iloc[0])
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
    df = app_state.get("df_scored")
    count = len(df) if df is not None and not getattr(df, "empty", True) else None
    return {
        **llm_status(),
        "openai_configured": is_openai_configured(),
        "openai_model": get_openai_model() if is_openai_configured() else None,
        "pipeline_ready": app_state.get("agent") is not None,
        "siniestros_count": count,
        "vercel": is_vercel_runtime(),
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


def agent_query(body: dict) -> dict:
    if not _ensure_agent_ready():
        raise ValueError(
            "Agente no inicializado. Cargue un Excel, pulse «Activar motor IA» o espere a que termine el análisis."
        )
    agent = app_state["agent"]
    question = (body or {}).get("question", "")
    if not question:
        raise ValueError("Pregunta vacía")
    agent.set_extra_context(build_agent_context())
    result = agent.query(question)
    if "datos" in result and result["datos"] is not None:
        items = result["datos"] if isinstance(result["datos"], list) else [result["datos"]]
        for item in items:
            if isinstance(item, dict):
                for k, v in list(item.items()):
                    if isinstance(v, float) and v != v:
                        item[k] = None
    return result


def export_powerbi() -> dict:
    df = app_state.get("df_scored")
    if df is None:
        raise ValueError("Pipeline no ejecutado")
    output_path = os.path.join("data", "processed", "powerbi_export.xlsx")
    export_to_powerbi(app_state["datasets"], df, output_path)
    export_csv_for_powerbi(df)
    return {"status": "success", "message": "Exportación completada", "excel_path": output_path}


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
        "model_version": "fraudia-ml-1.0",
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


def file_download_path(kind: str) -> Tuple[str, str]:
    if kind == "powerbi":
        path = os.path.join("data", "processed", "powerbi_export.xlsx")
        name = "powerbi_export.xlsx"
    else:
        path = os.path.join("data", "processed", "siniestros_scored.csv")
        name = "siniestros_scored.csv"
    if not os.path.exists(path):
        raise FileNotFoundError("Archivo no encontrado. Ejecute la exportación primero.")
    return path, name
