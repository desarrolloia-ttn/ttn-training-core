"""Modelos Pydantic para el contenido y el asistente."""
from typing import Literal

from pydantic import BaseModel, Field


# --------- Contenido del módulo ---------
class Section(BaseModel):
    heading: str
    steps: list[str] = Field(default_factory=list)


class Concept(BaseModel):
    term: str
    definition: str


class FunctionalExplanation(BaseModel):
    """Explicación funcional: qué hace, por qué existe, cuándo/quién lo usa, impacto."""

    what: str = ""
    why: str = ""
    when: str = ""
    who: str = ""
    impact: str = ""


class CaseStudy(BaseModel):
    scenario: str = ""
    task: str = ""


class ReviewQuestion(BaseModel):
    """Pregunta de repaso de opción múltiple (autoevaluación por lección)."""

    question: str
    options: list[str] = Field(default_factory=list)
    correctIndex: int = 0
    explanation: str = ""
    answer: str = ""  # compatibilidad con lecciones antiguas (respuesta abierta)


class Lesson(BaseModel):
    id: str
    code: str
    title: str
    duration: str
    summary: str
    objectives: list[str] = Field(default_factory=list)
    # Video de la lección (ruta relativa /api/media/{assetId}); se monta si está presente.
    video: str | None = None
    # --- Enriquecimiento pedagógico (todos opcionales para compatibilidad) ---
    intro: str = ""
    concepts: list[Concept] = Field(default_factory=list)
    functional: FunctionalExplanation | None = None
    sections: list[Section] = Field(default_factory=list)  # procedimiento paso a paso
    recommendations: list[str] = Field(default_factory=list)
    commonErrors: list[str] = Field(default_factory=list)
    errorConsequences: str = ""
    caseStudy: CaseStudy | None = None
    keyPoints: list[str] = Field(default_factory=list)
    reviewQuestions: list[ReviewQuestion] = Field(default_factory=list)


class Block(BaseModel):
    id: str
    title: str
    lessons: list[Lesson] = Field(default_factory=list)


class ModuleDoc(BaseModel):
    """Documento de apoyo del módulo (insumo usado para generarlo)."""

    kind: Literal["PDF", "DOC", "LINK"] = "PDF"
    title: str
    sub: str = ""
    assetId: str | None = None


class Module(BaseModel):
    product: str
    moduleId: int
    code: str
    title: str
    description: str
    source: str | None = None
    scope: str | None = None
    prerequisites: list[str] = Field(default_factory=list)
    docs: list[ModuleDoc] = Field(default_factory=list)
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


class CatalogModule(BaseModel):
    """Módulo del catálogo con estado calculado para el usuario actual."""

    id: int
    code: str
    title: str
    description: str
    lessonCount: int
    cover: str | None = None
    published: bool = False
    hasCertificate: bool = False
    accessible: bool = False
    completed: int = 0
    progress: int = 0
    status: Literal["done", "progress", "idle", "locked"] = "idle"


class CatalogModuleAdmin(BaseModel):
    """Módulo del catálogo para administración (crear/editar)."""

    id: int
    code: str
    title: str
    description: str
    hasCover: bool = False


class CatalogModuleUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    code: str | None = None


class Client(BaseModel):
    """Cliente/faceta de un producto (p. ej. Biowel Colombia, Biowel RD)."""

    id: int
    product: str
    name: str
    description: str = ""
    cover: str | None = None
    moduleCount: int = 0


class ClientUpdate(BaseModel):
    name: str | None = None
    description: str | None = None


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
    # certificaciones por módulo: { "2": {"score": 90, "passedAt": "..."} }
    certifications: dict[str, dict] = Field(default_factory=dict)


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


# --------- Insumos y generación de lecciones (panel admin) ---------
AssetKind = Literal["document", "audio", "video"]
AssetStatus = Literal["uploaded", "processing", "ready", "error"]
LessonStatus = Literal["draft", "published"]


class AssetPublic(BaseModel):
    """Insumo subido por el admin (documento / voz / video) ya procesado."""

    id: str
    kind: AssetKind
    filename: str
    mime: str | None = None
    sizeBytes: int = 0
    status: AssetStatus
    # true si tiene texto extraído (transcripción o texto del documento).
    hasText: bool = False
    textPreview: str | None = None
    error: str | None = None
    createdAt: str


class GenerateRequest(BaseModel):
    """Petición de generación de una lección/módulo a partir de insumos."""

    assetIds: list[str] = Field(default_factory=list)
    product: str = "biowel"
    clientId: int | None = Field(default=None, description="Cliente/faceta del producto.")
    moduleId: int | None = Field(
        default=None,
        description="Módulo del catálogo al que pertenece (opcional).",
    )
    version: str = Field(default="1.0", description="Etiqueta de versión (p. ej. 1.1).")
    title: str | None = Field(default=None, description="Título sugerido (opcional).")
    instructions: str | None = Field(
        default=None,
        description="Indicaciones extra del admin para orientar la generación.",
    )
    runReview: bool = Field(
        default=False,
        description="Revisión de fidelidad (llamada extra; el auditor de cobertura ya reporta faltantes).",
    )


# ---- Salida estructurada que produce el modelo de OpenAI ----
class GenSection(BaseModel):
    heading: str
    steps: list[str] = Field(default_factory=list)


