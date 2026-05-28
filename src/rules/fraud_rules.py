"""
Motor de reglas de negocio para detección de fraude en seguros.
Implementa las señales y reglas críticas definidas en el documento de requerimientos.
"""
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd


SIGNAL_CONFIG = {
    "borde_vigencia": {
        "nombre": "Reclamo cercano al borde de vigencia",
        "max_pts": 8,
        "campo": "dias_desde_inicio_poliza",
    },
    "demora_denuncia_robo": {
        "nombre": "Demora denuncia por robo",
        "max_pts": 8,
        "campo": "dias_entre_ocurrencia_reporte",
    },
    "frecuencia_asegurado": {
        "nombre": "Alta frecuencia de reclamos Asegurado",
        "max_pts": 8,
        "campo": "frecuencia_siniestros_asegurado",
    },
    "frecuencia_vehiculo": {
        "nombre": "Alta frecuencia de reclamos Vehículo",
        "max_pts": 6,
        "campo": "frecuencia_siniestros_vehiculo",
    },
    "frecuencia_conductor": {
        "nombre": "Alta frecuencia de conductor",
        "max_pts": 8,
        "campo": "frecuencia_siniestros_conductor",
    },
    "frecuencia_rc": {
        "nombre": "Alta frecuencia reclamos solo RC",
        "max_pts": 6,
        "campo": "frecuencia_solo_rc",
    },
    "proveedor_recurrente": {
        "nombre": "Beneficiario / Proveedor recurrente",
        "max_pts": 10,
    },
    "documentos_incompletos": {
        "nombre": "Documentos incompletos",
        "max_pts": 4,
        "campo": "documentos_completos",
    },
    "dinamica_sospechosa": {
        "nombre": "Dinámica sospechosa",
        "max_pts": 6,
        "campo": "flag_dinamica_sospechosa",
    },
    "sin_tercero_identificado": {
        "nombre": "Eventos sin tercero identificado",
        "max_pts": 5,
        "campo": "flag_sin_tercero_identificado",
    },
    "documentos_inconsistentes": {
        "nombre": "Documentos inconsistentes",
        "max_pts": 10,
    },
    "reporte_tardio": {
        "nombre": "Reporte tardío",
        "max_pts": 5,
        "campo": "dias_entre_ocurrencia_reporte",
    },
    "narrativa_similar": {
        "nombre": "Narrativas similares",
        "max_pts": 8,
    },
    "monto_cercano_suma": {
        "nombre": "Monto cercano o superior a suma asegurada",
        "max_pts": 5,
        "campo": "ratio_reclamado_asegurado",
    },
}

CRITICAL_RULES = {
    "RF-01": {
        "regla": "Cobertura Pérdida Total por Robo (PTxRB)",
        "clasificacion": "Rojo",
    },
    "RF-02": {
        "regla": "Evidencia de Falsificación o Adulteración Documental Evidente",
        "clasificacion": "Rojo",
    },
    "RF-03": {
        "regla": "Asegurado, Beneficiario o APS — Coincidencia exacta con Lista Restrictiva",
        "clasificacion": "Rojo",
    },
    "RF-04": {
        "regla": "Dinámica del Accidente Físicamente Imposible",
        "clasificacion": "Rojo",
    },
    "RF-05": {
        "regla": "Siniestro Extremo al Borde de Vigencia (< 48 hrs)",
        "clasificacion": "Amarillo",
    },
    "RF-06": {
        "regla": "Demora Atípica en Denuncia de Robo (> 4 días)",
        "clasificacion": "Amarillo",
    },
    "RF-07": {
        "regla": "Narrativa Idéntica (Clonada)",
        "clasificacion": "Amarillo",
    },
}

_DINAMICA_IMPOSIBLE_KEYWORDS = (
    "físicamente imposible",
    "fisicamente imposible",
    "dinámica imposible",
    "dinamica imposible",
    "volcadura en vía recta sin obstáculos",
    "volcadura en via recta sin obstaculos",
    "relatos contradictorios",
    "fotos no coinciden",
)

