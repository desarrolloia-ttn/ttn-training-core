"""Hash de contraseñas (PBKDF2) y tokens de sesión firmados (HMAC).

Sin dependencias externas: usa solo la librería estándar.
Las contraseñas se guardan SIEMPRE hasheadas, nunca en texto plano.
"""
import base64
import hashlib
import hmac
import json
import secrets
import time

_PBKDF2_ROUNDS = 200_000


def hash_password(password: str, salt: str | None = None) -> str:
    """Devuelve una cadena 'pbkdf2$sha256$rounds$salt$hash'."""
    if salt is None:
        salt = secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), _PBKDF2_ROUNDS)
    return f"pbkdf2$sha256${_PBKDF2_ROUNDS}${salt}${dk.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        _algo, digest, rounds, salt, hexhash = stored.split("$")
        dk = hashlib.pbkdf2_hmac(digest, password.encode(), bytes.fromhex(salt), int(rounds))
        return hmac.compare_digest(dk.hex(), hexhash)
    except (ValueError, AttributeError):
        return False


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _b64d(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def create_token(username: str, secret: str, ttl_hours: int) -> str:
    payload = {"sub": username, "exp": int(time.time()) + ttl_hours * 3600}
    body = _b64(json.dumps(payload, separators=(",", ":")).encode())
    sig = _b64(hmac.new(secret.encode(), body.encode(), hashlib.sha256).digest())
    return f"{body}.{sig}"


def verify_token(token: str, secret: str) -> str | None:
    """Devuelve el username si el token es válido y no expiró; si no, None."""
    try:
        body, sig = token.split(".")
        expected = _b64(hmac.new(secret.encode(), body.encode(), hashlib.sha256).digest())
        if not hmac.compare_digest(sig, expected):
            return None
        payload = json.loads(_b64d(body))
        if int(payload.get("exp", 0)) < int(time.time()):
            return None
        return payload.get("sub")
    except (ValueError, AttributeError, json.JSONDecodeError):
        return None
