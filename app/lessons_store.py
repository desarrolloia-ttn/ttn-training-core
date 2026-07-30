import json
from datetime import datetime, timezone

from .db import get_conn


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _row_to_dict(row) -> dict:
    return dict(row) if row is not None else None


# --------- Insumos ---------
def create_asset(
    asset_id: str,
    kind: str,
    filename: str,
    stored_path: str,
    mime: str | None,
    size_bytes: int,
    status: str = "uploaded",
) -> dict:
    created_at = _now()
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO source_asset
               (id, kind, filename, stored_path, mime, size_bytes, status, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (asset_id, kind, filename, stored_path, mime, size_bytes, status, created_at),
        )
    return get_asset(asset_id)


def update_asset_processing(
    asset_id: str, *, status: str, extracted_text: str = "", error: str | None = None
) -> dict:
    with get_conn() as conn:
        conn.execute(
            "UPDATE source_asset SET status=?, extracted_text=?, error=? WHERE id=?",
            (status, extracted_text, error, asset_id),
        )
    return get_asset(asset_id)


def get_asset(asset_id: str) -> dict | None:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM source_asset WHERE id=?", (asset_id,)).fetchone()
    return _row_to_dict(row)


def list_assets() -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM source_asset ORDER BY created_at DESC"
        ).fetchall()
    return [dict(r) for r in rows]


def delete_asset(asset_id: str) -> bool:
    with get_conn() as conn:
        cur = conn.execute("DELETE FROM source_asset WHERE id=?", (asset_id,))
    return cur.rowcount > 0


# --------- Lecciones / módulos generados ---------
def create_generated_module(
    module_uid: str,
    *,
    product: str,
    module_id: int | None,
    client_id: int | None,
    code: str,
    title: str,
    description: str,
    version: str,
    content_json: str,
    review_notes: str | None,
    source_ids: list[str],
    created_by: str | None,
) -> dict:
    now = _now()
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO generated_module
               (id, product, module_id, client_id, code, title, description, status, version,
                content_json, review_notes, source_ids, created_by, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, 'draft', ?, ?, ?, ?, ?, ?, ?)""",
            (
                module_uid, product, module_id, client_id, code, title, description, version,
                content_json, review_notes, json.dumps(source_ids),
                created_by, now, now,
            ),
        )
    return get_generated_module(module_uid)


def get_generated_module(module_uid: str) -> dict | None:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM generated_module WHERE id=?", (module_uid,)
        ).fetchone()
    return _row_to_dict(row)


def list_generated_modules() -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM generated_module ORDER BY updated_at DESC"
        ).fetchall()
    return [dict(r) for r in rows]


def list_published() -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM generated_module WHERE status='published' ORDER BY updated_at DESC"
        ).fetchall()
    return [dict(r) for r in rows]


def get_published_by_module(module_id: int) -> dict | None:
    """Módulo publicado más reciente para un moduleId del catálogo."""
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM generated_module WHERE status='published' AND module_id=? "
            "ORDER BY updated_at DESC LIMIT 1",
            (module_id,),
        ).fetchone()
    return _row_to_dict(row)


def list_published_versions(module_id: int) -> list[dict]:
    """Todas las versiones publicadas de un módulo (para el selector del alumno)."""
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM generated_module WHERE status='published' AND module_id=? "
            "ORDER BY updated_at DESC",
            (module_id,),
        ).fetchall()
    return [dict(r) for r in rows]


def get_published(module_uid: str) -> dict | None:
    """Un módulo por id, solo si está publicado."""
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM generated_module WHERE id=? AND status='published'",
            (module_uid,),
        ).fetchone()
    return _row_to_dict(row)


def update_content(
    module_uid: str, content_json: str, *, title: str, description: str, version: str | None = None
) -> dict | None:
    with get_conn() as conn:
        if version is None:
            cur = conn.execute(
                "UPDATE generated_module SET content_json=?, title=?, description=?, updated_at=? WHERE id=?",
                (content_json, title, description, _now(), module_uid),
            )
        else:
            cur = conn.execute(
                "UPDATE generated_module SET content_json=?, title=?, description=?, version=?, updated_at=? WHERE id=?",
                (content_json, title, description, version, _now(), module_uid),
            )
        if cur.rowcount == 0:
            return None
    return get_generated_module(module_uid)


def set_quiz(module_uid: str, quiz_json: str) -> dict | None:
    with get_conn() as conn:
        cur = conn.execute(
            "UPDATE generated_module SET quiz_json=?, updated_at=? WHERE id=?",
            (quiz_json, _now(), module_uid),
        )
        if cur.rowcount == 0:
            return None
    return get_generated_module(module_uid)


def set_certificate(module_uid: str, certificate_path: str) -> dict | None:
    with get_conn() as conn:
        cur = conn.execute(
            "UPDATE generated_module SET certificate_path=?, updated_at=? WHERE id=?",
            (certificate_path, _now(), module_uid),
        )
        if cur.rowcount == 0:
            return None
    return get_generated_module(module_uid)


def clear_certificate(module_uid: str) -> dict | None:
    with get_conn() as conn:
        cur = conn.execute(
            "UPDATE generated_module SET certificate_path=NULL, updated_at=? WHERE id=?",
            (_now(), module_uid),
        )
        if cur.rowcount == 0:
            return None
    return get_generated_module(module_uid)


def set_manual(module_uid: str, manual_json: str) -> dict | None:
    with get_conn() as conn:
        cur = conn.execute(
            "UPDATE generated_module SET manual_json=?, updated_at=? WHERE id=?",
            (manual_json, _now(), module_uid),
        )
        if cur.rowcount == 0:
            return None
    return get_generated_module(module_uid)


def clear_manual(module_uid: str) -> dict | None:
    with get_conn() as conn:
        cur = conn.execute(
            "UPDATE generated_module SET manual_json=NULL, updated_at=? WHERE id=?",
            (_now(), module_uid),
        )
        if cur.rowcount == 0:
            return None
    return get_generated_module(module_uid)


def set_status(module_uid: str, status: str) -> dict | None:
    with get_conn() as conn:
        cur = conn.execute(
            "UPDATE generated_module SET status=?, updated_at=? WHERE id=?",
            (status, _now(), module_uid),
        )
        if cur.rowcount == 0:
            return None
    return get_generated_module(module_uid)


def delete_generated_module(module_uid: str) -> bool:
    with get_conn() as conn:
        cur = conn.execute("DELETE FROM generated_module WHERE id=?", (module_uid,))
    return cur.rowcount > 0
