"""
Selección de proveedor LLM para el chat (Vercel / local).

Orden por defecto (LLM_PROVIDER=auto):
  1. Google Gemini (GEMINI_API_KEY) — preferido para explicabilidad
  2. OpenAI (OPENAI_API_KEY)
  3. Motor local por reglas (sin API externa)

LLM_PROVIDER=gemini | openai | local fuerza un modo.
"""
from __future__ import annotations

import os
from typing import Any, Dict, List, Optional, Tuple

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
    if gemini_client.is_gemini_configured():
        return "gemini"
    if openai_client.is_openai_configured():
        return "openai"
    return "local"


def chat_with_llm(
    question: str,
    dataset_context: str,
    history: Optional[List[Dict[str, Any]]] = None,
    factual_hints: Optional[str] = None,
) -> Tuple[Optional[str], str, Optional[str]]:
    """
    Responde como asistente conversacional usando el análisis en contexto.
    Retorna (texto | None, nombre_motor, error | None).
    """
    provider = get_llm_provider()
    if provider == "gemini":
        text, err = gemini_client.chat_conversational(
            question, dataset_context, history=history, factual_hints=factual_hints
        )
        if text:
            return text, "gemini", None
        return None, "reglas-local", err or "Gemini no respondió"
    if provider == "openai":
        text = openai_client.chat_conversational(
            question, dataset_context, history=history, factual_hints=factual_hints
        )
        if text:
            return text, "chatgpt", None
        return None, "reglas-local", "OpenAI no respondió — verifique OPENAI_API_KEY"
    return None, "reglas-local", None


def enhance_with_llm(
    question: str,
    factual_answer: str,
    dataset_context: str,
) -> Tuple[Optional[str], str, Optional[str]]:
    """Enriquece respuesta factual (modo legacy / fallback)."""
    provider = get_llm_provider()
    if provider == "openai":
        text = openai_client.enhance_agent_answer(question, factual_answer, dataset_context)
        if text:
            return text, "chatgpt+datos", None
        return None, "reglas-local", "OpenAI no respondió — verifique OPENAI_API_KEY"
    if provider == "gemini":
        text, err = gemini_client.enhance_agent_answer(question, factual_answer, dataset_context)
        if text:
            return text, "gemini+datos", None
        return None, "reglas-local", err or "Gemini no respondió"
    return None, "reglas-local", None


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
