# Despliegue en Vercel (público + ChatGPT)

Repositorio: [github.com/cristina-villacis/FraudIA](https://github.com/cristina-villacis/FraudIA)

## Qué hace el despliegue en Vercel

- Sirve la **web Flask** completa (dashboard, bandeja, modelo ML).
- Carga automáticamente `data/processed/siniestros_scored.csv` al iniciar (demo listo sin ejecutar pipeline).
- El **chatbot con IA** usa `OPENAI_API_KEY` configurada en Vercel.
- No usa SQLite en producción (solo datos en memoria desde el repo).

## 1. Conectar GitHub → Vercel

1. Entra en [vercel.com](https://vercel.com) e inicia sesión.
2. **Add New Project** → importa `cristina-villacis/FraudIA`.
3. Framework Preset: **Other**.
4. Root Directory: `.` (raíz del repo).
5. Build Command: dejar vacío o `echo Build OK` (ya está en `vercel.json`).
6. Install Command: `pip install -r requirements-vercel.txt` (ya en `vercel.json`).

## 2. Variables de entorno (obligatorias para el chatbot)

En Vercel → **Project → Settings → Environment Variables**:

| Variable | Valor | Entornos |
|----------|--------|----------|
| `OPENAI_API_KEY` | `sk-...` (tu clave) | Production, Preview |
| `OPENAI_MODEL` | `gpt-4o-mini` | Production, Preview |
| `OPENAI_ENABLED` | `true` | Production, Preview |
| `SECRET_KEY` | cadena aleatoria larga | Production, Preview |
| `VERCEL` | `1` | Production (opcional, ya en vercel.json) |

Opcional (si usa MySQL en la nube en lugar del demo embebido):

| Variable | Valor |
|----------|--------|
| `DATABASE_URL` | `mysql+pymysql://...` |

> **No** suba `.env` a Git. Solo configure claves en el panel de Vercel.

## 3. Desplegar

Tras guardar variables, pulse **Deploy**.  
Cada `git push` a `main` volverá a desplegar automáticamente.

URL pública: `https://fraudia-claims-xxx.vercel.app` (o el dominio que asigne Vercel).

## 4. Verificar ChatGPT

1. Abra la URL pública.
2. Vaya a **Modelo ML** → chat flotante.
3. O consulte: `GET https://su-dominio.vercel.app/api/agent-status`  
   Debe mostrar `"openai_configured": true` y `"pipeline_ready": true`.

## 5. Limitaciones en Vercel

| Función | Vercel | Local |
|---------|--------|-------|
| Dashboard + filtros | Sí | Sí |
| Chatbot OpenAI | Sí (con API key) | Sí |
| Pipeline completo (re-entrenar) | No recomendado (timeout ~60s) | Sí |
| Subir Excel grande | Limitado | Sí |
| SQLite persistente | No | Sí |
| NLP / modelos pesados (torch) | No incluidos | Sí |

Para re-entrenar el modelo o regenerar datos, use el entorno local y vuelva a hacer `git push` con el CSV actualizado en `data/processed/`.

## 6. Actualizar datos del demo

```powershell
# Local: ejecutar pipeline y exportar
python -m flask --app src.app.main run
# Ejecutar pipeline desde la UI o API, luego:
# Copiar data/processed/siniestros_scored.csv al repo

git add data/processed/siniestros_scored.csv
git commit -m "Actualizar dataset scored para Vercel"
git push
```

## 7. Dominio personalizado

Vercel → **Settings → Domains** → añada su dominio y siga las instrucciones DNS.
