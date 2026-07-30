"""Genera la evaluación (preguntas de opción múltiple) de un módulo con IA.

Trabaja sobre un RESUMEN del módulo ya generado (títulos, conceptos, puntos clave,
preguntas de repaso), no sobre el material fuente completo, por lo que es una sola
llamada pequeña que respeta el límite de tokens/min.
"""
from .config import get_settings
from .lesson_generator import _parse_with_backoff
from .schemas import GenQuiz, Module, QuizQuestion

_QUIZ_SYSTEM = """\
Eres un evaluador experto en formación sobre software clínico. A partir del RESUMEN
del módulo, crea preguntas de OPCIÓN MÚLTIPLE que midan COMPRENSIÓN (no memorización
literal). Reglas:
- Español, claras y sin ambigüedad.
- Cada pregunta con EXACTAMENTE 4 opciones plausibles y UNA sola correcta.
- `correctIndex` es el índice (base 0) de la opción correcta.
- Distractores realistas (errores típicos), no absurdos.
- Incluye una `explanation` breve de por qué la respuesta es correcta.
- Básate ÚNICAMENTE en el contenido del módulo; no inventes funciones que no aparezcan.
"""

_MAX_SUMMARY_CHARS = 9000


def _module_summary(module: Module) -> str:
    parts: list[str] = [f"MÓDULO: {module.title}"]
    for b in module.blocks:
        parts.append(f"\n## Bloque: {b.title}")
        for l in b.lessons:
            parts.append(f"\n### {l.title}")
            if l.summary:
                parts.append(l.summary)
            if l.concepts:
                parts.append("Conceptos: " + "; ".join(f"{c.term}: {c.definition}" for c in l.concepts))
            if l.keyPoints:
                parts.append("Claves: " + "; ".join(l.keyPoints))
            if l.reviewQuestions:
                parts.append("Repaso: " + "; ".join(f"{q.question} -> {q.answer}" for q in l.reviewQuestions))
    text = "\n".join(parts)
    return text[:_MAX_SUMMARY_CHARS]


def generate_quiz(module: Module, num_questions: int) -> list[QuizQuestion]:
    summary = _module_summary(module)
    if not summary.strip():
        raise ValueError("El módulo no tiene contenido para generar la evaluación.")
    user = (
        f"Genera {num_questions} preguntas de opción múltiple para evaluar este módulo.\n\n"
        f"RESUMEN DEL MÓDULO:\n{summary}"
    )
    completion = _parse_with_backoff(
        model=get_settings().lesson_model,
        max_tokens=get_settings().lesson_max_tokens,
        messages=[
            {"role": "system", "content": _QUIZ_SYSTEM},
            {"role": "user", "content": user},
        ],
        response_format=GenQuiz,
    )
    gen = completion.choices[0].message.parsed
    if gen is None or not gen.questions:
        raise RuntimeError("El modelo no devolvió preguntas válidas.")
    out: list[QuizQuestion] = []
    for q in gen.questions:
        if len(q.options) >= 2 and 0 <= q.correctIndex < len(q.options):
            out.append(
                QuizQuestion(
                    question=q.question,
                    options=q.options,
                    correctIndex=q.correctIndex,
                    explanation=q.explanation,
                )
            )
    if not out:
        raise RuntimeError("Las preguntas generadas no eran válidas.")
    return out[:num_questions]
