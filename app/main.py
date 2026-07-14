from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import assistant
from .config import get_settings
from .routers import assistant as assistant_router
from .routers import content as content_router

settings = get_settings()

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
)

app.include_router(content_router.router)
app.include_router(assistant_router.router)


@app.get("/api/health", tags=["health"])
def health() -> dict:
    """Estado del servicio y si el asistente está configurado."""
    return {
        "status": "ok",
        "assistantEnabled": assistant.is_enabled(),
        "model": settings.assistant_model,
    }
