"""Administración del catálogo de módulos (crear/editar módulos con portada).

CRUD bajo `/api/admin/catalog` (solo admin) + servir la portada en
`/api/catalog/modules/{id}/cover` (público, para las tarjetas del catálogo).
"""
import shutil
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse

from .. import catalog_store, client_store
from ..config import UPLOADS_DIR
from ..deps import current_user, require_admin
from ..schemas import CatalogModuleAdmin, CatalogModuleUpdate, Client, ClientUpdate

admin_router = APIRouter(prefix="/api/admin/catalog", tags=["admin-catalog"])
public_router = APIRouter(prefix="/api/catalog", tags=["catalog"])
clients_admin_router = APIRouter(prefix="/api/admin/clients", tags=["admin-clients"])
clients_router = APIRouter(prefix="/api/clients", tags=["clients"])


def _client_public(row: dict) -> Client:
    mods = catalog_store.list_modules(row["id"])
    return Client(
        id=row["id"],
        product=row["product"],
        name=row["name"],
        description=row.get("description", ""),
        cover=f"/api/clients/{row['id']}/cover" if row.get("cover_path") else None,
        moduleCount=len(mods),
    )


def _admin(row: dict) -> CatalogModuleAdmin:
    return CatalogModuleAdmin(
        id=row["id"],
        code=row["code"],
        title=row["title"],
        description=row["description"],
        hasCover=bool(row.get("cover_path")),
    )


def _save_cover(module_id: int, file: UploadFile) -> str:
    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    ext = Path(file.filename or "").suffix.lower() or ".png"
    dest = UPLOADS_DIR / f"cover_{module_id}{ext}"
    with dest.open("wb") as out:
        shutil.copyfileobj(file.file, out)
    return str(dest)


@admin_router.get("", response_model=list[CatalogModuleAdmin])
def list_catalog(clientId: int | None = None, _: dict = Depends(require_admin)) -> list[CatalogModuleAdmin]:
    return [_admin(r) for r in catalog_store.list_modules(clientId)]


@admin_router.post("", response_model=CatalogModuleAdmin, status_code=201)
def create_catalog(
    clientId: int = Form(...),
    title: str = Form(...),
    description: str = Form(""),
    code: str | None = Form(None),
    image: UploadFile | None = File(None),
    _: dict = Depends(require_admin),
) -> CatalogModuleAdmin:
    if not title.strip():
        raise HTTPException(status_code=422, detail="El título es obligatorio")
    if not client_store.get_client(clientId):
        raise HTTPException(status_code=404, detail="Cliente no encontrado")
    row = catalog_store.create_module(
        client_id=clientId, title=title.strip(), description=description.strip(), code=(code or None)
    )
    if image is not None and image.filename:
        row = catalog_store.set_cover(row["id"], _save_cover(row["id"], image))
    return _admin(row)


@admin_router.patch("/{module_id}", response_model=CatalogModuleAdmin)
def update_catalog(module_id: int, body: CatalogModuleUpdate, _: dict = Depends(require_admin)) -> CatalogModuleAdmin:
    row = catalog_store.update_module(
        module_id, title=body.title, description=body.description, code=body.code
    )
    if not row:
        raise HTTPException(status_code=404, detail="Módulo no encontrado")
    return _admin(row)


@admin_router.post("/{module_id}/cover", response_model=CatalogModuleAdmin)
def set_catalog_cover(module_id: int, image: UploadFile = File(...), _: dict = Depends(require_admin)) -> CatalogModuleAdmin:
    if not catalog_store.get_module(module_id):
        raise HTTPException(status_code=404, detail="Módulo no encontrado")
    row = catalog_store.set_cover(module_id, _save_cover(module_id, image))
    return _admin(row)


@admin_router.delete("/{module_id}", status_code=204)
def delete_catalog(module_id: int, _: dict = Depends(require_admin)) -> None:
    if not catalog_store.delete_module(module_id):
        raise HTTPException(status_code=404, detail="Módulo no encontrado")


