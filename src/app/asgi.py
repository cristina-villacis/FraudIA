"""
API web FraudIA — FastAPI (Python / ASGI) para Vercel y desarrollo local.
"""
from __future__ import annotations

import asyncio
import os
import traceback
from functools import partial

from typing import List, Optional

from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

import src.db.config  # noqa: F401 — carga .env del proyecto antes que el resto

from src.app.core import APP_DIR, reset_request_session_id, set_request_session_id  # noqa: E402
from src.app import api_handlers as h  # noqa: E402

app = FastAPI(title="FraudIA Claims", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

static_dir = os.path.join(APP_DIR, "static")
templates_dir = os.path.join(APP_DIR, "templates")
if os.path.isdir(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")


@app.middleware("http")
async def fraudia_session_middleware(request: Request, call_next):
    """Propaga X-FraudIA-Session para reutilizar /tmp entre requests en Vercel."""
    sid = (request.headers.get("X-FraudIA-Session") or "").strip() or None
    if not sid:
        cookie_sid = request.cookies.get("fraudia_session")
        sid = cookie_sid.strip() if cookie_sid else None
    token = set_request_session_id(sid)
    try:
        return await call_next(request)
    finally:
        reset_request_session_id(token)


@app.middleware("http")
async def vercel_bootstrap_middleware(request: Request, call_next):
    h.ensure_vercel_data()
    return await call_next(request)


def _is_same_origin_browser_request(request: Request) -> bool:
    """Peticiones desde la propia UI (mismo host) no requieren clave API."""
    host = (request.headers.get("host") or "").split(":")[0].lower()
    if not host:
        return False
    origin = (request.headers.get("origin") or "").lower()
    referer = (request.headers.get("referer") or "").lower()
    if origin and host in origin:
        return True
    if referer and host in referer:
        return True
    return False


@app.middleware("http")
async def vercel_api_key_middleware(request: Request, call_next):
    """
    Seguridad opcional en Vercel para endpoints API.
    Si VERCEL_API_KEY está definida, exige header X-Vercel-API-Key
    salvo en peticiones same-origin desde el navegador (chat, dashboard, etc.).
    """
    key = (os.getenv("VERCEL_API_KEY") or "").strip()
    path = request.url.path
    if not key:
        return await call_next(request)
    if path in ("/", "/api/health") or path.startswith("/static/"):
        return await call_next(request)
    if path.startswith("/api/"):
        incoming = (request.headers.get("X-Vercel-API-Key") or "").strip()
        if incoming != key and not _is_same_origin_browser_request(request):
            return JSONResponse({"error": "Unauthorized API key"}, status_code=401)
    return await call_next(request)


def _err(exc: Exception, status: int = 500):
    body = {"error": str(exc)}
    if os.getenv("FLASK_ENV") == "development" or os.getenv("VERCEL_ENV") == "preview":
        body["trace"] = traceback.format_exc()
    return JSONResponse(body, status_code=status)


@app.get("/", response_class=HTMLResponse)
async def index():
    index_path = os.path.join(templates_dir, "index.html")
    if os.path.exists(index_path):
        with open(index_path, encoding="utf-8") as f:
            return HTMLResponse(f.read())
    return HTMLResponse(
        "<h2>FraudIA Claims API online</h2>"
        "<p>UI no encontrada en bundle, pero la API está disponible.</p>"
    )


@app.get("/api/health")
async def api_health():
    return h.health()


@app.get("/api/deployment-info")
async def api_deployment_info():
    return h.deployment_info()


@app.get("/api/db-status")
async def api_db_status(quick: bool = True):
    return h.db_status(quick=quick)


@app.post("/api/db-init")
async def api_db_init():
    try:
        return h.db_init()
    except Exception as e:
        return _err(e)


@app.get("/api/download-template")
async def api_download_template():
    buf = h.build_template_excel()
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="plantilla_dataset_fraudia.xlsx"'},
    )


@app.post("/api/upload")
async def api_upload(file: UploadFile = File(...)):
    try:
        content = await file.read()
        loop = asyncio.get_running_loop()
        run = partial(h.upload_dataset, file.filename or "upload.xlsx", content)
        return await loop.run_in_executor(None, run)
    except ValueError as e:
        return _err(e, 400)
    except Exception as e:
        return _err(e)


@app.post("/api/load-synthetic")
async def api_load_synthetic():
    try:
        loop = asyncio.get_running_loop()
        # En Vercel el análisis corre en el mismo request (puede tardar varios minutos).
        return await loop.run_in_executor(None, h.load_synthetic)
    except Exception as e:
        return _err(e)


@app.get("/api/schema")
async def api_schema():
    from src.ingestion.schema import FIELD_DESCRIPTIONS

    return {"tables": FIELD_DESCRIPTIONS}


@app.post("/api/persist-datasets")
async def api_persist_datasets():
    try:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, h.persist_datasets_to_db)
    except ValueError as e:
        return _err(e, 400)
    except Exception as e:
        return _err(e)


