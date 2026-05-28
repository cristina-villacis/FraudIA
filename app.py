"""
Entrada Vercel / local — FastAPI (Python ASGI).
"""
import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

os.environ.setdefault("VERCEL", "1")
os.environ.setdefault("PYTHONPATH", ROOT)

from src.app.asgi import app  # noqa: E402
