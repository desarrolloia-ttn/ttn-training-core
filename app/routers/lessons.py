"""Panel de administración de lecciones: subir insumos y generar lecciones con IA.

Todos los endpoints exigen rol admin, salvo el streaming de media publicada
(`/api/media/{asset_id}`), que sirve el video/audio de una lección al alumno.
"""
import json
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse

from .. import (
    client_store,
    ingest,
    lesson_generator,
    lessons_store,
    manual_generator,
    quiz_generator,
    user_store,
)
from ..config import UPLOADS_DIR, get_settings
from ..deps import current_user, require_admin
from ..schemas import (
    AssetPublic,
    Block,
    GenerateRequest,
    GenManualDoc,
    GeneratedModulePublic,
    GeneratedModuleSummary,
    Lesson,
    LessonManualDoc,
    LessonUpdate,
    Module,
    ModuleDoc,
    PublishedVersion,
    QuizPublic,
    QuizQuestion,
    QuizQuestionPublic,
    QuizResult,
    QuizResultItem,
    QuizSubmit,
)

router = APIRouter(prefix="/api/admin/lessons", tags=["admin-lessons"])
media_router = APIRouter(prefix="/api/media", tags=["media"])
published_router = APIRouter(prefix="/api/published", tags=["published"])

_TEXT_PREVIEW = 280


# --------- Conversores ---------
def _asset_public(a: dict) -> AssetPublic:
    text = a.get("extracted_text") or ""
    return AssetPublic(
        id=a["id"],
        kind=a["kind"],
        filename=a["filename"],
        mime=a.get("mime"),
        sizeBytes=a.get("size_bytes", 0),
        status=a["status"],
        hasText=bool(text.strip()),
        textPreview=(text[:_TEXT_PREVIEW] + "…") if len(text) > _TEXT_PREVIEW else (text or None),
        error=a.get("error"),
        createdAt=a["created_at"],
    )


def _module_from_row(row: dict) -> Module:
    return Module.model_validate_json(row["content_json"])


def _docs_for_row(row: dict) -> list[ModuleDoc]:
    """Documentos de apoyo del módulo = insumos tipo documento usados para generarlo."""
    ids = json.loads(row.get("source_ids") or "[]")
    docs: list[ModuleDoc] = []
    for aid in ids:
        a = lessons_store.get_asset(aid)
        if not a or a.get("kind") != "document":
            continue
        fn = a["filename"]
        kind = "PDF" if fn.lower().endswith(".pdf") else "DOC"
        docs.append(ModuleDoc(kind=kind, title=fn, sub="Documento de apoyo", assetId=aid))
    return docs


def _gen_public(row: dict) -> GeneratedModulePublic:
    return GeneratedModulePublic(
        id=row["id"],
        product=row["product"],
        moduleId=row["module_id"],
        code=row["code"],
        title=row["title"],
        description=row["description"],
        version=row.get("version", "1.0"),
        status=row["status"],
        content=_module_from_row(row),
        reviewNotes=row.get("review_notes"),
        sourceAssetIds=json.loads(row.get("source_ids") or "[]"),
        hasQuiz=bool(row.get("quiz_json")),
        quizCount=len(json.loads(row.get("quiz_json") or "[]")),
        hasCertificate=bool(row.get("certificate_path")),
        hasManual=bool(row.get("manual_json")),
        createdAt=row["created_at"],
        updatedAt=row["updated_at"],
    )


def _quiz_from_row(row: dict) -> list[QuizQuestion]:
    return [QuizQuestion.model_validate(q) for q in json.loads(row.get("quiz_json") or "[]")]


def _gen_summary(row: dict) -> GeneratedModuleSummary:
    mod = _module_from_row(row)
    client_id = row.get("client_id")
    client = client_store.get_client(client_id) if client_id else None
    return GeneratedModuleSummary(
        id=row["id"],
        product=row["product"],
        moduleId=row["module_id"],
        clientId=client_id,
        clientName=client["name"] if client else None,
        code=row["code"],
        title=row["title"],
        version=row.get("version", "1.0"),
        status=row["status"],
        blockCount=len(mod.blocks),
        lessonCount=sum(len(b.lessons) for b in mod.blocks),
        updatedAt=row["updated_at"],
    )


