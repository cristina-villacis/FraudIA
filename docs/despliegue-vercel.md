# Despliegue en Vercel — flujo completo

Repositorio: [github.com/cristina-villacis/FraudIA](https://github.com/cristina-villacis/FraudIA)

## Lógica del sistema (lo que pediste)

```
┌─────────────────────────────────────────────────────────────────┐
│  BUILD en Vercel (al hacer deploy desde Git)                    │
│  scripts/prepare_vercel_bundle.py --synthetic                   │
├─────────────────────────────────────────────────────────────────┤
│  1. Generar datos sintéticos  (o cargar data/synthetic)         │
│  2. Feature engineering + NLP + reglas de fraude                │
│  3. Entrenar ML (Random Forest) + anomalías + score híbrido     │
│  4. Calcular KPIs del dashboard                                 │
│  5. Guardar bundle:                                             │
│     • data/processed/siniestros_scored.csv                      │
│     • data/processed/vercel_bundle/*.json (contexto agente)     │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  RUNTIME en Vercel (web pública)                                │
├─────────────────────────────────────────────────────────────────┤
│  • Dashboard y Modelo ML leen el CSV + JSON del análisis        │
│  • Chatbot: OpenAI recibe contexto real (scores, reglas, ML)    │
│    y genera explicaciones / respuestas (OPENAI_API_KEY)           │
└─────────────────────────────────────────────────────────────────┘
```

**Vercel no vuelve a entrenar en cada visita** — el análisis pesado ocurre en el **build**.  
En runtime solo se sirven resultados + llamadas a OpenAI.

## 1. Conectar GitHub → Vercel

1. [vercel.com](https://vercel.com) → **Add New Project** → `cristina-villacis/FraudIA`
2. Framework: **Other**
3. `vercel.json` ya define:
   - `installCommand`: `pip install -r requirements-vercel.txt`
   - `buildCommand`: `python scripts/prepare_vercel_bundle.py --synthetic`

## 2. Variables de entorno (chatbot IA)

| Variable | Valor |
|----------|--------|
| `OPENAI_API_KEY` | Tu clave `sk-...` |
| `OPENAI_MODEL` | `gpt-4o-mini` |
| `OPENAI_ENABLED` | `true` |
| `SECRET_KEY` | Cadena aleatoria |

Sin `OPENAI_API_KEY` el dashboard funciona; el chat no generará respuestas enriquecidas.

## 3. Probar localmente el mismo flujo que Vercel

```powershell
cd FraudIA
.\venv\Scripts\Activate.ps1
pip install -r requirements-vercel.txt
python scripts/prepare_vercel_bundle.py --synthetic
# o con datos ya cargados:
python scripts/prepare_vercel_bundle.py --from-dir data/synthetic

git add data/processed/
git commit -m "Actualizar bundle de análisis"
git push
```

## 4. Usar tus propios datos (no sintéticos)

1. Coloque Excel/CSV en `data/synthetic/` o `data/raw/` (con `etiqueta_fraude_simulada`).
2. Local: `python scripts/prepare_vercel_bundle.py --from-dir data/raw`
3. Suba `data/processed/siniestros_scored.csv` y `data/processed/vercel_bundle/` a Git.
4. En Vercel, cambie `buildCommand` a:
   ```json
   "buildCommand": "python scripts/prepare_vercel_bundle.py --from-dir data/synthetic"
   ```

## 5. Verificación

- `GET /api/deployment-info` → `manifest` con pasos del pipeline y `total_records`
- `GET /api/agent-status` → `pipeline_ready: true`, `openai_configured: true`
- Dashboard y chat en **Modelo ML**

## 6. Limitaciones

| Acción | Vercel runtime | Local |
|--------|----------------|-------|
| Ver dashboard analizado | Sí | Sí |
| Chat OpenAI con contexto del análisis | Sí | Sí |
| Subir Excel y re-entrenar al vuelo | No recomendado | Sí |
| Pipeline completo en cada clic | No (solo en build) | Sí |

Para un nuevo análisis en producción: ejecute el script local o redeploy (build regenera sintéticos con nueva semilla si usa `--synthetic`).
