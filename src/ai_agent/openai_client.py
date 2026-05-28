"""
Cliente opcional OpenAI (ChatGPT) para el agente de siniestros.
La API key debe estar en OPENAI_API_KEY (.env), nunca en el código.
"""
from __future__ import annotations

import os
from typing import Optional


def is_openai_configured() -> bool:
    return bool(os.getenv("OPENAI_API_KEY", "").strip())


def get_openai_model() -> str:
    return os.getenv("OPENAI_MODEL", "gpt-4o-mini").strip() or "gpt-4o-mini"


def enhance_agent_answer(
    question: str,
    factual_answer: str,
    dataset_context: str,
) -> Optional[str]:
    """
    Reformula la respuesta factual con ChatGPT, sin inventar datos.
    Retorna None si no hay API key o falla la llamada.
    """
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        return None

    from src.ai_agent.llm_prompts import SYSTEM_PROMPT, build_user_prompt

    system_prompt = SYSTEM_PROMPT
    user_content = build_user_prompt(question, factual_answer, dataset_context)

    try:
        from openai import OpenAI

        client = OpenAI(api_key=api_key)
        response = client.chat.completions.create(
            model=get_openai_model(),
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
            temperature=0.3,
            max_tokens=1200,
        )
        text = response.choices[0].message.content
        return text.strip() if text else None
    except Exception:
        return None
