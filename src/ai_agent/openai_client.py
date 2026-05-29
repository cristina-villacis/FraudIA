"""
Cliente opcional OpenAI (ChatGPT) para el agente de siniestros.
La API key debe estar en OPENAI_API_KEY (.env), nunca en el código.
"""
from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

from src.ai_agent.llm_prompts import (
    SYSTEM_PROMPT,
    build_conversational_user_prompt,
    build_user_prompt,
)


def is_openai_configured() -> bool:
    return bool(os.getenv("OPENAI_API_KEY", "").strip())


def get_openai_model() -> str:
    return os.getenv("OPENAI_MODEL", "gpt-4o-mini").strip() or "gpt-4o-mini"


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
            turns.append({"role": "assistant", "content": content[:4000]})
        else:
            turns.append({"role": "user", "content": content[:4000]})
    return turns[-8:]


def chat_conversational(
    question: str,
    dataset_context: str,
    history: Optional[List[Dict[str, Any]]] = None,
    factual_hints: Optional[str] = None,
) -> Optional[str]:
    """Chat principal con OpenAI."""
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        return None

    user_content = build_conversational_user_prompt(question, dataset_context, factual_hints)
    messages: List[Dict[str, str]] = [{"role": "system", "content": SYSTEM_PROMPT}]
    for turn in _normalize_history(history):
        messages.append({"role": turn["role"], "content": turn["content"]})
    messages.append({"role": "user", "content": user_content})

    try:
        from openai import OpenAI

        client = OpenAI(api_key=api_key)
        response = client.chat.completions.create(
            model=get_openai_model(),
            messages=messages,
            temperature=0.35,
            max_tokens=2000,
        )
        text = response.choices[0].message.content
        return text.strip() if text else None
    except Exception:
        return None


def enhance_agent_answer(
    question: str,
    factual_answer: str,
    dataset_context: str,
) -> Optional[str]:
    """Reformula la respuesta factual con ChatGPT."""
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        return None

    user_content = build_user_prompt(question, factual_answer, dataset_context)
    try:
        from openai import OpenAI

        client = OpenAI(api_key=api_key)
        response = client.chat.completions.create(
            model=get_openai_model(),
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ],
            temperature=0.3,
            max_tokens=1200,
        )
        text = response.choices[0].message.content
        return text.strip() if text else None
    except Exception:
        return None
