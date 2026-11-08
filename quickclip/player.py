"""Reproductor de previsualización basado en decodificación de FFmpeg."""

from __future__ import annotations

import shutil
import subprocess
import threading

from PyQt6.QtCore import QPointF, QRectF, QSize, Qt, QThreadPool, QTimer, pyqtSignal
from PyQt6.QtGui import (
    QColor,
    QFont,
    QImage,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QPolygonF,
)
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from . import ffmpeg
from .icons import volume_icon
from .theme import COLORS
from .workers import FunctionTask, PlaybackWorker


class VideoView(QWidget):
    """Área de video con ajuste de aspecto y marcador de posición."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("VideoView")
        self._image: QImage | None = None
        self._message = "Arrastra un video aquí"
        self._submessage = "o haz doble clic en el explorador · también puedes pulsar Ctrl+O"
        self.setMinimumSize(320, 200)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, True)

    def set_image(self, image: QImage | None) -> None:
        self._image = image
        self.update()

    def set_message(self, message: str, submessage: str = "") -> None:
        self._message = message
        self._submessage = submessage
        self._image = None
        self.update()

    def sizeHint(self) -> QSize:  # noqa: N802
        return QSize(720, 405)

    def paintEvent(self, _event) -> None:  # noqa: N802, D102
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        rect = QRectF(self.rect()).adjusted(1.0, 1.0, -1.0, -1.0)
        clip = QPainterPath()
        clip.addRoundedRect(rect, 10.0, 10.0)
        painter.setClipPath(clip)

        gradient = QLinearGradient(rect.topLeft(), rect.bottomRight())
        gradient.setColorAt(0.0, QColor("#06060a"))
        gradient.setColorAt(1.0, QColor("#0b0b12"))
        painter.fillPath(clip, gradient)

        if self._image is not None and not self._image.isNull():
            target = rect.adjusted(0.0, 0.0, 0.0, 0.0)
            scaled = self._image.scaled(
                QSize(int(target.width()), int(target.height())),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            x = target.x() + (target.width() - scaled.width()) / 2.0
            y = target.y() + (target.height() - scaled.height()) / 2.0
            painter.drawImage(QPointF(x, y), scaled)
        else:
            self._paint_placeholder(painter, rect)

        painter.setClipping(False)
        painter.setPen(QPen(QColor(COLORS["border_soft"]), 1.0))
        painter.drawRoundedRect(rect, 10.0, 10.0)

    def _paint_placeholder(self, painter: QPainter, rect: QRectF) -> None:
        center = rect.center()
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(43, 255, 136, 18))
        radius = 46.0
        painter.drawEllipse(center, radius, radius)

        triangle = QPolygonF(
            [
                QPointF(center.x() - 10.0, center.y() - 16.0),
                QPointF(center.x() - 10.0, center.y() + 16.0),
                QPointF(center.x() + 18.0, center.y()),
            ]
        )
        painter.setBrush(QColor(COLORS["accent"]))
        painter.drawPolygon(triangle)

        title_font = QFont(self.font())
        title_font.setPointSizeF(title_font.pointSizeF() + 3)
        title_font.setWeight(QFont.Weight.DemiBold)
        painter.setFont(title_font)
        painter.setPen(QColor(COLORS["muted"]))
        title_rect = QRectF(rect.x(), center.y() + 62.0, rect.width(), 30.0)
        painter.drawText(title_rect, Qt.AlignmentFlag.AlignHCenter, self._message)

        small = QFont(self.font())
        small.setPointSizeF(max(8.0, small.pointSizeF() - 1))
        painter.setFont(small)
        painter.setPen(QColor(COLORS["dim"]))
        sub_rect = QRectF(rect.x() + 20.0, center.y() + 88.0, rect.width() - 40.0, 44.0)
        painter.drawText(
            sub_rect,
            Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop | Qt.TextFlag.TextWordWrap,
            self._submessage,
        )


class PlayerWidget(QWidget):
    """Reproductor con play/pausa, barra de progreso y salto por fotogramas."""

    time_changed = pyqtSignal(float, float)
    playing_changed = pyqtSignal(bool)
    error = pyqtSignal(str)
    status = pyqtSignal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._info: ffmpeg.MediaInfo | None = None
        self._playhead = 0.0
        self._playing = False
        self._range_start = 0.0
        self._range_end = 0.0
        self._worker: PlaybackWorker | None = None
        self._audio: subprocess.Popen[bytes] | None = None
        self._muted = False
        self._seek_token = 0
        self._frame_pool = QThreadPool(self)
        self._frame_pool.setMaxThreadCount(2)
        self._shutdown = threading.Event()
        self._resume_after_scrub = False
        self._slider_active = False
        self._audio_available = shutil.which("ffplay") is not None

        self._seek_timer = QTimer(self)
        self._seek_timer.setSingleShot(True)
        self._seek_timer.setInterval(40)
        self._seek_timer.timeout.connect(self._submit_frame)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        self.view = VideoView()
        layout.addWidget(self.view, 1)

        transport = QFrame()
        transport.setObjectName("Transport")
        transport_layout = QHBoxLayout(transport)
        transport_layout.setContentsMargins(12, 8, 12, 8)
        transport_layout.setSpacing(8)

        self.prev_button = QPushButton("⏮")
        self.prev_button.setObjectName("TransportButton")
        self.prev_button.setToolTip("Ir al In del recorte (Home)")
        self.prev_button.clicked.connect(self.go_start)

        self.frame_back = QPushButton("◀")
        self.frame_back.setObjectName("TransportButton")
        self.frame_back.setToolTip("Fotograma anterior (←)")
        self.frame_back.clicked.connect(lambda: self.step_frames(-1))

        self.play_button = QPushButton("▶")
        self.play_button.setObjectName("PlayButton")
        self.play_button.setToolTip("Reproducir / pausar (Espacio)")
        self.play_button.clicked.connect(self.toggle_play)

        self.frame_forward = QPushButton("▶")
        self.frame_forward.setObjectName("TransportButton")
        self.frame_forward.setToolTip("Fotograma siguiente (→)")
        self.frame_forward.clicked.connect(lambda: self.step_frames(1))

        self.next_button = QPushButton("⏭")
        self.next_button.setObjectName("TransportButton")
        self.next_button.setToolTip("Ir al Out del recorte (End)")
        self.next_button.clicked.connect(self.go_end)

        self.current_label = QLabel("00:00.000")
        self.current_label.setObjectName("Timecode")
        self.current_label.setToolTip("Tiempo actual")

        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setRange(0, 1000)
        self.slider.setValue(0)
        self.slider.setEnabled(False)
        self.slider.sliderPressed.connect(self._on_slider_pressed)
        self.slider.sliderMoved.connect(self._on_slider_moved)
        self.slider.valueChanged.connect(self._on_slider_value_changed)
        self.slider.sliderReleased.connect(self._on_slider_released)

        self.total_label = QLabel("00:00.000")
        self.total_label.setObjectName("TimecodeMuted")

        self.mute_button = QPushButton()
        self.mute_button.setObjectName("MuteButton")
        self.mute_button.setCheckable(True)
        self.mute_button.setEnabled(self._audio_available)
        self.mute_button.setFixedSize(30, 26)
        self.mute_button.setIconSize(QSize(16, 16))
        self.mute_button.toggled.connect(self._on_mute_toggled)
        self._update_mute_visual(False)

        for widget in (
            self.prev_button,
            self.frame_back,
            self.play_button,
            self.frame_forward,
            self.next_button,
            self.current_label,
        ):
            transport_layout.addWidget(widget)
        transport_layout.addWidget(self.slider, 1)
        transport_layout.addWidget(self.total_label)
        transport_layout.addWidget(self.mute_button)
        layout.addWidget(transport)

        self._set_enabled(False)

    # ------------------------------------------------------------------ API
    @property
    def info(self) -> ffmpeg.MediaInfo | None:
        return self._info

    @property
    def playhead(self) -> float:
        return self._playhead

    @property
    def is_playing(self) -> bool:
        return self._playing

    def set_media(self, info: ffmpeg.MediaInfo) -> None:
        self.stop()
        self._info = info
        self._playhead = 0.0
        self._range_start = 0.0
        self._range_end = info.duration
        self._seek_token += 1
        self._seek_timer.stop()
        self.view.set_message("Cargando vista previa…")
        self.total_label.setText(ffmpeg.format_timecode(info.duration))
        self.slider.setRange(0, 1000)
        self.slider.setValue(0)
        self.slider.setEnabled(True)
        self._set_enabled(True)
        self._update_time_labels()
        self._seek_timer.start(20)

    def clear_media(self) -> None:
        self.stop()
        self._info = None
        self._playhead = 0.0
        self._range_start = 0.0
        self._range_end = 0.0
        self._seek_token += 1
        self.view.set_message(
            "Arrastra un video aquí",
            "o haz doble clic en el explorador · también puedes pulsar Ctrl+O",
        )
        self.current_label.setText("00:00.000")
        self.total_label.setText("00:00.000")
        self.slider.setValue(0)
        self.slider.setEnabled(False)
        self._set_enabled(False)

    def set_playback_range(self, start: float, end: float) -> None:
        if self._info is None:
            return
        duration = self.video_duration()
        start = max(0.0, min(duration, start))
        end = max(start, min(duration, end))
        if abs(start - self._range_start) < 1e-9 and abs(end - self._range_end) < 1e-9:
            return
        was_playing = self._playing
        if was_playing:
            self.pause()
        self._range_start = start
        self._range_end = end
        resume = was_playing
        moved = False
        step = 1.0 / self._info.safe_fps if self._info else 0.04
        if self._playhead < start:
            self._playhead = start
            moved = True
        elif self._playhead >= end:
            self._playhead = max(start, end - step)
            moved = True
            resume = False
        if moved:
            self._seek_token += 1
            self._update_time_labels()
            self._update_slider()
            self.time_changed.emit(self._playhead, duration)
            self._request_frame_now()
        if resume:
            self.play()

    def _playback_start(self) -> float:
        return max(0.0, min(self.video_duration(), self._range_start))

    def _playback_end(self) -> float:
        end = self.video_duration() if self._range_end <= 0 else self._range_end
        return max(self._playback_start(), min(self.video_duration(), end))

    def play(self) -> None:
        if self._info is None or self._playing:
            return
        if self.video_duration() <= 0:
            return
        start = self._playback_start()
        end = self._playback_end()
        if end - start <= 0.01:
            return
        if self._playhead < start - 0.01 or self._playhead >= end - 0.01:
            self._playhead = start
            self._update_time_labels()
            self._update_slider()
            self.time_changed.emit(self._playhead, self.video_duration())
        self._seek_token += 1
        self._seek_timer.stop()
        self._playing = True
        self.play_button.setText("⏸")
        self.playing_changed.emit(True)
        self._start_audio()
        self._start_worker()

    def pause(self) -> None:
        if not self._playing:
            return
        self._playing = False
        self.play_button.setText("▶")
        self._stop_worker()
        self._stop_audio()
        self.playing_changed.emit(False)
        self._request_frame_now()

    def toggle_play(self) -> None:
        if self._playing:
            self.pause()
        else:
            self.play()

    def stop(self) -> None:
        was_playing = self._playing
        self._playing = False
        self.play_button.setText("▶")
        self._stop_worker()
        self._stop_audio()
        if was_playing:
            self.playing_changed.emit(False)

    def shutdown(self) -> None:
        self._shutdown.set()
        self.stop()
        self._seek_timer.stop()
        self._frame_pool.waitForDone(2500)

    def seek(self, seconds: float) -> None:
        if self._info is None:
            return
        target = max(0.0, min(self.video_duration(), seconds))
        if self._playing:
            start = self._playback_start()
            end = self._playback_end()
            step = 1.0 / self._info.safe_fps if self._info else 0.04
            target = max(start, min(max(start, end - step), target))
        self._playhead = target
        self._seek_token += 1
        self._update_time_labels()
        self._update_slider()
        self.time_changed.emit(self._playhead, self.video_duration())
        if self._playing:
            self._stop_audio()
            self._stop_worker()
            self._start_audio()
            self._start_worker()
        else:
            self._seek_timer.start()

    def step_frames(self, frames: int) -> None:
        if self._info is None:
            return
        if self._playing:
            self.pause()
        step = 1.0 / self._info.safe_fps
        self.seek(self._playhead + frames * step)

    def go_start(self) -> None:
        if self._info is None:
            return
        self.seek(self._playback_start())

    def go_end(self) -> None:
        if self._info is None:
            return
        if self._playing:
            self.pause()
        start = self._playback_start()
        end = self._playback_end()
        self.seek(max(start, end - 1.0 / self._info.safe_fps))

    def begin_scrub(self) -> None:
        self._resume_after_scrub = self._playing
        if self._playing:
            self.pause()

    def end_scrub(self) -> None:
        if self._resume_after_scrub:
            self._resume_after_scrub = False
            self.play()

    def video_duration(self) -> float:
        return self._info.duration if self._info else 0.0

    # ------------------------------------------------------------- internals
    def _set_enabled(self, enabled: bool) -> None:
        for widget in (
            self.prev_button,
            self.frame_back,
            self.play_button,
            self.frame_forward,
            self.next_button,
            self.slider,
        ):
            widget.setEnabled(enabled)

    def _update_time_labels(self) -> None:
        self.current_label.setText(ffmpeg.format_timecode(self._playhead))

    def _update_slider(self) -> None:
        if self._info is None or self._slider_active:
            return
        duration = self.video_duration()
        value = 0 if duration <= 0 else int(round(self._playhead / duration * 1000))
        self.slider.blockSignals(True)
        self.slider.setValue(max(0, min(1000, value)))
        self.slider.blockSignals(False)

    def _start_worker(self) -> None:
        info = self._info
        if info is None:
            return
        size = ffmpeg.preview_size(info)
        worker = PlaybackWorker(
            info.path,
            self._playhead,
            self._playback_end(),
            size,
            info.safe_fps,
            self,
        )
        worker.frame_ready.connect(self._on_frame)
        worker.failed.connect(self._on_playback_error)
        worker.reached_end.connect(self._on_playback_end)
        worker.finished.connect(lambda worker=worker: self._on_worker_finished(worker))
        self._worker = worker
        worker.start()

    def _on_worker_finished(self, worker: PlaybackWorker) -> None:
        if self._worker is worker:
            self._worker = None
        worker.deleteLater()

    def _stop_worker(self) -> None:
        worker = self._worker
        self._worker = None
        if worker is not None:
            worker.stop()
            worker.wait(1500)

    def _on_frame(self, image: QImage, timestamp: float) -> None:
        if not self._playing:
            return
        self.view.set_image(image)
        self._playhead = timestamp
        self._update_time_labels()
        self._update_slider()
        self.time_changed.emit(self._playhead, self.video_duration())

    def _on_playback_error(self, message: str) -> None:
        self._playing = False
        self.play_button.setText("▶")
        self._stop_audio()
        self.playing_changed.emit(False)
        self.error.emit(message)

    def _on_playback_end(self) -> None:
        if not self._playing:
            return
        self._playing = False
        self.play_button.setText("▶")
        self._stop_audio()
        duration = self.video_duration()
        start = self._playback_start()
        end = self._playback_end()
        step = 1.0 / self._info.safe_fps if self._info else 0.04
        self._playhead = max(start, end - step)
        self._update_time_labels()
        self._update_slider()
        self.time_changed.emit(self._playhead, duration)
        self.playing_changed.emit(False)
        self._seek_token += 1
        self._seek_timer.start(30)

    def _submit_frame(self) -> None:
        info = self._info
        if info is None:
            return
        token = self._seek_token
        timestamp = self._playhead
        size = ffmpeg.preview_size(info)
        task = FunctionTask(self._extract_frame, info.path, timestamp, size, token)
        task.signals.result.connect(self._on_frame_extracted)
        task.signals.error.connect(self._on_frame_error)
        self._frame_pool.start(task)

    def _extract_frame(self, path: str, timestamp: float, size: tuple[int, int], token: int):
        if token != self._seek_token:
            return None
        data = ffmpeg.extract_preview_frame(
            path,
            timestamp,
            size,
            stop_event=self._shutdown,
        )
        if token != self._seek_token:
            return None
        return QImage.fromData(data)

    def _on_frame_extracted(self, image) -> None:
        if image is None or image.isNull() or self._playing:
            return
        self.view.set_image(image)

    def _on_frame_error(self, message: str) -> None:
        if self._playing:
            return
        self.view.set_message("No se pudo previsualizar", message)
        self.status.emit(message)

    def _request_frame_now(self) -> None:
        self._seek_token += 1
        self._seek_timer.start(0)

    def _start_audio(self) -> None:
        self._stop_audio()
        info = self._info
        if (
            info is None
            or self._muted
            or not info.has_audio
            or not self._audio_available
        ):
            return
        remaining = self._playback_end() - self._playhead
        if remaining <= 0.05:
            return
        command = [
            shutil.which("ffplay") or "ffplay",
            "-v",
            "quiet",
            "-nodisp",
            "-autoexit",
            "-ss",
            f"{self._playhead:.3f}",
            "-t",
            f"{remaining:.3f}",
            info.path,
        ]
        try:
            self._audio = subprocess.Popen(
                command,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except OSError:
            self._audio = None

    def _stop_audio(self) -> None:
        process = self._audio
        self._audio = None
        if process is not None and process.poll() is None:
            try:
                process.terminate()
                process.wait(timeout=0.5)
            except (OSError, subprocess.TimeoutExpired):
                try:
                    process.kill()
                except OSError:
                    pass

    def _on_mute_toggled(self, muted: bool) -> None:
        self._muted = muted
        self._update_mute_visual(muted)
        if muted:
            self._stop_audio()
        elif self._playing:
            self._start_audio()

    def _update_mute_visual(self, muted: bool) -> None:
        action = "Activar el sonido de previsualización" if muted else "Silenciar el audio de previsualización"
        self.mute_button.setIcon(volume_icon(muted))
        self.mute_button.setToolTip(action)
        self.mute_button.setAccessibleName(action)

    # ------------------------------------------------------------- slider UI
    def _on_slider_pressed(self) -> None:
        self._slider_active = True
        self.begin_scrub()

    def _on_slider_moved(self, value: int) -> None:
        if self._info is None:
            return
        duration = self.video_duration()
        target = duration * value / 1000.0
        self._playhead = target
        self.current_label.setText(ffmpeg.format_timecode(target))
        self._seek_token += 1
        self._seek_timer.start()
        self.time_changed.emit(target, duration)

    def _on_slider_value_changed(self, value: int) -> None:
        if self._slider_active:
            self._on_slider_moved(value)

    def _on_slider_released(self) -> None:
        self._slider_active = False
        self.seek(self._playhead)
        self.end_scrub()
