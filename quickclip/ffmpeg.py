"""Integración con FFmpeg/FFprobe: metadatos, fotogramas y recorte."""

from __future__ import annotations

import json
import shutil
import subprocess
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

from .config import PREVIEW_MAX_HEIGHT, PREVIEW_MAX_WIDTH, VIDEO_EXTENSIONS


class FFmpegError(RuntimeError):
    pass


@dataclass(slots=True)
class MediaInfo:
    path: str
    duration: float
    width: int
    height: int
    fps: float
    has_audio: bool
    video_codec: str = ""
    audio_codec: str = ""
    pix_fmt: str = ""
    bitrate: int = 0
    size: int = 0
    rotation: int = 0

    @property
    def display_width(self) -> int:
        return self.height if self.rotation in (90, 270) else self.width

    @property
    def display_height(self) -> int:
        return self.width if self.rotation in (90, 270) else self.height

    @property
    def aspect(self) -> float:
        return self.display_width / self.display_height if self.display_height else 16 / 9

    @property
    def safe_fps(self) -> float:
        return self.fps if self.fps and 0 < self.fps < 1000 else 30.0


@dataclass(slots=True)
class ExportPlan:
    source: str
    output: str
    start: float
    duration: float
    video_codec: str = ""
    audio_codec: str = ""
    pix_fmt: str = ""
    has_audio: bool = True
    notes: list[str] = field(default_factory=list)


def _which(name: str) -> str | None:
    return shutil.which(name)


def tools_available() -> tuple[bool, list[str]]:
    missing = [name for name in ("ffmpeg", "ffprobe") if not _which(name)]
    return (not missing, missing)


def ffmpeg_path() -> str:
    path = _which("ffmpeg")
    if not path:
        raise FFmpegError("FFmpeg no está instalado. Ejecuta: sudo apt install ffmpeg")
    return path


def ffprobe_path() -> str:
    path = _which("ffprobe")
    if not path:
        raise FFmpegError("FFprobe no está instalado. Ejecuta: sudo apt install ffmpeg")
    return path


def _run_process(
    cmd: list[str],
    *,
    text: bool = False,
    timeout: float = 25.0,
    stop_event: threading.Event | None = None,
    timeout_message: str = "FFmpeg agotó el tiempo de espera",
) -> subprocess.CompletedProcess:
    """Ejecuta un proceso y permite cancelarlo desde otro hilo."""
    process = subprocess.Popen(
        cmd,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=text,
    )
    started = time.monotonic()
    try:
        while True:
            if stop_event is not None and stop_event.is_set():
                process.kill()
                process.communicate()
                raise FFmpegError("Operación cancelada")
            remaining = timeout - (time.monotonic() - started)
            if remaining <= 0:
                process.kill()
                process.communicate()
                raise FFmpegError(timeout_message)
            try:
                stdout, stderr = process.communicate(timeout=min(0.2, remaining))
                break
            except subprocess.TimeoutExpired:
                continue
        return subprocess.CompletedProcess(cmd, process.returncode, stdout, stderr)
    finally:
        if process.poll() is None:
            try:
                process.kill()
                process.communicate(timeout=1.0)
            except (OSError, subprocess.TimeoutExpired):
                pass


def _parse_float(value: object, default: float = 0.0) -> float:
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


def _parse_fps(value: str | None) -> float:
    if not value or value in ("0/0", "N/A"):
        return 0.0
    try:
        if "/" in value:
            num, den = value.split("/", 1)
            denominator = float(den)
            return float(num) / denominator if denominator else 0.0
        return float(value)
    except (TypeError, ValueError, ZeroDivisionError):
        return 0.0


