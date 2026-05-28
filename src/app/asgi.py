"""
API web FraudIA — FastAPI (Python / ASGI) para Vercel y desarrollo local.
"""
from __future__ import annotations

import os
import traceback

from dotenv import load_dotenv
from fastapi import FastAPI, File, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

load_dotenv()

from src.app.core import APP_DIR  # noqa: E402
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
async def vercel_bootstrap_middleware(request: Request, call_next):
    h.ensure_vercel_data()
    return await call_next(request)


@app.middleware("http")
async def vercel_api_key_middleware(request: Request, call_next):
    """
    Seguridad opcional en Vercel para endpoints API.
    Si VERCEL_API_KEY está definida, exige header X-Vercel-API-Key.
    """
    key = (os.getenv("VERCEL_API_KEY") or "").strip()
    path = request.url.path
    if not key:
        return await call_next(request)
    if path in ("/", "/api/health") or path.startswith("/static/"):
        return await call_next(request)
    if path.startswith("/api/"):
        incoming = (request.headers.get("X-Vercel-API-Key") or "").strip()
        if incoming != key:
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
async def api_db_status():
    return h.db_status()


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
        return h.upload_dataset(file.filename or "upload.xlsx", content)
    except ValueError as e:
        return _err(e, 400)
    except Exception as e:
        return _err(e)


@app.post("/api/load-synthetic")
async def api_load_synthetic():
    try:
        return h.load_synthetic()
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
