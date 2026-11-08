"""Trabajos en segundo plano: miniaturas, fotogramas, playback y exportación."""

from __future__ import annotations

import subprocess
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from PyQt6.QtCore import QObject, QRunnable, QThread, pyqtSignal
from PyQt6.QtGui import QImage

from . import ffmpeg
from .config import FILMSTRIP_COUNT, FILMSTRIP_HEIGHT, filmstrip_dir


class WorkerSignals(QObject):
    finished = pyqtSignal()
    error = pyqtSignal(str)
    result = pyqtSignal(object)


class FunctionTask(QRunnable):
    """Ejecuta una función en el pool y devuelve el resultado como señal."""

    def __init__(self, fn, *args, **kwargs) -> None:
        super().__init__()
        self.fn = fn
        self.args = args
        self.kwargs = kwargs
        self.signals = WorkerSignals()
        self.setAutoDelete(True)

    def run(self) -> None:  # noqa: D102
        try:
            result = self.fn(*self.args, **self.kwargs)
        except Exception as exc:  # noqa: BLE001
            self.signals.error.emit(str(exc))
        else:
            self.signals.result.emit(result)
        finally:
            self.signals.finished.emit()


class FilmstripWorker(QThread):
    """Genera y cachea miniaturas equiespaciadas del video."""

    thumbnail = pyqtSignal(int, QImage)
    error = pyqtSignal(str)
    completed = pyqtSignal(int, int)

    def __init__(self, path: str, duration: float, count: int = FILMSTRIP_COUNT, parent=None) -> None:
        super().__init__(parent)
        self.path = path
        self.duration = duration
        self.count = max(1, count)
        self._stop = threading.Event()
        self.cache = filmstrip_dir(path, self.count)

    def stop(self) -> None:
        self._stop.set()

    def _timestamp(self, index: int) -> float:
        if self.count == 1:
            return min(0.5, max(0.0, self.duration / 2))
        fraction = index / (self.count - 1)
        return min(max(self.duration * 0.985, 0.0), self.duration * fraction)

    def _load_cached(self, index: int) -> QImage | None:
        file = self.cache / f"{index:03d}.png"
        if not file.is_file():
            return None
        image = QImage(str(file))
        return image if not image.isNull() else None

    def _extract(self, index: int) -> tuple[int, QImage | None]:
        if self._stop.is_set():
            return index, None
        file = self.cache / f"{index:03d}.png"
        cached = self._load_cached(index)
        if cached is not None:
            return index, cached
        try:
            data = ffmpeg.extract_filmstrip_frame(
                self.path,
                self._timestamp(index),
                FILMSTRIP_HEIGHT,
                stop_event=self._stop,
            )
        except ffmpeg.FFmpegError:
            return index, None
        image = QImage.fromData(data)
        if image.isNull():
            return index, None
        if not self._stop.is_set():
            file.write_bytes(data)
        return index, image

    def run(self) -> None:  # noqa: D102
        generated = 0
        failures = 0
        try:
            with ThreadPoolExecutor(max_workers=3, thread_name_prefix="filmstrip") as pool:
                futures = [pool.submit(self._extract, index) for index in range(self.count)]
                for future in futures:
                    if self._stop.is_set():
                        break
                    try:
                        index, image = future.result()
                    except Exception:  # noqa: BLE001
                        failures += 1
                        continue
                    if image is not None and not self._stop.is_set():
                        self.thumbnail.emit(index, image)
                        generated += 1
                    else:
                        failures += 1
                if self._stop.is_set():
                    for future in futures:
                        future.cancel()
        except Exception as exc:  # noqa: BLE001
            self.error.emit(str(exc))
        if not self._stop.is_set():
            self.completed.emit(generated, failures)