def probe_media(path: str, stop_event: threading.Event | None = None) -> MediaInfo:
    """Lee los metadatos de un video con ffprobe."""
    if not Path(path).is_file():
        raise FFmpegError(f"El archivo no existe: {path}")
    cmd = [
        ffprobe_path(),
        "-v",
        "error",
        "-print_format",
        "json",
        "-show_format",
        "-show_streams",
        path,
    ]
    result = _run_process(
        cmd,
        text=True,
        timeout=30.0,
        stop_event=stop_event,
        timeout_message="FFprobe agotó el tiempo de espera",
    )
    if result.returncode != 0:
        message = (result.stderr or "No se pudo leer el video").strip().splitlines()[-1]
        raise FFmpegError(message)

    try:
        payload = json.loads(result.stdout or "{}")
    except json.JSONDecodeError as exc:
        raise FFmpegError("Respuesta inválida de FFprobe") from exc

    streams = payload.get("streams") or []
    video = next((s for s in streams if s.get("codec_type") == "video"), None)
    audio = next((s for s in streams if s.get("codec_type") == "audio"), None)
    if video is None:
        raise FFmpegError("El archivo no contiene una pista de video")

    duration = _parse_float((payload.get("format") or {}).get("duration"))
    if duration <= 0:
        duration = _parse_float(video.get("duration"))
    if duration <= 0:
        raise FFmpegError("No se pudo determinar la duración del video")

    rotation = 0
    for side in video.get("side_data_list") or []:
        if "rotation" in side:
            rotation = int(_parse_float(side.get("rotation"), 0))
            break
    if not rotation:
        rotation = int(_parse_float((video.get("tags") or {}).get("rotate"), 0))
    rotation %= 360

    fps = _parse_fps(video.get("avg_frame_rate")) or _parse_fps(video.get("r_frame_rate"))

    info = MediaInfo(
        path=str(path),
        duration=duration,
        width=int(video.get("width") or 0),
        height=int(video.get("height") or 0),
        fps=fps,
        has_audio=audio is not None,
        video_codec=str(video.get("codec_name") or ""),
        audio_codec=str(audio.get("codec_name") or "") if audio else "",
        pix_fmt=str(video.get("pix_fmt") or ""),
        bitrate=int(_parse_float((payload.get("format") or {}).get("bit_rate"))),
        size=int(_parse_float((payload.get("format") or {}).get("size"))),
        rotation=rotation,
    )
    if info.width <= 0 or info.height <= 0:
        raise FFmpegError("Dimensiones de video no válidas")
    return info


def preview_size(info: MediaInfo) -> tuple[int, int]:
    """Tamaño par y reducido para decodificar el preview fluido."""
    width = max(2, info.display_width)
    height = max(2, info.display_height)
    scale = min(PREVIEW_MAX_WIDTH / width, PREVIEW_MAX_HEIGHT / height, 1.0)
    out_w = max(2, int(round(width * scale)))
    out_h = max(2, int(round(height * scale)))
    out_w -= out_w % 2
    out_h -= out_h % 2
    return out_w, out_h


def _scale_frame(size: tuple[int, int]) -> str:
    width, height = size
    return f"scale={width}:{height}:flags=bicubic"


def extract_preview_frame(
    path: str,
    timestamp: float,
    size: tuple[int, int],
    stop_event: threading.Event | None = None,
) -> bytes:
    width, height = size
    cmd = [
        ffmpeg_path(),
        "-v",
        "error",
        "-ss",
        f"{max(0.0, timestamp):.3f}",
        "-i",
        path,
        "-frames:v",
        "1",
        "-an",
        "-sn",
        "-vf",
        _scale_frame((width, height)),
        "-f",
        "image2pipe",
        "-vcodec",
        "png",
        "pipe:1",
    ]
    result = _run_process(
        cmd,
        stop_event=stop_event,
        timeout_message="Se agotó el tiempo al extraer el fotograma",
    )
    if result.returncode != 0 or not result.stdout:
        raise FFmpegError("No se pudo extraer el fotograma")
    return result.stdout


def extract_filmstrip_frame(
    path: str,
    timestamp: float,
    height: int,
    stop_event: threading.Event | None = None,
) -> bytes:
    cmd = [
        ffmpeg_path(),
        "-v",
        "error",
        "-ss",
        f"{max(0.0, timestamp):.3f}",
        "-i",
        path,
        "-frames:v",
        "1",
        "-an",
        "-sn",
        "-vf",
        f"scale=-2:{height}:flags=bilinear",
        "-f",
        "image2pipe",
        "-vcodec",
        "png",
        "pipe:1",
    ]
    result = _run_process(
        cmd,
        stop_event=stop_event,
        timeout_message="Se agotó el tiempo al extraer la miniatura",
    )
    if result.returncode != 0 or not result.stdout:
        raise FFmpegError("No se pudo extraer la miniatura")
    return result.stdout


