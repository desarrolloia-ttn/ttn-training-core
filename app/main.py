from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import assistant
from .config import get_settings
from .db import init_db
from .routers import assistant as assistant_router
from .routers import auth as auth_router
from .routers import catalog as catalog_router
from .routers import content as content_router
from .routers import lessons as lessons_router
from .routers import users as users_router

settings = get_settings()

# Crea la base de datos SQLite de lecciones/insumos si no existe.
init_db()

app = FastAPI(
    title="TTN Training Core",
    description="Backend de la plataforma de capacitación de Biowel (módulo Asistencial).",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Content-Disposition"],  # para leer el nombre del archivo en descargas
)

app.include_router(content_router.router)
app.include_router(assistant_router.router)
app.include_router(auth_router.router)
app.include_router(users_router.router)
app.include_router(lessons_router.router)
app.include_router(lessons_router.media_router)
app.include_router(lessons_router.published_router)
app.include_router(catalog_router.admin_router)
app.include_router(catalog_router.public_router)
app.include_router(catalog_router.clients_admin_router)
app.include_router(catalog_router.clients_router)


@app.get("/api/health", tags=["health"])
def health() -> dict:
    """Estado del servicio y si el asistente está configurado."""
    return {
        "status": "ok",
        "assistantEnabled": assistant.is_enabled(),
        "model": settings.assistant_model,
    }
