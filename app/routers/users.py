"""Endpoints de administración de usuarios (solo admin)."""
from fastapi import APIRouter, Depends, HTTPException

from .. import user_store
from ..deps import require_admin, to_public
from ..schemas import ModuleAccessUpdate, UserCreate, UserPublic, UserUpdate

router = APIRouter(prefix="/api/users", tags=["users"])


@router.get("", response_model=list[UserPublic])
def list_users(_: dict = Depends(require_admin)) -> list[UserPublic]:
    return [to_public(u) for u in user_store.list_users()]


@router.post("", response_model=UserPublic, status_code=201)
def create_user(body: UserCreate, _: dict = Depends(require_admin)) -> UserPublic:
    if not body.username.strip() or not body.password:
        raise HTTPException(status_code=422, detail="Usuario y contraseña son obligatorios")
    if len(body.password) < 4:
        raise HTTPException(status_code=422, detail="La contraseña debe tener al menos 4 caracteres")
    user = user_store.create_user(
        body.username, body.name, body.password, body.role, body.unlockedModules
    )
    if not user:
        raise HTTPException(status_code=409, detail="Ya existe un usuario con ese nombre de usuario")
    return to_public(user)


@router.patch("/{user_id}/modules", response_model=UserPublic)
def set_module_access(
    user_id: str,
    body: ModuleAccessUpdate,
    _: dict = Depends(require_admin),
) -> UserPublic:
    user = user_store.set_module_access(user_id, body.moduleId, body.unlocked)
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    return to_public(user)


@router.patch("/{user_id}", response_model=UserPublic)
def update_user(user_id: str, body: UserUpdate, _: dict = Depends(require_admin)) -> UserPublic:
    target = user_store.get_by_id(user_id)
    if not target:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    # No dejar la plataforma sin administradores.
    if target["role"] == "admin" and body.role == "usuario" and user_store.count_admins() <= 1:
        raise HTTPException(status_code=400, detail="No puedes quitar el rol al último administrador")
    if body.password is not None and len(body.password) < 4:
        raise HTTPException(status_code=422, detail="La contraseña debe tener al menos 4 caracteres")
    updated = user_store.update_user(user_id, body.name, body.role, body.password)
    if not updated:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    return to_public(updated)


@router.delete("/{user_id}", status_code=204)
def delete_user(user_id: str, admin: dict = Depends(require_admin)) -> None:
    if user_id == admin["id"]:
        raise HTTPException(status_code=400, detail="No puedes eliminar tu propia cuenta")
    target = user_store.get_by_id(user_id)
    if not target:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    if target["role"] == "admin" and user_store.count_admins() <= 1:
        raise HTTPException(status_code=400, detail="No puedes eliminar al último administrador")
    user_store.delete_user(user_id)
