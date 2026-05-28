"""Tests de clasificación del score de riesgo sugerido."""
import pytest

from src.risk.classification import (
    SCORE_AMARILLO_MAX,
    SCORE_ROJO_MIN,
    SCORE_VERDE_MAX,
    classify_risk,
    get_risk_metadata,
)


class TestClassifyRisk:
    def test_verde(self):
        assert classify_risk(0) == "Verde"
        assert classify_risk(40) == "Verde"

    def test_amarillo(self):
        assert classify_risk(41) == "Amarillo"
        assert classify_risk(75) == "Amarillo"

    def test_rojo(self):
        assert classify_risk(76) == "Rojo"
        assert classify_risk(100) == "Rojo"

    def test_metadata_acciones(self):
        assert "Continuar flujo normal" in get_risk_metadata("Verde")["accion"]
        assert "revisión documental" in get_risk_metadata("Amarillo")["accion"]
        assert "revisión especializada de campo" in get_risk_metadata("Rojo")["accion"]

    def test_constants(self):
        assert SCORE_VERDE_MAX == 40
        assert SCORE_AMARILLO_MAX == 75
        assert SCORE_ROJO_MIN == 76
