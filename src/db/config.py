"""
Conexión a base de datos.

- Local: variables TIDB_* en `.env` (instancia Fraulocal / pruebas).
- Vercel: `DATABASE_URL` en el panel de Vercel (otra instancia).
"""
import os
import ssl
from pathlib import Path
from urllib.parse import quote_plus, urlparse

from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import sessionmaker, Session

_ROOT = Path(__file__).resolve().parents[2]
_ENV_FILE = _ROOT / ".env"


def _load_env() -> None:
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    if _ENV_FILE.is_file():
        load_dotenv(_ENV_FILE, override=True)


_load_env()


def _on_vercel() -> bool:
    return bool(os.getenv("VERCEL_ENV") or os.getenv("VERCEL_DEPLOYMENT_ID"))


def _database_url() -> str:
    if not _on_vercel():
        host = (os.getenv("TIDB_HOST") or "").strip()
        if host:
            user = os.getenv("TIDB_USER", "")
            password = os.getenv("TIDB_PASSWORD", "")
            port = (os.getenv("TIDB_PORT") or "4000").strip()
            # TiDB Connect muestra "sys"; las tablas de la app van en fraudia_claims
            database = (os.getenv("TIDB_DATABASE") or "fraudia_claims").strip()
            if database.lower() == "sys":
                database = "fraudia_claims"
            return (
                f"mysql+pymysql://{quote_plus(user)}:{quote_plus(password)}"
                f"@{host}:{port}/{database}"
            )
    return os.environ.get("DATABASE_URL", "sqlite:///data/fraudia_claims.db")


def _database_user_label() -> str:
    return urlparse(_database_url()).username or "—"


def _mysql_connect_args(url: str) -> dict:
    if not url.lower().startswith("mysql"):
        return {}
    timeout = int(os.getenv("MYSQL_CONNECT_TIMEOUT", "8"))
    args: dict = {
        "charset": "utf8mb4",
        "connect_timeout": timeout,
        "read_timeout": timeout,
        "write_timeout": timeout,
    }
    host = (urlparse(url).hostname or "").lower()
    if "tidbcloud.com" in host or os.getenv("MYSQL_SSL", "").lower() in ("1", "true", "yes"):
        ca = (os.getenv("TIDB_SSL_CA") or os.getenv("MYSQL_SSL_CA") or "").strip()
        if ca and os.path.isfile(ca):
            ctx = ssl.create_default_context(cafile=ca)
        else:
            ctx = ssl.create_default_context()
        ctx.check_hostname = True
        ctx.verify_mode = ssl.CERT_REQUIRED
        args["ssl"] = ctx
    return args


def ensure_tidb_database() -> None:
    """Crea fraudia_claims en TiDB si no existe (conexión inicial vía sys)."""
    url = _database_url()
    if not url.lower().startswith("mysql"):
        return
    parsed = urlparse(url)
    target = (parsed.path or "").lstrip("/").split("?")[0]
    if not target or target.lower() in ("sys", "mysql"):
        target = "fraudia_claims"
    base = (
        f"{parsed.scheme}://{quote_plus(parsed.username or '')}:"
        f"{quote_plus(parsed.password or '')}@{parsed.hostname}:{parsed.port or 4000}/sys"
    )
    eng = create_engine(base, connect_args=_mysql_connect_args(base), pool_pre_ping=True)
    safe = target.replace("`", "")
    with eng.connect() as conn:
        conn.execute(text(f"CREATE DATABASE IF NOT EXISTS `{safe}`"))
        conn.commit()
    eng.dispose()


def is_persistent_database_configured() -> bool:
    url = (_database_url() or "").strip().lower()
    return bool(url) and not url.startswith("sqlite") and url.startswith(("mysql", "postgresql", "postgres"))


_engine = None
_SessionFactory = None


def get_engine():
    global _engine
    url = _database_url()
    if _engine is None:
        connect_args = {"check_same_thread": False} if url.startswith("sqlite") else _mysql_connect_args(url)
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
        with get_engine().connect() as conn:
            conn.execute(text("SELECT 1")).fetchone()
        parsed = urlparse(url)
        if "tidbcloud.com" in url.lower():
            db_type = "TiDB Cloud (MySQL)"
        elif "mysql" in url.lower():
            db_type = "MySQL"
        else:
            db_type = "SQLite"
        host = f"{parsed.hostname}:{parsed.port}" if parsed.hostname else "local"
        return {
            "status": "ok",
            "type": db_type,
            "host": host,
            "database": (parsed.path or "").lstrip("/") or "—",
            "user": _database_user_label(),
        }
    except Exception as e:
        msg = str(e)
        hint = None
        if "10061" in msg or "2003" in msg or "Connection refused" in msg:
            hint = (
                "No se alcanza TiDB en el puerto 4000 (firewall, cluster pausado o endpoint público "
                "desactivado). Ejecute: python -m scripts.verificar_tidb"
            )
        elif "1045" in msg or "Access denied" in msg:
            hint = "Usuario o contraseña incorrectos en .env (TIDB_USER / TIDB_PASSWORD)."
        out = {"status": "error", "message": msg, "user": _database_user_label()}
        if hint:
            out["hint"] = hint
        return out
