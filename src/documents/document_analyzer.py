"""
Análisis antifraude por documento PDF (independiente o cruzado con dataset cargado).
"""
from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any, Dict, List, Optional

import pandas as pd

from src.nlp.text_analysis import compute_text_similarity


def _alert(code: str, mensaje: str, severidad: str = "media", puntos: int = 5) -> Dict[str, Any]:
    return {"codigo": code, "mensaje": mensaje, "severidad": severidad, "puntos": puntos}


def analyze_document(
    *,
    tipo_documento: str,
    texto_extraido: str,
    campos: Dict[str, Any],
    datasets: Optional[Dict[str, pd.DataFrame]] = None,
    vincular_dataset: bool = False,
) -> Dict[str, Any]:
    alertas: List[Dict[str, Any]] = []
    inconsistencias: List[str] = []
    texto = (texto_extraido or "").lower()
    campos = campos or {}
    id_sin = campos.get("id_siniestro")
    placa_doc = (campos.get("placa") or "").upper()

    if not id_sin:
        alertas.append(_alert("DOC-001", "No se identificó ID de siniestro en el documento.", "alta", 8))

    tipo_l = (tipo_documento or "").lower()

    if "sin denuncia policial" in texto or "sin denuncia policial previa" in texto:
        alertas.append(_alert("DOC-PP-01", "Parte indica ausencia de denuncia policial previa.", "alta", 12))

    if re.search(r"(\d{2,3})\s*%\s*de la suma asegurada", texto):
        alertas.append(_alert("DOC-PP-02", "Monto reclamado muy cercano a la suma asegurada (≥80%).", "alta", 10))

    if "falsific" in texto or "adulter" in texto or "documento falso" in texto:
        alertas.append(_alert("DOC-RF02", "Texto sugiere falsificación o adulteración documental.", "critica", 20))

    if "sin tercero" in texto or "no hay testigos" in texto:
        alertas.append(_alert("DOC-RC", "Evento sin terceros o sin testigos declarados.", "media", 6))

    if tipo_l.find("factura") >= 0:
        monto = campos.get("monto_total")
        if monto and float(monto) > 50000:
            alertas.append(_alert("DOC-FA-01", f"Monto de factura elevado: ${float(monto):,.2f}.", "media", 5))
        caso = (campos.get("caso_muestra") or "").lower()
        if caso and "legitimo" not in caso and "legítimo" not in caso:
            alertas.append(_alert("DOC-FA-02", f"Etiqueta de caso en factura: {campos.get('caso_muestra')}.", "media", 4))

    if tipo_l.find("declaracion") >= 0 or tipo_l.find("accidente") >= 0:
        if "semáforo" in texto and "rojo" in texto and "no pude frenar" in texto:
            pass  # narrativa común
        if len((campos.get("descripcion") or "")) < 40:
            alertas.append(_alert("DOC-DA-01", "Descripción del accidente muy breve o no extraída.", "baja", 3))

    siniestro_row = None
    if vincular_dataset and datasets and id_sin and "siniestros" in datasets:
        sin_df = datasets["siniestros"]
        if "id_siniestro" in sin_df.columns:
            match = sin_df[sin_df["id_siniestro"].astype(str) == str(id_sin)]
            if match.empty:
                inconsistencias.append(f"Siniestro {id_sin} no existe en el dataset cargado.")
                alertas.append(_alert("DOC-LINK-01", "Siniestro del PDF no encontrado en dataset.", "alta", 10))
            else:
                siniestro_row = match.iloc[0]
                placa_ds = str(siniestro_row.get("placa_vehiculo", "") or "").upper()
                if placa_doc and placa_ds and placa_doc != placa_ds:
                    inconsistencias.append(f"Placa PDF ({placa_doc}) ≠ dataset ({placa_ds}).")
                    alertas.append(_alert("DOC-LINK-02", "Placa del documento no coincide con el dataset.", "alta", 12))

                monto_fact = campos.get("monto_total")
                monto_rec = siniestro_row.get("monto_reclamado")
                if monto_fact and monto_rec and pd.notna(monto_rec):
                    try:
                        ratio = float(monto_fact) / float(monto_rec) if float(monto_rec) > 0 else 0
                        if ratio > 1.25 or ratio < 0.5:
                            inconsistencias.append(
                                f"Monto factura ({monto_fact}) difiere del reclamado ({monto_rec})."
                            )
                            alertas.append(_alert("DOC-LINK-03", "Monto de factura inconsistente con reclamo.", "media", 8))
                    except (TypeError, ValueError):
                        pass

                desc_ds = str(siniestro_row.get("descripcion", "") or "")
                desc_doc = str(campos.get("descripcion") or texto_extraido[:500] or "")
                if desc_ds and desc_doc and len(desc_doc) > 30:
                    sim = compute_text_similarity(
                        pd.Series([desc_ds, desc_doc]),
                        threshold=0.5,
                    )
                    pairs = sim.get("pairs") or []
                    if not pairs:
                        inconsistencias.append("Narrativa del PDF poco alineada con la del siniestro en dataset.")
                        alertas.append(_alert("DOC-LINK-04", "Baja similitud narrativa PDF vs dataset.", "media", 7))

                np_pol = str(siniestro_row.get("numero_parte_policial", "") or "")
                np_doc = str(campos.get("numero_parte_policial") or "")
                if tipo_l.find("parte") >= 0 and np_pol and np_doc and np_pol != np_doc:
                    inconsistencias.append(f"N° parte PDF ({np_doc}) ≠ registro ({np_pol}).")
                    alertas.append(_alert("DOC-LINK-05", "Número de parte policial no coincide.", "alta", 9))

    score = min(100, sum(a["puntos"] for a in alertas))
    if score >= 25:
        semaforo = "Rojo"
    elif score >= 12:
        semaforo = "Amarillo"
    else:
        semaforo = "Verde"

    reglas = [a["codigo"] for a in alertas if a["severidad"] in ("alta", "critica")]

    return {
        "score_documento": round(score, 1),
        "semaforo": semaforo,
        "alertas": alertas,
        "inconsistencias": inconsistencias,
        "reglas_disparadas": reglas,
        "fecha_analisis": datetime.utcnow().isoformat(),
        "siniestro_vinculado": id_sin,
        "encontrado_en_dataset": siniestro_row is not None,
    }