@public_router.get("/modules/{module_id}/cover")
def get_cover(module_id: int) -> FileResponse:
    row = catalog_store.get_module(module_id)
    if not row or not row.get("cover_path"):
        raise HTTPException(status_code=404, detail="Sin portada")
    path = Path(row["cover_path"])
    if not path.exists():
        raise HTTPException(status_code=404, detail="Archivo no disponible")
    return FileResponse(path)


# --------- Clientes (facetas del producto) ---------
def _save_client_cover(client_id: int, file: UploadFile) -> str:
    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    ext = Path(file.filename or "").suffix.lower() or ".png"
    dest = UPLOADS_DIR / f"client_cover_{client_id}{ext}"
    with dest.open("wb") as out:
        shutil.copyfileobj(file.file, out)
    return str(dest)


@clients_router.get("", response_model=list[Client])
def list_clients(product: str | None = None, _: dict = Depends(current_user)) -> list[Client]:
    return [_client_public(c) for c in client_store.list_clients(product)]


@clients_router.get("/{client_id}", response_model=Client)
def get_client(client_id: int, _: dict = Depends(current_user)) -> Client:
    row = client_store.get_client(client_id)
    if not row:
        raise HTTPException(status_code=404, detail="Cliente no encontrado")
    return _client_public(row)


@clients_router.get("/{client_id}/cover")
def get_client_cover(client_id: int) -> FileResponse:
    row = client_store.get_client(client_id)
    if not row or not row.get("cover_path"):
        raise HTTPException(status_code=404, detail="Sin portada")
    path = Path(row["cover_path"])
    if not path.exists():
        raise HTTPException(status_code=404, detail="Archivo no disponible")
    return FileResponse(path)


@clients_admin_router.get("", response_model=list[Client])
def admin_list_clients(product: str | None = None, _: dict = Depends(require_admin)) -> list[Client]:
    return [_client_public(c) for c in client_store.list_clients(product)]


@clients_admin_router.post("", response_model=Client, status_code=201)
def create_client(
    product: str = Form("biowel"),
    name: str = Form(...),
    description: str = Form(""),
    image: UploadFile | None = File(None),
    _: dict = Depends(require_admin),
) -> Client:
    if not name.strip():
        raise HTTPException(status_code=422, detail="El nombre es obligatorio")
    row = client_store.create_client(product=product.strip() or "biowel", name=name.strip(), description=description.strip())
    if image is not None and image.filename:
        row = client_store.set_cover(row["id"], _save_client_cover(row["id"], image))
    return _client_public(row)


@clients_admin_router.patch("/{client_id}", response_model=Client)
def update_client(client_id: int, body: ClientUpdate, _: dict = Depends(require_admin)) -> Client:
    row = client_store.update_client(client_id, name=body.name, description=body.description)
    if not row:
        raise HTTPException(status_code=404, detail="Cliente no encontrado")
    return _client_public(row)


@clients_admin_router.post("/{client_id}/cover", response_model=Client)
def set_client_cover(client_id: int, image: UploadFile = File(...), _: dict = Depends(require_admin)) -> Client:
    if not client_store.get_client(client_id):
        raise HTTPException(status_code=404, detail="Cliente no encontrado")
    row = client_store.set_cover(client_id, _save_client_cover(client_id, image))
    return _client_public(row)


@clients_admin_router.delete("/{client_id}/cover", response_model=Client)
def delete_client_cover(client_id: int, _: dict = Depends(require_admin)) -> Client:
    cur = client_store.get_client(client_id)
    if not cur:
        raise HTTPException(status_code=404, detail="Cliente no encontrado")
    if cur.get("cover_path"):
        Path(cur["cover_path"]).unlink(missing_ok=True)
    row = client_store.clear_cover(client_id)
    return _client_public(row)


@clients_admin_router.delete("/{client_id}", status_code=204)
def delete_client(client_id: int, _: dict = Depends(require_admin)) -> None:
    if not client_store.delete_client(client_id):
        raise HTTPException(status_code=404, detail="Cliente no encontrado")
