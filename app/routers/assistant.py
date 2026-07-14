"""Endpoints del asistente de capacitación (OpenAI)."""
from fastapi import APIRouter, HTTPException

from .. import assistant
from ..schemas import ChatRequest, ChatResponse, Suggestion

router = APIRouter(prefix="/api/assistant", tags=["assistant"])


@router.get("/suggestions", response_model=list[Suggestion])
def suggestions() -> list[Suggestion]:
    """Sugerencias de preguntas para arrancar la conversación."""
    return assistant.SUGGESTIONS


@router.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest) -> ChatResponse:
    """Responde una pregunta del alumno usando el manual como fuente."""
    if not assistant.is_enabled():
        raise HTTPException(
            status_code=503,
            detail="El asistente no está configurado. Falta OPENAI_API_KEY.",
        )
    if not req.message.strip():
        raise HTTPException(status_code=422, detail="El mensaje está vacío.")

    try:
        reply, model = assistant.chat(req.message, req.context, req.history)
    except Exception as exc:  # noqa: BLE001 - se traduce a error HTTP legible
        raise HTTPException(status_code=502, detail=f"Error consultando a OpenAI: {exc}") from exc

    return ChatResponse(reply=reply, model=model)