@app.post("/api/upload-documents")
async def api_upload_documents(
    files: List[UploadFile] = File(...),
    link_to_dataset: bool = Form(False),
    tipo_documento: Optional[str] = Form(None),
):
    try:
        batch = []
        for f in files:
            batch.append((f.filename or "documento.pdf", await f.read()))
        return h.upload_documents(batch, link_to_dataset=link_to_dataset, tipo_documento=tipo_documento)
    except ValueError as e:
        return _err(e, 400)
    except Exception as e:
        return _err(e)


@app.get("/api/documents")
async def api_list_documents():
    try:
        return h.list_uploaded_documents()
    except Exception as e:
        return _err(e)


@app.get("/api/documents/{doc_id}")
async def api_get_document(doc_id: int):
    try:
        return h.get_uploaded_document(doc_id)
    except LookupError as e:
        return _err(e, 404)
    except Exception as e:
        return _err(e)


@app.post("/api/load-from-db")
async def api_load_from_db():
    try:
        return h.load_from_db()
    except ValueError as e:
        return _err(e, 400)
    except Exception as e:
        return _err(e)


@app.post("/api/run-pipeline")
async def api_run_pipeline():
    try:
        return h.run_pipeline()
    except ValueError as e:
        return _err(e, 400)
    except Exception as e:
        from src.app.core import app_state

        app_state["pipeline_status"] = "error"
        return _err(e)


@app.get("/api/pipeline-status")
async def api_pipeline_status():
    return h.get_pipeline_job_status()


@app.get("/api/dashboard-filters")
async def api_dashboard_filters():
    try:
        return h.dashboard_filters()
    except ValueError as e:
        return _err(e, 400)


@app.get("/api/dashboard-data")
async def api_dashboard_data(request: Request):
    try:
        return h.dashboard_data(request.query_params)
    except ValueError as e:
        return _err(e, 400)


@app.get("/api/case/{case_id}")
async def api_case(case_id: str):
    try:
        return h.get_case(case_id)
    except LookupError as e:
        return _err(e, 404)
    except ValueError as e:
        return _err(e, 400)


@app.get("/api/agent-status")
async def api_agent_status():
    return h.agent_status()


@app.post("/api/agent-query")
async def api_agent_query(request: Request):
    try:
        body = await request.json()
        return h.agent_query(body)
    except ValueError as e:
        return _err(e, 400)


@app.post("/api/export-powerbi")
async def api_export_powerbi():
    try:
        return h.export_powerbi()
    except ValueError as e:
        return _err(e, 400)


@app.get("/api/download-powerbi")
async def api_download_powerbi():
    try:
        path, name = h.file_download_path("powerbi")
        return FileResponse(path, filename=name, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    except FileNotFoundError as e:
        return _err(e, 404)


@app.get("/api/download-csv")
async def api_download_csv():
    try:
        path, name = h.file_download_path("csv")
        return FileResponse(path, filename=name, media_type="text/csv")
    except FileNotFoundError as e:
        return _err(e, 404)


@app.get("/api/model-metrics")
async def api_model_metrics():
    try:
        return h.model_metrics()
    except ValueError as e:
        return _err(e, 400)


@app.get("/api/nlp-summary")
async def api_nlp_summary():
    try:
        return h.nlp_summary()
    except ValueError as e:
        return _err(e, 400)


@app.get("/api/status")
async def api_status():
    return h.get_status()


@app.post("/api/session-bootstrap")
async def api_session_bootstrap():
    try:
        return h.session_bootstrap()
    except ValueError as e:
        return _err(e, 400)
