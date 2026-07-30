"""Ingesta de insumos: extrae texto de documentos y transcribe voz/video.

- Documentos PDF -> `pdftotext` (CLI, disponible en el entorno).
- Documentos de texto plano (.txt/.md) -> lectura directa.
- Voz (audio) -> OpenAI Audio Transcriptions (Whisper).
- Video -> se extrae la pista de audio con `ffmpeg` y luego se transcribe.
"""
import re
import shutil
import subprocess
from functools import lru_cache
from pathlib import Path

from openai import OpenAI

from .config import get_settings

# Límite de la API de transcripción de OpenAI (25 MB por archivo).
_TRANSCRIBE_MAX_BYTES = 25 * 1024 * 1024

# Rutas absolutas donde suelen vivir los binarios en Windows, por si el proceso
# del backend se lanzó sin el PATH que los expone (p. ej. sin Git mingw64).
_PDFTOTEXT_CANDIDATES = [
    r"C:\Program Files\Git\mingw64\bin\pdftotext.exe",
    r"C:\Program Files\Git\usr\bin\pdftotext.exe",
    r"C:\ProgramData\chocolatey\bin\pdftotext.exe",
]
_FFMPEG_CANDIDATES = [
    r"C:\ProgramData\chocolatey\bin\ffmpeg.exe",
    r"C:\Program Files\Git\mingw64\bin\ffmpeg.exe",
]


@lru_cache
def _resolve_exe(name: str, configured: str, candidates: tuple[str, ...]) -> str:
    """Resuelve un ejecutable: ruta configurada -> PATH -> rutas conocidas."""
    if configured:
        return configured
    found = shutil.which(name)
    if found:
        return found
    for cand in candidates:
        if Path(cand).exists():
            return cand
    raise RuntimeError(
        f"No se encontró el ejecutable '{name}'. Instálalo o define su ruta en el .env "
        f"(por ejemplo {name.upper()}_PATH=C:\\ruta\\a\\{name}.exe)."
    )


def _pdftotext_exe() -> str:
    return _resolve_exe("pdftotext", get_settings().pdftotext_path, tuple(_PDFTOTEXT_CANDIDATES))


def _ffmpeg_exe() -> str:
    return _resolve_exe("ffmpeg", get_settings().ffmpeg_path, tuple(_FFMPEG_CANDIDATES))


@lru_cache
def _client() -> OpenAI:
    return OpenAI(api_key=get_settings().openai_api_key)


def kind_for(filename: str, mime: str | None) -> str:
    """Determina el rol del insumo por su tipo: document | audio | video."""
    ext = Path(filename).suffix.lower()
    mime = (mime or "").lower()
    if mime.startswith("video/") or ext in {".mp4", ".mov", ".mkv", ".avi", ".webm", ".m4v"}:
        return "video"
    if mime.startswith("audio/") or ext in {".mp3", ".wav", ".m4a", ".ogg", ".flac", ".aac"}:
        return "audio"
    return "document"


# --------- Documentos ---------
def extract_document_text(path: Path) -> str:
    ext = path.suffix.lower()
    if ext in {".txt", ".md"}:
        return path.read_text(encoding="utf-8", errors="replace").strip()
    if ext == ".pdf":
        return _pdf_to_text(path)
    raise ValueError(
        f"Formato de documento no soportado: {ext or '(sin extensión)'}. "
        "Usa PDF o texto plano (.txt/.md)."
    )


def _pdf_to_text(path: Path) -> str:
    # `pdftotext -enc UTF-8 -nopgbrk <in> -` escribe el texto por stdout.
    proc = subprocess.run(
        [_pdftotext_exe(), "-enc", "UTF-8", "-nopgbrk", str(path), "-"],
        capture_output=True,
        timeout=120,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            "No se pudo extraer texto del PDF: "
            + (proc.stderr.decode("utf-8", "replace")[:300] or "error desconocido")
        )
    return proc.stdout.decode("utf-8", "replace").strip()


# --------- Audio / video ---------
def transcribe_media(path: Path, kind: str) -> str:
    """Transcribe voz o la pista de audio de un video. Devuelve el texto."""
    audio_path = path
    tmp_audio: Path | None = None
    if kind == "video":
        tmp_audio = _extract_audio(path)
        audio_path = tmp_audio

    try:
        size = audio_path.stat().st_size
        if size > _TRANSCRIBE_MAX_BYTES:
            raise ValueError(
                "El audio a transcribir supera el límite de 25 MB de la API "
                f"({size // (1024 * 1024)} MB). Recorta el material o súbelo por partes."
            )
        with audio_path.open("rb") as fh:
            result = _client().audio.transcriptions.create(
                model=get_settings().transcription_model,
                file=fh,
            )
        return (getattr(result, "text", "") or "").strip()
    finally:
        if tmp_audio and tmp_audio.exists():
            tmp_audio.unlink(missing_ok=True)


def _extract_audio(video_path: Path) -> Path:
    """Extrae audio mono 16 kHz en mp3 (ligero) desde el video con ffmpeg."""
    out = video_path.with_suffix(".extracted.mp3")
    proc = subprocess.run(
        [
            _ffmpeg_exe(), "-y", "-i", str(video_path),
            "-vn", "-ac", "1", "-ar", "16000", "-b:a", "48k",
            str(out),
        ],
        capture_output=True,
        timeout=600,
    )
    if proc.returncode != 0 or not out.exists():
        raise RuntimeError(
            "ffmpeg no pudo extraer el audio del video: "
            + (proc.stderr.decode("utf-8", "replace")[-300:] or "error desconocido")
        )
    return out


def process_asset(path: Path, kind: str) -> str:
    """Devuelve el texto extraído/transcrito según el tipo de insumo."""
    if kind == "document":
        return extract_document_text(path)
    return transcribe_media(path, kind)


def media_duration_seconds(path: Path) -> float | None:
    """Duración (segundos) de un video/audio usando ffmpeg; None si no se pudo."""
    try:
        proc = subprocess.run([_ffmpeg_exe(), "-i", str(path)], capture_output=True, timeout=60)
    except Exception:
        return None
    err = proc.stderr.decode("utf-8", "replace")
    m = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", err)
    if not m:
        return None
    return int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))


def format_duration(seconds: float) -> str:
    """Formatea segundos: '2:10' (m:ss) o '1h 05min' si supera la hora."""
    total = int(round(seconds))
    if total >= 3600:
        return f"{total // 3600}h {(total % 3600) // 60:02d}min"
    return f"{total // 60}:{total % 60:02d}"
