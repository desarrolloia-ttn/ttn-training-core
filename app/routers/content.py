"""Endpoints de contenido de los módulos de capacitación."""
from fastapi import APIRouter, Depends, HTTPException

from .. import catalog, content_store
from ..deps import current_user
from ..schemas import CatalogModule, Module, ModuleSummary

router = APIRouter(prefix="/api", tags=["content"])


@router.get("/catalog", response_model=list[CatalogModule])
def get_catalog(clientId: int | None = None, user: dict = Depends(current_user)) -> list[CatalogModule]:
    """Catálogo de módulos con estado para el usuario. Filtra por cliente si se indica."""
    return catalog.build_catalog(user, client_id=clientId)


@router.get("/modules", response_model=list[ModuleSummary])
def list_modules(product: str | None = None) -> list[ModuleSummary]:
    """Lista los módulos disponibles (opcionalmente filtrando por producto)."""
    return content_store.list_modules(product)


@router.get("/products/{product}/modules/{module_id}", response_model=Module)
def get_module(product: str, module_id: int) -> Module:
    """Devuelve el detalle completo de un módulo con sus bloques y lecciones."""
    module = content_store.get_module(product, module_id)
    if module is None:
        raise HTTPException(status_code=404, detail="Módulo no encontrado")
    return module
