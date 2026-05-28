# TiDB Cloud + Vercel (producción con datos reales)

Tu instancia **Siniestros** en TiDB Cloud (AWS `us-east-1`) es compatible con este proyecto: usa el driver **MySQL** (`mysql+pymysql://`).

Con `DATABASE_URL` configurada en Vercel, el flujo queda igual que en local:

1. Subir dataset o generar sintéticos  
2. Guardar tablas en TiDB  
3. Ejecutar análisis completo  
4. Dashboard y Modelo ML leen los resultados de **ese** dataset  

Ya no depende del modo demo “In-memory (Vercel)”.

---

## 1. Obtener la cadena de conexión en TiDB Cloud

1. Entra a [TiDB Cloud](https://tidbcloud.com) → cluster **Siniestros** (Active).  
2. Menú **Connect** → **Public endpoint** (o el que uses).  
3. Crea una base de datos si no existe, por ejemplo: `fraudia_claims`  
4. Copia usuario, contraseña, host y puerto (suele ser **4000**).  
5. Descarga el certificado CA si el asistente lo pide (el código ya usa TLS por defecto para hosts `*.tidbcloud.com`).

Formato para FraudIA:

```text
mysql+pymysql://USUARIO:CONTRASEÑA@HOST_TIDB:4000/fraudia_claims
```

Ejemplo con tu cluster **Siniestros** (sustituye `TU_PASSWORD` por la misma de tu `.env` local):

```text
mysql+pymysql://2HEb2hZnGuHVGPc.root:TU_PASSWORD@gateway01.us-east-1.prod.aws.tidbcloud.com:4000/fraudia_claims
```

**CA / `<CA_PATH>`:** en Vercel **no hace falta** subir el archivo CA. El código detecta `*.tidbcloud.com` y usa TLS automáticamente.

**Importante:** Si la contraseña tiene caracteres especiales (`@`, `#`, `%`), codifícala en URL (ej. `@` → `%40`).

---

## 2. Variables en Vercel

Proyecto → **Settings** → **Environment Variables**:

| Variable | Valor | Entornos |
|----------|--------|----------|
| `DATABASE_URL` | Cadena `mysql+pymysql://...` de TiDB | Production, Preview |
| `OPENAI_API_KEY` | Tu clave OpenAI | Production, Preview |
| `OPENAI_MODEL` | `gpt-4o-mini` | Production, Preview |
| `OPENAI_ENABLED` | `true` | Production, Preview |
| `SECRET_KEY` | Texto aleatorio largo | Production, Preview |
| `MYSQL_SSL` | No necesario (el host ya es `tidbcloud.com`) | — |

Guarda y haz **Redeploy** del último deployment.

---

## 3. Crear tablas (una vez)

Tras el deploy, llama una vez:

```http
POST https://TU-DOMINIO.vercel.app/api/db-init
```

O desde terminal:

```bash
curl -X POST https://fraud-ia.vercel.app/api/db-init
```

Respuesta esperada: `{"status":"ok","message":"Tablas creadas en la base de datos"}`

---

## 4. Verificar conexión

Abre la app y revisa el badge superior:

- Antes: `DB: In-memory (Vercel)`  
- Después: `DB: TiDB Cloud (MySQL)` (o `MySQL`) con host del gateway TiDB  

También puedes usar:

```http
GET https://TU-DOMINIO.vercel.app/api/db-status
```

---

## 5. Flujo de uso en producción

1. **Datos** → subir Excel/CSV o **Generar datos sintéticos**  
2. **Ejecutar análisis completo** (entrena y guarda scores en TiDB)  
3. **Dashboard** y **Modelo ML** → deben coincidir con el número de siniestros cargados  
4. Chat IA usa el contexto del análisis actual  

---

## 6. Local con la misma TiDB (opcional)

En `.env` (no subir a Git):

```env
DATABASE_URL=mysql+pymysql://USUARIO:PASSWORD@HOST:4000/fraudia_claims
```

```powershell
.\venv\Scripts\Activate.ps1
pip install pymysql cryptography
python -m src.app.main
```

---

## Solución de problemas

| Síntoma | Causa | Qué hacer |
|---------|--------|-----------|
| Sigue `In-memory (Vercel)` | `DATABASE_URL` no definida o mal escrita | Revisar variable en Vercel y redeploy |
| `Can't connect to MySQL server` | IP/firewall TiDB | En TiDB Cloud → Security → permitir acceso (0.0.0.0/0 para pruebas o IP de Vercel) |
| `SSL` / certificate error | TLS | Host debe ser `*.tidbcloud.com`; o `MYSQL_SSL=true` |
| `No module named 'pymysql'` | Dependencia faltante | Ya está en `requirements.txt`; redeploy |
| Dashboard con datos viejos | Análisis no ejecutado tras carga | Subir datos → **Ejecutar análisis** de nuevo |

---

## Nota de seguridad

- No subas `DATABASE_URL` con contraseña a Git.  
- Usa solo **Environment Variables** de Vercel.  
- Rota la contraseña del usuario TiDB si alguna vez se expuso.
