"""
Configuración de base de datos.
Soporta MySQL en la nube (TiDB, AWS RDS, PlanetScale, Azure, GCP)
y SQLite como fallback local.
"""
import os

from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import sessionmaker, Session

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "sqlite:///data/fraudia_claims.db",
)

_engine = None
_SessionFactory = None


def get_engine():
    global _engine
    if _engine is None:
        connect_args = {}
        if DATABASE_URL.startswith("sqlite"):
            connect_args = {"check_same_thread": False}

        _engine = create_engine(
            DATABASE_URL,
            echo=False,
            pool_pre_ping=True,
            connect_args=connect_args,
        )

        if DATABASE_URL.startswith("sqlite"):
            @event.listens_for(_engine, "connect")
            def _set_sqlite_pragma(dbapi_conn, _):
                cursor = dbapi_conn.cursor()
                cursor.execute("PRAGMA journal_mode=WAL")
                cursor.execute("PRAGMA foreign_keys=ON")
                cursor.close()

    return _engine


def get_session() -> Session:
    global _SessionFactory
    if _SessionFactory is None:
        _SessionFactory = sessionmaker(bind=get_engine())
    return _SessionFactory()


def test_connection() -> dict:
    try:
        engine = get_engine()
        with engine.connect() as conn:
            result = conn.execute(text("SELECT 1"))
            result.fetchone()
        db_type = "MySQL" if "mysql" in DATABASE_URL else "SQLite"
        host = DATABASE_URL.split("@")[-1].split("/")[0] if "@" in DATABASE_URL else "local"
        return {"status": "ok", "type": db_type, "host": host}
    except Exception as e:
        return {"status": "error", "message": str(e)}
