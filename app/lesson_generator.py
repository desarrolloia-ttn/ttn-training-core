"""Genera lecciones estructuradas a partir de los insumos ya analizados.

El "agente" recibe todo el material fuente (texto de documentos + transcripciones
de voz/video) y redacta un módulo con bloques y lecciones fieles a ese material,
usando *structured outputs* de OpenAI para que la salida valide directamente
contra los modelos del dominio. Un segundo paso opcional revisa la fidelidad.
"""
import re
import threading
import time
from functools import lru_cache

from openai import OpenAI, RateLimitError

from .config import get_settings
from .schemas import Block, GenBlock, GenLesson, GenModule, GenVideoOrder, Lesson, Module, Section

# Tope defensivo de material fuente total (el material se procesa por apartados).
_MAX_SOURCE_CHARS = 400_000

# Detecta encabezados numerados (1., 3.1., 6.10., 8.2.3 ...) al inicio de línea.
_HEADING_RE = re.compile(r"(?m)^[ \t]*(\d{1,2}(?:\.\d{1,2}){0,3})\.?[ \t]+([^\n.]{3,90})[ \t]*$")

_DETAIL_SYSTEM = """\
Eres un Analista Senior de Capacitación y Diseñador Instruccional experto en el
software clínico Biowel PRO y en crear academias virtuales (estilo cursos oficiales
de Microsoft, SAP u Oracle). Desarrollas lecciones para una plataforma e-learning.

Tu misión NO es resumir ni copiar el manual: conviértelo en una EXPERIENCIA DE
APRENDIZAJE donde el estudiante siente que alguien le está enseñando, sin asumir
conocimientos previos. Cada lección aborda UN solo concepto y dura 5-15 min.

Sigue SIEMPRE esta secuencia pedagógica: concepto → lógica → procedimiento →
ejemplo → errores.

REGLA CLAVE — NO SEAS GENÉRICO. Nada de "configurar el sistema" o "completar los    
campos". Nombra el submódulo, apartado, pestaña, botón, campo y opción EXACTOS del
material (entre comillas cuando ayude). Si el material omite contexto, puedes
completarlo con buenas prácticas, pero acláralo como recomendación.

Recibes VARIOS APARTADOS del manual (cada uno con su título y su texto). Genera UNA
lección RICA por CADA apartado listado, SIN omitir ninguno; agrúpalas en uno o más
bloques coherentes. NO resumas: cubre todo el contenido de cada apartado. Rellena en
CADA lección:
- title, duration ("8 min"), summary (1-2 frases: qué logra y cuándo se usa).
- objectives: 2-4 objetivos concretos y verificables.
- intro: introducción sencilla que enganche y explique por qué es importante.
- concepts: conceptos clave (term + definition) a entender ANTES de los pasos.
- functional: explicación funcional — what (qué hace), why (por qué existe),
  when (cuándo se usa), who (quién lo usa), impact (qué impacto tiene).
- sections: PROCEDIMIENTO paso a paso (heading + pasos numerados concretos, con
  campos obligatorios por su nombre, opciones de listas desplegables y el
  estado/resultado esperado, p. ej. queda "Habilitado" o se abre una ventana).
- recommendations: buenas prácticas.
- commonErrors: errores típicos del usuario y cómo evitarlos.
- errorConsequences: qué ocurre si se configura mal.
- caseStudy: escenario real (scenario) + lo que el estudiante debe hacer (task).
- keyPoints: puntos clave para recordar.
- reviewQuestions: 3-6 preguntas de repaso de OPCIÓN MÚLTIPLE para autoevaluación
  (question; options con 3-4 alternativas plausibles; correctIndex = índice base 0 de
  la correcta; explanation = por qué es correcta). Evalúan comprensión, no memorización.

Español, tono didáctico. No incluyas credenciales ni datos personales de pacientes;
usa ejemplos ficticios.
"""

