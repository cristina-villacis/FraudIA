"""Reporte forense PDF por siniestro (formato FXecure)."""
from __future__ import annotations

import io
from typing import Any, Dict

from fpdf import FPDF

from src.reporting.case_report import build_case_report

_MESES_ES = (
    "enero", "febrero", "marzo", "abril", "mayo", "junio",
    "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
)


def _safe_text(value: Any, max_len: int = 800) -> str:
    """Texto compatible con Helvetica/latin-1: conserva tildes y ñ; sustituye símbolos especiales."""
    if value is None:
        return ""
    s = str(value).strip()
    for src, dst in (
        ("\u2265", ">="),
        ("\u2264", "<="),
        ("\u2260", "!="),
        ("\u2014", "-"),
        ("\u2013", "-"),
        ("\u2022", "-"),
        ("\u00a0", " "),
    ):
        s = s.replace(src, dst)
    try:
        s.encode("latin-1")
    except UnicodeEncodeError:
        s = s.encode("latin-1", "replace").decode("latin-1")
    return s[:max_len]


class _ReportPDF(FPDF):
    def __init__(self, case_id: str, generated: str):
        super().__init__()
        self._case_id = case_id
        self._generated = generated

    def header(self):
        self.set_font("Helvetica", "B", 10)
        self.set_text_color(0, 82, 155)
        self.cell(95, 5, "FXecure", ln=0)
        self.set_font("Helvetica", "", 8)
        self.set_text_color(80, 80, 80)
        self.cell(95, 5, "Agente IA Antifraude - Reporte de Evaluación", ln=1, align="R")
        self.set_font("Helvetica", "B", 9)
        self.set_text_color(0, 0, 0)
        self.cell(95, 5, self._case_id, ln=0)
        self.cell(95, 5, f"Generado: {self._generated}", ln=1, align="R")
        self.set_font("Helvetica", "I", 7)
        self.set_text_color(120, 120, 80)
        self.cell(0, 4, "DOCUMENTO CONFIDENCIAL - USO EXCLUSIVO UNIDAD ANTIFRAUDE", ln=1)
        self.ln(2)

    def footer(self):
        self.set_y(-10)
        self.set_font("Helvetica", "I", 7)
        self.set_text_color(120, 120, 120)
        self.cell(0, 5, f"Pág. {self.page_no()}/{{nb}}", align="R")


