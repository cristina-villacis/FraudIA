"""
Extracción de texto y campos estructurados desde PDFs del evento aseguradora.
Tipos: Declaración de Accidente, Factura, Parte Policial.
"""
from __future__ import annotations

import json
import os
import re
import unicodedata
from typing import Any, Dict, Optional, Tuple

from pypdf import PdfReader

TIPOS_DOCUMENTO = {
    "declaracion_accidente": "Declaración de Accidente",
    "factura": "Factura",
    "parte_policial": "Parte Policial",
}

_PREFIX_TIPO = {
    "DA_": "declaracion_accidente",
    "PP_": "parte_policial",
    "FA_": "factura",
    "FC_": "factura",
}


def _normalize(text: str) -> str:
    t = unicodedata.normalize("NFKD", text or "")
    return "".join(c for c in t if not unicodedata.combining(c))


def extract_pdf_text(content: bytes) -> str:
    import io

    reader = PdfReader(io.BytesIO(content))
    parts = []
    for page in reader.pages:
        parts.append(page.extract_text() or "")
    return "\n".join(parts).strip()


def detect_tipo_from_filename(filename: str, folder_hint: Optional[str] = None) -> str:
    name = _normalize(filename).upper()
    if folder_hint:
        fh = _normalize(folder_hint).lower()
        if "declaracion" in fh or "accidente" in fh:
            return "declaracion_accidente"
        if "factura" in fh:
            return "factura"
        if "parte" in fh and "policial" in fh:
            return "parte_policial"
    for prefix, tipo in _PREFIX_TIPO.items():
        if name.startswith(prefix):
            return tipo
    if "FACTURA" in name or "FACTURAS" in name:
        return "factura"
    if "PARTE" in name:
        return "parte_policial"
    if name.startswith("DA_"):
        return "declaracion_accidente"
    return "declaracion_accidente"


def parse_ids_from_filename(filename: str) -> Dict[str, Optional[str]]:
    name = _normalize(os.path.basename(filename))
    out: Dict[str, Optional[str]] = {"id_siniestro": None, "id_documento": None}
    m_sin = re.search(r"(SIN-\d+)", name, re.I)
    m_doc = re.search(r"(DOC-\d+)", name, re.I)
    if m_sin:
        out["id_siniestro"] = m_sin.group(1).upper()
    if m_doc:
        out["id_documento"] = m_doc.group(1).upper()
    return out


def _first_match(pattern: str, text: str, flags: int = re.I) -> Optional[str]:
    m = re.search(pattern, text, flags)
    return m.group(1).strip() if m else None


def _parse_money(text: str) -> Optional[float]:
    m = re.search(r"\$?\s*([\d]{1,3}(?:[.,]\d{3})*(?:[.,]\d{2})?)", text)
    if not m:
        return None
    raw = m.group(1).replace(".", "").replace(",", ".")
    try:
        return float(raw)
    except ValueError:
        return None


def parse_fields_from_text(text: str, tipo: str) -> Dict[str, Any]:
    t = _normalize(text)
    fields: Dict[str, Any] = {}

    fields["id_siniestro"] = _first_match(r"Siniestro[:\s]+(SIN-\d+)", t) or _first_match(r"Siniestro Ref[:\s]+(SIN-\d+)", t)
    fields["id_documento"] = _first_match(r"Doc ID[:\s]+(DOC-\d+)", t) or _first_match(r"Doc ID Sistema[:\s]+(DOC-\d+)", t)
    fields["placa"] = _first_match(r"Placa[:\s]+([A-Z]{3}-\d{4})", t)
    fields["numero_parte_policial"] = _first_match(r"Parte Policial No[:\s]+([A-Z0-9]+)", t) or _first_match(
        r"Parte No[:\s]+([A-Z0-9]+)", t
    )
    fields["poliza"] = _first_match(r"Póliza[:\s]+([A-Z0-9-]+)", t) or _first_match(r"Poliza[:\s]+([A-Z0-9-]+)", t)
    fields["fecha_hecho"] = _first_match(r"Fecha del Hecho[:\s]+(\d{4}-\d{2}-\d{2})", t) or _first_match(
        r"Fecha[:\s]+(\d{2}-\d{2}-\d{4})", t
    )
    fields["fecha_documento"] = _first_match(r"En Quito a (\d{1,2} de [A-Za-z]+ de \d{4})", t)

    if tipo == "factura":
        fields["numero_factura"] = _first_match(r"FACTURA\s*N[ºo°\.:\s]*([0-9-]+)", t)
        fields["fecha_factura"] = _first_match(r"Fecha[:\s]+(\d{4}-\d{2}-\d{2})", t)
        fields["cliente"] = _first_match(r"Cliente[:\s]+([^\n]+)", t)
        m_total = re.search(r"TOTAL A PAGAR\s*\$?\s*([\d.,]+)", t, re.I)
        if m_total:
            fields["monto_total"] = _parse_money(m_total.group(0))
        fields["caso_muestra"] = _first_match(r"Caso[:\s]+([^\n|]+)", t)

    if tipo == "declaracion_accidente":
        desc = _first_match(
            r"Explique detalladamente como ocurrio el accidente[:\s]+(.+?)(?:A juicio del conductor|Nombres y apellidos)",
            t,
            re.S | re.I,
        )
        if desc:
            fields["descripcion"] = re.sub(r"\s+", " ", desc)[:2000]
        fields["asegurado_nombre"] = _first_match(r"Asegurado\s+([A-Z][^\n]+)", t)

    if tipo == "parte_policial":
        circ = _first_match(r"Circunstancias del Hecho[:\s]+(.+?)(?:Parte Elevado|PARTICIPANTE)", t, re.S | re.I)
        if circ:
            fields["descripcion"] = re.sub(r"\s+", " ", circ)[:2000]
        fields["conductor"] = _first_match(r"Apellidos y Nombres[:\s]+([^\n]+)", t)
        pct = _first_match(r"(\d{1,3})\s*%\s*de la suma asegurada", t)
        if pct:
            fields["pct_suma_asegurada_texto"] = int(pct)

    return {k: v for k, v in fields.items() if v is not None and str(v).strip()}


def process_pdf_upload(
    filename: str,
    content: bytes,
    tipo_hint: Optional[str] = None,
    folder_hint: Optional[str] = None,
) -> Dict[str, Any]:
    tipo_key = tipo_hint or detect_tipo_from_filename(filename, folder_hint)
    if tipo_key in TIPOS_DOCUMENTO:
        tipo_label = TIPOS_DOCUMENTO[tipo_key]
    elif tipo_key in TIPOS_DOCUMENTO.values():
        tipo_label = tipo_key
        tipo_key = next(k for k, v in TIPOS_DOCUMENTO.items() if v == tipo_key)
    else:
        tipo_key = "declaracion_accidente"
        tipo_label = TIPOS_DOCUMENTO[tipo_key]

    text = extract_pdf_text(content)
    ids = parse_ids_from_filename(filename)
    fields = parse_fields_from_text(text, tipo_key)
    for k, v in ids.items():
        if v and not fields.get(k):
            fields[k] = v

    return {
        "tipo_documento": tipo_label,
        "tipo_key": tipo_key,
        "nombre_archivo": os.path.basename(filename),
        "texto_extraido": text,
        "campos_extraidos": fields,
        "id_siniestro": fields.get("id_siniestro") or ids.get("id_siniestro"),
        "id_documento": fields.get("id_documento") or ids.get("id_documento"),
    }


def campos_to_json(fields: Dict[str, Any]) -> str:
    return json.dumps(fields, ensure_ascii=False, default=str)
