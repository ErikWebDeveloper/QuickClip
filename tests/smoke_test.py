#!/usr/bin/env python3
"""Prueba de humo de QuickClip: metadatos, miniaturas, reproducción y exportación.

Uso:
    QT_QPA_PLATFORM=offscreen python3 tests/smoke_test.py
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PyQt6.QtCore import QTimer  # noqa: E402
from PyQt6.QtTest import QTest  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402

from quickclip import ffmpeg  # noqa: E402
from quickclip.export_dialog import ExportDialog  # noqa: E402
from quickclip.main_window import MainWindow  # noqa: E402
from quickclip.theme import apply_theme  # noqa: E402
from quickclip.workers import ExportWorker  # noqa: E402


def wait_until(predicate, timeout: float = 20.0, interval: int = 50) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        QTest.qWait(interval)
    return predicate()


def make_sample(directory: Path) -> Path:
    sample = directory / "sample.mp4"
    if sample.is_file():
        return sample
    subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "testsrc2=size=640x360:rate=30:duration=6",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:duration=6",
            "-c:v",
            "libx264",
            "-preset",
            "ultrafast",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-shortest",
            str(sample),
        ],
        check=True,
    )
    return sample


def run_export(plan: ffmpeg.ExportPlan) -> tuple[bool, str]:
    result = {"ok": False, "message": "", "finished": False}
    worker = ExportWorker(plan)

    def on_finished() -> None:
        result["finished"] = True

    def on_success(_output: str) -> None:
        result["ok"] = True

    def on_error(message: str) -> None:
        result["message"] = message

    def on_cancelled() -> None:
        result["message"] = "cancelado"

    worker.succeeded.connect(on_success)
    worker.failed.connect(on_error)
    worker.cancelled.connect(on_cancelled)
    worker.finished.connect(on_finished)
    worker.start()
    wait_until(lambda: result["finished"], timeout=60)
    worker.wait(5000)
    QTest.qWait(100)
    return result["ok"], result["message"]


def main() -> int:
    assert ffmpeg.tools_available()[0], "FFmpeg/FFprobe no disponibles"
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    temp = Path(tempfile.mkdtemp(prefix="quickclip-test-"))
    os.environ["XDG_CONFIG_HOME"] = str(temp / "config")
    os.environ["XDG_CACHE_HOME"] = str(temp / "cache")
    app = QApplication.instance() or QApplication(sys.argv)
    apply_theme(app)
    sample = make_sample(temp)
    failures: list[str] = []

    def check(name: str, condition: bool, detail: str = "") -> None:
        print(f"[{'OK ' if condition else 'FAIL'}] {name}{(' — ' + detail) if detail else ''}")
        if not condition:
            failures.append(name)

    info = ffmpeg.probe_media(str(sample))
    check("probe duración", abs(info.duration - 6.0) < 0.2, f"{info.duration:.3f}s")
    check("probe dimensiones", (info.width, info.height) == (640, 360), f"{info.width}x{info.height}")
    check("probe audio", info.has_audio)
    check("preview size", ffmpeg.preview_size(info) == (640, 360), str(ffmpeg.preview_size(info)[:]))
    frame = ffmpeg.extract_preview_frame(str(sample), 2.0, ffmpeg.preview_size(info))
    check("extracción de fotograma", len(frame) > 1000, f"{len(frame)} bytes")
    thumb = ffmpeg.extract_filmstrip_frame(str(sample), 1.0, 64)
    check("extracción de miniatura", len(thumb) > 500, f"{len(thumb)} bytes")

    first = temp / "clip.mp4"
    first.write_bytes(b"x")
    second = ffmpeg.next_available_path(first)
    check("auto-incremento de nombre", second.name == "clip_01.mp4", second.name)

    command = ffmpeg.build_export_command(
        ffmpeg.ExportPlan(
            source=str(sample),
            output=str(temp / "command.mp4"),
            start=1.0,
            duration=2.0,
            audio_codec="aac",
            has_audio=True,
        )
    )
    check(
        "el corte siempre recodifica el video",
        "libx264" in command and "-crf" in command,
    )
    check(
        "el audio compatible se copia sin pérdida",
        "-c:a" in command and command[command.index("-c:a") + 1] == "copy",
    )

    precise_out = temp / "clip_preciso.mkv"
    ok, message = run_export(
        ffmpeg.ExportPlan(
            source=str(sample),
            output=str(precise_out),
            start=1.0,
            duration=2.0,
            video_codec=info.video_codec,
            audio_codec=info.audio_codec,
            pix_fmt=info.pix_fmt,
            has_audio=True,
        )
    )
    check("exportación siempre precisa", ok, message)
    if ok:
        precise_info = ffmpeg.probe_media(str(precise_out))
        check(
            "duración precisa al fotograma",
            abs(precise_info.duration - 2.0) < 0.35,
            f"{precise_info.duration:.2f}s",
        )
        check(
            "audio original conservado",
            precise_info.audio_codec == info.audio_codec,
            f"{info.audio_codec} → {precise_info.audio_codec}",
        )
        check(
            "formato de píxel conservado",
            precise_info.pix_fmt == info.pix_fmt,
            f"{info.pix_fmt} → {precise_info.pix_fmt}",
        )

    window = MainWindow()
    window.show()
    check(
        "botones de herramientas con iconos",
        all(
            not button.icon().isNull()
            for button in (
                window.mark_in_button,
                window.mark_out_button,
                window.reset_selection_button,
                window.player.mute_button,
            )
        ),
    )
    unmuted_key = window.player.mute_button.icon().cacheKey()
    window.player.mute_button.setChecked(True)
    check(
        "el icono de mute refleja el estado",
        window.player.mute_button.icon().cacheKey() != unmuted_key
        and "Activar" in window.player.mute_button.toolTip(),
    )
    window.open_path(str(sample))

    loaded = wait_until(lambda: window.info is not None, timeout=15)
    check("carga en la interfaz", loaded)
    if loaded:
        window.timeline.set_filmstrip_state(True)
        strip_done = wait_until(
            lambda: window._filmstrip is None and not window.timeline._loading,
            timeout=25,
        )
        thumbs = sum(1 for thumb in window.timeline._thumbs if thumb is not None)
        check("filmstrip en segundo plano", strip_done and thumbs >= 8, f"{thumbs} miniaturas")
        check(
            "selección inicial completa",
            window.timeline.in_point == 0.0
            and abs(window.timeline.out_point - info.duration) < 0.01,
        )

        window.timeline.set_selection(1.0, 3.5)
        check(
            "actualización de etiquetas In/Out",
            window.in_value.text().startswith("00:01")
            and window.out_value.text().startswith("00:03"),
            f"{window.in_value.text()} / {window.out_value.text()}",
        )

        window.player.seek(2.0)
        frame_ready = wait_until(
            lambda: not window.player.is_playing
            and window.player.view._image is not None
            and abs(window.player.playhead - 2.0) < 0.15,
            timeout=15,
        )
        check("salto y fotograma de previsualización", frame_ready)

        start_playhead = window.player.playhead
        window.player.play()
        QTest.qWait(900)
        progressed = window.player.playhead > start_playhead + 0.2
        window.player.pause()
        check("reproducción avanza", progressed, f"{start_playhead:.2f} → {window.player.playhead:.2f}")
        check("playhead sincronizado", abs(window.timeline.playhead - window.player.playhead) < 0.2)

        window.timeline.set_selection(1.0, 2.0)
        window.player.seek(1.2)
        window.player.play()
        bounded_end = wait_until(lambda: not window.player.is_playing, timeout=5)
        check(
            "reproducción limitada al recorte",
            bounded_end and 1.85 <= window.player.playhead <= 2.02,
            f"playhead={window.player.playhead:.2f}",
        )

        window.player.seek(5.5)
        window.player.play()
        check(
            "play desde fuera empieza en In",
            abs(window.player.playhead - 1.0) < 0.05
            and abs(window.timeline.playhead - 1.0) < 0.05,
            f"playhead={window.player.playhead:.2f}",
        )
        window.player.pause()
        window.player.go_end()
        check(
            "End va al final del recorte",
            1.9 <= window.player.playhead <= 2.0,
            f"playhead={window.player.playhead:.2f}",
        )
        window.player.go_start()
        check(
            "Inicio va al In del recorte",
            abs(window.player.playhead - 1.0) < 0.05,
            f"playhead={window.player.playhead:.2f}",
        )

        dialog = ExportDialog(window.info, 1.0, 3.5, window)
        dialog.name_edit.setText("sample")
        dialog.extension_combo.setCurrentIndex(dialog.extension_combo.findData(".mp4"))
        check(
            "protección del archivo original",
            dialog._validate() is not None,
            dialog._validate() or "",
        )
        dialog.name_edit.setText("salida_prueba")
        check("validación de nombre", dialog._validate() is None, dialog._validate() or "")
        collision = temp / "salida_prueba.mp4"
        collision.write_bytes(b"x")
        dialog._refresh_warning()
        check(
            "aviso de archivo existente",
            not dialog.warning_banner.isHidden()
            and "ya está en esa carpeta" in dialog.warning_banner._text.text(),
        )
        dialog.deleteLater()

    window.player.shutdown()
    window._stop_filmstrip()
    window.close()
    window.deleteLater()
    QTest.qWait(200)

    print()
    if failures:
        print(f"FALLARON {len(failures)} pruebas: {', '.join(failures)}")
        return 1
    print("Todas las pruebas pasaron.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
