"""Ventana principal de QuickClip: explorador, reproductor, timeline y exportación."""

from __future__ import annotations

import os
import threading
from pathlib import Path

from PyQt6.QtCore import QEvent, QSettings, QSize, Qt, QThreadPool, QTimer
from PyQt6.QtGui import QAction, QFontMetrics, QKeySequence
from PyQt6.QtWidgets import (
    QAbstractSpinBox,
    QApplication,
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from . import ffmpeg
from .config import (
    APP_NAME,
    APP_VERSION,
    FILMSTRIP_COUNT,
    ORG_NAME,
    VIDEO_EXTENSIONS,
    default_video_dirs,
    human_size,
    is_video_file,
    debug_exit_log,
)
from .export_dialog import ExportDialog
from .explorer import FileExplorer
from .icons import full_range_icon, trim_in_icon, trim_out_icon
from .player import PlayerWidget
from .theme import COLORS
from .timeline import TimelineWidget
from .workers import FilmstripWorker, FunctionTask


TOAST_STYLE = f"""
QFrame#Toast {{
    background-color: {COLORS['elevated']};
    border: 1px solid {COLORS['border']};
    border-radius: 10px;
}}
QLabel#ToastText {{
    color: {COLORS['text']};
    background: transparent;
    font-weight: 600;
}}
QLabel#ToastDot {{
    background: transparent;
    font-size: 15px;
}}
"""


class Toast(QFrame):
    """Aviso flotante breve en la esquina inferior derecha."""

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setObjectName("Toast")
        self.setStyleSheet(TOAST_STYLE)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 9, 16, 9)
        layout.setSpacing(9)
        self.dot = QLabel("●")
        self.dot.setObjectName("ToastDot")
        self.label = QLabel("")
        self.label.setObjectName("ToastText")
        layout.addWidget(self.dot)
        layout.addWidget(self.label)
        self.hide()
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.hide)

    def show_message(self, text: str, kind: str = "info") -> None:
        colors = {
            "info": COLORS["accent"],
            "success": COLORS["accent"],
            "warning": COLORS["warning"],
            "error": COLORS["danger"],
        }
        color = colors.get(kind, COLORS["accent"])
        self.dot.setStyleSheet(f"color: {color}; background: transparent; font-size: 15px;")
        self.label.setText(text)
        self.adjustSize()
        self._reposition()
        self.show()
        self.raise_()
        self._timer.start(4200)

    def _reposition(self) -> None:
        parent = self.parentWidget()
        if parent is None:
            return
        margin = 24
        x = parent.width() - self.width() - margin
        y = parent.height() - self.height() - margin
        self.move(max(margin, x), max(margin, y))


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("MainWindow")
        self.setWindowTitle(f"{APP_NAME} — Editor rápido de clips")
        self.resize(1320, 860)
        self.setMinimumSize(1040, 680)
        self.setAcceptDrops(True)
        self.settings = QSettings(ORG_NAME, APP_NAME)
        self.info: ffmpeg.MediaInfo | None = None
        self._filmstrip: FilmstripWorker | None = None
        self._shutdown = threading.Event()
        self._probe_token = 0
        self._toast: Toast | None = None
        self._status_timer = QTimer(self)
        self._status_timer.setSingleShot(True)
        self._status_timer.timeout.connect(lambda: self._set_status("Listo", persist=True))
        self._probe_pool = QThreadPool(self)
        self._probe_pool.setMaxThreadCount(1)

        self._build_ui()
        self._build_actions()
        self._build_menu()
        self._wire()
        self._restore_state()
        self._update_media_actions()
        self._update_file_header()
        self._check_tools()
        QApplication.instance().installEventFilter(self)

    # ------------------------------------------------------------------ UI
    def _build_ui(self) -> None:
        central = QWidget()
        central.setObjectName("Central")
        self.setCentralWidget(central)
        outer = QVBoxLayout(central)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        outer.addWidget(self._build_top_bar())

        content = QWidget()
        content.setObjectName("Content")
        content_layout = QHBoxLayout(content)
        content_layout.setContentsMargins(14, 14, 14, 12)
        content_layout.setSpacing(12)

        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter.setChildrenCollapsible(False)
        self.splitter.setHandleWidth(8)

        explorer_panel = QFrame()
        explorer_panel.setObjectName("Panel")
        explorer_layout = QVBoxLayout(explorer_panel)
        explorer_layout.setContentsMargins(2, 2, 2, 2)
        self.explorer = FileExplorer()
        explorer_layout.addWidget(self.explorer)
        explorer_panel.setMinimumWidth(250)
        explorer_panel.setMaximumWidth(430)

        preview_column = QWidget()
        preview_column.setObjectName("PreviewColumn")
        preview_layout = QVBoxLayout(preview_column)
        preview_layout.setContentsMargins(0, 0, 0, 0)
        preview_layout.setSpacing(10)

        self.player = PlayerWidget()
        preview_layout.addWidget(self.player, 1)

        timeline_panel = QFrame()
        timeline_panel.setObjectName("TimelinePanel")
        timeline_panel.setStyleSheet(
            f"QFrame#TimelinePanel {{ background-color: {COLORS['panel']};"
            f" border: 1px solid {COLORS['border_soft']}; border-radius: 12px; }}"
        )
        timeline_layout = QVBoxLayout(timeline_panel)
        timeline_layout.setContentsMargins(14, 11, 14, 10)
        timeline_layout.setSpacing(8)

        timeline_header = QHBoxLayout()
        timeline_header.setSpacing(6)
        timeline_title = QLabel("LÍNEA DE TIEMPO")
        timeline_title.setObjectName("PanelTitle")
        timeline_header.addWidget(timeline_title)
        timeline_header.addStretch(1)
        self.mark_in_button = self._timeline_tool_button(
            trim_in_icon(), "Fijar el In del recorte en el playhead (I)"
        )
        self.mark_out_button = self._timeline_tool_button(
            trim_out_icon(), "Fijar el Out del recorte en el playhead (O)"
        )
        self.reset_selection_button = self._timeline_tool_button(
            full_range_icon(), "Seleccionar el video completo (R)"
        )
        timeline_header.addWidget(self.mark_in_button)
        timeline_header.addWidget(self.mark_out_button)
        timeline_header.addWidget(self.reset_selection_button)
        timeline_layout.addLayout(timeline_header)

        self.timeline = TimelineWidget()
        timeline_layout.addWidget(self.timeline)

        selection_row = QHBoxLayout()
        selection_row.setSpacing(18)
        in_layout, self.in_value = self._selection_stat("IN", "SelectionIn")
        out_layout, self.out_value = self._selection_stat("OUT", "SelectionOut")
        duration_layout, self.duration_value = self._selection_stat("DURACIÓN", "TimecodeMuted")
        selection_row.addLayout(in_layout)
        selection_row.addLayout(out_layout)
        selection_row.addLayout(duration_layout)
        self.frames_label = QLabel("")
        self.frames_label.setObjectName("MutedSmall")
        selection_row.addWidget(self.frames_label)
        selection_row.addStretch(1)
        hint = QLabel("Arrastra los tiradores · rueda del ratón para afinar · I / O para marcar")
        hint.setObjectName("MutedSmall")
        selection_row.addWidget(hint)
        timeline_layout.addLayout(selection_row)

        preview_layout.addWidget(timeline_panel)

        self.splitter.addWidget(explorer_panel)
        self.splitter.addWidget(preview_column)
        self.splitter.setStretchFactor(0, 0)
        self.splitter.setStretchFactor(1, 1)
        self.splitter.setSizes([290, 980])
        content_layout.addWidget(self.splitter, 1)
        outer.addWidget(content, 1)

        status = self.statusBar()
        status.setSizeGripEnabled(False)
        self.status_label = QLabel("Listo")
        self.status_label.setObjectName("MutedSmall")
        status.addWidget(self.status_label, 1)
        self.strip_status = QLabel("")
        self.strip_status.setObjectName("MutedSmall")
        status.addPermanentWidget(self.strip_status)
        self.ffmpeg_status = QLabel("")
        self.ffmpeg_status.setObjectName("MutedSmall")
        status.addPermanentWidget(self.ffmpeg_status)

        self._toast = Toast(central)
        self._update_selection_ui(0.0, 0.0, 0.0)

    def _build_top_bar(self) -> QFrame:
        bar = QFrame()
        bar.setObjectName("TopBar")
        bar.setFixedHeight(64)
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(16, 8, 16, 8)
        layout.setSpacing(12)

        badge = QLabel("QC")
        badge.setObjectName("AppBadge")
        badge.setFixedSize(34, 30)
        badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        badge.setStyleSheet(
            f"background-color: {COLORS['accent']}; color: #04140b; border-radius: 8px;"
            " font-size: 14px; font-weight: 900; letter-spacing: 1px;"
        )
        layout.addWidget(badge)

        brand = QVBoxLayout()
        brand.setSpacing(0)
        title = QLabel("QuickClip")
        title.setObjectName("AppTitle")
        subtitle = QLabel("EDITOR RÁPIDO DE CLIPS")
        subtitle.setStyleSheet(
            f"color: {COLORS['dim']}; font-size: 9px; font-weight: 700; letter-spacing: 1.5px;"
        )
        brand.addWidget(title)
        brand.addWidget(subtitle)
        layout.addLayout(brand)

        divider = QFrame()
        divider.setFixedSize(1, 30)
        divider.setStyleSheet(f"background-color: {COLORS['border_soft']};")
        layout.addWidget(divider)

        file_info = QVBoxLayout()
        file_info.setSpacing(1)
        self.file_name_label = QLabel("Sin video cargado")
        self.file_name_label.setStyleSheet(
            f"color: {COLORS['muted']}; font-size: 13px; font-weight: 600;"
        )
        self.file_meta_label = QLabel("Abre o arrastra un archivo para empezar")
        self.file_meta_label.setObjectName("MutedSmall")
        file_info.addWidget(self.file_name_label)
        file_info.addWidget(self.file_meta_label)
        layout.addLayout(file_info, 1)

        self.open_button = QPushButton("Abrir video")
        self.open_button.setProperty("variant", "ghost")
        self.open_button.setToolTip("Abrir un video (Ctrl+O)")
        self.export_button = QPushButton("Exportar clip")
        self.export_button.setProperty("variant", "primary")
        self.export_button.setToolTip("Recortar y guardar el clip (Ctrl+E)")
        layout.addWidget(self.open_button)
        layout.addWidget(self.export_button)
        return bar

    @staticmethod
    def _timeline_tool_button(icon, tooltip: str) -> QPushButton:
        button = QPushButton()
        button.setProperty("variant", "iconChip")
        button.setIcon(icon)
        button.setIconSize(QSize(16, 16))
        button.setFixedSize(30, 28)
        button.setToolTip(tooltip)
        button.setAccessibleName(tooltip)
        return button

    @staticmethod
    def _selection_stat(title: str, value_name: str) -> tuple[QVBoxLayout, QLabel]:
        column = QVBoxLayout()
        column.setSpacing(1)
        label = QLabel(title)
        label.setObjectName("MutedSmall")
        value = QLabel("00:00.000")
        value.setObjectName(value_name)
        if value_name == "TimecodeMuted":
            value.setStyleSheet(
                "font-family: 'JetBrains Mono', 'Ubuntu Mono', monospace;"
                f" color: {COLORS['text']}; font-weight: 700;"
            )
        column.addWidget(label)
        column.addWidget(value)
        return column, value

    def _build_actions(self) -> None:
        self.open_action = QAction("Abrir video…", self)
        self.open_action.setShortcut(QKeySequence.StandardKey.Open)
        self.open_action.triggered.connect(self.open_dialog)

        self.export_action = QAction("Exportar recorte…", self)
        self.export_action.setShortcut(QKeySequence("Ctrl+E"))
        self.export_action.triggered.connect(self.export_clip)

        self.quit_action = QAction("Salir", self)
        self.quit_action.setShortcut(QKeySequence.StandardKey.Quit)
        self.quit_action.triggered.connect(self.close)

        self.mark_in_action = QAction(trim_in_icon(), "Marcar In\tI", self)
        self.mark_in_action.triggered.connect(self.mark_in)
        self.mark_out_action = QAction(trim_out_icon(), "Marcar Out\tO", self)
        self.mark_out_action.triggered.connect(self.mark_out)
        self.reset_selection_action = QAction(full_range_icon(), "Seleccionar todo\tR", self)
        self.reset_selection_action.triggered.connect(self.reset_selection)

        self.play_action = QAction("Reproducir / pausar\tEspacio", self)
        self.play_action.triggered.connect(self.player.toggle_play)
        self.step_back_action = QAction("Fotograma anterior\t←", self)
        self.step_back_action.triggered.connect(lambda: self.player.step_frames(-1))
        self.step_forward_action = QAction("Fotograma siguiente\t→", self)
        self.step_forward_action.triggered.connect(lambda: self.player.step_frames(1))
        self.start_action = QAction("Ir al In del recorte\tInicio", self)
        self.start_action.triggered.connect(self.player.go_start)
        self.end_action = QAction("Ir al Out del recorte\tFin", self)
        self.end_action.triggered.connect(self.player.go_end)

        self.about_action = QAction("Acerca de QuickClip", self)
        self.about_action.triggered.connect(self.show_about)
        self.cache_action = QAction("Abrir carpeta de caché", self)
        self.cache_action.triggered.connect(self.open_cache_folder)

        self._media_actions = [
            self.export_action,
            self.mark_in_action,
            self.mark_out_action,
            self.reset_selection_action,
            self.play_action,
            self.step_back_action,
            self.step_forward_action,
            self.start_action,
            self.end_action,
        ]

    def _build_menu(self) -> None:
        menu = self.menuBar()
        file_menu = menu.addMenu("Archivo")
        file_menu.addAction(self.open_action)
        file_menu.addAction(self.export_action)
        file_menu.addSeparator()
        file_menu.addAction(self.quit_action)

        edit_menu = menu.addMenu("Edición")
        edit_menu.addAction(self.mark_in_action)
        edit_menu.addAction(self.mark_out_action)
        edit_menu.addAction(self.reset_selection_action)

        play_menu = menu.addMenu("Reproducción")
        play_menu.addAction(self.play_action)
        play_menu.addAction(self.step_back_action)
        play_menu.addAction(self.step_forward_action)
        play_menu.addSeparator()
        play_menu.addAction(self.start_action)
        play_menu.addAction(self.end_action)

        help_menu = menu.addMenu("Ayuda")
        help_menu.addAction(self.about_action)
        help_menu.addAction(self.cache_action)

    def _wire(self) -> None:
        self.open_button.clicked.connect(self.open_dialog)
        self.export_button.clicked.connect(self.export_clip)
        self.explorer.file_activated.connect(self.open_path)
        self.explorer.status_message.connect(lambda text: self._set_status(text))

        self.player.time_changed.connect(self._on_time_changed)
        self.player.error.connect(lambda message: self._notify(message, "error"))
        self.player.status.connect(lambda message: self._set_status(message))

        self.timeline.seeking.connect(self.player.seek)
        self.timeline.seek_committed.connect(self.player.seek)
        self.timeline.drag_started.connect(self.player.begin_scrub)
        self.timeline.drag_ended.connect(self.player.end_scrub)
        self.timeline.selection_changed.connect(self._on_selection_changed)
        self.timeline.error.connect(lambda message: self._notify(message, "error"))

        self.mark_in_button.clicked.connect(self.mark_in)
        self.mark_out_button.clicked.connect(self.mark_out)
        self.reset_selection_button.clicked.connect(self.reset_selection)

    # --------------------------------------------------------------- state
    def _restore_state(self) -> None:
        geometry = self.settings.value("window/geometry")
        if geometry:
            self.restoreGeometry(geometry)
        sizes = self.settings.value("window/splitter")
        if sizes:
            try:
                self.splitter.setSizes([int(value) for value in sizes])
            except (TypeError, ValueError):
                pass
        last_folder = self.settings.value("paths/last_folder")
        if last_folder and Path(last_folder).is_dir():
            self.explorer.set_root(last_folder)
        else:
            folders = default_video_dirs()
            self.explorer.set_root(folders[0] if folders else Path.home())

    def _save_state(self) -> None:
        self.settings.setValue("window/geometry", self.saveGeometry())
        self.settings.setValue("window/splitter", self.splitter.sizes())
        self.settings.setValue("paths/last_folder", self.explorer.current_folder())

    def _check_tools(self) -> None:
        ok, missing = ffmpeg.tools_available()
        if ok:
            self.ffmpeg_status.setText("● FFmpeg listo")
            self.ffmpeg_status.setStyleSheet(
                f"color: {COLORS['accent_dim']}; font-size: 11px;"
            )
            self.ffmpeg_status.setToolTip("FFmpeg y FFprobe detectados en el sistema")
        else:
            self.ffmpeg_status.setText("● FFmpeg no encontrado")
            self.ffmpeg_status.setStyleSheet(
                f"color: {COLORS['danger']}; font-size: 11px; font-weight: 700;"
            )
            self.ffmpeg_status.setToolTip("Instala FFmpeg con: sudo apt install ffmpeg")
            QTimer.singleShot(
                350,
                lambda: QMessageBox.warning(
                    self,
                    "FFmpeg no encontrado",
                    "QuickClip necesita FFmpeg para leer, previsualizar y recortar video.\n\n"
                    "Instálalo en Ubuntu con:\n    sudo apt install ffmpeg",
                ),
            )

    def _update_media_actions(self) -> None:
        enabled = self.info is not None
        for action in self._media_actions:
            action.setEnabled(enabled)
        self.export_button.setEnabled(enabled)
        self.mark_in_button.setEnabled(enabled)
        self.mark_out_button.setEnabled(enabled)
        self.reset_selection_button.setEnabled(enabled)

    def _update_file_header(self) -> None:
        if self.info is None:
            self.file_name_label.setText("Sin video cargado")
            self.file_name_label.setStyleSheet(
                f"color: {COLORS['muted']}; font-size: 13px; font-weight: 600;"
            )
            self.file_meta_label.setText("Abre o arrastra un archivo para empezar")
            self.setWindowTitle(f"{APP_NAME} — Editor rápido de clips")
            return
        info = self.info
        name = Path(info.path).name
        metrics = QFontMetrics(self.file_name_label.font())
        elided = metrics.elidedText(name, Qt.TextElideMode.ElideMiddle, 430)
        self.file_name_label.setText(elided)
        self.file_name_label.setToolTip(info.path)
        self.file_name_label.setStyleSheet(
            f"color: {COLORS['text']}; font-size: 13px; font-weight: 600;"
        )
        self.file_meta_label.setText(
            f"{info.display_width}×{info.display_height}  ·  {info.safe_fps:.2f} fps  ·  "
            f"{ffmpeg.format_short_time(info.duration)}  ·  {info.video_codec.upper()}"
            f"{'  ·  ' + human_size(info.size) if info.size else ''}"
        )
        self.setWindowTitle(f"{name} — {APP_NAME}")

    def _on_selection_changed(self, in_point: float, out_point: float) -> None:
        self.player.set_playback_range(in_point, out_point)
        self._update_selection_ui(in_point, out_point, out_point - in_point)
        duration = ffmpeg.format_short_time(out_point - in_point)
        self.export_button.setToolTip(f"Recortar y guardar {duration} (Ctrl+E)")

    def _update_selection_ui(self, in_point: float, out_point: float, duration: float) -> None:
        self.in_value.setText(ffmpeg.format_timecode(in_point))
        self.out_value.setText(ffmpeg.format_timecode(out_point))
        self.duration_value.setText(ffmpeg.format_timecode(duration))
        if self.info is not None:
            frames = max(1, int(round(duration * self.info.safe_fps)))
            self.frames_label.setText(f"· {frames} fotogramas")
        else:
            self.frames_label.setText("")

    def _on_time_changed(self, current: float, _duration: float) -> None:
        self.timeline.set_playhead(current)

    # ---------------------------------------------------------------- media
    def open_dialog(self) -> None:
        start_dir = self.settings.value("paths/open_dir")
        if not start_dir or not Path(start_dir).is_dir():
            start_dir = self.explorer.current_folder()
        patterns = " ".join(f"*{ext}" for ext in VIDEO_EXTENSIONS)
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Abrir video",
            str(start_dir),
            f"Videos ({patterns});;Todos los archivos (*)",
        )
        if path:
            self.open_path(path)

    def open_path(self, path: str) -> None:
        candidate = Path(path).expanduser()
        if candidate.is_dir():
            self.explorer.set_root(candidate)
            return
        if not candidate.is_file():
            self._notify("El archivo no existe", "error")
            return
        if not is_video_file(candidate):
            self._notify("Formato de video no admitido", "warning")
            return

        self.settings.setValue("paths/open_dir", str(candidate.parent))
        self._set_status(f"Analizando {candidate.name}…")
        self.file_name_label.setText(f"Analizando {candidate.name}…")
        token = self._probe_token + 1
        self._probe_token = token
        task = FunctionTask(ffmpeg.probe_media, str(candidate), self._shutdown)
        task.signals.result.connect(lambda info: self._on_probe_ok(token, info))
        task.signals.error.connect(lambda message: self._on_probe_error(token, message))
        self._probe_pool.start(task)

    def _on_probe_ok(self, token: int, info: ffmpeg.MediaInfo) -> None:
        if token != self._probe_token:
            return
        self.info = info
        self.player.set_media(info)
        self.timeline.set_media(info)
        self.timeline.set_playhead(0.0)
        self._update_selection_ui(0.0, info.duration, info.duration)
        self._start_filmstrip(info)
        self._update_file_header()
        self._update_media_actions()
        self.settings.setValue("paths/last_folder", str(Path(info.path).parent))
        self.explorer.set_root(Path(info.path).parent)
        self._set_status(
            f"Video cargado · {ffmpeg.format_short_time(info.duration)} ·"
            f" {info.display_width}×{info.display_height}"
        )

    def _on_probe_error(self, token: int, message: str) -> None:
        if token != self._probe_token:
            return
        self._update_file_header()
        self._notify(message, "error")
        self._set_status("No se pudo abrir el video")

    # ----------------------------------------------------------- filmstrip
    def _start_filmstrip(self, info: ffmpeg.MediaInfo) -> None:
        self._stop_filmstrip()
        count = FILMSTRIP_COUNT if info.duration >= 8 else max(8, int(info.duration * 3))
        worker = FilmstripWorker(info.path, info.duration, count, self)
        self._filmstrip = worker
        self.timeline.set_filmstrip_state(True, "Generando miniaturas…")
        self.strip_status.setText("Miniaturas 0%")

        def on_thumbnail(index, image, worker=worker):
            if self._filmstrip is not worker:
                return
            self.timeline.set_thumbnail(index, image)
            loaded = sum(1 for thumb in self.timeline._thumbs if thumb is not None)
            self.strip_status.setText(f"Miniaturas {int(loaded / count * 100)}%")

        def on_completed(generated, failures, worker=worker):
            if self._filmstrip is not worker:
                return
            self.timeline.set_filmstrip_state(False)
            self.strip_status.setText("")
            if failures and not generated:
                self._set_status("No se pudieron generar las miniaturas", persist=False)
            elif failures:
                self._set_status(f"Miniaturas listas · {generated} correctas, {failures} fallidas")

        def on_error(message, worker=worker):
            if self._filmstrip is not worker:
                return
            self.timeline.set_filmstrip_state(False)
            self._set_status(f"No se pudieron generar miniaturas: {message}")

        worker.thumbnail.connect(on_thumbnail)
        worker.completed.connect(on_completed)
        worker.error.connect(on_error)
        worker.finished.connect(lambda worker=worker: self._on_filmstrip_finished(worker))
        worker.start()

    def _on_filmstrip_finished(self, worker: FilmstripWorker) -> None:
        if self._filmstrip is worker:
            self._filmstrip = None
        worker.deleteLater()

    def _stop_filmstrip(self) -> None:
        worker = self._filmstrip
        self._filmstrip = None
        if worker is not None:
            try:
                worker.stop()
                worker.wait(2000)
            except RuntimeError:
                pass

    # ------------------------------------------------------------ selection
    def mark_in(self) -> None:
        if self.info is None:
            return
        playhead = min(self.player.playhead, self.timeline.out_point - self.timeline.min_gap)
        self.timeline.set_selection(playhead, self.timeline.out_point)
        self._set_status(f"In marcado en {ffmpeg.format_timecode(self.timeline.in_point)}")

    def mark_out(self) -> None:
        if self.info is None:
            return
        playhead = max(self.player.playhead, self.timeline.in_point + self.timeline.min_gap)
        self.timeline.set_selection(self.timeline.in_point, min(playhead, self.timeline.duration))
        self._set_status(f"Out marcado en {ffmpeg.format_timecode(self.timeline.out_point)}")

    def reset_selection(self) -> None:
        if self.info is None:
            return
        self.timeline.set_selection(0.0, self.timeline.duration)
        self._set_status("Selección completa restaurada")

    # ------------------------------------------------------------- export
    def export_clip(self) -> None:
        if self.info is None:
            self._notify("Abre un video antes de exportar", "warning")
            return
        dialog = ExportDialog(
            self.info,
            self.timeline.in_point,
            self.timeline.out_point,
            self,
        )
        dialog.exported.connect(self._on_exported)
        dialog.exec()

    def _on_exported(self, path: str) -> None:
        self._notify(f"Clip exportado: {Path(path).name}", "success")
        self._set_status(f"Exportado en {path}")
        self.settings.setValue("paths/last_folder", str(Path(path).parent))

    # ------------------------------------------------------------ feedback
    def _set_status(self, text: str, persist: bool = False) -> None:
        self.status_label.setText(text)
        self._status_timer.stop()
        if not persist:
            self._status_timer.start(7000)

    def _notify(self, text: str, kind: str = "info") -> None:
        if self._toast is not None:
            self._toast.show_message(text, kind)

    def open_cache_folder(self) -> None:
        from .config import cache_root

        from PyQt6.QtCore import QUrl
        from PyQt6.QtGui import QDesktopServices

        QDesktopServices.openUrl(QUrl.fromLocalFile(str(cache_root())))

    def show_about(self) -> None:
        ok, _ = ffmpeg.tools_available()
        text = (
            f"<b style='font-size:16px;'>QuickClip {APP_VERSION}</b><br>"
            "<span style='color:#8c8ca2;'>Editor minimalista de recortes para Ubuntu.</span>"
            "<br><br>"
            "Arrastra un video, ajusta los tiradores <b style='color:#2bff88;'>In</b> / "
            "<b style='color:#9b6bff;'>Out</b> y exporta en segundos."
            "<br><br>"
            f"FFmpeg: {'detectado' if ok else '<span style=\"color:#ff5470;\">no encontrado</span>'}"
            "<br>"
            "Atajos: Espacio · I · O · ←/→ · Ctrl+O · Ctrl+E"
        )
        box = QMessageBox(self)
        box.setWindowTitle("Acerca de QuickClip")
        box.setTextFormat(Qt.TextFormat.RichText)
        box.setText(text)
        box.setStandardButtons(QMessageBox.StandardButton.Ok)
        box.exec()

    # -------------------------------------------------------------- events
    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        if self._toast is not None:
            self._toast._reposition()

    def dragEnterEvent(self, event) -> None:  # noqa: N802
        mime = event.mimeData()
        if mime.hasUrls():
            for url in mime.urls():
                if url.isLocalFile():
                    path = Path(url.toLocalFile())
                    if path.is_dir() or is_video_file(path):
                        event.acceptProposedAction()
                        return
        event.ignore()

    def dragMoveEvent(self, event) -> None:  # noqa: N802
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event) -> None:  # noqa: N802
        for url in event.mimeData().urls():
            if not url.isLocalFile():
                continue
            path = Path(url.toLocalFile())
            if path.is_dir():
                self.explorer.set_root(path)
                event.acceptProposedAction()
                return
            if is_video_file(path) or path.is_file():
                self.open_path(str(path))
                event.acceptProposedAction()
                return
        event.ignore()

    def eventFilter(self, obj, event) -> bool:  # noqa: N802
        if event.type() != QEvent.Type.KeyPress:
            return super().eventFilter(obj, event)
        if not self.isActiveWindow():
            return super().eventFilter(obj, event)
        app = QApplication.instance()
        if app is not None and (
            app.activeModalWidget() is not None or app.activePopupWidget() is not None
        ):
            return super().eventFilter(obj, event)
        focus = app.focusWidget() if app is not None else None
        if isinstance(focus, (QLineEdit, QAbstractSpinBox, QComboBox, QTextEdit, QPlainTextEdit)):
            return super().eventFilter(obj, event)
        if self.info is None:
            return super().eventFilter(obj, event)

        key = event.key()
        modifiers = event.modifiers()
        no_mods = modifiers in (
            Qt.KeyboardModifier.NoModifier,
            Qt.KeyboardModifier.KeypadModifier,
        )
        if no_mods and key == Qt.Key.Key_Space and not event.isAutoRepeat():
            self.player.toggle_play()
            return True
        if no_mods and key == Qt.Key.Key_I and not event.isAutoRepeat():
            self.mark_in()
            return True
        if no_mods and key == Qt.Key.Key_O and not event.isAutoRepeat():
            self.mark_out()
            return True
        if no_mods and key == Qt.Key.Key_R and not event.isAutoRepeat():
            self.reset_selection()
            return True
        if key == Qt.Key.Key_Left:
            if modifiers & Qt.KeyboardModifier.ShiftModifier:
                self.player.seek(self.player.playhead - 1.0)
            else:
                self.player.step_frames(-1)
            return True
        if key == Qt.Key.Key_Right:
            if modifiers & Qt.KeyboardModifier.ShiftModifier:
                self.player.seek(self.player.playhead + 1.0)
            else:
                self.player.step_frames(1)
            return True
        if no_mods and key == Qt.Key.Key_Home and not event.isAutoRepeat():
            self.player.go_start()
            return True
        if no_mods and key == Qt.Key.Key_End and not event.isAutoRepeat():
            self.player.go_end()
            return True
        return super().eventFilter(obj, event)

    def closeEvent(self, event) -> None:  # noqa: N802
        debug_exit_log("closeEvent start")
        watchdog = threading.Timer(6.0, lambda: (debug_exit_log("watchdog fired"), os._exit(0)))
        watchdog.daemon = True
        watchdog.start()
        self._shutdown.set()
        self.player.shutdown()
        debug_exit_log("player shutdown done")
        self._stop_filmstrip()
        debug_exit_log("filmstrip stopped")
        self._probe_pool.waitForDone(2000)
        debug_exit_log("probe pool done")
        self._save_state()
        try:
            QApplication.instance().removeEventFilter(self)
        except Exception:  # noqa: BLE001
            pass
        event.accept()
        debug_exit_log("closeEvent accepted")
        app = QApplication.instance()
        if app is not None:
            QTimer.singleShot(0, app.quit)
