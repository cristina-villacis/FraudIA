# FraudIA Claims - Sistema de Detección de Fraude en Seguros

## Descripción
Prototipo funcional de Inteligencia Artificial que analiza siniestros de seguros, detecta patrones anómalos o señales de posible fraude, asigna un score de riesgo y genera explicaciones para apoyar la revisión del analista.

## Arquitectura
```
[Dataset Upload Web] → [Flask API] → [Data Pipeline Python]
     ↓                                      ↓
[Dashboard Web]  ←  [Análisis ML/NLP]  →  [Power BI Export]
     ↓
[Agente IA - Consultas Lenguaje Natural]
```

## Componentes
- **Ingesta de datos**: Carga y validación de datasets via web o archivo
- **Feature Engineering**: Construcción de variables derivadas
- **Reglas de Negocio**: Motor de reglas con puntuación configurable
- **ML Supervisado**: Random Forest para predicción de fraude
- **Detección de Anomalías**: Isolation Forest para casos atípicos
- **NLP**: Similitud textual de narrativas, extracción de entidades
- **Explainability**: SHAP values + explicaciones en lenguaje natural
- **Agente IA**: Consultas en lenguaje natural sobre casos
- **Dashboard**: Interfaz web con semáforo verde/amarillo/rojo
- **Power BI**: Exportación automatizada para visualización

## Variables de entorno (OpenAI + base de datos)

| Archivo | Git | Uso |
|---------|-----|-----|
| `.env.example` | Sí | Plantilla que viaja con el repo |
| `.env` | No | Claves reales en tu PC o en el servidor |

```powershell
copy .env.example .env
# Editar .env: OPENAI_API_KEY, DATABASE_URL, etc.
```

Tras `git clone` en otro equipo o servidor: repetir `copy .env.example .env` y completar claves ahí.  
Detalle: [docs/despliegue.md](docs/despliegue.md)

## Publicar en Vercel (web pública + chatbot IA)

Repositorio: [github.com/cristina-villacis/FraudIA](https://github.com/cristina-villacis/FraudIA)

1. Importe el repo en [vercel.com](https://vercel.com) → **Add New Project**.
2. Configure variables de entorno en Vercel: `OPENAI_API_KEY`, `OPENAI_MODEL`, `SECRET_KEY`.
3. Deploy automático en cada `git push` a `main`.

En cada deploy, Vercel **genera datos sintéticos, ejecuta el pipeline completo** (reglas + ML + dashboard) y publica el resultado. El chatbot OpenAI explica ese análisis en runtime.

Guía paso a paso: [docs/despliegue-vercel.md](docs/despliegue-vercel.md)

## Instalación

```bash
pip install -r requirements-local.txt
python -m spacy download es_core_news_sm
```

> En Vercel se usa `requirements.txt` (ligero, sin torch). Localmente use `requirements-local.txt`.

## Ejecución

```bash
# Generar datos sintéticos
python -m src.ingestion.generate_synthetic

# Ejecutar aplicación web
python -m src.app.main
```

Acceder a http://localhost:5000

## Estructura
```
fraudia-claims/
├── data/raw/processed/synthetic/
├── notebooks/ (exploración, modelo, evaluación)
├── src/
│   ├── ingestion/     (carga de datos)
│   ├── features/      (ingeniería de features)
│   ├── rules/         (reglas de negocio)
│   ├── models/        (ML supervisado + anomalías)
│   ├── explainability/(explicaciones SHAP)
│   ├── nlp/           (procesamiento lenguaje natural)
│   ├── ai_agent/      (agente consultas)
│   └── app/           (aplicación web Flask)
├── docs/
├── tests/
└── presentation/
```

## Niveles de Riesgo
| Nivel | Score | Acción |
|-------|-------|--------|
| 🟢 Verde | 0-40 | Bajo — Continuar flujo normal |
| 🟡 Amarillo | 41-75 | Medio — Escala a Unidad Antifraude para revisión documental |
| 🔴 Rojo | 76-100 | Alto — Escala Unidad Antifraude para revisión especializada de campo |
