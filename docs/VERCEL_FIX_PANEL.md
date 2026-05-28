# Si sigue el error `functions api/index.py`

El código en GitHub **ya no tiene** ese bloque. Si el error continúa, la causa casi seguro es la **configuración guardada en el panel de Vercel**, no el repo.

## Paso 1 — Comprobar el commit del deploy

En **Deployments**, el commit debe ser reciente (ej. `fix: remove vercel.json` o posterior a `eb33d90`).

Si ves `f712e39` o más antiguo, ese deploy usa `vercel.json` viejo con `functions`.

## Paso 2 — Limpiar overrides en Vercel (importante)

1. Proyecto **fraud-ia** → **Settings** → **Build and Deployment**
2. En cada campo, **desactiva "Override"** (toggle gris):
   - Framework Preset → **Flask** o **Other**
   - Build Command → vacío (usa `pyproject.toml`)
   - Output Directory → vacío
   - Install Command → vacío (usa `requirements.txt`)
   - Root Directory → vacío (`.`)
3. Guarda cambios.

## Paso 3 — Borrar configuración antigua en el proyecto

Si en Settings aparece un editor de **vercel.json** pegado manualmente, **bórralo** y guarda.

## Paso 4 — Nuevo deploy

- Haz un commit nuevo en `main` (ya se hace desde el repo), o
- **Deployments** → los tres puntos del último commit en Git → **Redeploy** (solo si ese commit es el nuevo).

No uses Redeploy en deployments fallidos viejos.

## Paso 5 — Si nada funciona: reimportar

1. Desconecta el repo o elimina el proyecto en Vercel.
2. **Add New Project** → importa `cristina-villacis/FraudIA` de nuevo.
3. Framework: **Other** o **Flask**.
4. Añade variables: `OPENAI_API_KEY`, `SECRET_KEY`, `OPENAI_MODEL`.

## Estructura correcta en Git (sin vercel.json)

```
FraudIA/
  app.py              ← entrada Flask (app)
  pyproject.toml      ← entrypoint + build
  requirements.txt    ← dependencias ligeras
  src/app/main.py     ← aplicación
  data/processed/     ← CSV + vercel_bundle/
```

No debe existir `vercel.json` con `functions` ni carpeta `api/index.py`.
