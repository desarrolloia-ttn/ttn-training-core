# TTN Training Core

Backend (Python + FastAPI) de la plataforma de capacitación **Capacita+ / Biowel**. Expone el catálogo por producto/cliente, la generación de **lecciones con IA** desde insumos (PDF/voz/video), **evaluaciones**, **certificados**, **manual de usuario** y un **asistente conectado a OpenAI**. Lo consume el SPA [`ttn-training-spa`](../ttn-training-spa).

- **Stack:** Python 3.12 · FastAPI · OpenAI SDK
- **Persistencia:** SQLite (`data/lessons.db`) para lecciones/catálogo/clientes; `data/users.json` para usuarios y permisos.

---

## Puesta en marcha

```bash
# 1. Entorno virtual
py -3.12 -m venv .venv
.venv\Scripts\activate          # Windows PowerShell
# source .venv/bin/activate     # macOS/Linux

# 2. Dependencias
pip install -r requirements.txt

# 3. Configuración
copy .env.example .env          # Windows  (cp en macOS/Linux)
#   Edita .env y coloca tu OPENAI_API_KEY

# 4. Levantar el servidor
uvicorn app.main:app --reload --port 8000
```

- API: **http://localhost:8000**
- Swagger (docs interactivas): **http://localhost:8000/docs**

> La `OPENAI_API_KEY` se lee del entorno (`.env`); nunca se escribe en el código ni se sube al repo. El asistente y la generación corren en el backend: el SPA nunca ve la key.

### Variables de entorno principales (`.env`)

| Variable | Por defecto | Descripción |
|----------|-------------|-------------|
| `OPENAI_API_KEY` | *(vacío)* | Habilita asistente, generación de lecciones, evaluación y manual. Sin ella devuelven 503. |
| `ADMIN_DEFAULT_PASSWORD` | `admin1234` | Contraseña inicial del usuario `admin` al sembrar `users.json`. |
| `AUTH_SECRET` | `dev-insecure-secret-cambiame` | Secreto para firmar el token de sesión. **Cambiar en producción.** |
| `CORS_ORIGINS` | `http://localhost:5173` | Orígenes del SPA permitidos. |
| `QUIZ_PASSING_SCORE` | `80` | % mínimo para aprobar la evaluación y certificar. |

> Opcional para procesar insumos: **poppler** (`pdftotext`) para PDF y **ffmpeg** para transcribir voz/video.

---

## Iniciar sesión

Autenticación por usuario/contraseña. El flujo:

1. `POST /api/auth/login` con `{ "username": "...", "password": "..." }`.
2. Devuelve `{ token, user }`. El SPA guarda el token y lo envía como `Authorization: Bearer <token>` en cada petición.
3. `GET /api/auth/me` devuelve el usuario actual a partir del token.

Ejemplo:

```bash
curl -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"admin1234"}'
```

- Contraseñas hasheadas con **PBKDF2** (nunca en texto plano).
- Token firmado con **HMAC** (`AUTH_SECRET`).

### Usuarios sembrados (demo — CAMBIAR)

Se crean automáticamente la **primera vez** que arranca el backend, en `data/users.json`:

| Usuario | Contraseña | Rol |
|---------|-----------|-----|
| `admin` | `admin1234` (o `ADMIN_DEFAULT_PASSWORD`) | **admin** |
| `ana` | `ana1234` | usuario |
| `carlos` | `carlos1234` | usuario |

Para **regenerarlos**, borra `data/users.json` y reinicia el backend.

### Roles

- **admin:** acceso a **todos** los módulos + gestión de usuarios, clientes, módulos y lecciones (crear evaluación, certificado y manual).
- **usuario:** nace con **todos los módulos bloqueados**; el admin habilita cada módulo por usuario (`PATCH /api/users/{id}/modules`).

---

## Endpoints principales

| Método | Ruta | Descripción |
|--------|------|-------------|
| POST | `/api/auth/login` | Login → token + usuario |
| GET | `/api/auth/me` | Usuario actual (Bearer) |
| GET | `/api/users` · POST · PATCH · DELETE | Gestión de usuarios (admin) |
| PATCH | `/api/users/{id}/modules` | (Des)bloquear un módulo a un usuario (admin) |
| GET | `/api/catalog?clientId=` | Catálogo con estado (acceso/progreso) del usuario |
| GET/POST/PATCH/DELETE | `/api/clients` · `/api/admin/clients` | Clientes de cada producto |
| GET/POST/PATCH/DELETE | `/api/admin/catalog` | Módulos del catálogo (admin) |
| POST | `/api/admin/lessons/generate` | Genera lecciones con IA desde insumos (admin) |
| POST | `/api/admin/lessons/{id}/quiz` | Genera la evaluación (admin) |
| POST | `/api/admin/lessons/{id}/manual` | Genera el manual de usuario estructurado (admin) |
| GET | `/api/published/modules/{id}/quiz` | Evaluación del módulo (alumno) |
| GET | `/api/published/modules/{id}/manual` | Manual del módulo (alumno con acceso) |

Lista completa en **`/docs`**.

---

## Estructura

```
app/
├── main.py               # App FastAPI, CORS, routers
├── config.py             # Settings por variables de entorno (.env)
├── schemas.py            # Modelos Pydantic
├── auth.py               # Hash de contraseñas + firma de token
├── user_store.py         # Usuarios y permisos (data/users.json)
├── db.py                 # SQLite: esquema + migraciones
├── catalog.py / catalog_store.py / client_store.py / lessons_store.py
├── lesson_generator.py · quiz_generator.py · manual_generator.py · ingest.py
└── routers/              # auth, users, content, assistant, catalog, lessons
content/   · temario base sembrado
data/      · users.json + lessons.db + uploads (en .gitignore)
```