_FALSIFICACION_KEYWORDS = (
    "falsific",
    "adulter",
    "documento alterado",
    "documento falso",
)


def score_borde_vigencia(row: pd.Series) -> Tuple[int, str]:
    dias = row.get("dias_desde_inicio_poliza", 999)
    dias_fin = row.get("dias_desde_fin_poliza", 999)
    min_dias = min(dias, dias_fin) if not pd.isna(dias_fin) else dias

    if pd.isna(min_dias):
        return 0, ""
    if min_dias <= 10:
        return 8, f"Siniestro a {int(min_dias)} días del borde de vigencia (≤10 días: 8 pts)"
    elif min_dias <= 30:
        return 4, f"Siniestro a {int(min_dias)} días del borde de vigencia (11-30 días: 4 pts)"
    return 0, ""


def score_demora_denuncia_robo(row: pd.Series) -> Tuple[int, str]:
    cobertura = str(row.get("cobertura", "")).lower()
    if "robo" not in cobertura:
        return 0, ""

    dias = row.get("dias_entre_ocurrencia_reporte", 0)
    if pd.isna(dias):
        return 0, ""

    horas_estimadas = dias * 24
    if horas_estimadas > 48:
        return 8, f"Demora de ~{int(horas_estimadas)}h en denuncia de robo (>48h: 8 pts)"
    elif horas_estimadas >= 24:
        return 4, f"Demora de ~{int(horas_estimadas)}h en denuncia de robo (24-48h: 4 pts)"
    return 0, ""


def score_frecuencia_asegurado(row: pd.Series) -> Tuple[int, str]:
    freq = row.get("frecuencia_siniestros_asegurado", 0)
    if pd.isna(freq):
        return 0, ""
    if freq >= 3:
        return 8, f"Asegurado con {int(freq)} siniestros (≥3: 8 pts)"
    elif freq == 2:
        return 4, f"Asegurado con {int(freq)} siniestros (2: 4 pts)"
    return 0, ""


def score_frecuencia_vehiculo(row: pd.Series) -> Tuple[int, str]:
    freq = row.get("frecuencia_siniestros_vehiculo", 0)
    if pd.isna(freq):
        return 0, ""
    if freq >= 3:
        return 6, f"Vehículo con {int(freq)} siniestros (≥3: 6 pts)"
    elif freq == 2:
        return 3, f"Vehículo con {int(freq)} siniestros (2: 3 pts)"
    return 0, ""


def score_frecuencia_conductor(row: pd.Series) -> Tuple[int, str]:
    freq = row.get("frecuencia_siniestros_conductor", 0)
    if pd.isna(freq):
        return 0, ""
    if freq >= 3:
        return 8, f"Conductor presente en {int(freq)} siniestros (≥3: 8 pts)"
    elif freq == 2:
        return 4, f"Conductor en {int(freq)} siniestros (2: 4 pts)"
    return 0, ""


def score_frecuencia_rc(row: pd.Series) -> Tuple[int, str]:
    freq = row.get("frecuencia_solo_rc", 0)
    if pd.isna(freq):
        return 0, ""
    if freq > 2:
        return 6, f"Frecuencia atípica solo RC: {int(freq)} eventos (>2: 6 pts)"
    elif freq == 1:
        return 3, f"Evento previo solo RC (1: 3 pts)"
    return 0, ""


def score_proveedor_recurrente(row: pd.Series) -> Tuple[int, str]:
    en_lista = row.get("prov_en_lista_restrictiva", 0)
    if not pd.isna(en_lista) and en_lista == 1:
        return 10, "Proveedor en Lista Restrictiva (10 pts)"

    casos_obs = row.get("prov_casos_observados", 0)
    if not pd.isna(casos_obs) and casos_obs > 2:
        return 5, f"Proveedor con {int(casos_obs)} casos observados este año (>2: 5 pts)"
    return 0, ""


