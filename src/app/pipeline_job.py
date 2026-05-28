"""Pipeline de análisis en segundo plano (evita bloquear /api/upload)."""
from __future__ import annotations

import threading
import time
from typing import Any, Dict, Optional

_lock = threading.Lock()
_state: Dict[str, Any] = {
    "status": "idle",  # idle | running | completed | error
    "error": None,
    "result": None,
    "started_at": None,
    "finished_at": None,
    "progress_message": "",
}


def pipeline_status() -> dict:
    with _lock:
        out = {
            "status": _state["status"],
            "error": _state["error"],
            "progress_message": _state.get("progress_message") or "",
            "started_at": _state.get("started_at"),
            "finished_at": _state.get("finished_at"),
        }
        if _state["status"] == "completed" and _state.get("result"):
            out["result"] = _state["result"]
            out["auto_analyzed"] = True
        return out


def is_pipeline_running() -> bool:
    with _lock:
        return _state["status"] == "running"


def set_progress_message(message: str) -> None:
    with _lock:
        if _state["status"] == "running":
            _state["progress_message"] = message


def start_background_pipeline(run_fn) -> bool:
    """run_fn: callable sin args que ejecuta el pipeline y devuelve dict resultado."""
    with _lock:
        if _state["status"] == "running":
            return False
        _state["status"] = "running"
        _state["error"] = None
        _state["result"] = None
        _state["started_at"] = time.time()
        _state["finished_at"] = None
        _state["progress_message"] = "Iniciando motor IA…"

    def worker():
        try:
            with _lock:
                _state["progress_message"] = "Feature engineering, reglas, ML y NLP…"
            result = run_fn()
            with _lock:
                _state["result"] = result
                _state["status"] = "completed"
                _state["finished_at"] = time.time()
                _state["progress_message"] = "Análisis completado"
        except Exception as exc:
            with _lock:
                _state["error"] = str(exc)
                _state["status"] = "error"
                _state["finished_at"] = time.time()
                _state["progress_message"] = "Error en análisis"

    threading.Thread(target=worker, daemon=True).start()
    return True
