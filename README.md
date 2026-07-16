# TTN Training Core

Backend de la plataforma de capacitación de **Biowel PRO**. Sirve el contenido de
los módulos de formación y expone un **asistente conectado a OpenAI** que responde
usando el manual del producto como fuente.

Primer módulo implementado: **Módulo 2 · Asistencial** (Bloques 0 a 3:
introducción/acceso, agendamiento, admisión y atención, ordenamiento). La
Dispensación se cubrirá en el Módulo 4.

- **Stack:** Python + FastAPI + OpenAI SDK
- **Persistencia:** contenido en archivos (JSON), sin base de datos todavía
- **Consumidor:** el SPA `ttn-training-spa` (Vite/React)

## Estructura

```
ttn-training-core/
├── app/
│   ├── main.py            # App FastAPI, CORS, health
│   ├── config.py          # Settings por variables de entorno
│   ├── schemas.py         # Modelos Pydantic (Module/Block/Lesson, Chat)
│   ├── content_store.py   # Carga el contenido desde content/*.json
│   ├── assistant.py       # Integración con OpenAI (manual como fuente)
│   └── routers/
│       ├── content.py     # /api/modules, /api/products/{p}/modules/{id}
│       └── assistant.py   # /api/assistant/chat, /api/assistant/suggestions
├── content/
│   └── biowel_asistencial.json   # Temario del módulo (4 bloques, 15 lecciones)
├── resources/
│   └── manual_asistencial.txt    # Manual limpio que alimenta al asistente
├── requirements.txt
├── .env.example
└── README.md
```

## Puesta en marcha

```bash
# 1. Entorno virtual (recomendado)
py -3.12 -m venv .venv
.venv\Scripts\activate        # Windows PowerShell
# source .venv/bin/activate   # macOS/Linux

# 2. Dependencias
pip install -r requirements.txt

# 3. Configuración
copy .env.example .env        # Windows  (cp en macOS/Linux)
#   Edita .env y coloca tu OPENAI_API_KEY

# 4. Levantar el servidor
uvicorn app.main:app --reload --port 8000
```

- API: http://localhost:8000
- Documentación interactiva (Swagger): http://localhost:8000/docs

> **Seguridad:** la `OPENAI_API_KEY` se lee del entorno (`.env`), nunca se
> escribe en el código ni se sube al repositorio (`.env` está en `.gitignore`).
> El asistente corre **en el backend**: el SPA nunca ve la key.

## Endpoints

| Método | Ruta | Descripción |
|--------|------|-------------|
| GET | `/api/health` | Estado del servicio y si el asistente está configurado |
| GET | `/api/modules?product=biowel` | Lista de módulos (resumen) |
| GET | `/api/products/{product}/modules/{module_id}` | Detalle del módulo con bloques y lecciones |
| GET | `/api/assistant/suggestions` | Preguntas sugeridas para el chat |
| POST | `/api/assistant/chat` | Pregunta del alumno → respuesta de OpenAI |
| POST | `/api/auth/login` | Login con usuario/contraseña → token + usuario |
| GET | `/api/auth/me` | Usuario actual (requiere token Bearer) |
| GET | `/api/users` | Lista de usuarios (solo admin) |
| PATCH | `/api/users/{id}/modules` | (Des)bloquear un módulo para un usuario (solo admin) |

## Autenticación y roles

- Usuarios, roles y módulos desbloqueados se guardan en `data/users.json`
  (se siembra solo la primera vez; el archivo está en `.gitignore`).
- Contraseñas hasheadas con PBKDF2 (nunca en texto plano). Token de sesión
  firmado con HMAC (`AUTH_SECRET`), enviado como `Authorization: Bearer <token>`.
- Dos roles: **admin** (acceso a todos los módulos + gestión de usuarios) y
  **usuario** (todos los módulos bloqueados salvo los que el admin le desbloquee).

**Usuarios demo sembrados (CAMBIAR estas contraseñas):**

| Usuario | Contraseña | Rol |
|---------|-----------|-----|
| `admin` | `admin1234` (o `ADMIN_DEFAULT_PASSWORD`) | admin |
| `ana` | `ana1234` | usuario |
| `carlos` | `carlos1234` | usuario |

Para regenerar los usuarios demo, borra `data/users.json` y reinicia el backend.


Ejemplo de `POST /api/assistant/chat`:

```json
{
  "message": "¿Cómo creo una agenda para un médico?",
  "context": "Lección: Configuración de agendas del médico",
  "history": []
}
```

Respuesta:

```json
{ "reply": "Para crear una agenda...", "model": "gpt-4o" }
```

Si no hay `OPENAI_API_KEY`, `/api/assistant/chat` responde **503** (el resto de
endpoints de contenido funcionan igual).

## Conexión con el SPA (siguiente paso)

El SPA (`ttn-training-spa`) hoy tiene el contenido quemado en
`src/data/products.ts` y `src/pages/Modulo.tsx`, y el asistente simulado en
`src/components/Assistant.tsx`. Para consumir este backend:

1. Definir `VITE_API_URL=http://localhost:8000` en el `.env` del SPA.
2. Reemplazar el contenido de `Modulo.tsx` por un `fetch` a
   `GET /api/products/biowel/modules/2` y renderizar los bloques/lecciones.
3. En `Assistant.tsx`, sustituir `pickReply()` por un `POST /api/assistant/chat`
   enviando `message`, el `context` actual y el `history`.

## Contenido

El temario vive en `content/biowel_asistencial.json` y se valida contra los
modelos Pydantic de `app/schemas.py` al cargarse. Para editar o ampliar el
contenido basta con modificar ese archivo (o agregar nuevos módulos y
registrarlos en `app/content_store.py`).