class GenLesson(BaseModel):
    title: str
    duration: str
    summary: str
    objectives: list[str] = Field(default_factory=list)
    intro: str = ""
    concepts: list[Concept] = Field(default_factory=list)
    functional: FunctionalExplanation | None = None
    sections: list[GenSection] = Field(default_factory=list)  # procedimiento
    recommendations: list[str] = Field(default_factory=list)
    commonErrors: list[str] = Field(default_factory=list)
    errorConsequences: str = ""
    caseStudy: CaseStudy | None = None
    keyPoints: list[str] = Field(default_factory=list)
    reviewQuestions: list[ReviewQuestion] = Field(default_factory=list)


class GenBlock(BaseModel):
    title: str
    lessons: list[GenLesson] = Field(default_factory=list)


class GenModule(BaseModel):
    """Contenido que el modelo redacta; los ids/códigos se asignan luego."""

    title: str
    description: str
    blocks: list[GenBlock] = Field(default_factory=list)


# ---- Temario (paso 1 de la generación en dos fases) ----
class GenOutlineBlock(BaseModel):
    title: str
    lessonTitles: list[str] = Field(default_factory=list)


class GenOutline(BaseModel):
    """Índice exhaustivo del material: un título de lección por apartado."""

    title: str
    description: str
    blocks: list[GenOutlineBlock] = Field(default_factory=list)


class GenVideoOrderItem(BaseModel):
    index: int  # índice original del video en la lista de insumos
    title: str  # título de la clase para ese video


class GenVideoOrder(BaseModel):
    """Orden pedagógico lógico de los videos (introducción → básico → avanzado)."""

    items: list[GenVideoOrderItem] = Field(default_factory=list)


# ---- Módulo generado, persistido en SQLite ----
class GeneratedModuleSummary(BaseModel):
    id: str
    product: str
    moduleId: int | None = None
    clientId: int | None = None
    clientName: str | None = None
    code: str
    title: str
    version: str = "1.0"
    status: LessonStatus
    blockCount: int
    lessonCount: int
    updatedAt: str


class GeneratedModulePublic(BaseModel):
    id: str
    product: str
    moduleId: int | None = None
    code: str
    title: str
    description: str
    version: str = "1.0"
    status: LessonStatus
    content: Module
    reviewNotes: str | None = None
    sourceAssetIds: list[str] = Field(default_factory=list)
    hasQuiz: bool = False
    quizCount: int = 0
    hasCertificate: bool = False
    hasManual: bool = False
    createdAt: str
    updatedAt: str


class PublishedVersion(BaseModel):
    """Versión publicada de un módulo, para el selector del alumno."""

    id: str
    version: str
    title: str
    lessonCount: int
    updatedAt: str


class LessonUpdate(BaseModel):
    """Edición del admin sobre el contenido generado (reemplazo completo)."""

    content: Module


# --------- Evaluación / certificación ---------
class GenQuizQuestion(BaseModel):
    """Pregunta de opción múltiple que produce el modelo."""

    question: str
    options: list[str] = Field(default_factory=list)
    correctIndex: int
    explanation: str = ""


class GenQuiz(BaseModel):
    questions: list[GenQuizQuestion] = Field(default_factory=list)


class ManualStep(BaseModel):
    titulo: str = ""
    explicacion: str = ""
    resultado: str = ""            # resultado esperado
    advertencias: list[str] = Field(default_factory=list)
    insuficiente: bool = False     # → "Información insuficiente para documentar este paso."


class ManualSection(BaseModel):
    titulo: str = ""
    pasos: list[ManualStep] = Field(default_factory=list)


class ManualFaq(BaseModel):
    pregunta: str = ""
    respuesta: str = ""


class GenManualDoc(BaseModel):
    """Manual de usuario estructurado (salida del agente A9). Se renderiza a PDF."""

    titulo: str = ""
    subtitulo: str = ""
    objetivo: str = ""
    alcance: str = ""
    requisitos: list[str] = Field(default_factory=list)
    procedimiento: list[ManualSection] = Field(default_factory=list)
    buenas_practicas: list[str] = Field(default_factory=list)
    errores_frecuentes: list[str] = Field(default_factory=list)
    recomendaciones: list[str] = Field(default_factory=list)
    glosario: list[Concept] = Field(default_factory=list)
    faq: list[ManualFaq] = Field(default_factory=list)
    resumen: str = ""


class LessonManualDoc(BaseModel):
    """Manual de una versión, servido al front para renderizar/exportar a PDF."""

    moduleId: int | None = None
    code: str = ""
    title: str = ""
    version: str = "1.0"
    date: str = ""
    doc: GenManualDoc


class LessonManualDoc(BaseModel):
    """Manual estructurado + metadatos, servido al front para renderizar/exportar a PDF."""

    moduleId: int | None = None
    code: str = ""
    title: str = ""
    version: str = "1.0"
    date: str = ""
    doc: GenManualDoc


class QuizQuestion(GenQuizQuestion):
    """Pregunta almacenada (misma forma; incluye la respuesta correcta)."""


class QuizQuestionPublic(BaseModel):
    """Pregunta enviada al alumno: SIN la respuesta correcta ni la explicación."""

    question: str
    options: list[str] = Field(default_factory=list)


class QuizPublic(BaseModel):
    moduleId: int
    passingScore: int
    questions: list[QuizQuestionPublic] = Field(default_factory=list)


class QuizSubmit(BaseModel):
    answers: list[int] = Field(default_factory=list)  # índice elegido por pregunta


class QuizResultItem(BaseModel):
    correctIndex: int
    yourIndex: int
    isCorrect: bool
    explanation: str = ""


class QuizResult(BaseModel):
    moduleId: int
    total: int
    correct: int
    score: int  # 0-100
    passingScore: int
    passed: bool
    certified: bool
    results: list[QuizResultItem] = Field(default_factory=list)
    version: str | None = Field(default=None, description="Nueva etiqueta de versión (opcional).")
