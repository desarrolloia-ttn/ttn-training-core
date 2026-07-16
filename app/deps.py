"""Dependencias de FastAPI para autenticación y autorización."""
from fastapi import Depends, Header, HTTPException

from . import user_store
from .auth import verify_token
from .config import get_settings
from .schemas import UserPublic


def to_public(user: dict) -> UserPublic:
    return UserPublic(
        id=user["id"],
        username=user["username"],
        name=user["name"],
        role=user["role"],
        unlockedModules=user.get("unlockedModules", []),
        progress=user.get("progress", {}),
    )


def current_user(authorization: str | None = Header(default=None)) -> dict:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="No autenticado")
    token = authorization.split(" ", 1)[1]
    username = verify_token(token, get_settings().auth_secret)
    if not username:
        raise HTTPException(status_code=401, detail="Sesión inválida o expirada")
    user = user_store.get_by_username(username)
    if not user:
        raise HTTPException(status_code=401, detail="Usuario no encontrado")
    return user


def require_admin(user: dict = Depends(current_user)) -> dict:
    if user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Requiere rol de administrador")
    return user
