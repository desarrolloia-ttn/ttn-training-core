"""Base de datos SQLite (stdlib) para insumos y lecciones generadas.

Se usa `sqlite3` de la librería estándar (no hay acceso a PyPI para instalar
un ORM). Se abre una conexión por operación para evitar problemas de hilos con
el threadpool de FastAPI; SQLite en modo WAL soporta bien esta carga.
"""
import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Iterator

from .config import CONTENT_DIR, DATA_DIR, LESSONS_DB

_SCHEMA = """
CREATE TABLE IF NOT EXISTS source_asset (
    id             TEXT PRIMARY KEY,
    kind           TEXT NOT NULL,           -- document | audio | video
    filename       TEXT NOT NULL,
    stored_path    TEXT NOT NULL,
    mime           TEXT,
    size_bytes     INTEGER NOT NULL DEFAULT 0,
    extracted_text TEXT NOT NULL DEFAULT '',
    status         TEXT NOT NULL DEFAULT 'uploaded',
    error          TEXT,
    created_at     TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS generated_module (
    id            TEXT PRIMARY KEY,
    product       TEXT NOT NULL,
    module_id     INTEGER,
    code          TEXT NOT NULL,
    title         TEXT NOT NULL,
    description   TEXT NOT NULL DEFAULT '',
    status        TEXT NOT NULL DEFAULT 'draft',   -- draft | published
    version       TEXT NOT NULL DEFAULT '1.0',     -- etiqueta de versión (p. ej. 1.1)
    content_json  TEXT NOT NULL,                   -- Module completo (blocks/lessons)
    review_notes  TEXT,
    source_ids    TEXT NOT NULL DEFAULT '[]',      -- JSON: ids de insumos usados
    certificate_path TEXT,                          -- documento de certificado subido por el admin
    manual_json   TEXT,                             -- manual de usuario estructurado (JSON) → PDF
    created_by    TEXT,
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS catalog_module (
    id           INTEGER PRIMARY KEY,
    code         TEXT NOT NULL,
    title        TEXT NOT NULL,
    description  TEXT NOT NULL DEFAULT '',
    lesson_count INTEGER NOT NULL DEFAULT 0,
    sort_order   INTEGER NOT NULL DEFAULT 0,
    cover_path   TEXT,
    created_at   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS client (
    id           INTEGER PRIMARY KEY,
    product      TEXT NOT NULL,          -- slug del producto: biowel | activos-fijos
    name         TEXT NOT NULL,          -- p. ej. "Biowel Colombia"
    description  TEXT NOT NULL DEFAULT '',
    sort_order   INTEGER NOT NULL DEFAULT 0,
    cover_path   TEXT,
    created_at   TEXT NOT NULL
);
"""


def init_db() -> None:
    """Crea el directorio de datos y las tablas si no existen, migra y siembra."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with _connect() as conn:
        conn.executescript(_SCHEMA)
        _migrate(conn)
        _seed_catalog(conn)
        _seed_clients(conn)


def _migrate(conn: sqlite3.Connection) -> None:
    """Migraciones idempotentes para bases de datos ya existentes."""
    gcols = {row["name"] for row in conn.execute("PRAGMA table_info(generated_module)")}
    if "version" not in gcols:
        conn.execute("ALTER TABLE generated_module ADD COLUMN version TEXT NOT NULL DEFAULT '1.0'")
    if "quiz_json" not in gcols:
        conn.execute("ALTER TABLE generated_module ADD COLUMN quiz_json TEXT")
    if "client_id" not in gcols:
        conn.execute("ALTER TABLE generated_module ADD COLUMN client_id INTEGER")
    if "certificate_path" not in gcols:
        conn.execute("ALTER TABLE generated_module ADD COLUMN certificate_path TEXT")
    if "manual_json" not in gcols:
        conn.execute("ALTER TABLE generated_module ADD COLUMN manual_json TEXT")
    ccols = {row["name"] for row in conn.execute("PRAGMA table_info(catalog_module)")}
    if "client_id" not in ccols:
        conn.execute("ALTER TABLE catalog_module ADD COLUMN client_id INTEGER")


def _seed_clients(conn: sqlite3.Connection) -> None:
    """Crea el cliente inicial 'Biowel Colombia' y le asigna el contenido existente."""
    count = conn.execute("SELECT COUNT(*) AS n FROM client").fetchone()["n"]
    if count:
        return
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    cur = conn.execute(
        "INSERT INTO client (product, name, description, sort_order, created_at) VALUES (?, ?, ?, ?, ?)",
        ("biowel", "Biowel Colombia", "Implementación de Biowel para Colombia.", 1, now),
    )
    client_id = cur.lastrowid
    # Todo el contenido existente (todo era biowel) pasa a este cliente.
    conn.execute("UPDATE catalog_module SET client_id=? WHERE client_id IS NULL", (client_id,))
    conn.execute("UPDATE generated_module SET client_id=? WHERE client_id IS NULL", (client_id,))


def _seed_catalog(conn: sqlite3.Connection) -> None:
    """Siembra el catálogo desde content/biowel_catalog.json si la tabla está vacía."""
    count = conn.execute("SELECT COUNT(*) AS n FROM catalog_module").fetchone()["n"]
    if count:
        return
    path = CONTENT_DIR / "biowel_catalog.json"
    if not path.exists():
        return
    with open(path, encoding="utf-8") as f:
        modules = json.load(f).get("modules", [])
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    for m in modules:
        conn.execute(
            "INSERT INTO catalog_module (id, code, title, description, lesson_count, sort_order, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (m["id"], m.get("code", f"MÓDULO {m['id']}"), m["title"], m.get("description", ""),
             m.get("lessonCount", 0), m["id"], now),
        )


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(LESSONS_DB, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA foreign_keys=ON;")
    return conn


@contextmanager
def get_conn() -> Iterator[sqlite3.Connection]:
    """Conexión con commit/rollback automático y cierre garantizado."""
    conn = _connect()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
