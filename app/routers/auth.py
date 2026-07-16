"""Endpoints de autenticación."""
from fastapi import APIRouter, Depends, HTTPException

from .. import user_store
from ..auth import create_token
from ..config import get_settings
from ..deps import current_user, to_public
from ..schemas import LoginRequest, LoginResponse, ProgressUpdate, UserPublic

router = APIRouter(prefix="/api/auth", tags=["auth"])

@router.post("/login", response_model=LoginResponse)
def login(req: LoginRequest) -> LoginResponse:
    user = user_store.authenticate(req.username, req.password)
    if not user:
        raise HTTPException(status_code=401, detail="Usuario o contraseña incorrectos")
    settings = get_settings()
    token = create_token(user["username"], settings.auth_secret, settings.auth_token_ttl_hours)
    return LoginResponse(token=token, user=to_public(user))


@router.get("/me", response_model=UserPublic)
def me(user: dict = Depends(current_user)) -> UserPublic:
    return to_public(user)


@router.put("/me/progress", response_model=UserPublic)
def save_progress(body: ProgressUpdate, user: dict = Depends(current_user)) -> UserPublic:
    updated = user_store.set_progress(user["id"], body.moduleId, body.completed)
    return to_public(updated or user)
