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
    history: list[ChatMessage] = Field(default_factory=list)


class ChatResponse(BaseModel):
    reply: str
    model: str


class Suggestion(BaseModel):
    label: str
    prompt: str