def output_extension(source: str, preferred: str | None = None) -> str:
    if preferred:
        ext = preferred.lower()
        if not ext.startswith("."):
            ext = "." + ext
        return ext
    ext = Path(source).suffix.lower()
    if ext in (".mp4", ".mkv", ".mov", ".m4v"):
        return ".mp4" if ext == ".m4v" else ext
    return ".mp4"


def default_output_name(source: str, extension: str | None = None) -> str:
    stem = Path(source).stem
    ext = output_extension(source, extension)
    return f"{stem}_clip{ext}"


def next_available_path(target: str | Path) -> Path:
    """Devuelve la primera ruta libre añadiendo _01, _02, ... al nombre."""
    path = Path(target)
    if not path.exists():
        return path
    stem, suffix = path.stem, path.suffix
    for index in range(1, 1000):
        candidate = path.with_name(f"{stem}_{index:02d}{suffix}")
        if not candidate.exists():
            return candidate
    return path.with_name(f"{stem}_{path.stat().st_mtime_ns}{suffix}")


def is_valid_output_extension(path: str) -> bool:
    return Path(path).suffix.lower() in VIDEO_EXTENSIONS and bool(Path(path).suffix)


_X264_PIXEL_FORMATS = {
    "yuv420p",
    "yuvj420p",
    "yuv422p",
    "yuvj422p",
    "yuv444p",
    "yuvj444p",
    "nv12",
    "nv16",
    "nv21",
    "yuv420p10le",
    "yuv422p10le",
    "yuv444p10le",
    "nv20le",
    "gray",
    "gray10le",
}


def _output_pixel_format(pix_fmt: str) -> str:
    return pix_fmt if pix_fmt in _X264_PIXEL_FORMATS else "yuv420p"


def _audio_copy_compatible(codec: str, extension: str) -> bool:
    if not codec:
        return False
    if extension == ".mkv":
        return True
    if extension in (".mp4", ".m4v"):
        return codec in {"aac", "mp3", "alac", "ac3", "eac3"}
    if extension == ".mov":
        return codec in {"aac", "mp3", "alac", "ac3", "eac3", "pcm_s16le", "pcm_s24le"}
    return False


def build_export_command(plan: ExportPlan) -> list[str]:
    """Construye un corte preciso conservando la máxima calidad disponible."""
    ext = Path(plan.output).suffix.lower()
    preroll = min(1.0, max(0.0, plan.start))
    input_seek = plan.start - preroll
    cmd = [
        ffmpeg_path(),
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-ss",
        f"{input_seek:.3f}",
        "-i",
        plan.source,
        "-ss",
        f"{preroll:.3f}",
        "-t",
        f"{plan.duration:.3f}",
        "-map",
        "0:v:0",
        "-map",
        "0:a:0?",
        "-sn",
        "-dn",
        "-c:v",
        "libx264",
        "-preset",
        "medium",
        "-crf",
        "16",
        "-pix_fmt",
        _output_pixel_format(plan.pix_fmt),
    ]

    if plan.has_audio:
        if _audio_copy_compatible(plan.audio_codec, ext):
            cmd += ["-c:a", "copy"]
        else:
            cmd += ["-c:a", "aac", "-b:a", "320k"]

    if ext in (".mp4", ".mov", ".m4v"):
        cmd += ["-movflags", "+faststart"]
    cmd += ["-progress", "pipe:1", "-nostats", plan.output]
    return cmd


def parse_progress_line(line: str) -> tuple[float | None, str | None]:
    """Extrae (segundos_de_salida, velocidad) de una línea de -progress."""
    line = line.strip()
    if not line or "=" not in line:
        return None, None
    key, value = line.split("=", 1)
    if key == "out_time_us":
        try:
            return int(value) / 1_000_000.0, None
        except ValueError:
            return None, None
    if key == "out_time_ms":
        try:
            return int(value) / 1_000_000.0, None
        except ValueError:
            return None, None
    if key == "speed":
        return None, value.strip() or None
    return None, None


def format_timecode(seconds: float, milliseconds: bool = True) -> str:
    seconds = max(0.0, seconds)
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    if milliseconds:
        millis = int(round((seconds - int(seconds)) * 1000))
        if millis >= 1000:
            millis = 999
        if hours:
            return f"{hours}:{minutes:02d}:{secs:02d}.{millis:03d}"
        return f"{minutes:02d}:{secs:02d}.{millis:03d}"
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


def format_short_time(seconds: float) -> str:
    return format_timecode(seconds, milliseconds=False)
