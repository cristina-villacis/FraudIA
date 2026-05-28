"""
Integra PDFs analizados con el dataset de siniestros para pipeline, dashboard y agente.
"""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

from src.risk.classification import classify_risk


def aggregate_documents_by_siniestro(documents: List[Dict[str, Any]]) -> pd.DataFrame:
    """Agrega métricas de documentos subidos por id_siniestro."""
    if not documents:
        return pd.DataFrame(
            columns=[
                "id_siniestro", "score_documentos_max", "num_pdfs_cargados",
                "alertas_pdf", "semaforo_documento_peor",
            ]
        )

    rows = []
    for doc in documents:
        id_sin = doc.get("id_siniestro")
        if not id_sin:
            continue
        alertas = doc.get("alertas") or []
        if isinstance(alertas, str):
            try:
                alertas = json.loads(alertas)
            except json.JSONDecodeError:
                alertas = []
        rows.append({
            "id_siniestro": str(id_sin),
            "score_documento": float(doc.get("score_documento") or 0),
            "semaforo": doc.get("semaforo") or "Verde",
            "tipo_documento": doc.get("tipo_documento") or "",
            "nombre_archivo": doc.get("nombre_archivo") or "",
            "alertas_text": " | ".join(
                f"{a.get('codigo', 'DOC')}: {a.get('mensaje', '')}" for a in alertas if isinstance(a, dict)
            ),
        })

    if not rows:
        return pd.DataFrame(
            columns=[
                "id_siniestro", "score_documentos_max", "num_pdfs_cargados",
                "alertas_pdf", "semaforo_documento_peor",
            ]
        )

    df = pd.DataFrame(rows)
    rank = {"Verde": 0, "Amarillo": 1, "Rojo": 2}

    def _worst_semaforo(series: pd.Series) -> str:
        best = "Verde"
        for s in series:
            if rank.get(s, 0) > rank.get(best, 0):
                best = s
        return best

    agg = df.groupby("id_siniestro", as_index=False).agg(
        score_documentos_max=("score_documento", "max"),
        num_pdfs_cargados=("nombre_archivo", "count"),
        alertas_pdf=("alertas_text", lambda x: " || ".join(v for v in x if v)),
        semaforo_documento_peor=("semaforo", _worst_semaforo),
        tipos_pdf=("tipo_documento", lambda x: ", ".join(sorted(set(str(v) for v in x if v)))),
    )
    return agg


def enrich_datasets_with_uploaded_documents(
    datasets: Dict[str, pd.DataFrame],
    documents: List[Dict[str, Any]],
) -> Dict[str, pd.DataFrame]:
    """Inyecta columnas de PDFs en siniestros antes del pipeline."""
    if not documents or "siniestros" not in datasets:
        return datasets

    sin = datasets["siniestros"].copy()
    for col in (
        "score_documentos_max", "num_pdfs_cargados", "alertas_pdf",
        "semaforo_documento_peor", "tipos_pdf", "tiene_alerta_pdf",
    ):
        if col in sin.columns:
            sin = sin.drop(columns=[col])
    agg = aggregate_documents_by_siniestro(documents)
    if agg.empty:
        return datasets

    sin = sin.merge(agg, on="id_siniestro", how="left", suffixes=("", "_pdf"))
    sin["score_documentos_max"] = sin["score_documentos_max"].fillna(0)
    sin["num_pdfs_cargados"] = sin["num_pdfs_cargados"].fillna(0).astype(int)
    sin["alertas_pdf"] = sin["alertas_pdf"].fillna("")
    sin["semaforo_documento_peor"] = sin["semaforo_documento_peor"].fillna("")
    sin["tiene_alerta_pdf"] = (sin["score_documentos_max"] >= 12).astype(int)

    datasets = dict(datasets)
    datasets["siniestros"] = sin
    return datasets


def apply_document_post_scoring(
    df_scored: pd.DataFrame,
    documents: List[Dict[str, Any]],
) -> pd.DataFrame:
    """
    Tras el pipeline ML: refuerza score/alertas con hallazgos de PDFs cargados.
    """
    if df_scored is None or df_scored.empty or not documents:
        return df_scored

    df = df_scored.copy()
    agg = aggregate_documents_by_siniestro(documents)
    if agg.empty or "id_siniestro" not in df.columns:
        return df

    df = df.merge(agg, on="id_siniestro", how="left", suffixes=("", "_dup"))
    for col in ("score_documentos_max", "num_pdfs_cargados", "alertas_pdf", "semaforo_documento_peor"):
        dup = f"{col}_dup"
        if dup in df.columns:
            df[col] = df[dup].combine_first(df.get(col))
            df.drop(columns=[dup], inplace=True, errors="ignore")

    df["score_documentos_max"] = df.get("score_documentos_max", pd.Series(0, index=df.index)).fillna(0)
    df["tiene_alerta_pdf"] = (df["score_documentos_max"] >= 12).astype(int)

    if "score_hibrido" in df.columns:
        boost = (df["score_documentos_max"] * 0.35).clip(0, 25)
        df["score_hibrido"] = np.round(
            np.maximum(df["score_hibrido"].fillna(0), df["score_hibrido"].fillna(0) + boost),
            1,
        ).clip(0, 100)
        df["semaforo_final"] = df["score_hibrido"].apply(classify_risk)

    if "alertas_reglas" in df.columns:
        def _merge_alerts(row):
            base = str(row.get("alertas_reglas") or "")
            pdf = str(row.get("alertas_pdf") or "").strip()
            if not pdf:
                return base
            extra = f"[PDF] {pdf}"
            if base and base != "Sin alertas":
                return f"{base} | {extra}"
            return extra

        df["alertas_reglas"] = df.apply(_merge_alerts, axis=1)

    return df


def build_documents_agent_summary(documents: List[Dict[str, Any]]) -> Dict[str, Any]:
    if not documents:
        return {"total": 0, "por_semaforo": {}, "items": []}

    por_sem: Dict[str, int] = {}
    items = []
    for d in documents[:25]:
        sem = d.get("semaforo") or "—"
        por_sem[sem] = por_sem.get(sem, 0) + 1
        alertas = d.get("alertas") or []
        items.append({
            "archivo": d.get("nombre_archivo"),
            "tipo": d.get("tipo_documento"),
            "siniestro": d.get("id_siniestro"),
            "semaforo": sem,
            "score": d.get("score_documento"),
            "alertas": [a.get("mensaje") for a in alertas[:3] if isinstance(a, dict)],
        })

    return {
        "total": len(documents),
        "por_semaforo": por_sem,
        "items": items,
    }


def documents_for_siniestro(documents: List[Dict[str, Any]], id_siniestro: str) -> List[Dict[str, Any]]:
    key = str(id_siniestro).strip().upper()
    return [d for d in documents if str(d.get("id_siniestro", "")).upper() == key]