# --------- Insumos ---------
@router.post("/assets", response_model=AssetPublic, status_code=201)
def upload_asset(file: UploadFile = File(...), _: dict = Depends(require_admin)) -> AssetPublic:
    settings = get_settings()
    if not settings.assistant_enabled:
        raise HTTPException(status_code=503, detail="OpenAI no está configurado (falta OPENAI_API_KEY).")

    filename = file.filename or "insumo"
    kind = ingest.kind_for(filename, file.content_type)
    asset_id = uuid.uuid4().hex
    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    dest = UPLOADS_DIR / f"{asset_id}{Path(filename).suffix.lower()}"

    max_bytes = settings.max_upload_mb * 1024 * 1024
    with dest.open("wb") as out:
        shutil.copyfileobj(file.file, out)
    size = dest.stat().st_size
    if size > max_bytes:
        dest.unlink(missing_ok=True)
        raise HTTPException(status_code=413, detail=f"El archivo supera el límite de {settings.max_upload_mb} MB.")

    lessons_store.create_asset(
        asset_id, kind, filename, str(dest), file.content_type, size, status="processing"
    )

    # Procesar (extraer texto / transcribir). Sincrónico: corre en el threadpool.
    try:
        text = ingest.process_asset(dest, kind)
        asset = lessons_store.update_asset_processing(asset_id, status="ready", extracted_text=text)
    except Exception as exc:  # noqa: BLE001 — se reporta al admin
        asset = lessons_store.update_asset_processing(asset_id, status="error", error=str(exc)[:500])

    return _asset_public(asset)


@router.get("/assets", response_model=list[AssetPublic])
def list_assets(_: dict = Depends(require_admin)) -> list[AssetPublic]:
    return [_asset_public(a) for a in lessons_store.list_assets()]


@router.delete("/assets/{asset_id}", status_code=204)
def delete_asset(asset_id: str, _: dict = Depends(require_admin)) -> None:
    asset = lessons_store.get_asset(asset_id)
    if not asset:
        raise HTTPException(status_code=404, detail="Insumo no encontrado")
    Path(asset["stored_path"]).unlink(missing_ok=True)
    lessons_store.delete_asset(asset_id)


# --------- Generación / CRUD de lecciones ---------
@router.post("/generate", response_model=GeneratedModulePublic, status_code=201)
def generate_lessons(body: GenerateRequest, admin: dict = Depends(require_admin)) -> GeneratedModulePublic:
    if not get_settings().assistant_enabled:
        raise HTTPException(status_code=503, detail="OpenAI no está configurado (falta OPENAI_API_KEY).")
    if not body.assetIds:
        raise HTTPException(status_code=422, detail="Selecciona al menos un insumo.")

    # Separar insumos: videos (curso ordenado, una clase por video) vs documentos.
    video_items: list[tuple[str, str, str]] = []  # (assetId, filename, transcript)
    doc_sources: list[tuple[str, str]] = []
    for aid in body.assetIds:
        asset = lessons_store.get_asset(aid)
        if not asset:
            raise HTTPException(status_code=404, detail=f"Insumo {aid} no encontrado")
        text = asset.get("extracted_text") or ""
        if not text.strip():
            continue
        if asset.get("kind") == "video":
            video_items.append((aid, asset["filename"], text))
        else:
            doc_sources.append((asset["filename"], text))
    if not video_items and not doc_sources:
        raise HTTPException(
            status_code=422,
            detail="Los insumos seleccionados no tienen texto utilizable (¿fallaron al procesarse?).",
        )

    blocks: list[Block] = []
    review: str | None = None
    video_map: dict[str, str] = {}  # lesson.id -> assetId del video

    try:
        # 1) Clases en video: el agente razona el ORDEN lógico y crea una lección por video.
        if video_items:
            vlessons: list[Lesson] = []
            for aid, gl in lesson_generator.build_video_lessons(video_items, body.instructions):
                les = lesson_generator.lesson_from_gen(gl, len(vlessons) + 1)
                video_map[les.id] = aid
                vlessons.append(les)
            if vlessons:
                blocks.append(Block(id="b-videos", title="Clases en video", lessons=vlessons))

        # 2) Lecciones desde documentos (flujo por apartados).
        if doc_sources:
            doc_module, review = lesson_generator.generate(
                doc_sources,
                product=body.product,
                module_id=body.moduleId,
                title_hint=body.title,
                instructions=body.instructions,
                run_review=body.runReview,
            )
            blocks.extend(doc_module.blocks)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"Fallo al generar con OpenAI: {exc}")

    if not any(b.lessons for b in blocks):
        raise HTTPException(status_code=502, detail="No se pudo generar contenido de los insumos.")

    # Re-secuenciar códigos (L01..) y montar los videos con su URL y duración reales.
    seq = 0
    for b in blocks:
        for l in b.lessons:
            seq += 1
            l.code = f"L{seq:02d}"
            aid = video_map.get(l.id)
            if aid:
                l.video = f"/api/media/{aid}"
                a = lessons_store.get_asset(aid)
                if a:
                    secs = ingest.media_duration_seconds(Path(a["stored_path"]))
                    if secs:
                        l.duration = ingest.format_duration(secs)

    module = Module(
        product=body.product,
        moduleId=body.moduleId if body.moduleId is not None else 0,
        code=f"M{body.moduleId}" if body.moduleId is not None else "GEN",
        title=body.title or "Curso de capacitación",
        description=f"Curso generado por IA a partir de {len(body.assetIds)} insumo(s).",
        source="Generado por IA a partir de insumos subidos",
        blocks=blocks,
    )

    row = lessons_store.create_generated_module(
        uuid.uuid4().hex,
        product=body.product,
        module_id=body.moduleId,
        client_id=body.clientId,
        code=module.code,
        title=module.title,
        description=module.description,
        version=body.version or "1.0",
        content_json=module.model_dump_json(),
        review_notes=review,
        source_ids=body.assetIds,
        created_by=admin.get("id"),
    )
    return _gen_public(row)


