"""Almacén de usuarios y permisos de módulo en archivo JSON (sin DB)."""
import json
import threading

from .auth import hash_password, verify_password
from .config import DATA_DIR, get_settings

_USERS_FILE = DATA_DIR / "users.json"
_lock = threading.Lock()

# Catálogo de módulos del producto Biowel (para el panel de administración).
MODULES = [
    {"id": 1, "title": "Administración"},
    {"id": 2, "title": "Asistencial"},
    {"id": 3, "title": "Cuentas Médicas"},
    {"id": 4, "title": "Dispensación"},
]


def _seed() -> dict:
    """Usuarios de demostración iniciales. Cambia estas credenciales."""
    admin_pw = get_settings().admin_default_password
    return {
        "users": [
            {"id": "admin", "username": "admin", "name": "Administrador", "role": "admin",
             "password": hash_password(admin_pw), "unlockedModules": [], "progress": {}},
            {"id": "ana", "username": "ana", "name": "Ana Martínez", "role": "usuario",
             "password": hash_password("ana1234"), "unlockedModules": [], "progress": {}},
            {"id": "carlos", "username": "carlos", "name": "Carlos Pérez", "role": "usuario",
             "password": hash_password("carlos1234"), "unlockedModules": [], "progress": {}},
        ]
    }


def _load() -> dict:
    if not _USERS_FILE.exists():
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        data = _seed()
        _USERS_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        return data
    return json.loads(_USERS_FILE.read_text(encoding="utf-8"))


def _save(data: dict) -> None:
    _USERS_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def get_by_username(username: str) -> dict | None:
    return next((u for u in _load()["users"] if u["username"] == username), None)


def get_by_id(user_id: str) -> dict | None:
    return next((u for u in _load()["users"] if u["id"] == user_id), None)


def authenticate(username: str, password: str) -> dict | None:
    user = get_by_username(username)
    if user and verify_password(password, user["password"]):
        return user
    return None


def list_users() -> list[dict]:
    return _load()["users"]


def create_user(
    username: str,
    name: str,
    password: str,
    role: str,
    unlocked: list[int] | None = None,
) -> dict | None:
    """Crea un usuario nuevo. Devuelve el usuario, o None si el username ya existe."""
    uname = username.strip()
    with _lock:
        data = _load()
        if any(u["username"].lower() == uname.lower() for u in data["users"]):
            return None
        user = {
            "id": uname,
            "username": uname,
            "name": name.strip() or uname,
            "role": role,
            "password": hash_password(password),
            "unlockedModules": sorted(set(unlocked or [])),
        }
        data["users"].append(user)
        _save(data)
        return user


def count_admins() -> int:
    return sum(1 for u in _load()["users"] if u["role"] == "admin")


def update_user(
    user_id: str,
    name: str | None = None,
    role: str | None = None,
    password: str | None = None,
) -> dict | None:
    with _lock:
        data = _load()
        for user in data["users"]:
            if user["id"] == user_id:
                if name is not None and name.strip():
                    user["name"] = name.strip()
                if role is not None:
                    user["role"] = role
                if password:
                    user["password"] = hash_password(password)
                _save(data)
                return user
        return None


def delete_user(user_id: str) -> bool:
    with _lock:
        data = _load()
        remaining = [u for u in data["users"] if u["id"] != user_id]
        if len(remaining) == len(data["users"]):
            return False
        data["users"] = remaining
        _save(data)
        return True


def set_progress(user_id: str, module_id: int, completed: list[str]) -> dict | None:
    """Guarda las lecciones completadas de un módulo para un usuario."""
    with _lock:
        data = _load()
        for user in data["users"]:
            if user["id"] == user_id:
                progress = user.setdefault("progress", {})
                progress[str(module_id)] = list(dict.fromkeys(completed))  # sin duplicados, orden estable
                _save(data)
                return user
        return None


def set_module_access(user_id: str, module_id: int, unlocked: bool) -> dict | None:
    """Desbloquea (o bloquea) un módulo para un usuario. Devuelve el usuario o None."""
    with _lock:
        data = _load()
        for user in data["users"]:
            if user["id"] == user_id:
                mods = set(user.get("unlockedModules", []))
                mods.add(module_id) if unlocked else mods.discard(module_id)
                user["unlockedModules"] = sorted(mods)
                _save(data)
                return user
        return None