class PlaybackWorker(QThread):
    """Decodifica el video por tubería y entrega fotogramas al reproductor."""

    frame_ready = pyqtSignal(QImage, float)
    failed = pyqtSignal(str)
    reached_end = pyqtSignal()

    def __init__(
        self,
        path: str,
        start: float,
        duration: float,
        size: tuple[int, int],
        fps: float,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.path = path
        self.start_time = max(0.0, start)
        self.duration = duration
        self.size = size
        self.fps = fps if fps and fps > 0 else 30.0
        self._stop = threading.Event()
        self._process: subprocess.Popen[bytes] | None = None

    def stop(self) -> None:
        self._stop.set()
        process = self._process
        if process and process.poll() is None:
            try:
                process.kill()
            except OSError:
                pass

    def run(self) -> None:  # noqa: D102
        width, height = self.size
        frame_size = width * height * 3
        remaining = max(0.0, self.duration - self.start_time)
        if remaining <= 0.01:
            self.reached_end.emit()
            return

        fps_text = f"{self.fps:.6f}".rstrip("0").rstrip(".") or "30"
        command = [
            ffmpeg.ffmpeg_path(),
            "-v",
            "error",
            "-ss",
            f"{self.start_time:.3f}",
            "-i",
            self.path,
            "-t",
            f"{remaining:.3f}",
            "-an",
            "-sn",
            "-dn",
            "-vf",
            f"scale={width}:{height}:flags=bilinear",
            "-r",
            fps_text,
            "-f",
            "rawvideo",
            "-pix_fmt",
            "rgb24",
            "pipe:1",
        ]
        try:
            process = subprocess.Popen(
                command,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                bufsize=frame_size * 2,
            )
        except OSError as exc:
            self.failed.emit(f"No se pudo iniciar FFmpeg: {exc}")
            return
        self._process = process

        interval = 1.0 / self.fps
        index = 0
        started = time.perf_counter()
        try:
            assert process.stdout is not None
            while not self._stop.is_set():
                frame = process.stdout.read(frame_size)
                if not frame or len(frame) < frame_size:
                    break
                image = QImage(
                    frame,
                    width,
                    height,
                    width * 3,
                    QImage.Format.Format_RGB888,
                ).copy()
                timestamp = self.start_time + index * interval
                due = started + index * interval
                delay = due - time.perf_counter()
                if delay > 0.002:
                    if self._stop.wait(delay):
                        break
                self.frame_ready.emit(image, min(timestamp, self.duration))
                index += 1
                if timestamp >= self.duration - interval * 0.5:
                    break
        except Exception as exc:  # noqa: BLE001
            if not self._stop.is_set():
                self.failed.emit(f"Error de reproducción: {exc}")
        finally:
            try:
                if process.poll() is None:
                    process.kill()
                process.wait(timeout=1.0)
            except (OSError, subprocess.TimeoutExpired):
                pass
            try:
                if process.stdout:
                    process.stdout.close()
            except OSError:
                pass
            self._process = None
        if not self._stop.is_set():
            self.reached_end.emit()


class ExportWorker(QThread):
    """Ejecuta el recorte preciso con FFmpeg."""

    progress = pyqtSignal(int, str)
    status = pyqtSignal(str)
    succeeded = pyqtSignal(str)
    failed = pyqtSignal(str)
    cancelled = pyqtSignal()

    def __init__(self, plan: ffmpeg.ExportPlan, parent=None) -> None:
        super().__init__(parent)
        self.plan = plan
        self._stop = threading.Event()
        self._process: subprocess.Popen[str] | None = None

    def cancel(self) -> None:
        self._stop.set()
        process = self._process
        if process and process.poll() is None:
            try:
                process.terminate()
            except OSError:
                pass

    def _cleanup(self) -> None:
        try:
            path = Path(self.plan.output)
            if path.exists():
                path.unlink()
                partial = path.with_name(path.name + ".part")
                if partial.exists():
                    partial.unlink()
        except OSError:
            pass

    def _run_once(self, plan: ffmpeg.ExportPlan) -> tuple[bool, str]:
        try:
            command = ffmpeg.build_export_command(plan)
        except ffmpeg.FFmpegError as exc:
            return False, str(exc)
        try:
            process = subprocess.Popen(
                command,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
            )
        except OSError as exc:
            return False, f"No se pudo iniciar FFmpeg: {exc}"
        self._process = process
        last_percent = -1
        stderr_tail: list[str] = []
        try:
            assert process.stdout is not None
            for line in process.stdout:
                if self._stop.is_set():
                    break
                seconds, speed = ffmpeg.parse_progress_line(line)
                if seconds is not None and plan.duration > 0:
                    percent = int(max(0.0, min(1.0, seconds / plan.duration)) * 100)
                    if percent != last_percent:
                        last_percent = percent
                        detail = f"{percent}%"
                        if speed:
                            detail = f"{percent}% · {speed}"
                        self.progress.emit(percent, detail)
                elif line.startswith("speed="):
                    speed = line.split("=", 1)[1].strip()
                    if speed and last_percent >= 0:
                        self.progress.emit(last_percent, f"{last_percent}% · {speed}")
            if process.stderr is not None:
                stderr_tail = [line.strip() for line in process.stderr.readlines() if line.strip()][-6:]
            returncode = process.wait()
        except Exception as exc:  # noqa: BLE001
            try:
                process.kill()
            except OSError:
                pass
            return False, f"Error durante la exportación: {exc}"
        finally:
            self._process = None

        if self._stop.is_set():
            return False, "cancelado"
        if returncode != 0:
            detail = stderr_tail[-1] if stderr_tail else f"FFmpeg terminó con código {returncode}"
            return False, detail
        output = Path(plan.output)
        if not output.is_file() or output.stat().st_size == 0:
            return False, "El archivo de salida está vacío"
        try:
            info = ffmpeg.probe_media(plan.output)
        except ffmpeg.FFmpegError as exc:
            return False, f"El archivo generado no es válido: {exc}"
        if info.duration <= 0:
            return False, "El archivo generado no contiene video"
        self.progress.emit(100, "100%")
        return True, ""

    def run(self) -> None:  # noqa: D102
        plan = self.plan
        self.status.emit("Preparando corte preciso…")
        self._cleanup()
        ok, error = self._run_once(plan)

        if self._stop.is_set():
            self._cleanup()
            self.cancelled.emit()
            return
        if ok:
            self.succeeded.emit(plan.output)
        else:
            self._cleanup()
            self.failed.emit(error or "No se pudo exportar el clip")