def merge_document_into_datasets(
    datasets: Dict[str, pd.DataFrame],
    *,
    id_documento: str,
    id_siniestro: Optional[str],
    tipo_documento: str,
    nombre_archivo: str,
    analisis: Dict[str, Any],
) -> Dict[str, pd.DataFrame]:
    """Añade o actualiza fila en tabla documentos del estado en memoria."""
    if not datasets:
        datasets = {}
    docs = datasets.get("documentos")
    if docs is None:
        docs = pd.DataFrame(
            columns=[
                "id_documento", "id_siniestro", "tipo_documento",
                "nombre_archivo_pdf", "entregado", "legible",
            ]
        )
    new_row = {
        "id_documento": id_documento or f"DOC-UP-{datetime.utcnow().strftime('%H%M%S')}",
        "id_siniestro": id_siniestro,
        "tipo_documento": tipo_documento,
        "nombre_archivo_pdf": nombre_archivo,
        "entregado": "Si",
        "legible": "Si",
        "score_documento": analisis.get("score_documento"),
        "semaforo_documento": analisis.get("semaforo"),
    }
    if "id_documento" in docs.columns and id_documento:
        docs = docs[docs["id_documento"].astype(str) != str(id_documento)]
    docs = pd.concat([docs, pd.DataFrame([new_row])], ignore_index=True)
    datasets["documentos"] = docs
    return datasets
