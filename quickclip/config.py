"""Constantes y rutas compartidas por QuickClip."""

from __future__ import annotations

import hashlib
import os
import time
from pathlib import Path

APP_NAME = "QuickClip"
APP_VERSION = "1.0.0"
ORG_NAME = "QuickClip"

VIDEO_EXTENSIONS = (
    ".mp4",
    ".mkv",
    ".mov",
    ".webm",
    ".avi",
    ".m4v",
    ".mpg",
    ".mpeg",
    ".ts",
    ".mts",
    ".m2ts",
    ".flv",
    ".wmv",
    ".3gp",
    ".ogv",
)

OUTPUT_EXTENSIONS = (".mp4", ".mkv", ".mov")

PREVIEW_MAX_WIDTH = 960
PREVIEW_MAX_HEIGHT = 540
FILMSTRIP_HEIGHT = 64
FILMSTRIP_COUNT = 28


def debug_exit_log(message: str) -> None:
    if not os.environ.get("QUICKCLIP_DEBUG_EXIT"):
        return
    try:
        with open("/tmp/quickclip-exit.log", "a", encoding="utf-8") as handle:
            handle.write(f"{time.monotonic():.3f} {message}\n")
    except OSError:
        pass


def cache_root() -> Path:
    base = os.environ.get("XDG_CACHE_HOME") or os.path.expanduser("~/.cache")
    path = Path(base) / "quickclip"
    path.mkdir(parents=True, exist_ok=True)
    return path


def filmstrip_dir(path: str, count: int = FILMSTRIP_COUNT) -> Path:
    """Directorio de caché estable para el filmstrip de un archivo."""
    try:
        stat = os.stat(path)
        key = f"{path}|{stat.st_size}|{stat.st_mtime_ns}|{count}"
    except OSError:
        key = f"{path}|{count}"
    digest = hashlib.sha1(key.encode("utf-8")).hexdigest()[:16]
    folder = cache_root() / "filmstrips" / digest
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def default_video_dirs() -> list[Path]:
    home = Path.home()
    candidates = [
        home / "Videos",
        home / "Captures",
        home / "Vídeos",
        home / "Escritorio",
        home / "Desktop",
        home / "Descargas",
        home / "Downloads",
    ]
    result: list[Path] = []
    seen: set[str] = set()
    for candidate in candidates:
        try:
            if candidate.is_dir():
                resolved = str(candidate)
                if resolved not in seen:
                    seen.add(resolved)
                    result.append(candidate)
        except OSError:
            continue
    if not result:
        result.append(home)
    return result


def is_video_file(path: str | Path) -> bool:
    return Path(path).suffix.lower() in VIDEO_EXTENSIONS


def human_size(num_bytes: float) -> str:
    units = ["B", "KB", "MB", "GB", "TB"]
    value = float(num_bytes)
    for unit in units:
        if value < 1024.0 or unit == units[-1]:
            return f"{value:.1f} {unit}" if unit != "B" else f"{int(value)} B"
        value /= 1024.0
    return f"{value:.1f} TB"
