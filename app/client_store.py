"""CRUD de clientes (facetas de un producto, p. ej. Biowel Colombia / Biowel RD)."""
from datetime import datetime, timezone

from .db import get_conn


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def list_clients(product: str | None = None) -> list[dict]:
    with get_conn() as conn:
        if product:
            rows = conn.execute(
                "SELECT * FROM client WHERE product=? ORDER BY sort_order, id", (product,)
            ).fetchall()
        else:
            rows = conn.execute("SELECT * FROM client ORDER BY product, sort_order, id").fetchall()
    return [dict(r) for r in rows]


def get_client(client_id: int) -> dict | None:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM client WHERE id=?", (client_id,)).fetchone()
    return dict(row) if row else None


def create_client(*, product: str, name: str, description: str) -> dict:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT COALESCE(MAX(sort_order), 0) AS s FROM client WHERE product=?", (product,)
        ).fetchone()
        cur = conn.execute(
            "INSERT INTO client (product, name, description, sort_order, created_at) VALUES (?, ?, ?, ?, ?)",
            (product, name, description, row["s"] + 1, _now()),
        )
        new_id = cur.lastrowid
    return get_client(new_id)


def update_client(client_id: int, *, name: str | None, description: str | None) -> dict | None:
    cur = get_client(client_id)
    if not cur:
        return None
    with get_conn() as conn:
        conn.execute(
            "UPDATE client SET name=?, description=? WHERE id=?",
            (
                name if name is not None else cur["name"],
                description if description is not None else cur["description"],
                client_id,
            ),
        )
    return get_client(client_id)


def set_cover(client_id: int, cover_path: str) -> dict | None:
    with get_conn() as conn:
        c = conn.execute("UPDATE client SET cover_path=? WHERE id=?", (cover_path, client_id))
        if c.rowcount == 0:
            return None
    return get_client(client_id)


def clear_cover(client_id: int) -> dict | None:
    """Quita la portada del cliente (cover_path = NULL)."""
    with get_conn() as conn:
        c = conn.execute("UPDATE client SET cover_path=NULL WHERE id=?", (client_id,))
        if c.rowcount == 0:
            return None
    return get_client(client_id)


def delete_client(client_id: int) -> bool:
    with get_conn() as conn:
        cur = conn.execute("DELETE FROM client WHERE id=?", (client_id,))
    return cur.rowcount > 0
