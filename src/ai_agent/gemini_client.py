"""
Cliente Google Gemini (REST) para el agente antifraude.
Ideal en Vercel: solo requiere requests + GEMINI_API_KEY en variables de entorno.
"""
from __future__ import annotations

import os
from typing import Any, Dict, List, Optional, Tuple

import requests

from src.ai_agent.llm_prompts import (
    SYSTEM_PROMPT,
    build_conversational_user_prompt,
    build_user_prompt,
)

GEMINI_API_BASE = "https://generativelanguage.googleapis.com/v1beta"

DEFAULT_GEMINI_MODELS = (
    "gemini-2.0-flash",
    "gemini-1.5-flash",
    "gemini-2.0-flash-lite",
    "gemini-1.5-flash-8b",
)


def is_gemini_configured() -> bool:
    return bool(os.getenv("GEMINI_API_KEY", "").strip())


def is_gemini_enabled() -> bool:
    return os.getenv("GEMINI_ENABLED", "true").lower() not in ("0", "false", "no")


def get_gemini_model() -> str:
    return os.getenv("GEMINI_MODEL", "gemini-2.0-flash").strip() or "gemini-2.0-flash"


def _model_candidates() -> list[str]:
    configured = get_gemini_model()
    out: list[str] = []
    for m in (configured, *DEFAULT_GEMINI_MODELS):
        if m and m not in out:
            out.append(m)
    return out


def _normalize_history(history: Optional[List[Dict[str, Any]]]) -> List[Dict[str, str]]:
    turns: List[Dict[str, str]] = []
    for item in history or []:
        if not isinstance(item, dict):
            continue
        role = str(item.get("role", "user")).lower()
        content = str(item.get("content", "")).strip()
        if not content:
            continue
        if role in ("assistant", "model", "agent"):
            turns.append({"role": "model", "content": content[:4000]})
        else:
            turns.append({"role": "user", "content": content[:4000]})
    return turns[-8:]


def _call_gemini(
    model: str,
    api_key: str,
    contents: List[Dict[str, Any]],
    *,
    temperature: float = 0.35,
    max_tokens: int = 2000,
) -> Tuple[Optional[str], Optional[str]]:
    url = f"{GEMINI_API_BASE}/models/{model}:generateContent"
    payload = {
        "systemInstruction": {"parts": [{"text": SYSTEM_PROMPT}]},
        "contents": contents,
        "generationConfig": {
            "temperature": temperature,
            "maxOutputTokens": max_tokens,
        },
    }
    try:
        resp = requests.post(
            url,
            params={"key": api_key},
            json=payload,
            timeout=60,
        )
        if resp.status_code != 200:
            detail = resp.text[:240].replace("\n", " ")
            return None, f"Gemini HTTP {resp.status_code} ({model}): {detail}"
        data = resp.json()
        candidates = data.get("candidates") or []
        if not candidates:
            block = (data.get("promptFeedback") or {}).get("blockReason")
            return None, f"Gemini sin respuesta ({model})" + (f": {block}" if block else "")
        parts = (candidates[0].get("content") or {}).get("parts") or []
        text = "".join(p.get("text", "") for p in parts if isinstance(p, dict))
        if text.strip():
            return text.strip(), None
        return None, f"Gemini respuesta vacía ({model})"
    except requests.Timeout:
        return None, f"Gemini timeout ({model})"
    except Exception as exc:
        return None, f"Gemini error ({model}): {exc}"


def chat_conversational(
    question: str,
    dataset_context: str,
    history: Optional[List[Dict[str, Any]]] = None,
    factual_hints: Optional[str] = None,
) -> Tuple[Optional[str], Optional[str]]:
    """
    Chat principal: responde con contexto del análisis y historial de conversación.
    """
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        return None, "GEMINI_API_KEY no configurada en el servidor"
    if not is_gemini_enabled():
        return None, "Gemini deshabilitado (GEMINI_ENABLED=false)"

    user_text = build_conversational_user_prompt(question, dataset_context, factual_hints)
    contents: List[Dict[str, Any]] = []
    for turn in _normalize_history(history):
        contents.append({"role": turn["role"], "parts": [{"text": turn["content"]}]})
    contents.append({"role": "user", "parts": [{"text": user_text}]})

    errors: list[str] = []
    for model in _model_candidates():
        text, err = _call_gemini(model, api_key, contents)
        if text:
            return text, None
        if err:
            errors.append(err)
    return None, errors[-1] if errors else "Gemini no respondió"


def enhance_agent_answer(
    question: str,
    factual_answer: str,
    dataset_context: str,
) -> Tuple[Optional[str], Optional[str]]:
    """Reformula la respuesta factual (fallback cuando no se usa chat principal)."""
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        return None, "GEMINI_API_KEY no configurada en el servidor"
    if not is_gemini_enabled():
        return None, "Gemini deshabilitado (GEMINI_ENABLED=false)"

    user_text = build_user_prompt(question, factual_answer, dataset_context)
    contents = [{"role": "user", "parts": [{"text": user_text}]}]
    errors: list[str] = []
    for model in _model_candidates():
        text, err = _call_gemini(model, api_key, contents, temperature=0.25, max_tokens=1400)
        if text:
            return text, None
        if err:
            errors.append(err)
    return None, errors[-1] if errors else "Gemini no respondió"
