"""Tests para el motor de reglas de negocio."""
import pandas as pd
import pytest
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.rules.fraud_rules import (
    score_borde_vigencia,
    score_demora_denuncia_robo,
    score_frecuencia_asegurado,
    score_frecuencia_vehiculo,
    score_frecuencia_conductor,
    score_proveedor_recurrente,
    score_documentos_incompletos,
    score_reporte_tardio,
    score_monto_cercano_suma,
    apply_rules,
    check_critical_rules,
    apply_critical_semaforo_override,
    _classify_risk,
)


class TestBordeVigencia:
    def test_within_10_days(self):
        row = pd.Series({"dias_desde_inicio_poliza": 5, "dias_desde_fin_poliza": 300})
        pts, _ = score_borde_vigencia(row)
        assert pts == 8

    def test_within_30_days(self):
        row = pd.Series({"dias_desde_inicio_poliza": 20, "dias_desde_fin_poliza": 300})
        pts, _ = score_borde_vigencia(row)
        assert pts == 4

    def test_outside_30_days(self):
        row = pd.Series({"dias_desde_inicio_poliza": 100, "dias_desde_fin_poliza": 200})
        pts, _ = score_borde_vigencia(row)
        assert pts == 0


class TestDemoraRobo:
    def test_robo_over_48h(self):
        row = pd.Series({"cobertura": "Robo", "dias_entre_ocurrencia_reporte": 5})
        pts, _ = score_demora_denuncia_robo(row)
        assert pts == 8

    def test_robo_24_48h(self):
        row = pd.Series({"cobertura": "Robo", "dias_entre_ocurrencia_reporte": 1.5})
        pts, _ = score_demora_denuncia_robo(row)
        assert pts == 4

    def test_non_robo(self):
        row = pd.Series({"cobertura": "Choque", "dias_entre_ocurrencia_reporte": 10})
        pts, _ = score_demora_denuncia_robo(row)
        assert pts == 0


class TestFrecuenciaAsegurado:
    def test_high_frequency(self):
        row = pd.Series({"frecuencia_siniestros_asegurado": 5})
        pts, _ = score_frecuencia_asegurado(row)
        assert pts == 8

    def test_medium_frequency(self):
        row = pd.Series({"frecuencia_siniestros_asegurado": 2})
        pts, _ = score_frecuencia_asegurado(row)
        assert pts == 4

    def test_low_frequency(self):
        row = pd.Series({"frecuencia_siniestros_asegurado": 1})
        pts, _ = score_frecuencia_asegurado(row)
        assert pts == 0


class TestProveedorRecurrente:
    def test_lista_restrictiva(self):
        row = pd.Series({"prov_en_lista_restrictiva": 1, "prov_casos_observados": 0})
        pts, _ = score_proveedor_recurrente(row)
        assert pts == 10

    def test_multiple_observed_cases(self):
        row = pd.Series({"prov_en_lista_restrictiva": 0, "prov_casos_observados": 4})
        pts, _ = score_proveedor_recurrente(row)
        assert pts == 5


class TestClassifyRisk:
    def test_rojo(self):
        assert _classify_risk(80) == "Rojo"

    def test_amarillo(self):
        assert _classify_risk(50) == "Amarillo"

    def test_verde(self):
        assert _classify_risk(15) == "Verde"

    def test_boundaries(self):
        assert _classify_risk(76) == "Rojo"
        assert _classify_risk(75) == "Amarillo"
        assert _classify_risk(41) == "Amarillo"
        assert _classify_risk(40) == "Verde"


class TestCriticalRules:
    def test_rf01_ptxrb(self):
        row = pd.Series({"cobertura": "Pérdida Total por Robo (PTxRB)", "descripcion": ""})
        flags = check_critical_rules(row)
        assert "RF-01" in flags

    def test_rf03_asegurado_lista(self):
        row = pd.Series({"aseg_en_lista_restrictiva": 1})
        flags = check_critical_rules(row)
        assert "RF-03" in flags

    def test_rf04_dinamica_imposible(self):
        row = pd.Series({
            "descripcion": "Volcadura en vía recta sin obstáculos visibles según fotos del lugar.",
        })
        flags = check_critical_rules(row)
        assert "RF-04" in flags

    def test_rf05_borde_48h(self):
        row = pd.Series({"dias_desde_inicio_poliza": 1, "dias_desde_fin_poliza": 200})
        flags = check_critical_rules(row)
        assert "RF-05" in flags

    def test_rf06_demora_robo(self):
        row = pd.Series({"cobertura": "Robo", "dias_entre_ocurrencia_reporte": 6})
        flags = check_critical_rules(row)
        assert "RF-06" in flags

    def test_rf07_narrativa_clonada(self):
        row = pd.Series({"id_siniestro": "SIN-000001"})
        flags = check_critical_rules(row, {"SIN-000001": 0.95})
        assert "RF-07" in flags

    def test_red_critical_forces_rojo(self):
        flags = check_critical_rules(pd.Series({"cobertura": "Pérdida Total por Robo (PTxRB)"}))
        assert apply_critical_semaforo_override(10, flags, "Verde") == "Rojo"


class TestApplyRules:
    def test_apply_rules_creates_score(self):
        df = pd.DataFrame({
            "id_siniestro": ["SIN-000001"],
            "cobertura": ["Choque"],
            "dias_desde_inicio_poliza": [100],
            "dias_desde_fin_poliza": [200],
            "dias_entre_ocurrencia_reporte": [1],
            "frecuencia_siniestros_asegurado": [1],
            "frecuencia_siniestros_vehiculo": [1],
            "frecuencia_siniestros_conductor": [1],
            "frecuencia_solo_rc": [0],
            "documentos_completos": ["Sí"],
            "monto_reclamado": [5000],
            "ratio_reclamado_asegurado": [0.3],
            "ratio_monto_vs_promedio_cobertura": [1.0],
        })
        result = apply_rules(df)
        assert "score_reglas" in result.columns
        assert "semaforo_reglas" in result.columns
        assert result["semaforo_reglas"].iloc[0] == "Verde"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
