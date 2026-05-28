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
from src.ingestion.load_data import (
    load_all_from_directory,
    load_file_to_tables,
    load_from_upload,
    load_insurer_default_workbook,
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


def _collect_uploaded_documents() -> List[Dict[str, Any]]:
    if _should_use_live_database():
        try:
            return list_documentos_subidos()
        except Exception:
            pass
    return list(app_state.get("documentos_subidos", []))


def _prepare_datasets_for_pipeline() -> Dict[str, pd.DataFrame]:
    datasets = app_state.get("datasets") or {}
    docs = _collect_uploaded_documents()
    if docs and "siniestros" in datasets:
        datasets = enrich_datasets_with_uploaded_documents(datasets, docs)
        app_state["datasets"] = datasets
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

    ctx = build_agent_context()
    ctx["manifest"] = {"steps": result.get("steps", [])}
    app_state["agent"] = ClaimsAgent(df_scored, extra_context=ctx)


def _run_analysis_after_load() -> Optional[Dict[str, Any]]:
    """Ejecuta pipeline completo tras cargar dataset (dashboard + ML + agente)."""
    if not app_state.get("datasets") or "siniestros" not in app_state["datasets"]:
        return None
    try:
        out = run_pipeline()
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


def _documents_storage_dir() -> str:
    if is_vercel_runtime():
        path = "/tmp/fraudia_documents"
        os.makedirs(path, exist_ok=True)
        return path
    os.makedirs(DOCUMENTS_UPLOAD_FOLDER, exist_ok=True)
    return DOCUMENTS_UPLOAD_FOLDER


def _runtime_cache_dir() -> str:
    return "/tmp/fraudia_runtime_datasets"


def _runtime_analysis_dir() -> str:
    return "/tmp/fraudia_runtime_analysis"


def _clear_runtime_analysis_cache() -> None:
    if not is_vercel_runtime():
        return
    import shutil

    path = _runtime_analysis_dir()
    if os.path.isdir(path):
        shutil.rmtree(path, ignore_errors=True)


def _persist_runtime_analysis(result: dict) -> None:
    """Guarda resultado del pipeline en /tmp (misma instancia serverless)."""
    if not (is_vercel_runtime() and not is_persistent_database_configured()):
        return
    df = result.get("df_scored")
    if df is None:
        return
    out_dir = _runtime_analysis_dir()
    os.makedirs(out_dir, exist_ok=True)
    df.to_csv(os.path.join(out_dir, "siniestros_scored.csv"), index=False)
    meta = {
        "model_snapshot": result.get("model_snapshot"),
        "dashboard_snapshot": result.get("dashboard_snapshot"),
        "nlp_results": result.get("nlp_results"),
        "total_records": result.get("total_records"),
        "auc_roc": result.get("auc_roc"),
    }
    with open(os.path.join(out_dir, "meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, default=str)


def _hydrate_runtime_analysis() -> bool:
    """Recupera último análisis guardado en /tmp (si existe)."""
    if not (is_vercel_runtime() and not is_persistent_database_configured()):
        return False
    csv_path = os.path.join(_runtime_analysis_dir(), "siniestros_scored.csv")
    if not os.path.exists(csv_path):
        return False
    df = pd.read_csv(csv_path)
    app_state["df_scored"] = df
    app_state["df_features"] = df.copy()
    app_state["pipeline_status"] = "completed"
    meta_path = os.path.join(_runtime_analysis_dir(), "meta.json")
    if os.path.exists(meta_path):
        with open(meta_path, encoding="utf-8") as f:
            meta = json.load(f)
        app_state["model_snapshot"] = meta.get("model_snapshot")
        app_state["dashboard_snapshot"] = meta.get("dashboard_snapshot")
        app_state["nlp_results"] = meta.get("nlp_results") or {}
    app_state["dashboard_last_payload"] = build_dashboard_payload(
        df, total_unfiltered=len(df), active_filters=[]
    )
    app_state["agent"] = ClaimsAgent(df, extra_context=build_agent_context())
    return True


def _persist_runtime_datasets(datasets: Dict[str, pd.DataFrame]) -> None:
    """
    En Vercel sin BD persistente, guarda datasets en /tmp para reuso entre requests
    del mismo contenedor serverless.
    """
    if not (is_vercel_runtime() and not is_persistent_database_configured()):
        return
    if not datasets or "siniestros" not in datasets:
        return
    cache_dir = _runtime_cache_dir()
    os.makedirs(cache_dir, exist_ok=True)
    manifest = {"tables": []}
    for name, df in datasets.items():
        path = os.path.join(cache_dir, f"{name}.csv")
        df.to_csv(path, index=False)
        manifest["tables"].append(name)
    with open(os.path.join(cache_dir, "manifest.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False)


def _load_runtime_datasets() -> Dict[str, pd.DataFrame]:
    if not (is_vercel_runtime() and not is_persistent_database_configured()):
        return {}
    cache_dir = _runtime_cache_dir()
    manifest_path = os.path.join(cache_dir, "manifest.json")
    if not os.path.exists(manifest_path):
        return {}
    try:
        with open(manifest_path, encoding="utf-8") as f:
            manifest = json.load(f)
        tables = manifest.get("tables") or []
        loaded: Dict[str, pd.DataFrame] = {}
        for name in tables:
            path = os.path.join(cache_dir, f"{name}.csv")
            if os.path.exists(path):
                loaded[name] = pd.read_csv(path)
        return normalize_datasets_columns(loaded)
    except Exception:
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

    app_state["df_scored"] = sin.copy()
    app_state["df_features"] = sin.copy()
    app_state["pipeline_status"] = "completed"
    app_state["dashboard_last_payload"] = build_dashboard_payload(
        app_state["df_scored"], total_unfiltered=len(app_state["df_scored"]), active_filters=[]
    )
    app_state["agent"] = ClaimsAgent(app_state["df_scored"], extra_context=build_agent_context())
    return True


def ensure_vercel_data() -> None:
    """
    En Vercel sin BD persistente: no reemplazar datos cargados por el usuario con el bundle demo.
    Solo precargar demo si no hay datasets ni análisis en /tmp.
    """
    if not is_vercel_runtime() or is_persistent_database_configured():
        return

    if app_state.get("datasets") and "siniestros" in app_state["datasets"]:
        if app_state.get("df_scored") is None:
            _hydrate_runtime_analysis()
        return

    runtime_ds = _load_runtime_datasets()
    if runtime_ds and "siniestros" in runtime_ds:
        app_state["datasets"] = runtime_ds
        if app_state.get("df_scored") is None:
            _hydrate_runtime_analysis()
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


def db_status() -> dict:
    if is_vercel_runtime() and not is_persistent_database_configured():
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
    """Plantilla alineada al dataset oficial de la aseguradora (hojas 1_Siniestros … 5_Documentos)."""
    templates = {
        "1_Siniestros": [
            "id_siniestro", "id_poliza", "id_asegurado", "ramo", "placa_vehiculo", "cobertura",
            "fecha_ocurrencia", "fecha_reporte", "dias_entre_ocurrencia_reporte",
            "monto_reclamado", "monto_estimado", "monto_pagado", "estado", "sucursal",
            "id_proveedor", "descripcion", "documentos_completos", "prov_en_lista_restrictiva",
            "dias_desde_inicio_poliza", "dias_desde_fin_poliza", "historial_siniestros_asegurado",
            "suma_asegurada", "similitud_narrativa_max", "numero_parte_policial",
        ],
        "2_Polizas": [
            "id_poliza", "id_asegurado", "ramo", "fecha_inicio", "fecha_fin",
            "suma_asegurada", "prima", "canal_venta", "estado_poliza",
        ],
        "3_Asegurados": [
            "id_asegurado", "nombres_asegurado", "segmento", "ciudad",
            "antiguedad_anos", "numero_polizas", "reclamos_ultimos_12m",
        ],
        "4_Proveedores": [
            "id_proveedor", "nombre_proveedor", "tipo", "ciudad",
            "reclamos_asociados", "en_lista_restrictiva",
        ],
        "5_Documentos": [
            "id_documento", "id_siniestro", "tipo_documento", "nombre_archivo_pdf",
        ],
    }
    guia = pd.DataFrame([
        {"Hoja": "1_Siniestros", "Notas": "Placa en siniestro; etiqueta_fraude se deriva si no viene"},
        {"Hoja": "2_Polizas", "Notas": "Prima anual → prima"},
        {"Hoja": "3_Asegurados", "Notas": "Perfil y reclamos recientes"},
        {"Hoja": "4_Proveedores", "Notas": "Lista restrictiva Sí/No"},
        {"Hoja": "5_Documentos", "Notas": "PDF por siniestro"},
    ])
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        for sheet, cols in templates.items():
            pd.DataFrame(columns=cols).to_excel(writer, sheet_name=sheet, index=False)
        guia.to_excel(writer, sheet_name="README", index=False)
    buf.seek(0)
    return buf


def load_insurer_dataset() -> dict:
    """Carga el Excel oficial desde data/raw/Evento_Datasets_Sinteticos_Fraude_500_v2.xlsx."""
    datasets = {
        name: ensure_str_columns(df)
        for name, df in load_insurer_default_workbook().items()
    }
    if "siniestros" not in datasets:
        raise ValueError("El workbook de la aseguradora no contiene la hoja 1_Siniestros.")
    app_state["datasets"] = datasets
    reset_pipeline_state()
    _clear_runtime_analysis_cache()
    _persist_runtime_datasets(app_state["datasets"])
    validation = validate_datasets(datasets)
    tables_info = {
        name: {"rows": len(df), "columns": len(df.columns), "cols": list(df.columns)}
        for name, df in datasets.items()
    }
    db_msg = ""
    if _should_use_live_database() and validation["has_siniestros"]:
        try:
            init_database()
            save_all_datasets({k: v.copy() for k, v in datasets.items()})
            db_msg = f" (guardado en {test_connection().get('type', 'BD')})"
        except Exception as exc:
            db_msg = f" (error BD: {exc})"
    resp = {
        "status": "success",
        "message": "Dataset oficial de la aseguradora cargado" + db_msg,
        "tables": tables_info,
        "has_siniestros": validation["has_siniestros"],
        "warnings": validation["warnings"],
        "source": "insurer_workbook",
    }
    if validation["has_siniestros"]:
        pipeline_out = _run_analysis_after_load()
        if pipeline_out:
            resp["pipeline"] = pipeline_out
            if pipeline_out.get("auto_analyzed"):
                resp["message"] += (
                    f" Análisis ejecutado: {pipeline_out.get('total_records', 0)} casos en dashboard/ML."
                )
    return resp


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
    if is_vercel_runtime():
        # Runtime serverless: evita escribir en disco de solo lectura.
        file_obj = io.BytesIO(content)
        file_obj.name = filename
        new_tables = {
            name: ensure_str_columns(df)
            for name, df in load_from_upload(file_obj, filename).items()
        }
    else:
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
    _clear_runtime_analysis_cache()
    _persist_runtime_datasets(app_state["datasets"])
    validation = validate_datasets(app_state["datasets"])
    tables_info = {
        name: {"rows": len(df), "columns": len(df.columns), "cols": list(df.columns)}
        for name, df in app_state["datasets"].items()
    }

    def _save_to_db(datasets):
        if "siniestros" not in datasets:
            return
        with _db_save_lock:
            init_database()
            return save_all_datasets({k: v.copy() for k, v in datasets.items()})

    db_save_result = None
    if validation["has_siniestros"]:
        datasets_copy = {k: v.copy() for k, v in app_state["datasets"].items()}
        if not _should_use_live_database():
            db_save_result = {"status": "skipped", "reason": "serverless-ephemeral-runtime"}
            db_msg = " (persistencia omitida en runtime Vercel)"
        else:
            try:
                db_save_result = _save_to_db(datasets_copy)
                db_msg = f" (guardado en {test_connection().get('type', 'BD')})"
            except Exception as exc:
                db_save_result = {"status": "error", "message": str(exc)}
                db_msg = " (error guardando en BD)"
    else:
        db_msg = ""
    msg = f"'{filename}' cargado ({', '.join(new_tables.keys())})." + db_msg
    resp = {
        "status": "success" if validation["has_siniestros"] else "warning",
        "message": msg,
        "tables": tables_info,
        "has_siniestros": validation["has_siniestros"],
        "warnings": validation["warnings"],
        "loaded_tables": list(new_tables.keys()),
        "db_save_result": db_save_result,
    }
    if validation["has_siniestros"]:
        pipeline_out = _run_analysis_after_load()
        if pipeline_out:
            resp["pipeline"] = pipeline_out
            if pipeline_out.get("auto_analyzed"):
                resp["message"] += (
                    f" Análisis ejecutado: {pipeline_out.get('total_records', 0)} casos en dashboard/ML."
                )
    return resp


def load_synthetic() -> dict:
    from src.ingestion.generate_synthetic import main as generate_data

    synth_dir = os.path.join("data", "synthetic")
    if is_vercel_runtime():
        synth_dir = "/tmp/fraudia_synthetic"
    seed_used = generate_data(output_dir=synth_dir)
    app_state["datasets"] = load_all_from_directory(synth_dir)
    reset_pipeline_state()
    _clear_runtime_analysis_cache()
    _persist_runtime_datasets(app_state["datasets"])
    tables_info = {
        name: {"rows": len(df), "columns": len(df.columns)}
        for name, df in app_state["datasets"].items()
    }

    if _should_use_live_database():
        init_database()
        save_all_datasets({k: v.copy() for k, v in app_state["datasets"].items()})
    resp = {
        "status": "success",
        "message": f"Datos sintéticos generados (semilla {seed_used})",
        "seed": seed_used,
        "tables": tables_info,
    }
    pipeline_out = _run_analysis_after_load()
    if pipeline_out:
        resp["pipeline"] = pipeline_out
        if pipeline_out.get("auto_analyzed"):
            resp["message"] += (
                f" Análisis ejecutado: {pipeline_out.get('total_records', 0)} casos en dashboard/ML."
            )
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

    datasets = normalize_datasets_columns(load_all_datasets())
    if not datasets or "siniestros" not in datasets:
        raise ValueError("No hay datos en la base de datos. Suba un archivo primero.")
    app_state["datasets"] = datasets
    reset_pipeline_state()
    _hydrate_agent_from_scored_if_available()
    db_info = test_connection()
    return {
        "status": "success",
        "message": f"Datos cargados desde {db_info.get('type', 'DB')}",
        "tables": {n: {"rows": len(d), "columns": len(d.columns)} for n, d in datasets.items()},
        "has_siniestros": True,
        "pipeline_ready": app_state.get("agent") is not None,
    }


def run_pipeline() -> dict:
    if is_vercel_runtime() and not is_persistent_database_configured():
        datasets = app_state.get("datasets") or {}
        if not datasets or "siniestros" not in datasets:
            datasets = _load_runtime_datasets()
            if datasets and "siniestros" in datasets:
                app_state["datasets"] = datasets
                reset_pipeline_state()
        if not datasets or "siniestros" not in datasets:
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
            return {
                "status": "success",
                "message": "Análisis cargado desde build Vercel. Redeploy para recalcular.",
                "total_records": len(app_state["df_scored"]) if app_state.get("df_scored") is not None else 0,
                "duration_seconds": 0,
                "steps": steps,
                "vercel": True,
                "bootstrap": boot,
            }
    if not app_state["datasets"] or "siniestros" not in app_state["datasets"]:
        raise ValueError("No hay datos cargados. Suba un archivo o cargue datos sintéticos.")
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

    def _persist_scores(df, payload):
        update_siniestros_scores(df)
        save_analysis_run(**payload)

    steps_out = list(result["steps"])
    if _should_use_live_database():
        try:
            _persist_scores(df_scored.copy(), db_payload)
            steps_out.append({"step": "Guardado en BD", "status": "ok"})
        except Exception as exc:
            steps_out.append({
                "step": "Guardado en BD",
                "status": "warning",
                "detail": str(exc)[:120],
            })
    else:
        _persist_runtime_analysis({**result, "df_scored": df_scored})

    return {
        "status": "success",
        "steps": steps_out,
        "executive_summary": app_state.get("executive_summary"),
        "total_records": len(df_scored),
        "duration_seconds": round(time.time() - t_start, 2),
        "analyzed_from_upload": True,
        "semaforo_counts": {
            "Rojo": int(sem_counts.get("Rojo", 0)),
            "Amarillo": int(sem_counts.get("Amarillo", 0)),
            "Verde": int(sem_counts.get("Verde", 0)),
        },
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
    return {
        "openai_configured": is_openai_configured(),
        "openai_model": get_openai_model() if is_openai_configured() else None,
        "pipeline_ready": app_state.get("agent") is not None,
        "vercel": is_vercel_runtime(),
    }


def agent_query(body: dict) -> dict:
    agent = app_state.get("agent")
    if agent is None:
        if _should_use_live_database():
            datasets = normalize_datasets_columns(load_all_datasets())
            if datasets:
                app_state["datasets"] = datasets
                _hydrate_agent_from_scored_if_available()
                agent = app_state.get("agent")
    if agent is None:
        raise ValueError(
            "Agente no inicializado. Ejecute el pipeline o cargue desde BD una tabla siniestros con score_hibrido/semaforo_final."
        )
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