def score_documentos_incompletos(row: pd.Series) -> Tuple[int, str]:
    docs = str(row.get("documentos_completos", "Sí")).lower()
    if docs == "no":
        return 4, "Documentos incompletos - falta documentación obligatoria (4 pts)"
    return 0, ""


def score_documentos_inconsistentes(row: pd.Series) -> Tuple[int, str]:
    tiene_inc = row.get("tiene_inconsistencia_doc", 0)
    if not pd.isna(tiene_inc) and tiene_inc > 0:
        return 10, "Documentos con inconsistencias detectadas (10 pts)"
    return 0, ""


def score_dinamica_sospechosa(row: pd.Series) -> Tuple[int, str]:
    if row.get("flag_dinamica_sospechosa", 0) == 1:
        return 6, "Dinámica del siniestro sospechosa o incongruente con el tipo de accidente (6 pts)"
    return 0, ""


def score_sin_tercero_identificado(row: pd.Series) -> Tuple[int, str]:
    if row.get("flag_sin_tercero_identificado", 0) == 1:
        return 5, "Evento reportado sin tercero identificado verificable (5 pts)"
    return 0, ""


def score_reporte_tardio(row: pd.Series) -> Tuple[int, str]:
    dias = row.get("dias_entre_ocurrencia_reporte", 0)
    if pd.isna(dias):
        return 0, ""
    if dias > 7:
        return 5, f"Reporte tardío: {int(dias)} días después del evento (>7 días: 5 pts)"
    elif 4 <= dias <= 7:
        return 3, f"Reporte tardío: {int(dias)} días después del evento (4-7 días: 3 pts)"
    return 0, ""


def score_monto_cercano_suma(row: pd.Series) -> Tuple[int, str]:
    ratio = row.get("ratio_reclamado_asegurado", 0)
    ratio_prom = row.get("ratio_monto_vs_promedio_cobertura", 1)

    if pd.isna(ratio):
        ratio = 0
    if pd.isna(ratio_prom):
        ratio_prom = 1

    if ratio > 0.95 or ratio_prom > 1.5:
        return 5, f"Monto reclamado {ratio*100:.0f}% de suma asegurada o {ratio_prom:.1f}x del promedio (4-5 pts)"
    return 0, ""


SCORING_FUNCTIONS = {
    "borde_vigencia": score_borde_vigencia,
    "demora_denuncia_robo": score_demora_denuncia_robo,
    "frecuencia_asegurado": score_frecuencia_asegurado,
    "frecuencia_vehiculo": score_frecuencia_vehiculo,
    "frecuencia_conductor": score_frecuencia_conductor,
    "frecuencia_rc": score_frecuencia_rc,
    "proveedor_recurrente": score_proveedor_recurrente,
    "documentos_incompletos": score_documentos_incompletos,
    "dinamica_sospechosa": score_dinamica_sospechosa,
    "sin_tercero_identificado": score_sin_tercero_identificado,
    "documentos_inconsistentes": score_documentos_inconsistentes,
    "reporte_tardio": score_reporte_tardio,
    "monto_cercano_suma": score_monto_cercano_suma,
}

MAX_SCORE_RULES = sum(cfg["max_pts"] for cfg in SIGNAL_CONFIG.values())


