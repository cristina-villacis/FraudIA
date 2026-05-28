"""
Punto de entrada Vercel / Flask (detectado como `app:app`).
"""
import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

os.environ.setdefault("VERCEL", "1")
os.environ.setdefault("PYTHONPATH", ROOT)

from src.app.main import app  # noqa: E402
