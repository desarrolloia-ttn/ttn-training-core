"""Genera un manual de usuario ESTRUCTURADO a partir del contenido de una versión
de lección ya generada. El resultado (GenManualDoc) se renderiza luego a PDF.

Fase 1 del "Agente de Manuales": trabaja sobre el Module estructurado que ya vive
en la BD (no re-ingesta los insumos crudos). Reutiliza el mecanismo de llamada con
backoff del generador de lecciones para respetar el límite de tokens/min.
"""
from .config import get_settings
from .lesson_generator import _parse_with_backoff
from .schemas import GenManualDoc, Module

_MANUAL_SYSTEM = """\
Eres un redactor técnico senior. Construyes un MANUAL DE USUARIO profesional a partir
EXCLUSIVAMENTE del contenido del módulo entregado. No uses conocimiento externo del
software ni inventes pantallas, campos o pasos que no aparezcan.

Debes devolver el manual en la estructura solicitada (JSON) con estos apartados:
- titulo, subtitulo (breve).
- objetivo, alcance (párrafos claros).
- requisitos (lista).
- procedimiento: una o varias secciones; cada sección con sus pasos. Cada paso:
  titulo, explicacion, resultado (resultado esperado), advertencias (lista; vacía si no hay).
- buenas_practicas, errores_frecuentes, recomendaciones (listas).
- glosario (term/definition), faq (pregunta/respuesta), resumen.

REGLAS DURAS:
- Usa solo información presente en el contenido. No completes con supuestos.
- Si un paso no puede explicarse porque falta información, ponlo con insuficiente=true
  y deja explicacion/resultado vacíos (el manual mostrará "Información insuficiente
  para documentar este paso.").
- Español neutro, claro, en modo imperativo, orientado a un usuario nuevo.
- Convierte el procedimiento paso a paso del material en pasos numerados y accionables.
"""

_MAX_BRIEF_CHARS = 14000


def _module_brief(module: Module) -> str:
    """Dump estructurado de todo el contenido del módulo para el redactor."""
    parts: list[str] = [f"MÓDULO: {module.title}"]
    if module.description:
        parts.append(f"Descripción: {module.description}")
    if module.scope:
        parts.append(f"Alcance declarado: {module.scope}")
    if module.prerequisites:
        parts.append("Prerrequisitos: " + "; ".join(module.prerequisites))

    for b in module.blocks:
        parts.append(f"\n== Bloque: {b.title} ==")
        for l in b.lessons:
            parts.append(f"\n--- Lección {l.code}: {l.title} ({l.duration}) ---")
            if l.summary:
                parts.append(f"Resumen: {l.summary}")
            if l.objectives:
                parts.append("Objetivos: " + "; ".join(l.objectives))
            if l.intro:
                parts.append(f"Introducción: {l.intro}")
            if l.concepts:
                parts.append("Conceptos: " + "; ".join(f"{c.term}: {c.definition}" for c in l.concepts))
            if l.functional:
                f = l.functional
                fx = "; ".join(
                    x for x in [
                        f"Qué: {f.what}" if f.what else "",
                        f"Por qué: {f.why}" if f.why else "",
                        f"Cuándo: {f.when}" if f.when else "",
                        f"Quién: {f.who}" if f.who else "",
                        f"Impacto: {f.impact}" if f.impact else "",
                    ] if x
                )
                if fx:
                    parts.append(f"Explicación funcional: {fx}")
            for s in l.sections:
                parts.append(f"Procedimiento — {s.heading}:")
                for i, step in enumerate(s.steps, 1):
                    parts.append(f"  {i}. {step}")
            if l.recommendations:
                parts.append("Recomendaciones: " + "; ".join(l.recommendations))
            if l.commonErrors:
                parts.append("Errores comunes: " + "; ".join(l.commonErrors))
            if l.errorConsequences:
                parts.append(f"Consecuencias de errores: {l.errorConsequences}")
            if l.caseStudy and (l.caseStudy.scenario or l.caseStudy.task):
                parts.append(f"Caso práctico: {l.caseStudy.scenario} → {l.caseStudy.task}")
            if l.keyPoints:
                parts.append("Puntos clave: " + "; ".join(l.keyPoints))
    text = "\n".join(parts)
    return text[:_MAX_BRIEF_CHARS]


def generate_manual(module: Module) -> GenManualDoc:
    """Devuelve el manual de usuario estructurado del módulo dado."""
    brief = _module_brief(module)
    if not brief.strip():
        raise ValueError("El módulo no tiene contenido para generar el manual.")
    user = (
        "Construye el manual de usuario del siguiente módulo, respetando la estructura y "
        "las reglas.\n\nCONTENIDO DEL MÓDULO:\n" + brief
    )
    completion = _parse_with_backoff(
        model=get_settings().lesson_model,
        max_tokens=get_settings().lesson_max_tokens,
        messages=[
            {"role": "system", "content": _MANUAL_SYSTEM},
            {"role": "user", "content": user},
        ],
        response_format=GenManualDoc,
    )
    doc = completion.choices[0].message.parsed
    if doc is None or not (doc.titulo or "").strip():
        raise RuntimeError("El modelo no devolvió un manual válido.")
    if not doc.titulo.strip():
        doc.titulo = module.title
    return doc
