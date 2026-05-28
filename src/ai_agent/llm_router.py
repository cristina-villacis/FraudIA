"""
Selección de proveedor LLM para el chat (Vercel / local).

Orden por defecto (LLM_PROVIDER=auto):
  1. OpenAI (OPENAI_API_KEY)
  2. Google Gemini (GEMINI_API_KEY)
  3. Motor local por reglas (sin API externa)

LLM_PROVIDER=gemini | openai | local fuerza un modo.
"""
from __future__ import annotations

import os
from typing import Optional, Tuple

from src.ai_agent import gemini_client, openai_client


def get_llm_provider() -> str:
    """Devuelve: openai | gemini | local."""
    mode = (os.getenv("LLM_PROVIDER") or "auto").strip().lower()
    if mode == "local":
        return "local"
    if mode == "openai":
        return "openai" if openai_client.is_openai_configured() else "local"
    if mode == "gemini":
        return "gemini" if gemini_client.is_gemini_configured() else "local"
    # auto
    if openai_client.is_openai_configured():
        return "openai"
    if gemini_client.is_gemini_configured():
        return "gemini"
    return "local"


def enhance_with_llm(
    question: str,
    factual_answer: str,
    dataset_context: str,
) -> Tuple[Optional[str], str]:
    """
    Enriquece respuesta factual con LLM externo si está configurado.
    Retorna (texto_enriquecido | None, nombre_motor).
    """
    provider = get_llm_provider()
    if provider == "openai":
        text = openai_client.enhance_agent_answer(question, factual_answer, dataset_context)
        if text:
            return text, "chatgpt+datos"
        return None, "reglas (OpenAI no respondió)"
    if provider == "gemini":
        text = gemini_client.enhance_agent_answer(question, factual_answer, dataset_context)
        if text:
            return text, "gemini+datos"
        return None, "reglas (Gemini no respondió)"
    return None, "reglas-local"


def llm_status() -> dict:
    provider = get_llm_provider()
    return {
        "llm_provider": provider,
        "llm_provider_mode": (os.getenv("LLM_PROVIDER") or "auto").strip().lower(),
        "openai_configured": openai_client.is_openai_configured(),
        "openai_model": openai_client.get_openai_model()
        if openai_client.is_openai_configured()
        else None,
        "gemini_configured": gemini_client.is_gemini_configured(),
        "gemini_model": gemini_client.get_gemini_model()
        if gemini_client.is_gemini_configured()
        else None,
        "local_engine_available": True,
    }
