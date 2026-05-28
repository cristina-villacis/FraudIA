# TiDB Cloud + Vercel (cluster Aseguradora)

Instancia **Aseguradora** en TiDB Cloud (Starter, AWS `us-east-1`, TiDB v8.5.3).

| Campo | Valor |
|-------|--------|
| Host | `gateway01.us-east-1.prod.aws.tidbcloud.com` |
| Puerto | `4000` |
| Usuario | `ezF1nSTkhwhsAAD.root` |
| Base de datos app | `fraudia_claims` (se crea con `/api/db-init`) |
| Connect en panel | muestra `sys` — es normal; FraudIA usa `fraudia_claims` |

Con `DATABASE_URL` configurada en Vercel, el flujo queda igual que en local:

1. Subir dataset o generar sintéticos  
2. Guardar tablas en TiDB  
3. Ejecutar análisis completo  
4. Dashboard y Modelo ML leen los resultados de **ese** dataset  

---

## 1. Cadena de conexión

Formato:

```text
mysql+pymysql://ezF1nSTkhwhsAAD.root:TU_PASSWORD@gateway01.us-east-1.prod.aws.tidbcloud.com:4000/fraudia_claims
```

Sustituye `TU_PASSWORD` por la contraseña del panel **Connect** de TiDB Cloud.

**CA / `<CA_PATH>`:** en Vercel no hace falta subir el archivo CA. El código detecta `*.tidbcloud.com` y usa TLS automáticamente.

Si la contraseña tiene caracteres especiales (`@`, `#`, `%`), codifícala en URL (ej. `@` → `%40`).

---

## 2. Variables en Vercel

Proyecto → **Settings** → **Environment Variables**:

| Variable | Valor | Entornos |
|----------|--------|----------|
| `DATABASE_URL` | Cadena `mysql+pymysql://...` de arriba | Production, Preview |
| `PERSIST_DATASET_ON_LOAD` | `true` | Production, Preview |
| `GEMINI_API_KEY` o `OPENAI_API_KEY` | Chat IA | Production, Preview |
| `SECRET_KEY` | Texto aleatorio largo | Production, Preview |

Guarda y haz **Redeploy**.

---

## 3. Crear tablas (una vez por instancia)

```bash
curl -X POST https://fraud-ia.vercel.app/api/db-init
```

Respuesta esperada: `{"status":"ok","message":"Tablas creadas en la base de datos"}`

---

## 4. Local (mismo cluster)

Copia `.env.example` → `.env` y pon la contraseña en `TIDB_PASSWORD`:

```powershell
copy .env.example .env
.\scripts\iniciar-local.ps1
```

O usa `DATABASE_URL` en `.env` en lugar de `TIDB_*`:

```env
DATABASE_URL=mysql+pymysql://ezF1nSTkhwhsAAD.root:PASSWORD@gateway01.us-east-1.prod.aws.tidbcloud.com:4000/fraudia_claims
```

---

## 5. Verificar

```http
GET https://fraud-ia.vercel.app/api/db-status
```

Badge en la app: `TiDB Cloud (MySQL)` con registros > 0 tras cargar datos.

---

## Solución de problemas

| Síntoma | Qué hacer |
|---------|-----------|
| `In-memory (Vercel)` | Falta `DATABASE_URL` → añadir y redeploy |
| `Can't connect` | TiDB Cloud → Security → permitir acceso público |
| FK / IntegrityError | Subir Excel **multihoja** (plantilla completa) |
| Dashboard vacío | Subir Excel → **Activar motor IA** |

---

## Seguridad

- No subas `.env` ni `DATABASE_URL` con contraseña a Git.  
- Rota la contraseña en TiDB Cloud si se expuso en chat o capturas.
