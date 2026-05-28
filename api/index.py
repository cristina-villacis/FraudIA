"""
Entrada Vercel — Flask WSGI (app exportada para serverless).
"""
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

os.environ.setdefault("VERCEL", "1")
os.environ.setdefault("PYTHONPATH", ROOT)

from src.app.main import app  # noqa: E402  # Flask instance `app`
