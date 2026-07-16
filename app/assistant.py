"""Asistente de capacitación conectado a OpenAI, con el/los manual(es) del módulo como fuente."""
from functools import lru_cache

from openai import OpenAI

from .config import RESOURCES_DIR, get_settings
from .schemas import ChatMessage, Suggestion

# Manuales fuente por módulo: id -> lista de (título, archivo en resources/).
_MANUALS: dict[int, list[tuple[str, str]]] = {
    2: [("GUÍA DE USO BIOWEL ASISTENCIAL", "manual_asistencial.txt")],
    4: [
        ("PARAMETRIZACIÓN DE TABLAS PARA DISPENSACIÓN (PROGRAMASTOP)", "manual_dispensacion_parametrizacion.txt"),
        ("FLUJO DE DISPENSACIÓN (PROGRAMASTOP)", "manual_dispensacion_flujo.txt"),
    ],
}
_DEFAULT_MODULE = 2  # si no se indica módulo, se usa Asistencial

_SYSTEM_TEMPLATE = """\
Eres el asistente de capacitación de la plataforma de formación de Biowel PRO.
Tu rol es ayudar a que el personal (médicos, enfermería, admisiones, farmacia)
aprenda a usar Biowel, con foco en el módulo en el que está el alumno.

Reglas:
- Responde SIEMPRE en español, claro y conciso, con un tono didáctico.
- Básate ÚNICAMENTE en el/los manual(es) que aparecen más abajo como fuente de verdad.
- Si la pregunta no está cubierta por el manual, dilo con honestidad y sugiere
  a quién o dónde consultar; no inventes pasos ni nombres de pantallas.
- Cuando expliques un procedimiento, usa pasos numerados y nombra los apartados,
  submódulos y botones tal como aparecen en el manual.
- No solicites ni expongas credenciales, tokens ni datos personales de pacientes.
  Usa ejemplos ficticios si necesitas ilustrar con datos.

{context_block}{manuals}
"""

SUGGESTIONS: list[Suggestion] = [
    Suggestion(label="Resume los puntos clave de esta lección",
               prompt="Resume los puntos clave de esta lección"),
    Suggestion(label="Hazme una pregunta de práctica",
               prompt="Hazme una pregunta de práctica sobre esta lección"),
    Suggestion(label="¿Cuáles son los pasos exactos?",
               prompt="Explícame los pasos exactos de este procedimiento"),
]


@lru_cache
def _read(filename: str) -> str:
    return (RESOURCES_DIR / filename).read_text(encoding="utf-8")


@lru_cache
def _manuals_text(module_id: int) -> str:
    entries = _MANUALS.get(module_id) or _MANUALS[_DEFAULT_MODULE]
    parts: list[str] = []
    for title, filename in entries:
        try:
            body = _read(filename)
        except FileNotFoundError:
            continue
        parts.append(f"=== MANUAL: {title} ===\n{body}\n=== FIN DEL MANUAL ===")
    return "\n\n".join(parts)


def _build_system(context: str | None, module_id: int) -> str:
    context_block = ""
    if context:
        context_block = (
            f"Contexto de la pantalla actual del alumno: {context}\n"
            "Prioriza este contexto al responder.\n\n"
        )
    return _SYSTEM_TEMPLATE.format(context_block=context_block, manuals=_manuals_text(module_id))


@lru_cache
def _client() -> OpenAI:
    return OpenAI(api_key=get_settings().openai_api_key)


def is_enabled() -> bool:
    return get_settings().assistant_enabled


def chat(
    message: str,
    context: str | None,
    history: list[ChatMessage],
    module_id: int | None = None,
) -> tuple[str, str]:
    """Envía la conversación a OpenAI y devuelve (respuesta, modelo)."""
    settings = get_settings()
    system = _build_system(context, module_id or _DEFAULT_MODULE)
    messages: list[dict] = [{"role": "system", "content": system}]
    messages.extend({"role": m.role, "content": m.content} for m in history)
    messages.append({"role": "user", "content": message})

    resp = _client().chat.completions.create(
        model=settings.assistant_model,
        max_tokens=settings.assistant_max_tokens,
        messages=messages,
    )
    reply = resp.choices[0].message.content or ""
    return reply, settings.assistant_model