_REVIEW_SYSTEM = """\
Eres un revisor de calidad de contenido de capacitación clínica. Compara el
BORRADOR de lecciones con el MATERIAL FUENTE y responde en español con una lista
breve de observaciones: (1) posibles afirmaciones sin respaldo en la fuente,
(2) pasos o pantallas que convendría verificar, (3) vacíos o temas del material
que no quedaron cubiertos. Si todo es fiel y completo, dilo explícitamente.
Sé conciso (máximo ~10 viñetas).
"""


@lru_cache
def _client() -> OpenAI:
    return OpenAI(api_key=get_settings().openai_api_key)


def _slug(text: str, fallback: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return s[:48] or fallback


def _build_source_block(sources: list[tuple[str, str]]) -> str:
    """sources: lista de (etiqueta, texto). Devuelve el bloque de material fuente."""
    parts: list[str] = []
    for label, text in sources:
        if not text.strip():
            continue
        parts.append(f"=== INSUMO: {label} ===\n{text}\n=== FIN ===")
    joined = "\n\n".join(parts)
    if len(joined) > _MAX_SOURCE_CHARS:
        joined = joined[:_MAX_SOURCE_CHARS] + "\n\n[MATERIAL TRUNCADO POR LONGITUD]"
    return joined


def generate(
    sources: list[tuple[str, str]],
    *,
    product: str,
    module_id: int | None,
    title_hint: str | None,
    instructions: str | None,
    run_review: bool = False,
) -> tuple[Module, str | None]:
    """Devuelve (Module generado, notas del auditor/revisión o None).

    El material se divide en APARTADOS (detección por código) y se genera UNA llamada
    por apartado, enviando solo su texto. Así cada llamada es pequeña (respeta el TPM)
    y hay cobertura 1:1. Un auditor reintenta los apartados que fallen y reporta los
    que queden pendientes (nunca se descartan en silencio).
    """
    source_block = _build_source_block(sources)
    if not source_block.strip():
        raise ValueError("No hay texto en los insumos para generar la lección.")

    units = _units(source_block)
    batches = _batches(units)

    gen_blocks: list[GenBlock] = []
    pending: list[list[tuple[str, str]]] = []
    for batch in batches:
        try:
            gen_blocks.extend(_develop_batch(batch, instructions).blocks)
        except Exception:
            pending.append(batch)

    # Auditor: reintenta una vez los lotes que fallaron.
    missing: list[str] = []
    for batch in pending:
        try:
            gen_blocks.extend(_develop_batch(batch, instructions).blocks)
        except Exception:
            missing.extend(h for h, _ in batch)

    if not gen_blocks:
        raise RuntimeError(
            "No se pudo generar contenido. Suele deberse al límite de tokens/min de "
            "OpenAI (TPM); reintenta con menos insumos o espera un minuto."
        )

    gen = GenModule(
        title=title_hint or "Curso de capacitación",
        description=f"Curso generado por IA a partir de {len(sources)} insumo(s).",
        blocks=gen_blocks,
    )
    module = _to_module(gen, product=product, module_id=module_id, title_hint=title_hint)

    notes: list[str] = []
    total = len(units)
    notes.append(f"✅ Cobertura: {total - len(missing)} de {total} apartados generados.")
    if missing:
        notes.append("⚠️ Apartados pendientes (vuelve a generar para completarlos): " + ", ".join(missing[:25]))
    if run_review:
        try:
            r = _review(source_block, module)
            if r:
                notes.append(r)
        except Exception:
            pass
    return module, "\n\n".join(notes) or None


def _units(source_block: str) -> list[tuple[str, str]]:
    """Divide el material en apartados (heading, texto); trocea los muy grandes."""
    limit = get_settings().lesson_source_chunk_chars
    sections = _split_sections(source_block)
    if not sections:
        # Sin estructura numerada: usa trozos de tamaño fijo como apartados.
        sections = [(f"Parte {i}", c) for i, c in enumerate(_chunk(source_block, limit), start=1)]
    units: list[tuple[str, str]] = []
    for heading, body in sections:
        if len(body) <= limit:
            units.append((heading, body))
        else:
            for j, sub in enumerate(_chunk(body, limit), start=1):
                units.append((f"{heading} (parte {j})", sub))
    return units


def _split_sections(text: str) -> list[tuple[str, str]] | None:
    """Detecta apartados numerados y devuelve (heading, cuerpo). None si no hay estructura."""
    matches = list(_HEADING_RE.finditer(text))
    if len(matches) < 2:
        return None
    out: list[tuple[str, str]] = []
    for i, m in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body = text[m.end():end].strip()
        if len(body) < 150:  # descarta índice/tabla de contenidos y encabezados sin cuerpo
            continue
        heading = f"{m.group(1)}. {m.group(2).strip()}"
        out.append((heading, body))
    return out or None


def _chunk(text: str, max_chars: int) -> list[str]:
    """Trocea texto respetando párrafos, sin exceder max_chars por trozo."""
    if len(text) <= max_chars:
        return [text]
    chunks: list[str] = []
    current = ""
    for para in text.split("\n\n"):
        piece = para + "\n\n"
        if len(current) + len(piece) > max_chars and current:
            chunks.append(current)
            current = ""
        if len(piece) > max_chars:
            for i in range(0, len(piece), max_chars):
                chunks.append(piece[i : i + max_chars])
            continue
        current += piece
    if current.strip():
        chunks.append(current)
    return chunks


# --- Regulador de ritmo (throttle) para respetar el TPM de la organización ---
_tpm_lock = threading.Lock()
_tpm_events: list[tuple[float, int]] = []  # (timestamp, tokens estimados)


def _throttle(est_tokens: int) -> None:
    budget = get_settings().lesson_tpm_budget
    with _tpm_lock:
        now = time.time()
        while _tpm_events and now - _tpm_events[0][0] > 60:
            _tpm_events.pop(0)
        used = sum(t for _, t in _tpm_events)
        if _tpm_events and used + est_tokens > budget:
            sleep_for = 60 - (now - _tpm_events[0][0]) + 0.5
            if sleep_for > 0:
                time.sleep(sleep_for)
            now = time.time()
            while _tpm_events and now - _tpm_events[0][0] > 60:
                _tpm_events.pop(0)
        _tpm_events.append((time.time(), est_tokens))


def _parse_with_backoff(**kwargs):
    """Ejecuta chat.completions.parse con throttle previo y reintentos ante 429 (TPM)."""
    est = sum(len(m.get("content", "")) for m in kwargs.get("messages", [])) // 4 + kwargs.get("max_tokens", 0)
    last: Exception | None = None
    for attempt in range(4):
        _throttle(est)
        try:
            return _client().chat.completions.parse(**kwargs)
        except RateLimitError as exc:
            last = exc
            time.sleep(15 + attempt * 20)  # 15s, 35s, 55s
    if last:
        raise last
    raise RuntimeError("Fallo desconocido al llamar a OpenAI.")


def _batches(units: list[tuple[str, str]]) -> list[list[tuple[str, str]]]:
    """Agrupa apartados en lotes (menos llamadas) sin exceder tamaño ni cantidad."""
    s = get_settings()
    max_chars = s.lesson_source_chunk_chars
    max_count = s.lesson_batch_max_sections
    batches: list[list[tuple[str, str]]] = []
    cur: list[tuple[str, str]] = []
    cur_chars = 0
    for heading, body in units:
        if cur and (cur_chars + len(body) > max_chars or len(cur) >= max_count):
            batches.append(cur)
            cur, cur_chars = [], 0
        cur.append((heading, body))
        cur_chars += len(body)
    if cur:
        batches.append(cur)
    return batches


def _develop_batch(batch: list[tuple[str, str]], instructions: str | None) -> GenModule:
    """Desarrolla las lecciones ricas de un lote de apartados en una sola llamada."""
    headings = ", ".join(h for h, _ in batch)
    listing = "\n\n".join(f"### APARTADO: {h}\n{b}" for h, b in batch)
    parts = [
        f"Genera UNA lección RICA por CADA uno de estos apartados, sin omitir ninguno: {headings}.",
        f"\nAPARTADOS:\n{listing}",
    ]
    if instructions:
        parts.append(f"\nIndicaciones del administrador: {instructions}")
    completion = _parse_with_backoff(
        model=get_settings().lesson_model,
        max_tokens=get_settings().lesson_max_tokens,
        messages=[
            {"role": "system", "content": _DETAIL_SYSTEM},
            {"role": "user", "content": "\n".join(parts)},
        ],
        response_format=GenModule,
    )
    gen = completion.choices[0].message.parsed
    if gen is None or not gen.blocks:
        raise RuntimeError("El lote no produjo lecciones.")
    return gen


# --------- Cursos en video: ordenamiento lógico + una lección por video ---------
_ORDER_SYSTEM = """\
Eres un diseñador instruccional. Recibes VARIOS videos (nombre de archivo + inicio de
su transcripción). Ordénalos en la SECUENCIA PEDAGÓGICA LÓGICA de un curso: primero la
introducción/bienvenida, luego de lo más básico y fundamental a lo más avanzado,
respetando prerrequisitos (no explicar algo que dependa de un video posterior).
Devuelve TODOS los videos (sin omitir ninguno) con su `index` original y un `title`
de clase claro y específico para cada uno, en el orden correcto.
"""


def order_videos(videos: list[tuple[str, str, str]], instructions: str | None) -> list[tuple[int, str]]:
    """videos: [(assetId, filename, transcript)]. Devuelve [(index_original, título)] en orden lógico."""
    if len(videos) <= 1:
        return [(0, videos[0][1])] if videos else []
    listing = "\n\n".join(
        f"[{i}] Archivo: {fn}\nInicio de transcripción: {(txt or '')[:800]}"
        for i, (aid, fn, txt) in enumerate(videos)
    )
    parts = [f"VIDEOS:\n{listing}"]
    if instructions:
        parts.append(f"\nIndicaciones del administrador: {instructions}")
    try:
        completion = _parse_with_backoff(
            model=get_settings().lesson_model,
            max_tokens=get_settings().lesson_max_tokens,
            messages=[
                {"role": "system", "content": _ORDER_SYSTEM},
                {"role": "user", "content": "\n".join(parts)},
            ],
            response_format=GenVideoOrder,
        )
        order = completion.choices[0].message.parsed
    except Exception:
        order = None

    result: list[tuple[int, str]] = []
    seen: set[int] = set()
    if order:
        for it in order.items:
            if 0 <= it.index < len(videos) and it.index not in seen:
                seen.add(it.index)
                result.append((it.index, it.title.strip() or videos[it.index][1]))
    # Asegura que ningún video quede fuera (en su orden original al final).
    for i, (aid, fn, txt) in enumerate(videos):
        if i not in seen:
            result.append((i, fn))
    return result


def build_video_lesson_content(title: str, transcript: str, instructions: str | None) -> GenLesson:
    """Genera UNA lección rica a partir de la transcripción de un video."""
    parts = [
        f"Genera UNA sola lección RICA para el video/clase titulada '{title}', basándote en su "
        "transcripción. Es una clase en video: la guía debe acompañar y complementar lo que se ve.",
        f"\nTRANSCRIPCIÓN DEL VIDEO:\n{transcript[:16000]}",
    ]
    if instructions:
        parts.append(f"\nIndicaciones del administrador: {instructions}")
    completion = _parse_with_backoff(
        model=get_settings().lesson_model,
        max_tokens=get_settings().lesson_max_tokens,
        messages=[
            {"role": "system", "content": _DETAIL_SYSTEM},
            {"role": "user", "content": "\n".join(parts)},
        ],
        response_format=GenLesson,
    )
    gl = completion.choices[0].message.parsed
    if gl is None:
        raise RuntimeError(f"No se pudo generar la lección del video '{title}'.")
    if not gl.title:
        gl.title = title
    return gl


def build_video_lessons(
    videos: list[tuple[str, str, str]], instructions: str | None
) -> list[tuple[str, GenLesson]]:
    """Ordena los videos y genera una lección por cada uno. Devuelve [(assetId, GenLesson)] en orden."""
    ordered = order_videos(videos, instructions)
    out: list[tuple[str, GenLesson]] = []
    for idx, title in ordered:
        aid, fn, transcript = videos[idx]
        try:
            gl = build_video_lesson_content(title, transcript, instructions)
        except Exception:
            continue
        out.append((aid, gl))
    return out


def lesson_from_gen(gl: GenLesson, seq: int) -> Lesson:
    """Convierte una GenLesson en Lesson asignando id/código secuencial."""
    return Lesson(
        id=f"{seq}-{_slug(gl.title, f'leccion-{seq}')}",
        code=f"L{seq:02d}",
        title=gl.title,
        duration=gl.duration or "",
        summary=gl.summary,
        objectives=gl.objectives,
        intro=gl.intro,
        concepts=gl.concepts,
        functional=gl.functional,
        sections=[Section(heading=s.heading, steps=s.steps) for s in gl.sections],
        recommendations=gl.recommendations,
        commonErrors=gl.commonErrors,
        errorConsequences=gl.errorConsequences,
        caseStudy=gl.caseStudy,
        keyPoints=gl.keyPoints,
        reviewQuestions=gl.reviewQuestions,
    )


def _to_module(
    gen: GenModule, *, product: str, module_id: int | None, title_hint: str | None
) -> Module:
    """Convierte la salida del modelo en un Module, asignando ids y códigos."""
    blocks: list[Block] = []
    lesson_counter = 0
    for b_idx, gblock in enumerate(gen.blocks, start=1):
        lessons: list[Lesson] = []
        for gl in gblock.lessons:
            lesson_counter += 1
            lessons.append(
                Lesson(
                    id=f"{b_idx}-{_slug(gl.title, f'leccion-{lesson_counter}')}",
                    code=f"L{lesson_counter:02d}",
                    title=gl.title,
                    duration=gl.duration or "",
                    summary=gl.summary,
                    objectives=gl.objectives,
                    intro=gl.intro,
                    concepts=gl.concepts,
                    functional=gl.functional,
                    sections=[Section(heading=s.heading, steps=s.steps) for s in gl.sections],
                    recommendations=gl.recommendations,
                    commonErrors=gl.commonErrors,
                    errorConsequences=gl.errorConsequences,
                    caseStudy=gl.caseStudy,
                    keyPoints=gl.keyPoints,
                    reviewQuestions=gl.reviewQuestions,
                )
            )
        blocks.append(
            Block(id=f"b{b_idx}-{_slug(gblock.title, f'bloque-{b_idx}')}",
                  title=gblock.title, lessons=lessons)
        )

    code = f"M{module_id}" if module_id is not None else _slug(gen.title, "modulo").upper()[:12]
    return Module(
        product=product,
        moduleId=module_id if module_id is not None else 0,
        code=code,
        title=title_hint or gen.title,
        description=gen.description,
        source="Generado por IA a partir de insumos subidos",
        blocks=blocks,
    )


def _review(source_block: str, module: Module) -> str | None:
    # Recorta las entradas para no exceder el límite de tokens/min (TPM).
    src = source_block[:14000]
    titles = "\n".join(
        f"- {l.title}" for b in module.blocks for l in b.lessons
    )[:6000]
    completion = _client().chat.completions.create(
        model=get_settings().lesson_model,
        max_tokens=600,
        messages=[
            {"role": "system", "content": _REVIEW_SYSTEM},
            {"role": "user", "content": f"MATERIAL FUENTE (parcial):\n{src}\n\nLECCIONES GENERADAS:\n{titles}"},
        ],
    )
    return (completion.choices[0].message.content or "").strip() or None
