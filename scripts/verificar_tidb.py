"""Diagnóstico de conexión TiDB local (sin imprimir contraseñas)."""
from __future__ import annotations

import socket
import sys

from src.db.config import _database_url, _load_env, test_connection
from urllib.parse import urlparse

_load_env()


def _tcp_probe(host: str, port: int, timeout: float = 5.0) -> str:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return "ok"
    except OSError as exc:
        return str(exc)


def main() -> int:
    url = _database_url()
    parsed = urlparse(url)
    if not url.lower().startswith("mysql"):
        print(f"Modo BD: {url.split('://')[0]} (no TiDB)")
        return 0

    host = parsed.hostname or "?"
    port = int(parsed.port or 4000)
    user = parsed.username or "?"
    db = (parsed.path or "").lstrip("/") or "fraudia_claims"

    print(f"Host:     {host}:{port}")
    print(f"Usuario:  {user}")
    print(f"Base:     {db}")
    print(f"TCP:      {_tcp_probe(host, port)}")
    info = test_connection()
    if info.get("status") == "ok":
        print(f"SQL:      OK ({info.get('type')})")
        return 0

    print(f"SQL:      ERROR — {info.get('message', '?')[:200]}")
    print()
    print("Revise en TiDB Cloud > cluster > Connect:")
    print("  • Cluster en estado Active (no pausado)")
    print("  • Public endpoint activado")
    print("  • IP permitida (o 0.0.0.0/0 para pruebas)")
    print("  • Host/puerto/usuario iguales al .env (TIDB_HOST, TIDB_USER, …)")
    print("Si está en red corporativa, el puerto 4000 puede estar bloqueado (firewall).")
    return 1


if __name__ == "__main__":
    sys.exit(main())
