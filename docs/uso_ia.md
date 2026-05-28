# Uso esperado de Inteligencia Artificial (Sección 9)

FraudIA Claims implementa el enfoque híbrido del reto: **reglas de negocio + ML supervisado + anomalías + NLP + dashboard + agente explicativo**.

## Arquitectura del pipeline de IA

```
Datos → Features → NLP (similitud) → Reglas (RF-01…RF-07)
                              ↓
                    Random Forest (etiqueta simulada)
                              ↓
                    Isolation Forest (anomalías)
                              ↓
                    Score híbrido + semáforo
                              ↓
              Dashboard / Casos / Agente IA / Export
```

## 1. Machine Learning supervisado

| Aspecto | Implementación |
|---------|----------------|
| **Objetivo** | Predicción de probabilidad de posible fraude por siniestro |
| **Modelo** | `RandomForestClassifier` (200 árboles, `class_weight=balanced`) |
| **Etiqueta** | `etiqueta_fraude_simulada` (generada en datos sintéticos o provista) |
| **Salida** | Columna `ml_fraud_probability` (0–1) |
| **Métricas** | AUC-ROC, validación cruzada 5-fold, precisión/recall/F1 |
| **Código** | `src/models/fraud_model.py` → `train_supervised_model`, `predict_fraud_probability` |

### Etiqueta simulada y self-training

En el prototipo, la **Fase 1 (entrenamiento base)** usa `etiqueta_fraude_simulada`: etiquetas artificiales coherentes con patrones de fraude (≈15 % casos sospechosos en datos sintéticos). Esto corresponde al escenario del reto cuando no hay etiquetas humanas reales.

Un ciclo **self-training** completo (Fases 2–4) sería:

1. Entrenar modelo base con etiquetas iniciales.
2. Predecir sobre datos sin etiquetar.
3. Aceptar solo predicciones de alta confianza (p. ej. probabilidad > 0,85 o < 0,15).
4. Reentrenar con etiquetas originales + pseudo-etiquetas.

**Estado actual:** Fase 1 implementada. Self-training iterativo queda como extensión (evita profecía autocumplida si no se filtra por confianza).

**Riesgo documentado:** aceptar pseudo-etiquetas erróneas refuerza errores del modelo; en producción se requiere validación humana o umbral alto de confianza.

## 2. Detección de anomalías

| Aspecto | Implementación |
|---------|----------------|
| **Objetivo** | Casos fuera del comportamiento esperado (sin etiqueta) |
| **Modelo** | `IsolationForest` (contaminación ~10 %) |
| **Salida** | `anomaly_score` normalizado 0–1 |
| **Uso** | 25 % del score híbrido; patrones en agente y dashboard |

## 3. Procesamiento de lenguaje natural (NLP)

| Capacidad | Implementación |
|-----------|----------------|
| Similitud textual | TF-IDF + similitud coseno entre `descripcion` |
| Narrativas clonadas | Umbral ≥ 70 % (puntos); RF-07 si ≥ 90 % |
| Extracción de entidades | Montos, fechas, ubicaciones, vehículos (`extract_entities`) |
| Resúmenes | Palabras frecuentes, longitud media (`generate_text_summary`) |
| **Código** | `src/nlp/text_analysis.py` |
| **API** | `GET /api/nlp-summary` |

## 4. Agente de IA explicativo

| Aspecto | Implementación |
|---------|----------------|
| **Tipo** | Motor de reglas sobre `df_scored` + **ChatGPT opcional** (OpenAI API) |
| **Entrada** | DataFrame post-pipeline con scores, ML, anomalías, alertas |
| **API** | `POST /api/agent-query`, `GET /api/agent-status` |
| **Código** | `src/ai_agent/claims_agent.py`, `src/ai_agent/openai_client.py` |

### Configurar ChatGPT (OpenAI)

1. Copie `.env.example` a `.env` (el archivo `.env` no se sube a git).
2. Defina `OPENAI_API_KEY=sk-...` (clave nueva; revoque cualquier clave expuesta).
3. Opcional: `OPENAI_MODEL=gpt-4o-mini` (o `gpt-4o`, etc.).
4. `pip install openai` y reinicie Flask.

Flujo: el motor calcula la respuesta factual desde los datos → ChatGPT la redacta sin inventar cifras.

### Datos que usa el agente

- `score_hibrido`, `semaforo_final`, `alertas_reglas`, `reglas_criticas`
- **`ml_fraud_probability`** — probabilidad del Random Forest
- **`anomaly_score`** — score de Isolation Forest
- Agregaciones por proveedor, ramo, asegurado, etc.

### Consultas de ejemplo

- *"Detalle del siniestro SIN-000042"* → incluye bloque **Señales de IA** (ML + anomalía + reglas críticas)
- *"¿Cuáles son los 10 casos de mayor riesgo?"* → muestra score híbrido y % ML
- *"¿Cuál es la probabilidad de fraude del modelo?"* → resumen ML y anomalías
- *"¿Qué patrones se detectaron?"* → frecuencias, lista restrictiva, anomalías, ML alto

## 5. Enfoque híbrido

```
Score_híbrido = 40% × score_reglas + 35% × ml_fraud_probability + 25% × anomaly_score
```

Además:

- Reglas críticas **RF-01…RF-07** pueden forzar semáforo Rojo/Amarillo.
- El score híbrido no baja del `score_reglas` cuando hay reglas críticas activas.
- `semaforo_final` = máximo entre semáforo por score y `semaforo_reglas`.

| Componente | Peso | Rol |
|------------|------|-----|
| Reglas de negocio | 40 % | Experiencia codificada, RF críticas |
| ML supervisado | 35 % | Patrones aprendidos con etiqueta simulada |
| Anomalías | 25 % | Comportamiento atípico no visto en entrenamiento |
| NLP | — | Refuerza reglas (similitud, RF-07) |
| Dashboard | — | Visualización y filtros |
| Agente | — | Explicación en lenguaje natural |

## 6. Explicabilidad

- **Por caso:** `GET /api/case/<id>` → alertas, factores, resumen (`explain_single_case`)
- **Modelo:** importancia de variables (Random Forest)
- **Agente:** respuestas citando scores y probabilidades reales del dataset

## Consideraciones éticas

- El sistema **no determina fraude**; prioriza casos para revisión humana.
- La etiqueta simulada es para **prototipo/demostración**, no sustituye investigación real.
- Reentrenamiento periódico y auditoría de falsos positivos son recomendables en producción.

## Archivos clave

| Módulo | Ruta |
|--------|------|
| ML + anomalías + híbrido | `src/models/fraud_model.py` |
| Reglas + RF críticas | `src/rules/fraud_rules.py` |
| NLP | `src/nlp/text_analysis.py` |
| Agente | `src/ai_agent/claims_agent.py` |
| Pipeline | `src/app/main.py` → `/api/run-pipeline` |
| Explicación | `src/explainability/explain_score.py` |
