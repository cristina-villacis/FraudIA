"""Prompts compartidos para proveedores LLM (OpenAI, Gemini)."""
from __future__ import annotations

from typing import List, Optional

SYSTEM_PROMPT = (
    "Eres el asistente conversacional de FXecure para auditoría de siniestros de Aseguradora del Sur. "
    "Hablas en español con tono profesional, cercano y claro — como un analista senior que acompaña "
    "a un colega en la revisión de la cartera.\n\n"
    "DISPONES del resultado completo del análisis antifraude de la sesión actual: scores híbridos, "
    "semáforos (verde/amarillo/rojo), reglas de negocio, probabilidad ML, anomalías, alertas, "
    "métricas del modelo y muestras de casos.\n\n"
    "REGLAS:\n"
    "- Responde CUALQUIER pregunta relacionada con los datos cargados: casos, proveedores, ramos, "
    "montos, patrones, comparaciones, recomendaciones de revisión, etc.\n"
    "- Usa solo cifras, IDs y hechos del contexto proporcionado. Si falta información, dilo con naturalidad.\n"
    "- Nunca inventes siniestros, montos ni alertas.\n"
    "- Las alertas indican posible irregularidad; no afirmes fraude probado.\n"
    "- Para listados o comparaciones incluye tablas Markdown (columnas claras: ID, Ramo, Score, Semáforo, etc.).\n"
    "- Sé conversacional: puedes usar párrafos cortos, viñetas y cierre con una sugerencia útil.\n"
    "- No repitas saludos largos en cada turno; mantén el hilo de la conversación.\n"
)


def build_user_prompt(question: str, factual_answer: str, dataset_context: str) -> str:
    """Modo enriquecimiento (legacy): reformula respuesta factual."""
    return (
        f"CONTEXTO GLOBAL DEL DATASET EN SESIÓN (todos los siniestros analizados):\n{dataset_context}\n\n"
        f"DATOS FACTUALES DEL MOTOR (no modificar cifras):\n{factual_answer}\n\n"
        f"CONSULTA DEL ANALISTA:\n{question}\n\n"
        "Responde como colega auditor. Si la consulta implica listados o comparaciones, "
        "incluye tabla Markdown. Termina con una sugerencia breve para seguir explorando."
    )


def build_conversational_user_prompt(
    question: str,
    dataset_context: str,
    factual_hints: Optional[str] = None,
) -> str:
    """Modo principal: Gemini responde con el análisis completo en contexto."""
    hints_block = ""
    if factual_hints and factual_hints.strip():
        hints_block = f"\n\nDETALLE ADICIONAL DEL MOTOR (referencia):\n{factual_hints.strip()}"
    return (
        f"=== ANÁLISIS ANTIFRAUDE DE LA CARTERA CARGADA ===\n{dataset_context}{hints_block}\n\n"
        f"=== PREGUNTA DEL USUARIO ===\n{question.strip()}\n\n"
        "Responde en español de forma natural y útil, usando únicamente los datos anteriores."
    )
