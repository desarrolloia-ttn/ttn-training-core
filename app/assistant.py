"""Asistente de capacitación conectado a OpenAI, con el manual como fuente."""
from functools import lru_cache

from openai import OpenAI

from .config import RESOURCES_DIR, get_settings
from .schemas import ChatMessage, Suggestion

_MANUAL_FILE = RESOURCES_DIR / "manual_asistencial.txt"

_SYSTEM_TEMPLATE = """\
Eres el asistente de capacitación de la plataforma de formación de Biowel PRO.
Tu rol es ayudar a que el personal (médicos, enfermería, admisiones, farmacia)
aprenda a usar el MÓDULO ASISTENCIAL del software Biowel.

Reglas:
- Responde SIEMPRE en español, claro y conciso, con un tono didáctico.
- Básate ÚNICAMENTE en el manual que aparece más abajo como fuente de verdad.
- Si la pregunta no está cubierta por el manual, dilo con honestidad y sugiere
  a quién o dónde consultar; no inventes pasos ni nombres de pantallas.
- Cuando expliques un procedimiento, usa pasos numerados y nombra los apartados,
  submódulos y botones tal como aparecen en el manual.
- No solicites ni expongas credenciales, tokens ni datos personales de pacientes.
  Usa ejemplos ficticios si necesitas ilustrar con datos.

{context_block}
=== MANUAL: GUÍA DE USO BIOWEL ASISTENCIAL ===
{manual}
=== FIN DEL MANUAL ===
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
def _load_manual() -> str:
    return _MANUAL_FILE.read_text(encoding="utf-8")


def _build_system(context: str | None) -> str:
    context_block = ""
    if context:
        context_block = (
            f"Contexto de la pantalla actual del alumno: {context}\n"
            "Prioriza este contexto al responder.\n\n"
        )
    return _SYSTEM_TEMPLATE.format(context_block=context_block, manual=_load_manual())


@lru_cache
def _client() -> OpenAI:
    return OpenAI(api_key=get_settings().openai_api_key)


def is_enabled() -> bool:
    return get_settings().assistant_enabled


def chat(message: str, context: str | None, history: list[ChatMessage]) -> tuple[str, str]:
    """Envía la conversación a OpenAI y devuelve (respuesta, modelo)."""
    settings = get_settings()
    # En OpenAI el prompt de sistema es el primer mensaje con role "system".
    messages: list[dict] = [{"role": "system", "content": _build_system(context)}]
    messages.extend({"role": m.role, "content": m.content} for m in history)
    messages.append({"role": "user", "content": message})

    resp = _client().chat.completions.create(
        model=settings.assistant_model,
        max_tokens=settings.assistant_max_tokens,
        messages=messages,
    )
    reply = resp.choices[0].message.content or ""
    return reply, settings.assistant_model