@router.get("", response_model=list[GeneratedModuleSummary])
def list_lessons(_: dict = Depends(require_admin)) -> list[GeneratedModuleSummary]:
    return [_gen_summary(r) for r in lessons_store.list_generated_modules()]


@router.get("/{module_uid}", response_model=GeneratedModulePublic)
def get_lessons(module_uid: str, _: dict = Depends(require_admin)) -> GeneratedModulePublic:
    row = lessons_store.get_generated_module(module_uid)
    if not row:
        raise HTTPException(status_code=404, detail="Lección no encontrada")
    return _gen_public(row)


@router.put("/{module_uid}", response_model=GeneratedModulePublic)
def update_lessons(module_uid: str, body: LessonUpdate, _: dict = Depends(require_admin)) -> GeneratedModulePublic:
    if not lessons_store.get_generated_module(module_uid):
        raise HTTPException(status_code=404, detail="Lección no encontrada")
    row = lessons_store.update_content(
        module_uid,
        body.content.model_dump_json(),
        title=body.content.title,
        description=body.content.description,
        version=body.version,
    )
    return _gen_public(row)


@router.post("/{module_uid}/quiz", response_model=GeneratedModulePublic)
def generate_quiz(module_uid: str, _: dict = Depends(require_admin)) -> GeneratedModulePublic:
    """Genera (o regenera) la evaluación de opción múltiple de esta versión."""
    if not get_settings().assistant_enabled:
        raise HTTPException(status_code=503, detail="OpenAI no está configurado.")
    row = lessons_store.get_generated_module(module_uid)
    if not row:
        raise HTTPException(status_code=404, detail="Lección no encontrada")
    try:
        questions = quiz_generator.generate_quiz(_module_from_row(row), get_settings().quiz_num_questions)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"Fallo al generar la evaluación: {exc}")
    quiz_json = json.dumps([q.model_dump() for q in questions], ensure_ascii=False)
    return _gen_public(lessons_store.set_quiz(module_uid, quiz_json))


def _manual_doc_response(row: dict) -> LessonManualDoc:
    doc = GenManualDoc.model_validate_json(row["manual_json"])
    return LessonManualDoc(
        moduleId=row.get("module_id"),
        code=row.get("code", ""),
        title=row.get("title", ""),
        version=row.get("version", "1.0"),
        date=(row.get("updated_at") or "")[:10],
        doc=doc,
    )


@router.post("/{module_uid}/manual", response_model=GeneratedModulePublic)
def generate_manual(module_uid: str, _: dict = Depends(require_admin)) -> GeneratedModulePublic:
    """Genera (o regenera) el manual de usuario estructurado de esta versión."""
    if not get_settings().assistant_enabled:
        raise HTTPException(status_code=503, detail="OpenAI no está configurado.")
    row = lessons_store.get_generated_module(module_uid)
    if not row:
        raise HTTPException(status_code=404, detail="Lección no encontrada")
    try:
        doc = manual_generator.generate_manual(_module_from_row(row))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"Fallo al generar el manual: {exc}")
    return _gen_public(lessons_store.set_manual(module_uid, doc.model_dump_json()))