def build_case_forensic_pdf(case: Dict[str, Any]) -> bytes:
    """Genera PDF desde dict de reporte (build_case_report) o fila enriquecida."""
    if "alertas_tabla" not in case and "score_hibrido" in case:
        import pandas as pd
        case = build_case_report(pd.Series(case))

    pdf = _ReportPDF(
        _safe_text(case.get("id_siniestro"), 40),
        _safe_text(case.get("generado"), 20),
    )
    pdf.alias_nb_pages()
    pdf.set_auto_page_break(auto=True, margin=16)
    pdf.add_page()

    pdf.set_font("Helvetica", "B", 13)
    pdf.cell(0, 8, _safe_text(case.get("titulo")), ln=1, align="C")
    pdf.set_font("Helvetica", "", 9)
    pdf.cell(0, 5, _safe_text(case.get("subtitulo")), ln=1, align="C")
    pdf.ln(3)

    # KPI row
    score = float(case.get("score_hibrido") or 0)
    sem = _safe_text(case.get("semaforo"), 15)
    nivel = _safe_text(case.get("nivel_riesgo"), 15)
    rango = _safe_text(case.get("rango_score"), 20)

    col_w = 63
    pdf.set_fill_color(240, 248, 255)
    pdf.set_font("Helvetica", "B", 8)
    pdf.cell(col_w, 5, "SCORE DE RIESGO", border=1, fill=True)
    pdf.cell(col_w, 5, "NIVEL DE RIESGO", border=1, fill=True)
    pdf.cell(col_w, 5, "RANGO", border=1, fill=True, ln=1)
    pdf.set_font("Helvetica", "B", 14)
    pdf.cell(col_w, 10, f"{score:.1f}", border=1, align="C")
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(col_w, 10, nivel, border=1, align="C")
    pdf.cell(col_w, 10, rango, border=1, align="C", ln=1)
    pdf.ln(2)
    pdf.set_font("Helvetica", "B", 9)
    pdf.multi_cell(0, 5, "ACCIÓN SUGERIDA: " + _safe_text(case.get("accion_destacada"), 400))
    pdf.ln(4)

    # Section 1
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(0, 6, "1. IDENTIFICACIÓN DEL SINIESTRO", ln=1)
    pdf.set_font("Helvetica", "", 9)
    fields = [
        ("No. Siniestro", case.get("id_siniestro")),
        ("Ramo", case.get("ramo")),
        ("Cobertura", case.get("cobertura")),
        ("Fecha de análisis", case.get("generado")),
        ("Monto reclamado", f"${float(case.get('monto_reclamado') or 0):,.2f}"),
        ("Asegurado", case.get("nombre_asegurado")),
        ("Póliza", case.get("id_poliza")),
        ("Reporte tardío", case.get("reporte_tardio") or "—"),
    ]
    half = 95
    for i in range(0, len(fields), 2):
        l1, v1 = fields[i]
        pdf.cell(40, 5, f"{l1}", border=0)
        pdf.cell(half - 40, 5, _safe_text(v1, 80), border=0)
        if i + 1 < len(fields):
            l2, v2 = fields[i + 1]
            pdf.cell(40, 5, f"{l2}", border=0)
            pdf.cell(half - 40, 5, _safe_text(v2, 80), border=0, ln=1)
        else:
            pdf.ln(5)
    pdf.ln(3)

    # Section 2 - alerts table
    alertas = case.get("alertas_tabla") or []
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(0, 6, f"2. ALERTAS DETECTADAS ({len(alertas)} senales)", ln=1)
    pdf.set_font("Helvetica", "B", 7)
    w = [8, 72, 28, 14, 18]
    headers = ["#", "DESCRIPCIÓN", "UMBRAL", "PTS", "SEV."]
    for h, ww in zip(headers, w):
        pdf.cell(ww, 5, h, border=1, fill=True)
    pdf.ln(5)
    pdf.set_font("Helvetica", "", 7)
    for a in alertas[:14]:
        pdf.cell(w[0], 5, str(a.get("num", "")), border=1)
        pdf.cell(w[1], 5, _safe_text(a.get("descripcion"), 55), border=1)
        pdf.cell(w[2], 5, _safe_text(a.get("umbral"), 18), border=1)
        pdf.cell(w[3], 5, str(a.get("puntos", "")), border=1)
        pdf.cell(w[4], 5, _safe_text(a.get("severidad"), 10), border=1, ln=1)
    pdf.ln(4)

    # Section 3 - factors
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(0, 6, "3. FACTORES PRINCIPALES DE EVALUACION", ln=1)
    pdf.set_font("Helvetica", "", 9)
    for f in case.get("factores_evaluacion") or []:
        pdf.cell(0, 5, f"  {_safe_text(f.get('factor'))}: {_safe_text(f.get('valor'))}", ln=1)
    pdf.ln(3)

    # Section 4 - score bars
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(0, 6, "4. DISTRIBUCIÓN DEL SCORE", ln=1)
    bars = case.get("score_bars") or []
    if bars:
        labels = "  ".join(f"{b.get('label')} {b.get('puntos')} pts" for b in bars[:10])
        pdf.set_font("Helvetica", "", 7)
        pdf.multi_cell(0, 4, _safe_text(labels, 200))
        vals = " ".join(str(b.get("puntos", 0)) for b in bars[:10])
        pdf.cell(0, 5, vals, ln=1)
    pdf.set_font("Helvetica", "I", 8)
    pdf.multi_cell(0, 4, _safe_text(case.get("distribucion_nota"), 200))
    pdf.ln(3)

    # Section 5
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(0, 6, "5. CONCLUSIÓN Y RECOMENDACIÓN", ln=1)
    pdf.set_font("Helvetica", "", 9)
    pdf.multi_cell(0, 5, _safe_text(case.get("conclusion"), 1200))
    pdf.ln(4)
    pdf.set_font("Helvetica", "I", 8)
    pdf.cell(0, 5, _safe_text(case.get("pie")), ln=1, align="C")
    try:
        from datetime import datetime
        now = datetime.now()
        fecha_pie = f"{now.day} de {_MESES_ES[now.month - 1].capitalize()} de {now.year}"
    except Exception:
        fecha_pie = _safe_text(case.get("pie_fecha"))
    pdf.cell(0, 5, fecha_pie, ln=1, align="C")

    buf = io.BytesIO()
    pdf.output(buf)
    return buf.getvalue()
