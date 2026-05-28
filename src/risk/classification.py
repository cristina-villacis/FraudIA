"""
Clasificación del score de riesgo sugerido (semáforo).

Rangos de negocio:
  0-40   Verde    Bajo   - Continuar flujo normal.
  41-75  Amarillo Medio  - Escala a Unidad Antifraude para revisión documental.
  76-100 Rojo     Alto   - Escala Unidad Antifraude para revisión especializada de campo.
"""
from typing import Any, Dict, Optional

import pandas as pd

SCORE_VERDE_MAX = 40
SCORE_AMARILLO_MIN = 41
SCORE_AMARILLO_MAX = 75
SCORE_ROJO_MIN = 76

RISK_METADATA: Dict[str, Dict[str, str]] = {
    "Verde": {
        "nivel": "Bajo",
        "emoji": "🟢",
        "accion": "Continuar flujo normal.",
        "descripcion": "RIESGO BAJO — Continuar flujo normal.",
    },
    "Amarillo": {
        "nivel": "Medio",
        "emoji": "🟡",
        "accion": "Escala a Unidad Antifraude para revisión documental.",
        "descripcion": "RIESGO MEDIO — Escala a Unidad Antifraude para revisión documental.",
    },
    "Rojo": {
        "nivel": "Alto",
        "emoji": "🔴",
        "accion": "Escala Unidad Antifraude para revisión especializada de campo.",
        "descripcion": "RIESGO ALTO — Escala Unidad Antifraude para revisión especializada de campo.",
    },
}


def classify_risk(score: Any) -> str:
    """Clasifica un score 0-100 en Verde, Amarillo o Rojo."""
    if score is None or (isinstance(score, float) and pd.isna(score)):
        return "Verde"
    try:
        s = float(score)
    except (TypeError, ValueError):
        return "Verde"
    if s >= SCORE_ROJO_MIN:
        return "Rojo"
    if s >= SCORE_AMARILLO_MIN:
        return "Amarillo"
    return "Verde"


def get_risk_metadata(semaforo: str) -> Dict[str, str]:
    """Metadatos de nivel y acción sugerida para un semáforo."""
    return dict(RISK_METADATA.get(semaforo, RISK_METADATA["Verde"]))


def score_range_label(semaforo: str) -> str:
    """Etiqueta de rango numérico para documentación/UI."""
    if semaforo == "Rojo":
        return f"{SCORE_ROJO_MIN}-100"
    if semaforo == "Amarillo":
        return f"{SCORE_AMARILLO_MIN}-{SCORE_AMARILLO_MAX}"
    return f"0-{SCORE_VERDE_MAX}"
