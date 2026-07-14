"""Carga el contenido de los módulos desde archivos JSON (sin base de datos)."""
import json
from functools import lru_cache

from .config import CONTENT_DIR
from .schemas import Module, ModuleSummary

# Mapa de archivos de contenido disponibles.
_CONTENT_FILES = {
    ("biowel", 2): "biowel_asistencial.json",
}


@lru_cache
def _load_all() -> dict[tuple[str, int], Module]:
    modules: dict[tuple[str, int], Module] = {}
    for key, filename in _CONTENT_FILES.items():
        path = CONTENT_DIR / filename
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        modules[key] = Module.model_validate(data)
    return modules


def get_module(product: str, module_id: int) -> Module | None:
    return _load_all().get((product, module_id))


def list_modules(product: str | None = None) -> list[ModuleSummary]:
    out: list[ModuleSummary] = []
    for mod in _load_all().values():
        if product and mod.product != product:
            continue
        lesson_count = sum(len(b.lessons) for b in mod.blocks)
        out.append(
            ModuleSummary(
                product=mod.product,
                moduleId=mod.moduleId,
                code=mod.code,
                title=mod.title,
                description=mod.description,
                blockCount=len(mod.blocks),
                lessonCount=lesson_count,
            )
        )
    return out
