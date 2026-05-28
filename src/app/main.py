"""
Punto de arranque local — servidor Python (FastAPI + Uvicorn).
"""
import os

# Variables de BD: src.db.config carga .env del proyecto (override en local)
import src.db.config  # noqa: F401

def _warm_database_background() -> None:
    """No bloquea el arranque del servidor (TiDB Cloud puede tardar)."""
    import threading

    def _run():
        try:
            from src.db.repository import init_database
            from src.db.config import test_connection

            init_database()
            info = test_connection()
            print(f"  BD lista: {info.get('type', '?')} ({info.get('status', '?')})")
        except Exception as exc:
            print(f"  BD (aviso): {exc}")

    threading.Thread(target=_run, daemon=True).start()


if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("FLASK_PORT", os.environ.get("PORT", 5001)))
    local_url = os.environ.get("APP_URL", f"http://localhost:{port}")
    print(f"\n{'='*60}")
    print("  FraudIA Claims — LOCAL")
    print(f"  {local_url}")
    print(f"  (también: http://127.0.0.1:{port})")
    print("  Conectando a TiDB en segundo plano…")
    print(f"{'='*60}\n")
    _warm_database_background()
    reload = os.getenv("FLASK_DEBUG", "0").lower() in ("1", "true", "yes")
    uvicorn.run("src.app.asgi:app", host="0.0.0.0", port=port, reload=reload)