@router.get("/{module_uid}/manual", response_model=LessonManualDoc)
def get_lesson_manual(module_uid: str, _: dict = Depends(require_admin)) -> LessonManualDoc:
    """Manual estructurado de esta versión (el front lo renderiza / exporta a PDF)."""
    row = lessons_store.get_generated_module(module_uid)
    if not row:
        raise HTTPException(status_code=404, detail="Lección no encontrada")
    if not row.get("manual_json"):
        raise HTTPException(status_code=404, detail="Esta versión no tiene manual generado")
    return _manual_doc_response(row)


@router.delete("/{module_uid}/manual", response_model=GeneratedModulePublic)
def delete_lesson_manual(module_uid: str, _: dict = Depends(require_admin)) -> GeneratedModulePublic:
    if not lessons_store.get_generated_module(module_uid):
        raise HTTPException(status_code=404, detail="Lección no encontrada")
    return _gen_public(lessons_store.clear_manual(module_uid))


def _save_certificate(module_uid: str, file: UploadFile) -> str:
    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    ext = Path(file.filename or "").suffix.lower() or ".pdf"
    dest = UPLOADS_DIR / f"certificate_{module_uid}{ext}"
    with dest.open("wb") as out:
        shutil.copyfileobj(file.file, out)
    return str(dest)


@router.post("/{module_uid}/certificate", response_model=GeneratedModulePublic)
def set_lesson_certificate(
    module_uid: str, file: UploadFile = File(...), _: dict = Depends(require_admin)
) -> GeneratedModulePublic:
    """Sube el documento de certificado (PDF/imagen) de esta versión de lección."""
    row = lessons_store.get_generated_module(module_uid)
    if not row:
        raise HTTPException(status_code=404, detail="Lección no encontrada")
    old = row.get("certificate_path")
    path = _save_certificate(module_uid, file)
    if old and old != path:  # limpia un archivo previo con otra extensión
        Path(old).unlink(missing_ok=True)
    return _gen_public(lessons_store.set_certificate(module_uid, path))


@router.delete("/{module_uid}/certificate", response_model=GeneratedModulePublic)
def delete_lesson_certificate(module_uid: str, _: dict = Depends(require_admin)) -> GeneratedModulePublic:
    row = lessons_store.get_generated_module(module_uid)
    if not row:
        raise HTTPException(status_code=404, detail="Lección no encontrada")
    if row.get("certificate_path"):
        Path(row["certificate_path"]).unlink(missing_ok=True)
    return _gen_public(lessons_store.clear_certificate(module_uid))


@router.post("/{module_uid}/publish", response_model=GeneratedModulePublic)
def publish_lessons(module_uid: str, _: dict = Depends(require_admin)) -> GeneratedModulePublic:
    row = lessons_store.set_status(module_uid, "published")
    if not row:
        raise HTTPException(status_code=404, detail="Lección no encontrada")
    return _gen_public(row)


@router.post("/{module_uid}/unpublish", response_model=GeneratedModulePublic)
def unpublish_lessons(module_uid: str, _: dict = Depends(require_admin)) -> GeneratedModulePublic:
    row = lessons_store.set_status(module_uid, "draft")
    if not row:
        raise HTTPException(status_code=404, detail="Lección no encontrada")
    return _gen_public(row)


@router.delete("/{module_uid}", status_code=204)
def delete_lessons(module_uid: str, _: dict = Depends(require_admin)) -> None:
    if not lessons_store.delete_generated_module(module_uid):
        raise HTTPException(status_code=404, detail="Lección no encontrada")


# --------- Contenido publicado (visible para el alumno) ---------
@published_router.get("/modules/{module_id}/versions", response_model=list[PublishedVersion])
def list_published_versions(module_id: int) -> list[PublishedVersion]:
    """Lista las versiones publicadas de un módulo (para el selector del alumno)."""
    out: list[PublishedVersion] = []
    for row in lessons_store.list_published_versions(module_id):
        mod = _module_from_row(row)
        out.append(
            PublishedVersion(
                id=row["id"],
                version=row.get("version", "1.0"),
                title=row["title"],
                lessonCount=sum(len(b.lessons) for b in mod.blocks),
                updatedAt=row["updated_at"],
            )
        )
    return out


@published_router.get("/lessons/{module_uid}", response_model=Module)
def get_published_lesson(module_uid: str) -> Module:
    """Contenido de una versión publicada concreta, por su id."""
    row = lessons_store.get_published(module_uid)
    if not row:
        raise HTTPException(status_code=404, detail="Versión no encontrada o no publicada")
    mod = _module_from_row(row)
    mod.docs = _docs_for_row(row)
    return mod


