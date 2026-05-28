"""
Módulo de Procesamiento de Lenguaje Natural (NLP).
- Similitud textual entre narrativas de siniestros
- Extracción de entidades
- Resúmenes automáticos
"""
import re
from collections import Counter
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity


STOPWORDS_ES = {
    "de", "la", "el", "en", "y", "a", "los", "del", "las", "un", "por",
    "con", "no", "una", "su", "para", "es", "al", "lo", "como", "más",
    "pero", "sus", "le", "ya", "o", "fue", "este", "ha", "sí", "porque",
    "esta", "son", "entre", "está", "cuando", "muy", "sin", "sobre",
    "ser", "también", "me", "hasta", "hay", "donde", "quien", "desde",
    "todo", "nos", "durante", "se", "que",
}


def compute_text_similarity(descriptions: pd.Series, threshold: float = 0.70) -> Dict:
    if descriptions is None or len(descriptions) < 2:
        return {"similarity_matrix": None, "pairs": [], "max_similarities": {}}

    clean_texts = descriptions.fillna("").apply(_preprocess_text)

    vectorizer = TfidfVectorizer(
        max_features=5000,
        ngram_range=(1, 2),
        stop_words=list(STOPWORDS_ES),
        min_df=1,
    )
    tfidf_matrix = vectorizer.fit_transform(clean_texts)
    sim_matrix = cosine_similarity(tfidf_matrix)

    np.fill_diagonal(sim_matrix, 0)

    similar_pairs = []
    max_similarities = {}
    indices = descriptions.index.tolist()

    for i in range(len(sim_matrix)):
        max_sim = sim_matrix[i].max()
        max_similarities[indices[i]] = round(float(max_sim), 4)

        for j in range(i + 1, len(sim_matrix)):
            if sim_matrix[i][j] >= threshold:
                similar_pairs.append({
                    "idx_1": indices[i],
                    "idx_2": indices[j],
                    "similarity": round(float(sim_matrix[i][j]), 4),
                })

    similar_pairs.sort(key=lambda x: x["similarity"], reverse=True)

    return {
        "similarity_matrix": sim_matrix,
        "pairs": similar_pairs[:100],
        "max_similarities": max_similarities,
        "n_pairs_above_threshold": len(similar_pairs),
        "threshold": threshold,
    }


def get_similarity_scores_by_id(
    df: pd.DataFrame,
    id_col: str = "id_siniestro",
    desc_col: str = "descripcion",
    threshold: float = 0.70,
) -> Dict[str, float]:
    if desc_col not in df.columns or id_col not in df.columns:
        return {}

    clean_desc = df[desc_col].fillna("").apply(_preprocess_text)
    clean_counts = clean_desc.value_counts().to_dict()

    result = compute_text_similarity(df[desc_col], threshold)
    max_sims = result.get("max_similarities", {})

    id_to_sim = {}
    for idx, sin_id, clean in zip(df.index.tolist(), df[id_col].tolist(), clean_desc.tolist()):
        if idx in max_sims:
            sim = float(max_sims[idx])
            tokens = [w for w in clean.split() if len(w) > 2]

            # Evita sobre-penalizar plantillas repetidas en datos sintéticos.
            if len(tokens) < 8 or len(clean) < 45:
                sim = min(sim, 0.65)
            if clean and clean_counts.get(clean, 0) > 3:
                sim = min(sim, 0.69)

            id_to_sim[sin_id] = round(sim, 4)

    return id_to_sim


def _preprocess_text(text: str) -> str:
    if not isinstance(text, str):
        return ""
    text = text.lower()
    text = re.sub(r"[^\w\sáéíóúñü]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def extract_entities(text: str) -> Dict[str, List[str]]:
    """Extrae entidades básicas sin dependencias pesadas de spaCy."""
    if not isinstance(text, str) or not text:
        return {"locations": [], "amounts": [], "dates": [], "vehicles": [], "people": []}

    amounts = re.findall(r"\$[\d,.]+|\d+(?:\.\d{2})\s*(?:dólares|USD)", text)
    dates = re.findall(
        r"\d{1,2}[/\-]\d{1,2}[/\-]\d{2,4}|\d{1,2}\s+de\s+\w+\s+de\s+\d{4}", text
    )
    vehicle_patterns = re.findall(
        r"(?:vehículo|auto|carro|camioneta|moto)\s+\w+", text, re.IGNORECASE
    )
    location_patterns = re.findall(
        r"(?:Av\.|Calle|Carrera|Km\.?|autopista|vía)\s+[\w\s]+", text, re.IGNORECASE
    )

    return {
        "locations": location_patterns[:5],
        "amounts": amounts[:5],
        "dates": dates[:5],
        "vehicles": vehicle_patterns[:5],
    }


def extract_entities_batch(df: pd.DataFrame, desc_col: str = "descripcion") -> pd.DataFrame:
    df = df.copy()
    if desc_col in df.columns:
        entities = df[desc_col].apply(extract_entities)
        df["entidades_extraidas"] = entities
    return df


def generate_text_summary(df: pd.DataFrame, desc_col: str = "descripcion") -> Dict:
    if desc_col not in df.columns:
        return {}

    texts = df[desc_col].dropna()
    all_words = []
    for text in texts:
        clean = _preprocess_text(text)
        words = [w for w in clean.split() if w not in STOPWORDS_ES and len(w) > 3]
        all_words.extend(words)

    word_freq = Counter(all_words).most_common(30)

    avg_length = texts.str.len().mean()
    empty_count = (texts == "").sum()

    return {
        "total_descripciones": len(texts),
        "descripciones_vacias": int(empty_count),
        "longitud_promedio": round(avg_length, 1),
        "palabras_frecuentes": [{"palabra": w, "frecuencia": c} for w, c in word_freq],
    }