def apply_rules(df: pd.DataFrame, similarity_scores: Dict[str, float] = None) -> pd.DataFrame:
    from src.utils.dataframe_columns import ensure_str_columns

    df = ensure_str_columns(df.copy())
    all_scores = []
    all_alerts = []
    all_details = []
    all_critical = []

    for idx, row in df.iterrows():
        row_score = 0
        row_alerts = []
        row_details = {}

        for signal_name, func in SCORING_FUNCTIONS.items():
            pts, explanation = func(row)
            row_details[signal_name] = pts
            if pts > 0:
                row_score += pts
                row_alerts.append(explanation)

        if similarity_scores and row.get("id_siniestro") in similarity_scores:
            sim = similarity_scores[row["id_siniestro"]]
            if sim > 0.85:
                pts = 8
                row_alerts.append(f"Similitud textual >{sim*100:.0f}% con otro reclamo (8 pts)")
            elif sim >= 0.70:
                pts = 4
                row_alerts.append(f"Similitud textual {sim*100:.0f}% con otro reclamo (4 pts)")
            else:
                pts = 0
            row_score += pts
            row_details["narrativa_similar"] = pts

        critical_flags = check_critical_rules(row, similarity_scores)
        for code, info in critical_flags.items():
            row_alerts.append(f"[{code}] {info['regla']} → {info['clasificacion']}")

        all_scores.append(row_score)
        all_alerts.append(row_alerts)
        all_details.append(row_details)
        all_critical.append(critical_flags)

    score_normalized = np.array(all_scores, dtype=float)
    score_normalized = np.clip(score_normalized / MAX_SCORE_RULES * 100, 0, 100)

    df["score_reglas"] = np.round(score_normalized, 1)
    df["alertas_reglas"] = [" | ".join(a) if a else "Sin alertas" for a in all_alerts]
    df["num_alertas"] = [len(a) for a in all_alerts]
    df["detalle_reglas"] = all_details
    df["reglas_criticas"] = [
        ", ".join(sorted(flags.keys())) if flags else ""
        for flags in all_critical
    ]

    df["semaforo_reglas"] = df["score_reglas"].apply(_classify_risk)
    df["semaforo_reglas"] = [
        apply_critical_semaforo_override(score, flags, sem)
        for score, flags, sem in zip(df["score_reglas"], all_critical, df["semaforo_reglas"])
    ]
    df["score_reglas"] = [
        apply_critical_score_floor(score, flags)
        for score, flags in zip(df["score_reglas"], all_critical)
    ]

    return ensure_str_columns(df)


def _norm_text(value) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    return str(value).lower().strip()


def _is_truthy_flag(value) -> bool:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return False
    if isinstance(value, (int, float, np.integer, np.floating)):
        return int(value) == 1
    return str(value).strip().lower() in ("1", "true", "si", "sí", "yes")


def _is_ptxrb(cobertura: str, descripcion: str = "") -> bool:
    text = f"{cobertura} {descripcion}".lower()
    if "ptxrb" in text or "pt x rb" in text:
        return True
    has_robo = "robo" in text
    has_perdida_total = "pérdida total" in text or "perdida total" in text
    return has_robo and has_perdida_total


def _is_robo_cobertura(cobertura: str) -> bool:
    c = _norm_text(cobertura)
    return "robo" in c or "ptxrb" in c


def _hours_from_policy_border(row: pd.Series) -> float:
    dias_inicio = row.get("dias_desde_inicio_poliza", 999)
    dias_fin = row.get("dias_desde_fin_poliza", 999)
    candidates = []
    for d in (dias_inicio, dias_fin):
        if d is not None and not (isinstance(d, float) and pd.isna(d)):
            candidates.append(float(d))
    if not candidates:
        return 999 * 24
    return min(candidates) * 24