@published_router.get("/modules/{module_id}", response_model=Module)
def get_published_module(module_id: int) -> Module:
    """Devuelve el módulo publicado más reciente para un moduleId del catálogo."""
    row = lessons_store.get_published_by_module(module_id)
    if not row:
        raise HTTPException(status_code=404, detail="No hay lección publicada para este módulo")
    mod = _module_from_row(row)
    mod.docs = _docs_for_row(row)
    return mod


@published_router.get("/modules/{module_id}/manual", response_model=LessonManualDoc)
def get_published_manual(module_id: int, user: dict = Depends(current_user)) -> LessonManualDoc:
    """Manual de usuario de la versión publicada más reciente del módulo (alumno)."""
    is_admin = user.get("role") == "admin"
    if not is_admin and module_id not in set(user.get("unlockedModules", [])):
        raise HTTPException(status_code=403, detail="No tienes acceso a este módulo")
    row = lessons_store.get_published_by_module(module_id)
    if not row or not row.get("manual_json"):
        raise HTTPException(status_code=404, detail="Este módulo no tiene manual disponible")
    return _manual_doc_response(row)


@published_router.get("/modules/{module_id}/quiz", response_model=QuizPublic)
def get_published_quiz(module_id: int) -> QuizPublic:
    """Evaluación del módulo (versión publicada más reciente), SIN respuestas."""
    row = lessons_store.get_published_by_module(module_id)
    if not row or not row.get("quiz_json"):
        raise HTTPException(status_code=404, detail="Este módulo no tiene evaluación disponible")
    questions = _quiz_from_row(row)
    return QuizPublic(
        moduleId=module_id,
        passingScore=get_settings().quiz_passing_score,
        questions=[QuizQuestionPublic(question=q.question, options=q.options) for q in questions],
    )


@published_router.get("/modules/{module_id}/certificate")
def get_published_certificate(module_id: int, user: dict = Depends(current_user)) -> FileResponse:
    """Descarga el documento de certificado del módulo. Solo si el usuario lo aprobó."""
    if str(module_id) not in (user.get("certifications") or {}):
        raise HTTPException(status_code=403, detail="Aún no has aprobado la evaluación de este módulo")
    row = lessons_store.get_published_by_module(module_id)
    if not row or not row.get("certificate_path"):
        raise HTTPException(status_code=404, detail="Este módulo no tiene un documento de certificado")
    path = Path(row["certificate_path"])
    if not path.exists():
        raise HTTPException(status_code=404, detail="Archivo no disponible")
    return FileResponse(path, filename=path.name)


@published_router.post("/modules/{module_id}/quiz/submit", response_model=QuizResult)
def submit_published_quiz(module_id: int, body: QuizSubmit, user: dict = Depends(current_user)) -> QuizResult:
    """Califica la evaluación, y si aprueba registra la certificación del usuario."""
    row = lessons_store.get_published_by_module(module_id)
    if not row or not row.get("quiz_json"):
        raise HTTPException(status_code=404, detail="Este módulo no tiene evaluación disponible")
    questions = _quiz_from_row(row)
    total = len(questions)
    answers = body.answers
    results: list[QuizResultItem] = []
    correct = 0
    for i, q in enumerate(questions):
        chosen = answers[i] if i < len(answers) else -1
        is_ok = chosen == q.correctIndex
        if is_ok:
            correct += 1
        results.append(
            QuizResultItem(correctIndex=q.correctIndex, yourIndex=chosen, isCorrect=is_ok, explanation=q.explanation)
        )
    score = round(correct / total * 100) if total else 0
    passing = get_settings().quiz_passing_score
    passed = score >= passing
    if passed:
        user_store.set_certification(
            user["id"], module_id, {"score": score, "passedAt": datetime.now(timezone.utc).isoformat(timespec="seconds")}
        )
    return QuizResult(
        moduleId=module_id,
        total=total,
        correct=correct,
        score=score,
        passingScore=passing,
        passed=passed,
        certified=passed,
        results=results,
    )


# --------- Media (streaming del insumo de video/voz al alumno) ---------
@media_router.get("/{asset_id}")
def get_media(asset_id: str) -> FileResponse:
    asset = lessons_store.get_asset(asset_id)
    if not asset:
        raise HTTPException(status_code=404, detail="Recurso no encontrado")
    path = Path(asset["stored_path"])
    if not path.exists():
        raise HTTPException(status_code=404, detail="Archivo no disponible")
    # Los documentos se descargan con su nombre original; video/voz se reproducen.
    filename = asset["filename"] if asset.get("kind") == "document" else None
    return FileResponse(
        path,
        media_type=asset.get("mime") or "application/octet-stream",
        filename=filename,
    )
