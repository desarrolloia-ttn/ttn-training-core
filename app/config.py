"""Configuración de la aplicación (variables de entorno)."""
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# Raíz del repositorio (…/ttn-training-core)
BASE_DIR = Path(__file__).resolve().parent.parent
CONTENT_DIR = BASE_DIR / "content"
RESOURCES_DIR = BASE_DIR / "resources"


class Settings(BaseSettings):
    """Ajustes leídos de variables de entorno / archivo .env."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- OpenAI / asistente ---
    # NUNCA se escribe la key en el código: se lee del entorno.
    openai_api_key: str = ""
    assistant_model: str = "gpt-4o"
    assistant_max_tokens: int = 1024

    # --- CORS: orígenes del SPA (Vite) permitidos ---
    cors_origins: list[str] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]

    @property
    def assistant_enabled(self) -> bool:
        """El asistente solo funciona si hay API key configurada."""
        return bool(self.openai_api_key)


@lru_cache
def get_settings() -> Settings:
    return Settings()