def check_critical_rules(row: pd.Series, similarity_scores: Dict = None) -> Dict:
    """Evalúa reglas críticas RF-01 … RF-07. Retorna dict código → metadatos."""
    flags = {}
    cobertura = _norm_text(row.get("cobertura", ""))
    descripcion = _norm_text(row.get("descripcion", ""))

    # RF-01 — PTxRB (Rojo)
    if _is_ptxrb(cobertura, descripcion):
        flags["RF-01"] = CRITICAL_RULES["RF-01"]

    # RF-02 — Falsificación / adulteración documental (Rojo)
    if _is_truthy_flag(row.get("tiene_inconsistencia_doc")) or _is_truthy_flag(row.get("flag_falsificacion_doc")):
        flags["RF-02"] = CRITICAL_RULES["RF-02"]
    elif any(kw in descripcion for kw in _FALSIFICACION_KEYWORDS):
        flags["RF-02"] = CRITICAL_RULES["RF-02"]

    # RF-03 — Lista restrictiva: asegurado, beneficiario, proveedor/APS (Rojo)
    if (
        _is_truthy_flag(row.get("prov_en_lista_restrictiva"))
        or _is_truthy_flag(row.get("aseg_en_lista_restrictiva"))
        or _is_truthy_flag(row.get("beneficiario_en_lista_restrictiva"))
        or _is_truthy_flag(row.get("conductor_en_lista_restrictiva"))
    ):
        flags["RF-03"] = CRITICAL_RULES["RF-03"]

    # RF-04 — Dinámica físicamente imposible (Rojo)
    if _is_truthy_flag(row.get("flag_dinamica_imposible")):
        flags["RF-04"] = CRITICAL_RULES["RF-04"]
    elif any(kw in descripcion for kw in _DINAMICA_IMPOSIBLE_KEYWORDS):
        flags["RF-04"] = CRITICAL_RULES["RF-04"]

    # RF-05 — Borde de vigencia < 48 h (Amarillo)
    if _hours_from_policy_border(row) < 48:
        flags["RF-05"] = CRITICAL_RULES["RF-05"]

    # RF-06 — Demora denuncia robo > 4 días (Amarillo)
    if _is_robo_cobertura(cobertura):
        dias_rep = row.get("dias_entre_ocurrencia_reporte", 0)
        if not pd.isna(dias_rep) and float(dias_rep) > 4:
            flags["RF-06"] = CRITICAL_RULES["RF-06"]

    # RF-07 — Narrativa clonada (Amarillo)
    if similarity_scores:
        id_sin = row.get("id_siniestro")
        if id_sin in similarity_scores and similarity_scores[id_sin] >= 0.90:
            flags["RF-07"] = CRITICAL_RULES["RF-07"]

    return flags


def apply_critical_semaforo_override(score: float, flags: Dict, semaforo: str) -> str:
    """Las reglas críticas rojas fuerzan Rojo; las amarillas elevan al menos a Amarillo."""
    if not flags:
        return semaforo
    if any(CRITICAL_RULES[c]["clasificacion"] == "Rojo" for c in flags):
        return "Rojo"
    if any(CRITICAL_RULES[c]["clasificacion"] == "Amarillo" for c in flags):
        if semaforo == "Verde":
            return "Amarillo"
    return semaforo


def apply_critical_score_floor(score: float, flags: Dict) -> float:
    """Garantiza score mínimo acorde a reglas críticas activas."""
    if not flags:
        return float(score)
    if any(CRITICAL_RULES[c]["clasificacion"] == "Rojo" for c in flags):
        return float(max(score, 76))
    if any(CRITICAL_RULES[c]["clasificacion"] == "Amarillo" for c in flags):
        return float(max(score, 41))
    return float(score)


# Alias interno legacy
_check_critical_rules = check_critical_rules


def _classify_risk(score: float) -> str:
    from src.risk.classification import classify_risk

    return classify_risk(score)


def get_rules_summary(df: pd.DataFrame) -> Dict:
    if "semaforo_reglas" not in df.columns:
        return {}

    total = len(df)
    counts = df["semaforo_reglas"].value_counts().to_dict()
    return {
        "total_siniestros": total,
        "rojo": counts.get("Rojo", 0),
        "amarillo": counts.get("Amarillo", 0),
        "verde": counts.get("Verde", 0),
        "pct_rojo": round(counts.get("Rojo", 0) / total * 100, 1) if total > 0 else 0,
        "pct_amarillo": round(counts.get("Amarillo", 0) / total * 100, 1) if total > 0 else 0,
        "pct_verde": round(counts.get("Verde", 0) / total * 100, 1) if total > 0 else 0,
        "score_promedio": round(df["score_reglas"].mean(), 1),
        "score_max": round(df["score_reglas"].max(), 1),
    }
