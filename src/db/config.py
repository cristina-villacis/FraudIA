"""
Configuración de base de datos.
Soporta MySQL en la nube (TiDB, AWS RDS, PlanetScale, Azure, GCP)
y SQLite como fallback local.
"""
import os
import ssl
from urllib.parse import urlparse

from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import sessionmaker, Session

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

def _database_url() -> str:
    return os.environ.get("DATABASE_URL", "sqlite:///data/fraudia_claims.db")


_engine = None
_SessionFactory = None


def _mysql_connect_args(url: str) -> dict:
    """TLS para TiDB Cloud / MySQL gestionado (Vercel serverless)."""
    if not url.lower().startswith("mysql"):
        return {}
    args: dict = {"charset": "utf8mb4"}
    host = (urlparse(url).hostname or "").lower()
    if "tidbcloud.com" in host or os.getenv("MYSQL_SSL", "").lower() in ("1", "true", "yes"):
        ctx = ssl.create_default_context()
        ctx.check_hostname = True
        ctx.verify_mode = ssl.CERT_REQUIRED
        args["ssl"] = ctx
    return args


def is_persistent_database_configured() -> bool:
    """
    True cuando la BD configurada es apta para entorno serverless (MySQL/TiDB remota).
    SQLite local en ruta de proyecto no es persistente en Vercel.
    """
    url = (_database_url() or "").strip().lower()
    if not url:
        return False
    if url.startswith("sqlite"):
        return False
    return url.startswith(("mysql", "postgresql", "postgres"))


def get_engine():
    global _engine
    url = _database_url()
    if _engine is None:
        connect_args = {}
        if url.startswith("sqlite"):
            connect_args = {"check_same_thread": False}
        else:
            connect_args = _mysql_connect_args(url)

        _engine = create_engine(
            url,
            echo=False,
            pool_pre_ping=True,
            pool_recycle=280,
            connect_args=connect_args,
        )

        if url.startswith("sqlite"):
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
        url = _database_url()
        engine = get_engine()
        with engine.connect() as conn:
            result = conn.execute(text("SELECT 1"))
            result.fetchone()
        if "tidbcloud.com" in url.lower():
            db_type = "TiDB Cloud (MySQL)"
        elif "mysql" in url.lower():
            db_type = "MySQL"
        else:
            db_type = "SQLite"
        host = url.split("@")[-1].split("/")[0] if "@" in url else "local"
        return {"status": "ok", "type": db_type, "host": host}
    except Exception as e:
        return {"status": "error", "message": str(e)}
