"""
Cliente Google Gemini (REST) para el agente antifraude.
Ideal en Vercel: solo requiere requests + GEMINI_API_KEY en variables de entorno.
"""
from __future__ import annotations

import os
from typing import Optional

import requests

from src.ai_agent.llm_prompts import SYSTEM_PROMPT, build_user_prompt

GEMINI_API_BASE = "https://generativelanguage.googleapis.com/v1beta"


def is_gemini_configured() -> bool:
    return bool(os.getenv("GEMINI_API_KEY", "").strip())


def is_gemini_enabled() -> bool:
    return os.getenv("GEMINI_ENABLED", "true").lower() not in ("0", "false", "no")


def get_gemini_model() -> str:
    return os.getenv("GEMINI_MODEL", "gemini-2.0-flash").strip() or "gemini-2.0-flash"


def enhance_agent_answer(
    question: str,
    factual_answer: str,
    dataset_context: str,
) -> Optional[str]:
    """
    Reformula la respuesta factual con Gemini, sin inventar datos.
    Retorna None si no hay API key o falla la llamada.
    """
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key or not is_gemini_enabled():
        return None

    model = get_gemini_model()
    url = f"{GEMINI_API_BASE}/models/{model}:generateContent"
    user_text = build_user_prompt(question, factual_answer, dataset_context)

    payload = {
        "systemInstruction": {"parts": [{"text": SYSTEM_PROMPT}]},
        "contents": [{"role": "user", "parts": [{"text": user_text}]}],
        "generationConfig": {
            "temperature": 0.3,
            "maxOutputTokens": 1200,
        },
    }

    try:
        resp = requests.post(
            url,
            params={"key": api_key},
            json=payload,
            timeout=45,
        )
        if resp.status_code != 200:
            return None
        data = resp.json()
        candidates = data.get("candidates") or []
        if not candidates:
            return None
        parts = (candidates[0].get("content") or {}).get("parts") or []
        text = "".join(p.get("text", "") for p in parts if isinstance(p, dict))
        return text.strip() if text else None
    except Exception:
        return None
