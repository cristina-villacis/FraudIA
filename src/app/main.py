"""
Punto de arranque local — servidor Python (FastAPI + Uvicorn).
"""
import os

from dotenv import load_dotenv

load_dotenv()

if __name__ == "__main__":
    import uvicorn

    from src.db.config import test_connection
    from src.db.repository import init_database

    try:
        init_database()
    except Exception:
        pass

    port = int(os.environ.get("FLASK_PORT", os.environ.get("PORT", 5000)))
    db_info = test_connection()
    print(f"\n{'='*60}")
    print("  FraudIA Claims — Python (FastAPI)")
    print(f"  http://localhost:{port}")
    print(f"  BD: {db_info.get('type', '?')} ({db_info.get('status', '?')})")
    print(f"{'='*60}\n")
    uvicorn.run("src.app.asgi:app", host="0.0.0.0", port=port, reload=True)
