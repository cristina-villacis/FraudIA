# Arquitectura del Sistema FraudIA Claims

## Diagrama de Arquitectura

```
┌─────────────────────────────────────────────────────────────┐
│                    CAPA DE PRESENTACIÓN                      │
│                                                              │
│  ┌──────────────┐  ┌──────────────┐  ┌───────────────────┐  │
│  │  Dashboard    │  │  Agente IA   │  │  Power BI Export  │  │
│  │  Web (Flask)  │  │  (Chat NL)   │  │  (Excel/CSV)     │  │
│  └──────┬───────┘  └──────┬───────┘  └───────┬───────────┘  │
└─────────┼──────────────────┼──────────────────┼──────────────┘
          │                  │                  │
┌─────────┼──────────────────┼──────────────────┼──────────────┐
│         ▼                  ▼                  ▼              │
│                    CAPA DE API (Flask REST)                   │
│    /api/upload  /api/run-pipeline  /api/agent-query          │
│    /api/export-powerbi  /api/dashboard-data  /api/case/:id   │
└─────────┬────────────────────────────────────────────────────┘
          │
┌─────────▼────────────────────────────────────────────────────┐
│                    CAPA DE PROCESAMIENTO                      │
│                                                              │
│  ┌────────────┐  ┌───────────────┐  ┌────────────────────┐  │
│  │  Ingesta   │  │   Feature     │  │  Reglas de         │  │
│  │  de Datos  │→ │  Engineering  │→ │  Negocio (Score)   │  │
│  └────────────┘  └───────────────┘  └─────────┬──────────┘  │
│                                               │              │
│  ┌────────────┐  ┌───────────────┐  ┌─────────▼──────────┐  │
│  │  NLP       │  │  ML           │  │  Score Híbrido     │  │
│  │  Similitud │→ │  Supervisado  │→ │  (Reglas+ML+       │  │
│  │  Textual   │  │  + Anomalías  │  │   Anomalías)       │  │
│  └────────────┘  └───────────────┘  └─────────┬──────────┘  │
│                                               │              │
│  ┌────────────────────────────────────────────▼──────────┐   │
│  │              Explicabilidad (SHAP + Narrativas)        │   │
│  └────────────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────────┘
          │
┌─────────▼────────────────────────────────────────────────────┐
│                    CAPA DE DATOS                             │
│                                                              │
│  ┌────────────┐  ┌───────────────┐  ┌────────────────────┐  │
│  │  CSV/Excel  │  │  Datos        │  │  Modelos           │  │
│  │  (Upload)   │  │  Sintéticos   │  │  Entrenados        │  │
│  └────────────┘  └───────────────┘  └────────────────────┘  │
└──────────────────────────────────────────────────────────────┘
```

## Componentes Principales

### 1. Ingesta de Datos (`src/ingestion/`)
- Carga desde CSV, Excel o upload web
- Validación de esquemas
- Limpieza automática (fechas, numéricos, strings)
- Generador de datos sintéticos

### 2. Feature Engineering (`src/features/`)
- Merge de tablas (pólizas, asegurados, vehículos, proveedores, documentos)
- Variables temporales (borde de vigencia, reporte tardío)
- Variables de frecuencia (asegurado, vehículo, conductor, proveedor)
- Variables de montos (z-score por ramo, ratio vs suma asegurada)

### 3. Motor de Reglas (`src/rules/`)
- 12 señales de fraude con puntuación configurable
- 7 reglas críticas (RF-01 a RF-07)
- Score normalizado 0-100
- Semáforo: Verde (0-40), Amarillo (41-75), Rojo (76-100)

### 4. Modelos ML (`src/models/`)
- **Supervisado**: Random Forest con balanceo de clases
- **Anomalías**: Isolation Forest
- **Híbrido**: Ponderación reglas (40%) + ML (35%) + anomalías (25%)

### 5. NLP (`src/nlp/`)
- TF-IDF + Cosine Similarity para narrativas
- Extracción de entidades básica
- Análisis de frecuencia de palabras

### 6. Explicabilidad (`src/explainability/`)
- Explicaciones en lenguaje natural por caso
- Resumen ejecutivo agregado
- Recomendaciones por nivel de riesgo

### 7. Agente IA (`src/ai_agent/`)
- Procesamiento de consultas en lenguaje natural
- 12 tipos de consulta soportados
- Respuestas contextualizadas con datos

### 8. Aplicación Web (`src/app/`)
- Dashboard interactivo con Plotly
- Upload de archivos
- Chat con agente IA
- Exportación Power BI

## Tecnologías

| Componente | Tecnología |
|-----------|-----------|
| Backend | Python 3.11+, Flask |
| ML | scikit-learn, Isolation Forest, Random Forest |
| NLP | TF-IDF, Cosine Similarity |
| Frontend | HTML5, CSS3, JavaScript, Plotly.js |
| Datos | pandas, numpy |
| Exportación | openpyxl, xlsxwriter |
| Visualización | Power BI (via Excel/CSV) |

## Flujo de Datos

1. **Entrada**: Dataset vía upload web o datos sintéticos
2. **Limpieza**: Validación, tipos, nulos
3. **Features**: 40+ variables derivadas
4. **Reglas**: Score basado en 12 señales
5. **ML**: Probabilidad de fraude + detección anomalías
6. **Score Final**: Híbrido ponderado → Semáforo
7. **Salida**: Dashboard, Agente IA, Power BI
