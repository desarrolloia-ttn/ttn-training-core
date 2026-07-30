"""CRUD del catálogo de módulos (tabla catalog_module)."""
from datetime import datetime, timezone

from .db import get_conn


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def list_modules(client_id: int | None = None) -> list[dict]:
    with get_conn() as conn:
        if client_id is not None:
            rows = conn.execute(
                "SELECT * FROM catalog_module WHERE client_id=? ORDER BY sort_order, id", (client_id,)
            ).fetchall()
        else:
            rows = conn.execute("SELECT * FROM catalog_module ORDER BY sort_order, id").fetchall()
    return [dict(r) for r in rows]


def get_module(module_id: int) -> dict | None:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM catalog_module WHERE id=?", (module_id,)).fetchone()
    return dict(row) if row else None


def create_module(*, client_id: int, title: str, description: str, code: str | None) -> dict:
    with get_conn() as conn:
        row = conn.execute("SELECT COALESCE(MAX(id), 0) AS m FROM catalog_module").fetchone()
        new_id = row["m"] + 1
        srow = conn.execute(
            "SELECT COALESCE(MAX(sort_order), 0) AS s FROM catalog_module WHERE client_id=?", (client_id,)
        ).fetchone()
        new_order = srow["s"] + 1
        conn.execute(
            "INSERT INTO catalog_module (id, code, title, description, lesson_count, sort_order, client_id, created_at) "
            "VALUES (?, ?, ?, ?, 0, ?, ?, ?)",
            (new_id, code or f"MÓDULO {new_id}", title, description, new_order, client_id, _now()),
        )
    return get_module(new_id)


def update_module(module_id: int, *, title: str | None, description: str | None, code: str | None) -> dict | None:
    cur = get_module(module_id)
    if not cur:
        return None
    with get_conn() as conn:
        conn.execute(
            "UPDATE catalog_module SET title=?, description=?, code=? WHERE id=?",
            (
                title if title is not None else cur["title"],
                description if description is not None else cur["description"],
                code if code is not None else cur["code"],
                module_id,
            ),
        )
    return get_module(module_id)


def set_cover(module_id: int, cover_path: str) -> dict | None:
    with get_conn() as conn:
        cur = conn.execute(
            "UPDATE catalog_module SET cover_path=? WHERE id=?", (cover_path, module_id)
        )
        if cur.rowcount == 0:
            return None
    return get_module(module_id)


def delete_module(module_id: int) -> bool:
    with get_conn() as conn:
        cur = conn.execute("DELETE FROM catalog_module WHERE id=?", (module_id,))
    return cur.rowcount > 0
