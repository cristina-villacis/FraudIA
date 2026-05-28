# Despliegue y variables de entorno

## Qué va a Git y qué no

| Archivo | ¿Sube a Git? | Contenido |
|---------|--------------|-----------|
| `.env.example` | Sí | Plantilla **sin** claves reales |
| `.env` | **No** (`.gitignore`) | Claves reales (OpenAI, BD, etc.) |

## Configuración local (tu PC)

1. Copiar plantilla si no existe `.env`:
   ```powershell
   copy .env.example .env
   ```
2. Editar `.env` y pegar `OPENAI_API_KEY`, `DATABASE_URL`, etc.
3. `pip install -r requirements.txt`
4. Iniciar Flask.

## Después de `git clone` (servidor / otro equipo)

```bash
git clone <repo>
cd "Reto Aseguradora Sur"
copy .env.example .env    # Windows
# cp .env.example .env      # Linux
```

Editar **solo** `.env` en esa máquina con las claves de producción.

## Hosting en la nube (recomendado)

No suba claves al repositorio. Configúrelas en el panel del proveedor:

| Variable | Descripción |
|----------|-------------|
| `DATABASE_URL` | Conexión MySQL/TiDB |
| `OPENAI_API_KEY` | Clave OpenAI (ChatGPT) |
| `OPENAI_MODEL` | Ej. `gpt-4o-mini` |
| `OPENAI_ENABLED` | `true` |
| `FLASK_PORT` | Puerto (ej. 5000) |

Plataformas: **Vercel** (recomendado para demo público), Railway, Render, Azure App Service, AWS, etc. → sección **Environment Variables**.

### Vercel (Git → web pública)

Ver guía completa: [despliegue-vercel.md](despliegue-vercel.md)

## GitHub Actions (opcional)

Usar **Repository secrets**: `OPENAI_API_KEY`, `DATABASE_URL`.

## Verificar ChatGPT

Con la app en marcha y pipeline ejecutado:

`GET http://localhost:5000/api/agent-status`

Debe responder `"openai_configured": true`.
