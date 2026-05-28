"""Handlers HTTP (lógica de negocio sin framework web)."""
from __future__ import annotations

import io
import os
import time
import traceback
import threading
from typing import Any, Dict, Optional, Tuple

import pandas as pd

from src.app.core import (
    UPLOAD_FOLDER,
    app_state,
    build_agent_context,
    merge_uploaded_tables,
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
from src.ai_agent.openai_client import is_openai_configured, get_openai_model
from src.explainability.explain_score import explain_single_case
from src.ingestion.load_data import load_all_from_directory, load_file_to_tables, validate_datasets
from src.app.powerbi_export import export_to_powerbi, export_csv_for_powerbi
from src.utils.dataframe_columns import ensure_str_columns, normalize_datasets_columns
from src.db.config import test_connection
from src.db.repository import (
    init_database,
    save_all_datasets,
    load_all_datasets,
    update_siniestros_scores,
    save_analysis_run,
    get_analysis_history,
    get_db_stats,
)


def ensure_vercel_data() -> None:
    if is_vercel_runtime() and app_state.get("df_scored") is None:
        try:
            bootstrap_vercel_demo(app_state)
        except Exception as exc:
            print(f"[Vercel] Error cargando bundle: {exc}")


def health() -> dict:
    return {
        "status": "ok",
        "vercel": is_vercel_runtime(),
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
        "analysis_flow": (
            "build: datos → pipeline → bundle; runtime: dashboard + OpenAI"
        ) if is_vercel_runtime() else "local: carga/sintéticos → pipeline",
        "manifest": manifest,
        "records": manifest.get("total_records")
        or (len(app_state["df_scored"]) if app_state.get("df_scored") is not None else 0),
    }


def db_status() -> dict:
    if is_vercel_runtime():
        return {
            "status": "ok",
            "type": "In-memory (Vercel)",
            "host": "demo",
            "message": "Datos desde bundle embebido (CSV + JSON).",
        }
    conn = test_connection()
    if conn["status"] == "ok":
        conn["stats"] = get_db_stats()
        conn["history"] = get_analysis_history()
    return conn


def db_init() -> dict:
    init_database()
    return {"status": "ok", "message": "Tablas creadas en la base de datos"}


def build_template_excel() -> io.BytesIO:
    templates = {
        "siniestros": [
            "id_siniestro", "id_poliza", "id_asegurado", "ramo", "cobertura",
            "fecha_ocurrencia", "fecha_reporte", "monto_reclamado", "monto_estimado",
            "monto_pagado", "estado", "sucursal", "descripcion", "documentos_completos",
            "beneficiario", "dias_desde_inicio_poliza", "dias_desde_fin_poliza",
            "dias_entre_ocurrencia_reporte", "historial_siniestros_asegurado",
            "etiqueta_fraude_simulada",
        ],
        "polizas": [
            "id_poliza", "id_asegurado", "ramo", "fecha_inicio", "fecha_fin",
            "prima", "suma_asegurada", "deducible", "canal_venta", "ciudad", "estado_poliza",
        ],
        "asegurados": [
            "id_asegurado", "segmento", "antiguedad_anos", "ciudad",
            "numero_polizas", "reclamos_ultimos_12m", "mora_actual", "score_cliente",
        ],
        "proveedores": [
            "id_proveedor", "tipo", "ciudad", "reclamos_asociados",
            "monto_promedio_reclamado", "casos_observados", "antiguedad_anos",
        ],
        "documentos": [
            "id_documento", "id_siniestro", "tipo_documento", "entregado",
            "legible", "fecha_emision", "inconsistencia_detectada", "observacion",
        ],
    }
    guia = pd.DataFrame([
        {"Tabla": "siniestros", "Campos_clave": "id_siniestro, id_poliza, id_asegurado", "Propósito": "Análisis antifraude"},
        {"Tabla": "polizas", "Campos_clave": "id_poliza, id_asegurado", "Propósito": "Vigencia y suma asegurada"},
        {"Tabla": "asegurados", "Campos_clave": "id_asegurado", "Propósito": "Perfil del asegurado"},
        {"Tabla": "proveedores", "Campos_clave": "id_proveedor", "Propósito": "Riesgo por proveedor"},
        {"Tabla": "documentos", "Campos_clave": "id_documento, id_siniestro", "Propósito": "Consistencia documental"},
    ])
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        for sheet, cols in templates.items():
            pd.DataFrame(columns=cols).to_excel(writer, sheet_name=sheet, index=False)
        guia.to_excel(writer, sheet_name="Guia", index=False)
    buf.seek(0)
    return buf


def upload_dataset(filename: str, content: bytes) -> dict:
    ext = os.path.splitext(filename)[1].lower()
    if ext not in (".csv", ".xlsx", ".xls"):
        raise ValueError("Formato no soportado. Use CSV o Excel (.xlsx).")
    filepath = os.path.join(UPLOAD_FOLDER, filename)
    with open(filepath, "wb") as f:
        f.write(content)
    new_tables = {
        name: ensure_str_columns(df)
        for name, df in load_file_to_tables(filepath, filename).items()
    }
    if not new_tables:
        raise ValueError("El archivo no contiene datos válidos (hojas vacías).")
    merge_uploaded_tables(new_tables)
    reset_pipeline_state()
    validation = validate_datasets(app_state["datasets"])
    tables_info = {
        name: {"rows": len(df), "columns": len(df.columns), "cols": list(df.columns)}
        for name, df in app_state["datasets"].items()
    }

    def _save_to_db(datasets):
        if "siniestros" not in datasets:
            return
        with _db_save_lock:
            try:
                init_database()
                save_all_datasets({k: v.copy() for k, v in datasets.items()})
            except Exception:
                pass

    if validation["has_siniestros"]:
        datasets_copy = {k: v.copy() for k, v in app_state["datasets"].items()}
        threading.Thread(target=_save_to_db, args=(datasets_copy,), daemon=True).start()
        db_msg = f" (guardando en {test_connection().get('type', 'BD')} en segundo plano)"
    else:
        db_msg = ""
    msg = f"'{filename}' cargado ({', '.join(new_tables.keys())})." + db_msg
    return {
        "status": "success" if validation["has_siniestros"] else "warning",
        "message": msg,
        "tables": tables_info,
        "has_siniestros": validation["has_siniestros"],
        "warnings": validation["warnings"],
        "loaded_tables": list(new_tables.keys()),
    }


def load_synthetic() -> dict:
    from src.ingestion.generate_synthetic import main as generate_data

    seed_used = generate_data()
    app_state["datasets"] = load_all_from_directory(os.path.join("data", "synthetic"))
    reset_pipeline_state()
    tables_info = {
        name: {"rows": len(df), "columns": len(df.columns)}
        for name, df in app_state["datasets"].items()
    }

    def _save_synthetic_db(datasets):
        try:
            init_database()
            save_all_datasets(datasets)
        except Exception:
            pass

    threading.Thread(
        target=_save_synthetic_db,
        args=({k: v.copy() for k, v in app_state["datasets"].items()},),
        daemon=True,
    ).start()
    return {
        "status": "success",
        "message": f"Datos sintéticos generados (semilla {seed_used})",
        "seed": seed_used,
        "tables": tables_info,
    }


def load_from_db() -> dict:
    datasets = normalize_datasets_columns(load_all_datasets())
    if not datasets or "siniestros" not in datasets:
        raise ValueError("No hay datos en la base de datos. Suba un archivo primero.")
    app_state["datasets"] = datasets
    reset_pipeline_state()
    db_info = test_connection()
    return {
        "status": "success",
        "message": f"Datos cargados desde {db_info.get('type', 'DB')}",
        "tables": {n: {"rows": len(d), "columns": len(d.columns)} for n, d in datasets.items()},
        "has_siniestros": True,
    }


def run_pipeline() -> dict:
    if is_vercel_runtime():
        boot = bootstrap_vercel_demo(app_state)
        return {
            "status": "success",
            "message": "Análisis cargado desde build Vercel. Redeploy para recalcular.",
            "total_records": len(app_state["df_scored"]) if app_state.get("df_scored") is not None else 0,
            "vercel": True,
            "bootstrap": boot,
        }
    if not app_state["datasets"] or "siniestros" not in app_state["datasets"]:
        raise ValueError("No hay datos cargados. Suba un archivo o cargue datos sintéticos.")
    t_start = time.time()
    app_state["pipeline_status"] = "running"
    from src.pipeline.run_full_analysis import execute_full_pipeline

    result = execute_full_pipeline(app_state["datasets"])
    df_scored = result["df_scored"]
    app_state.update({
        "datasets": result["datasets"],
        "df_features": result["df_features"],
        "df_scored": df_scored,
        "model_results": result["model_results"],
        "anomaly_results": result["anomaly_results"],
        "nlp_results": result["nlp_results"],
        "dashboard_snapshot": result["dashboard_snapshot"],
        "dashboard_last_payload": result["dashboard_last_payload"],
        "model_snapshot": result["model_snapshot"],
        "pipeline_status": "completed",
    })
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

    def _persist_scores(df, payload):
        try:
            update_siniestros_scores(df)
            save_analysis_run(**payload)
        except Exception:
            pass

    threading.Thread(target=_persist_scores, args=(df_scored.copy(), db_payload), daemon=True).start()
    app_state["agent"] = ClaimsAgent(df_scored, extra_context=build_agent_context())
    return {
        "status": "success",
        "steps": result["steps"] + [{"step": "Guardado en BD", "status": "ok"}],
        "executive_summary": result["executive_summary"],
        "total_records": result["total_records"],
        "duration_seconds": result["duration_seconds"],
    }


def dashboard_filters() -> dict:
    df = app_state.get("df_scored")
    if df is None:
        raise ValueError("Pipeline no ejecutado")
    return get_filter_options(df)


def dashboard_data(query_params) -> dict:
    df = app_state.get("df_scored")
    if df is None:
        raise ValueError("Pipeline no ejecutado")
    params = params_from_request(query_params)
    df_filtered, active_filters = apply_dashboard_filters(df, params)
    payload = build_dashboard_payload(df_filtered, total_unfiltered=len(df), active_filters=active_filters)
    app_state["dashboard_last_payload"] = payload
    return payload


def get_case(case_id: str) -> dict:
    df = app_state.get("df_scored")
    if df is None:
        raise ValueError("Pipeline no ejecutado")
    mask = df["id_siniestro"].str.upper() == case_id.upper()
    if mask.sum() == 0:
        raise LookupError(f"Siniestro {case_id} no encontrado")
    return explain_single_case(df[mask].iloc[0])


def agent_status() -> dict:
    return {
        "openai_configured": is_openai_configured(),
        "openai_model": get_openai_model() if is_openai_configured() else None,
        "pipeline_ready": app_state.get("agent") is not None,
        "vercel": is_vercel_runtime(),
    }


def agent_query(body: dict) -> dict:
    agent = app_state.get("agent")
    if agent is None:
        raise ValueError("Agente no inicializado. Ejecute el pipeline primero.")
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


def model_metrics() -> dict:
    results = app_state.get("model_results")
    if results is None:
        snapshot = app_state.get("model_snapshot")
        if snapshot:
            return snapshot
        raise ValueError("Modelo no entrenado")
    if is_vercel_runtime() or results.get("trained") or "model" not in results:
        return results
    from src.models.fraud_model import get_model_metrics_summary

    metrics = get_model_metrics_summary(results)
    metrics["confusion_matrix"] = results.get("confusion_matrix")
    return metrics


def nlp_summary() -> dict:
    results = app_state.get("nlp_results")
    if results is None:
        raise ValueError("Análisis NLP no ejecutado")
    return results


def get_status() -> dict:
    db_info = (
        {"status": "ok", "type": "In-memory (Vercel)", "host": "demo"}
        if is_vercel_runtime()
        else test_connection()
    )
    return {
        "pipeline_status": app_state["pipeline_status"],
        "datasets_loaded": list(app_state["datasets"].keys()),
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
