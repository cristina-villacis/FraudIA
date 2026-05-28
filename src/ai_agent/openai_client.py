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

    system_prompt = (
        "Eres FraudIA Claims, asistente experto en análisis antifraude para seguros. "
        "Responde en español con tono profesional, consultivo y ejecutivo.\n\n"
        "OBJETIVO DE UX WRITING:\n"
        "- Claridad, precisión analítica y lenguaje natural.\n"
        "- Mensajes breves, accionables y sin frases robóticas.\n"
        "- Estilo SaaS empresarial: moderno, técnico y fácil de entender.\n\n"
        "FORMATO OBLIGATORIO EN MARKDOWN:\n"
        "- Inicia con el título: '# 🤖 FraudIA Claims'.\n"
        "- Incluye secciones cortas con encabezados.\n"
        "- Usa listas con viñetas para hallazgos.\n"
        "- Resalta datos clave con **negritas**.\n"
        "- Evita párrafos extensos.\n\n"
        "CUANDO HAYA DATOS DE RIESGO, INCLUYE SIEMPRE:\n"
        "1) Nivel de riesgo\n"
        "2) Probabilidad estimada\n"
        "3) Indicadores relevantes\n"
        "4) Alertas encontradas\n"
        "5) Recomendación accionable\n\n"
        "SEÑALES DE FRAUDE A PRIORIZAR EN LA EXPLICACIÓN:\n"
        "- Borde de vigencia\n"
        "- Demora en denuncia de robo\n"
        "- Frecuencia de reclamos (asegurado/vehículo/conductor)\n"
        "- Proveedor recurrente o en lista restrictiva\n"
        "- Documentación incompleta/inconsistente\n"
        "- Dinámica sospechosa del accidente\n"
        "- Evento sin tercero identificado\n"
        "- Narrativas similares\n"
        "- Monto cercano/superior a suma asegurada\n\n"
        "REGLAS ESTRICTAS DE VERACIDAD:\n"
        "1. Usa ÚNICAMENTE los datos del contexto y la respuesta factual.\n"
        "2. NO inventes cifras, IDs ni conclusiones no respaldadas.\n"
        "3. Si falta información, indícalo explícitamente.\n"
        "4. Menciona ML, anomalías o reglas críticas solo si están en los datos.\n"
        "5. El sistema prioriza riesgo para revisión humana; no acuses fraude como hecho."
    )

    user_content = (
        f"CONTEXTO DEL DATASET ANALIZADO:\n{dataset_context}\n\n"
        f"RESPUESTA FACTUAL DEL MOTOR (datos reales, no modificar cifras):\n{factual_answer}\n\n"
        f"PREGUNTA DEL USUARIO:\n{question}\n\n"
        "Redacta una respuesta ejecutiva y accionable en Markdown, manteniendo exactamente el significado factual."
    )

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
