"""
Punto de entrada serverless para Vercel (Flask WSGI).
"""
import os
import sys

# Raíz del proyecto en PYTHONPATH
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

os.environ.setdefault("VERCEL", "1")

from src.app.main import app  # noqa: E402

# Vercel @vercel/python busca el objeto WSGI `app`
application = app
