"""Catálogo de módulos servido al front (fuente única de verdad).

La metadata base de cada módulo vive aquí (no en el SPA). Los módulos publicados
desde el panel de administración se superponen (título, descripción y número real
de lecciones). El estado (acceso/progreso) se calcula por usuario.
"""
import json

from . import catalog_store, lessons_store

# La metadata base del catálogo vive en la tabla catalog_module (editable desde el
# panel admin; sembrada al inicio desde content/biowel_catalog.json). Los módulos
# publicados solo aportan que hay contenido y el número de lecciones.


def _cover_url(module_id: int, cover_path: str | None) -> str | None:
    return f"/api/catalog/modules/{module_id}/cover" if cover_path else None


def _status(accessible: bool, lesson_count: int, completed: int) -> str:
    if not accessible:
        return "locked"
    if lesson_count and completed >= lesson_count:
        return "done"
    if completed > 0:
        return "progress"
    return "idle"


def build_catalog(user: dict, client_id: int | None = None) -> list[dict]:
    """Construye el catálogo para un usuario: base + publicados + acceso/progreso.

    Si se pasa `client_id`, solo incluye los módulos de ese cliente.
    """
    is_admin = user.get("role") == "admin"
    unlocked = set(user.get("unlockedModules", []))
    progress = user.get("progress", {})

    modules: dict[int, dict] = {}
    for m in catalog_store.list_modules(client_id):
        modules[m["id"]] = {
            "id": m["id"],
            "code": m["code"],
            "title": m["title"],
            "description": m["description"],
            "lessonCount": m["lesson_count"],
            "cover": _cover_url(m["id"], m.get("cover_path")),
        }

    # Superponer módulos publicados. IMPORTANTE: el título/descripción/código del
    # módulo NO cambian (son los del catálogo base); la versión publicada solo
    # aporta que hay contenido y el número de lecciones de la versión más reciente.
    # `list_published` viene ordenado por updated_at desc → la primera por módulo
    # es la más reciente.
    counted: set[int] = set()
    for row in lessons_store.list_published():
        mid = row.get("module_id")
        if mid is None:
            continue
        base = modules.get(mid)
        if base is None:
            # El módulo publicado no pertenece a este catálogo/cliente → se ignora
            # (evita que el contenido de un cliente aparezca en otro).
            continue
        content = json.loads(row["content_json"])
        lesson_count = sum(len(b.get("lessons", [])) for b in content.get("blocks", []))
        base["published"] = True
        if mid not in counted:
            base["lessonCount"] = lesson_count
            # El certificado vigente es el de la versión publicada más reciente.
            base["hasCertificate"] = bool(row.get("certificate_path"))
            counted.add(mid)

    out: list[dict] = []
    for mid, m in sorted(modules.items()):
        accessible = is_admin or mid in unlocked
        completed = len(progress.get(str(mid), []))
        lesson_count = m.get("lessonCount", 0)
        pct = round(completed / lesson_count * 100) if lesson_count else 0
        out.append(
            {
                "id": mid,
                "code": m.get("code", f"MÓDULO {mid}"),
                "title": m.get("title", f"Módulo {mid}"),
                "description": m.get("description", ""),
                "lessonCount": lesson_count,
                "cover": m.get("cover"),
                "published": bool(m.get("published", False)),
                "hasCertificate": bool(m.get("hasCertificate", False)),
                "accessible": accessible,
                "completed": completed,
                "progress": pct,
                "status": _status(accessible, lesson_count, completed),
            }
        )
    return out
