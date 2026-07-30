"""Configuración de la aplicación (variables de entorno)."""
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# Raíz del repositorio (…/ttn-training-core)
BASE_DIR = Path(__file__).resolve().parent.parent
CONTENT_DIR = BASE_DIR / "content"
RESOURCES_DIR = BASE_DIR / "resources"
DATA_DIR = BASE_DIR / "data"  # estado mutable (usuarios, permisos)
UPLOADS_DIR = DATA_DIR / "uploads"  # insumos subidos (video/voz/documentos)
LESSONS_DB = DATA_DIR / "lessons.db"  # lecciones generadas (SQLite)


class Settings(BaseSettings):
    """Ajustes leídos de variables de entorno / archivo .env."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- OpenAI / asistente ---
    # NUNCA se escribe la key en el código: se lee del entorno.
    openai_api_key: str = ""
    assistant_model: str = "gpt-4o"
    assistant_max_tokens: int = 1024

    # --- Generación de lecciones (panel admin) ---
    # Modelo que redacta las lecciones. gpt-4o-mini tiene un TPM mucho más alto y es
    # más barato → más seguro para la cuota actual. Subir a gpt-4o si amplían el límite.
    lesson_model: str = "gpt-4o-mini"
    # Tokens máximos de salida por llamada (un lote produce varias lecciones ricas).
    lesson_max_tokens: int = 6000
    # Tamaño máximo (caracteres) de material por llamada. Un apartado más grande se parte.
    lesson_source_chunk_chars: int = 18000
    # Máximo de apartados agrupados por llamada (menos llamadas = más rápido).
    lesson_batch_max_sections: int = 6
    # Presupuesto de tokens/min (TPM) para regular el ritmo. Por defecto alto porque
    # gpt-4o-mini tiene TPM elevado; el backoff ante 429 cubre el resto. Si se usa
    # gpt-4o (TPM 30k), bajar este valor a ~28000.
    lesson_tpm_budget: int = 180000

    # --- Evaluaciones / certificación ---
    quiz_num_questions: int = 10  # preguntas de la evaluación del módulo
    quiz_passing_score: int = 80  # % mínimo para aprobar y certificar
    # Modelo de transcripción de voz/video (Whisper).
    transcription_model: str = "whisper-1"
    # Tamaño máximo de insumo aceptado (MB).
    max_upload_mb: int = 200
    # Rutas a los binarios externos. Vacío = autodetección (PATH y ubicaciones conocidas).
    pdftotext_path: str = ""
    ffmpeg_path: str = ""

    # --- CORS: orígenes del SPA (Vite) permitidos ---
    cors_origins: list[str] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]

    # --- Autenticación ---
    # Secreto para firmar los tokens de sesión. CAMBIAR en producción.
    auth_secret: str = "dev-insecure-secret-cambiame"
    auth_token_ttl_hours: int = 12
    # Contraseña inicial del usuario admin al sembrar users.json (cambiar luego).
    admin_default_password: str = "admin1234"

    @property
    def assistant_enabled(self) -> bool:
        """El asistente solo funciona si hay API key configurada."""
        return bool(self.openai_api_key)


@lru_cache
def get_settings() -> Settings:
    return Settings()
