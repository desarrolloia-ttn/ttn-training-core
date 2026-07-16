"""Modelos Pydantic para el contenido y el asistente."""
from typing import Literal

from pydantic import BaseModel, Field


# --------- Contenido del módulo ---------
class Section(BaseModel):
    heading: str
    steps: list[str] = Field(default_factory=list)


class Lesson(BaseModel):
    id: str
    code: str
    title: str
    duration: str
    summary: str
    objectives: list[str] = Field(default_factory=list)
    sections: list[Section] = Field(default_factory=list)
    keyPoints: list[str] = Field(default_factory=list)


class Block(BaseModel):
    id: str
    title: str
    lessons: list[Lesson] = Field(default_factory=list)


class Module(BaseModel):
    product: str
    moduleId: int
    code: str
    title: str
    description: str
    source: str | None = None
    scope: str | None = None
    prerequisites: list[str] = Field(default_factory=list)
    blocks: list[Block] = Field(default_factory=list)


class ModuleSummary(BaseModel):
    """Vista ligera de un módulo (sin el detalle de lecciones)."""

    product: str
    moduleId: int
    code: str
    title: str
    description: str
    blockCount: int
    lessonCount: int


# --------- Asistente ---------
class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class ChatRequest(BaseModel):
    message: str
    context: str | None = Field(
        default=None,
        description="Contexto de la pantalla actual del alumno (p. ej. la lección).",
    )
    moduleId: int | None = Field(
        default=None,
        description="Módulo actual, para cargar el/los manual(es) correcto(s) como fuente.",
    )
    history: list[ChatMessage] = Field(default_factory=list)


class ChatResponse(BaseModel):
    reply: str
    model: str


class Suggestion(BaseModel):
    label: str
    prompt: str


# --------- Autenticación / usuarios ---------
class LoginRequest(BaseModel):
    username: str
    password: str


class UserPublic(BaseModel):
    """Usuario sin datos sensibles (nunca incluye la contraseña)."""

    id: str
    username: str
    name: str
    role: Literal["admin", "usuario"]
    unlockedModules: list[int] = Field(default_factory=list)
    # progreso de lecciones por módulo: { "2": ["obj", "acceso", ...] }
    progress: dict[str, list[str]] = Field(default_factory=dict)


class ProgressUpdate(BaseModel):
    moduleId: int
    completed: list[str] = Field(default_factory=list)


class LoginResponse(BaseModel):
    token: str
    user: UserPublic


class ModuleAccessUpdate(BaseModel):
    moduleId: int
    unlocked: bool


class UserCreate(BaseModel):
    username: str
    name: str
    password: str
    role: Literal["admin", "usuario"] = "usuario"
    unlockedModules: list[int] = Field(default_factory=list)


class UserUpdate(BaseModel):
    """Actualización parcial: solo los campos presentes se modifican."""

    name: str | None = None
    role: Literal["admin", "usuario"] | None = None
    password: str | None = None
