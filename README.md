# 🛡️ FXecure

**Sistema inteligente de detección de fraude en seguros impulsado por Inteligencia Artificial.**

---

# 🌐 Demo en línea

### Acceder al sistema
🚀 [FXecure - IA de fraudes de siniestros](https://fxecure-ia.vercel.app/)

## 📝 Descripción general

**FXecure** es una plataforma avanzada diseñada para detectar, analizar y prevenir posibles fraudes en reclamaciones de seguros mediante técnicas modernas de Machine Learning, análisis estadístico, procesamiento de lenguaje natural y sistemas de explicabilidad de IA.

El sistema permite automatizar procesos de auditoría, optimizar tiempos de revisión y reducir pérdidas económicas causadas por reclamaciones fraudulentas.

FXecure combina:

* 🤖 Inteligencia Artificial.
* 🔍 Detección de anomalías.
* 🗣️ NLP (Natural Language Processing).
* 💡 Explainable AI.
* 📊 Dashboards interactivos.
* 🔌 APIs REST.
* 💬 Agentes IA conversacionales.

---

# 🚀 Características principales

## 🧠 Detección inteligente de fraude
FXecure utiliza múltiples modelos y estrategias para evaluar reclamaciones:

* 🌲 Random Forest.
* 🥷 Isolation Forest.
* 📏 Reglas heurísticas.
* 🎯 Scoring de riesgo.
* ⚙️ Detección híbrida basada en IA + reglas.

---

## 🗣️ Procesamiento de lenguaje natural (NLP)
El sistema analiza descripciones textuales de siniestros para detectar:

* 🔍 Patrones sospechosos.
* ⚠️ Inconsistencias semánticas.
* 🗣️ Lenguaje manipulativo.
* 📑 Descripciones duplicadas.
* 🚨 Indicadores de fraude.

---

## 💡 Explainable AI (XAI)
Implementación de SHAP para explicar predicciones del modelo:

* 📊 Variables más influyentes.
* 🔍 Interpretabilidad del modelo.
* 🌐 Transparencia algorítmica.
* 📋 Soporte para auditorías.

---

## 📊 Dashboard analítico
Visualización en tiempo real de:

* 🚨 Casos sospechosos.
* 📈 KPIs de fraude.
* ⚙️ Métricas operativas.
* 📉 Tendencias de riesgo.
* 🕒 Estadísticas históricas.

---

## 💬 Agente IA conversacional
Consultas en lenguaje natural como:

* 🗣️ *“¿Qué reclamaciones tienen mayor riesgo?”*
* 🗣️ *“Muéstrame los fraudes detectados esta semana.”*
* 🗣️ *“¿Qué variables afectaron esta predicción?”*

---

# 🏗️ Arquitectura del proyecto

```bash
FXecure/
│
├── Ingestion/           # Ingesta y carga de datos
├── features/            # Ingeniería de características
├── rules/               # Motor de reglas
├── models/              # Modelos ML
├── explainability/      # SHAP y explicabilidad
├── nlp/                 # NLP y análisis textual
├── ai_agent/            # Agente IA
├── app/                 # Frontend / Dashboard
├── data/                # Datasets
├── notebooks/           # Experimentación
├── tests/               # Testing
├── requirements.txt
└── README.md
```

# 🛠️ Stack tecnológico

## 💻 Backend

* 🐍 Python
* ⚡ FastAPI
* 🧪 Flask

## 🤖 Inteligencia Artificial y Data Science

* 📦 Scikit-learn
* 🐼 Pandas
* 🔢 NumPy
* 📊 SHAP
* 🚀 XGBoost

## 🗣️ NLP

* 🦅 spaCy
* 🔤 NLTK
* 🤗 Transformers

## 📊 Visualización

* 🎈 Streamlit
* 📈 Plotly
* 📊 Power BI

## 🗄️ Base de datos

* 🐘 PostgreSQL
* 🗃️ SQLite

## 🚀 DevOps

* 🐋 Docker
* 🐙 GitHub Actions
* ☁️ Vercel
* 🚀 Render

---

# 🔄 Flujo del sistema

```text
1. Ingesta de reclamaciones
          ↓
2. Limpieza y transformación
          ↓
3. Feature Engineering
          ↓
4. Evaluación mediante reglas
          ↓
5. Predicción ML
          ↓
6. Detección de anomalías
          ↓
7. Explicabilidad SHAP
          ↓
8. Dashboard y reportes
```

---

# 📥 Instalación

## 1. Clonar el repositorio
```bash
git clone [https://github.com/tuusuario/fxecure.git](https://github.com/tuusuario/fxecure.git)

cd fxecure
```

---

## 2. Crear entorno virtual

### 🪟 Windows
```bash
python -m venv venv

venv\Scripts\activate
```

### 🐧 Linux / 🍏 macOS
```bash
python3 -m venv venv

source venv/bin/activate
```

---

## 3. Instalar dependencias
```bash
pip install -r requirements.txt
```

---

# ⚙️ Configuración

Crear archivo `.env`
```env
DATABASE_URL=postgresql://user:password@localhost/fxecure

API_KEY=your_api_key

MODEL_PATH=models/
```

---

# 🚀 Ejecución

## ⚡ Ejecutar FastAPI
```bash
uvicorn main:app --reload
```

## 🧪 Ejecutar Flask
```bash
python app.py
```

## 🎈 Ejecutar dashboard
```bash
streamlit run dashboard.py
```

---

# 🤖 Machine Learning

## 📊 Modelos implementados

| Modelo | Tipo | Objetivo |
| :--- | :--- | :--- |
| **Random forest** | Supervisado | Clasificación de fraude |
| **Isolation forest** | No Supervisado | Detección de anomalías |
| **XGBoost** | Supervisado | Optimización de precisión |
| **Reglas heurísticas** | Basado en reglas | Validaciones críticas |

---

## 📋 Variables analizadas

* 💰 Monto reclamado.
* ⏳ Historial del cliente.
* 🔄 Frecuencia de reclamaciones.
* ⏱️ Tiempo entre incidentes.
* 📝 Descripciones textuales.
* 📍 Ubicación geográfica.
* 👥 Patrones de comportamiento.

---

# 💡 Explainable AI

FXecure utiliza **SHAP** para interpretar predicciones del modelo.

Ejemplo:
```python
explainer = shap.TreeExplainer(model)

shap_values = explainer.shap_values(X_test)
```

### ✨ Beneficios:

* 🌐 Transparencia.
* 🤝 Confianza operativa.
* 🔍 Interpretabilidad.
* 📜 Cumplimiento regulatorio.

---

# 🗣️ NLP y Análisis textual

El módulo NLP permite:

* 🔍 Analizar siniestros.
* 🚨 Detectar lenguaje sospechoso.
* 🏷️ Extraer entidades relevantes.
* 📈 Clasificar riesgo textual.

Ejemplo:
```python
import spacy

nlp = spacy.load("es_core_news_sm")

doc = nlp(texto)
```

---

# 🔌 API REST

## 📍 Endpoints

| Método | Endpoint | Descripción |
| :--- | :--- | :--- |
| `POST` | `/predict` | Predicción de fraude |
| `GET` | `/claims` | Obtener reclamaciones |
| `GET` | `/metrics` | Métricas del sistema |
| `POST` | `/chat` | Consultas IA |
| `GET` | `/explain/{id}` | Explicación SHAP |

---

## 📥 Ejemplo request
```json
{
  "claim_amount": 15000,
  "claim_history": 5,
  "incident_description": "El vehículo fue robado durante la madrugada"
}
```

---

## 📤 Ejemplo response
```json
{
  "fraud_probability": 0.92,
  "risk_level": "HIGH",
  "explanation": "Patrón inconsistente detectado"
}
```

---

# 📊 Dashboard

El dashboard permite:
* 📈 Visualización en tiempo real.
* ⚙️ Métricas operativas.
* 🔍 Seguimiento de reclamaciones.
* 🚨 Análisis de fraude.
* 💡 Explicaciones SHAP.

---

# 🔒 Seguridad

FXecure implementa:
* 🌐 Variables de entorno.
* 🛡️ Validación de datos.
* 🧼 Sanitización de inputs.
* 🔑 Protección de endpoints.
* 🔐 Manejo seguro de credenciales.

---

# 🧪 Testing

## 🏃‍♂️ Ejecutar pruebas
```bash
pytest tests/
```

## 📊 Cobertura
```bash
pytest --cov=.
```

---

# 🐋 Docker

## 🏗️ Construir imagen
```bash
docker build -t fxecure .
```

## 🏃‍♂️ Ejecutar contenedor
```bash
docker run -p 8000:8000 fxecure
```

---

# 🔄 CI/CD

Integración compatible con:
* 🐙 GitHub Actions
* 🐋 Docker Hub
* 🚀 Render
* 🚊 Railway
* ☁️ Vercel

Ejemplo básico:
```yaml
name: FXecure CI

on:
  push:
    branches:
      - main

jobs:
  build:
    runs-on: ubuntu-latest

    steps:
      - uses: actions/checkout@v4

      - name: Setup Python
        uses: actions/setup-python@v5

      - name: Install dependencies
        run: pip install -r requirements.txt

      - name: Run tests
        run: pytest
```

---

# 💼 Casos de uso

* 🏢 Aseguradoras.
* 📋 Auditorías internas.
* 🛡️ Prevención de fraude.
* 🤖 Automatización de análisis.
* 📈 Evaluación de riesgo.

---

# 🗺️ Roadmap

* 🤖 Integración con LLMs.
* 🖼️ Detección multimodal.
* 📸 Análisis de imágenes de siniestros.
* ⏱️ Predicción en tiempo real.
* ⚙️ Motor avanzado de reglas dinámicas.

---

# 🤝 Contribución

1. 🍴 Fork del proyecto.
2. 🌿 Crear nueva rama.
3. 💾 Realizar cambios.
4. 🚀 Enviar Pull Request.

---

# 📄 Licencia
Este proyecto se encuentra bajo la licencia **MIT**.

---

# 👥 Autores

| Nombre | Descripción |
| :--- | :--- |
| **Cristina Villacís** | ` Futura Ingeniera en Ciencias de la Computación ` |
| **Jareth Rojas** | `Futuro Ingeniero en Ciencia de Datos e IA ` |
| **Liskeyla Macías** | `Analista de Datos y Procesos `|

---

# 🏢 Equipo FXecure
Proyecto desarrollado por un equipo multidisciplinario enfocado en Inteligencia Artificial, análisis de datos y desarrollo de soluciones innovadoras para la detección de fraude en seguros.