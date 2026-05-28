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
3. `app.py` configura la API Python (FastAPI/ASGI) para Vercel.
4. **Importante:** `requirements.txt` en la raíz es la versión **ligera** para Vercel.

## 2. Variables de entorno (chatbot IA)

| Variable | Valor |
|----------|--------|
| `OPENAI_API_KEY` | Tu clave `sk-...` |
| `OPENAI_MODEL` | `gpt-4o-mini` |
| `OPENAI_ENABLED` | `true` |
| `SECRET_KEY` | Cadena aleatoria |
| `VERCEL_API_KEY` | Clave opcional para proteger `/api/*` por header `X-Vercel-API-Key` |
| `DATABASE_URL` | **Obligatoria** si quiere BD real en Vercel (MySQL/TiDB/Postgres) |

Sin `OPENAI_API_KEY` el dashboard funciona; el chat no generará respuestas enriquecidas.
Sin `DATABASE_URL` en Vercel, el sistema opera en modo bundle/in-memory (demo).

## 3. Probar localmente el mismo flujo que Vercel

```powershell
cd FraudIA
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
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
4. Opcional: ejecute el bundle localmente antes del push:
   `python scripts/prepare_vercel_bundle.py --from-dir data/synthetic`

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

## Solución de problemas

### Error `functions api/index.py doesn't match any Serverless Functions`
Ese error corresponde a una configuración antigua. El proyecto actual usa `app.py` (FastAPI) sin `functions` legacy.

### "This deployment can not be redeployed"
Vercel **no permite** volver a desplegar un build fallido. Solución:
1. Haga `git push` con un **commit nuevo** (aunque sea un cambio mínimo).
2. Espere el deployment automático desde GitHub.
3. No use **Redeploy** en el deployment viejo; abra el **nuevo** que aparece arriba en la lista.

### Pantalla "No Production Deployment"
Significa que **ningún build terminó bien**. En Vercel → **Deployments** → abra el último → **Building** / **Logs**.

Causas frecuentes y corrección:

| Error en logs | Causa | Solución |
|---------------|--------|----------|
| `exceeded maximum size` / timeout install | `torch` en requirements | Ya corregido: `requirements.txt` ligero en repo |
| `python: command not found` | Runtime incorrecto | Usar `runtime.txt` con `python-3.11` |
| `ModuleNotFoundError` | Falta paquete | Revisar `requirements.txt` |
| Build OK pero 500 al abrir | Falta CSV/bundle | `includeFiles` en `vercel.json` incluye `data/processed/**` |

### Tras un deploy correcto
- `https://su-dominio.vercel.app/api/health` → `{"status":"ok",...}`
- Si `pipeline_ready: false` en el primer hit, espere 2–3 s y recargue (carga del CSV).

### Variables obligatorias en Vercel
Sin `OPENAI_API_KEY` el dashboard funciona; el chat no usará ChatGPT.
