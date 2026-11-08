"""Diálogo de exportación con renombrado en línea y gestión de colisiones."""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import QUrl, pyqtSignal
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from . import ffmpeg
from .config import OUTPUT_EXTENSIONS, human_size
from .theme import COLORS
from .workers import ExportWorker


def _mono_label(text: str, color: str = COLORS["text"], size: int = 15) -> QLabel:
    label = QLabel(text)
    label.setStyleSheet(
        f"color: {color}; font-family: 'JetBrains Mono', 'Ubuntu Mono', monospace;"
        f" font-size: {size}px; font-weight: 700;"
    )
    return label


def _small_title(text: str) -> QLabel:
    label = QLabel(text.upper())
    label.setStyleSheet(
        f"color: {COLORS['muted']}; font-size: 10px; font-weight: 700; letter-spacing: 1px;"
    )
    return label


class ExportDialog(QDialog):
    exported = pyqtSignal(str)

    def __init__(
        self,
        info: ffmpeg.MediaInfo,
        in_point: float,
        out_point: float,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("ExportDialog")
        self.setWindowTitle("Exportar clip")
        self.setModal(True)
        self.setMinimumWidth(590)
        self.info = info
        self.in_point = max(0.0, in_point)
        self.out_point = max(self.in_point, out_point)
        self.duration = max(0.0, self.out_point - self.in_point)
        self._worker: ExportWorker | None = None
        self._success = False
        self._last_output: str | None = None

        default_ext = ffmpeg.output_extension(info.path)
        if default_ext not in OUTPUT_EXTENSIONS:
            default_ext = ".mp4"

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 22, 24, 20)
        root.setSpacing(16)

        header = QVBoxLayout()
        header.setSpacing(4)
        title = QLabel("Exportar recorte")
        title.setStyleSheet("font-size: 20px; font-weight: 800;")
        subtitle = QLabel(Path(info.path).name)
        subtitle.setObjectName("Muted")
        header.addWidget(title)
        header.addWidget(subtitle)
        root.addLayout(header)

        root.addWidget(self._build_summary())

        self.form_card = QFrame()
        self.form_card.setObjectName("Card")
        form = QVBoxLayout(self.form_card)
        form.setContentsMargins(16, 14, 16, 14)
        form.setSpacing(8)

        form.addWidget(_small_title("Carpeta de destino"))
        folder_row = QHBoxLayout()
        folder_row.setSpacing(8)
        self.folder_edit = QLineEdit(str(Path(info.path).parent))
        self.folder_edit.textChanged.connect(self._refresh_warning)
        self.browse_button = QPushButton("Elegir…")
        self.browse_button.clicked.connect(self._browse_folder)
        folder_row.addWidget(self.folder_edit, 1)
        folder_row.addWidget(self.browse_button)
        form.addLayout(folder_row)

        form.addSpacing(4)
        form.addWidget(_small_title("Nombre del archivo"))
        name_row = QHBoxLayout()
        name_row.setSpacing(8)
        self.name_edit = QLineEdit(f"{Path(info.path).stem}_clip")
        self.name_edit.setPlaceholderText("mi_clip")
        self.name_edit.textChanged.connect(self._refresh_warning)
        self.extension_combo = QComboBox()
        for ext in OUTPUT_EXTENSIONS:
            self.extension_combo.addItem(ext.upper().lstrip("."), ext)
        index = self.extension_combo.findData(default_ext)
        self.extension_combo.setCurrentIndex(index if index >= 0 else 0)
        self.extension_combo.currentIndexChanged.connect(self._refresh_warning)
        name_row.addWidget(self.name_edit, 1)
        name_row.addWidget(self.extension_combo)
        form.addLayout(name_row)

        form.addSpacing(4)
        hint = QLabel(
            "Corte preciso al fotograma. El video se codifica en H.264 de alta calidad "
            "y el audio se conserva sin recodificar cuando el formato lo permite."
        )
        hint.setObjectName("MutedSmall")
        hint.setWordWrap(True)
        form.addWidget(hint)
        root.addWidget(self.form_card)

        self.warning_banner = self._banner("WarningBanner", "Archivo existente", "")
        self.warning_banner.hide()
        root.addWidget(self.warning_banner)

        self.error_banner = self._banner("ErrorBanner", "No se pudo exportar", "")
        self.error_banner.hide()
        root.addWidget(self.error_banner)

        self.success_banner = self._banner("SuccessBanner", "Clip exportado", "")
        self.success_banner.hide()
        root.addWidget(self.success_banner)

        self.progress_box = QWidget()
        progress_layout = QVBoxLayout(self.progress_box)
        progress_layout.setContentsMargins(0, 0, 0, 0)
        progress_layout.setSpacing(6)
        self.status_label = QLabel("Preparando recorte…")
        self.status_label.setObjectName("MutedSmall")
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setTextVisible(False)
        progress_layout.addWidget(self.status_label)
        progress_layout.addWidget(self.progress)
        self.progress_box.hide()
        root.addWidget(self.progress_box)

        footer = QHBoxLayout()
        footer.setSpacing(8)
        self.open_folder_button = QPushButton("Abrir carpeta")
        self.open_folder_button.setProperty("variant", "ghost")
        self.open_folder_button.clicked.connect(self._open_folder)
        self.open_folder_button.hide()
        footer.addWidget(self.open_folder_button)
        footer.addStretch(1)
        self.cancel_button = QPushButton("Cancelar")
        self.cancel_button.clicked.connect(self._on_cancel)
        self.export_button = QPushButton("Exportar clip")
        self.export_button.setProperty("variant", "primary")
        self.export_button.clicked.connect(self._on_export_clicked)
        footer.addWidget(self.cancel_button)
        footer.addWidget(self.export_button)
        root.addLayout(footer)

        self._refresh_warning()
        if self.duration <= 0.04:
            self._show_error("La selección es demasiado corta para exportar.")
            self.export_button.setEnabled(False)

    # ------------------------------------------------------------------ UI
    def _build_summary(self) -> QFrame:
        card = QFrame()
        card.setObjectName("Card")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(10)

        grid = QGridLayout()
        grid.setHorizontalSpacing(26)
        grid.setVerticalSpacing(2)

        stats = [
            ("Entrada", ffmpeg.format_timecode(self.in_point), COLORS["accent"]),
            ("Salida", ffmpeg.format_timecode(self.out_point), COLORS["violet"]),
            ("Duración", ffmpeg.format_timecode(self.duration), COLORS["text"]),
        ]
        for column, (title, value, color) in enumerate(stats):
            grid.addWidget(_small_title(title), 0, column)
            grid.addWidget(_mono_label(value, color), 1, column)
        layout.addLayout(grid)

        meta = QLabel(
            f"{self.info.display_width}×{self.info.display_height}  ·  "
            f"{self.info.safe_fps:.2f} fps  ·  {self.info.video_codec.upper() or 'VIDEO'}"
            f"{'  ·  ' + self.info.audio_codec.upper() if self.info.has_audio else '  ·  sin audio'}"
            f"  ·  origen {human_size(self.info.size)}"
        )
        meta.setObjectName("MutedSmall")
        meta.setWordWrap(True)
        layout.addWidget(meta)
        return card

    def _banner(self, object_name: str, title: str, text: str) -> QFrame:
        frame = QFrame()
        frame.setObjectName(object_name)
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(3)
        title_label = QLabel(title)
        title_label.setObjectName("BannerTitle")
        if object_name == "WarningBanner":
            title_label.setProperty("class", "WarningTitle")
            title_label.setStyleSheet(f"color: {COLORS['warning']}; font-weight: 700;")
        elif object_name == "SuccessBanner":
            title_label.setStyleSheet(f"color: {COLORS['accent']}; font-weight: 700;")
        else:
            title_label.setStyleSheet(f"color: {COLORS['danger']}; font-weight: 700;")
        text_label = QLabel(text)
        text_label.setObjectName("BannerText")
        text_label.setWordWrap(True)
        layout.addWidget(title_label)
        layout.addWidget(text_label)
        frame._title = title_label  # type: ignore[attr-defined]
        frame._text = text_label  # type: ignore[attr-defined]
        return frame

    @staticmethod
    def _set_banner(frame: QFrame, title: str | None = None, text: str | None = None) -> None:
        if title is not None:
            frame._title.setText(title)  # type: ignore[attr-defined]
        if text is not None:
            frame._text.setText(text)  # type: ignore[attr-defined]
        frame.show()

    # ------------------------------------------------------------- target
    def target_folder(self) -> Path:
        return Path(self.folder_edit.text().strip()).expanduser()

    def target_name(self) -> str:
        return self.name_edit.text().strip()

    def target_path(self) -> Path:
        return self.target_folder() / f"{self.target_name()}{self.extension_combo.currentData()}"

    def _validate(self) -> str | None:
        name = self.target_name()
        if not name:
            return "Escribe un nombre para el archivo de salida."
        if "/" in name or "\\" in name:
            return "El nombre no puede contener barras."
        folder = self.target_folder()
        if not folder.exists():
            return "La carpeta de destino no existe."
        if not folder.is_dir():
            return "La ruta de destino no es una carpeta."
        target = self.target_path()
        try:
            if target.resolve() == Path(self.info.path).resolve():
                return "No puedes sobrescribir el video original. Elige otro nombre."
        except OSError:
            pass
        return None

    def _refresh_warning(self) -> None:
        if self._worker is not None and self._worker.isRunning():
            return
        target = self.target_path()
        if target.exists():
            suggestion = ffmpeg.next_available_path(target)
            self._set_banner(
                self.warning_banner,
                "El archivo ya existe",
                f"«{target.name}» ya está en esa carpeta. Al exportar podrás sobrescribirlo "
                f"o crear «{suggestion.name}». También puedes cambiar el nombre ahora.",
            )
        else:
            self.warning_banner.hide()
        invalid = not self.target_name() or "/" in self.target_name()
        self.name_edit.setProperty("invalid", "true" if invalid else "false")
        self.name_edit.style().unpolish(self.name_edit)
        self.name_edit.style().polish(self.name_edit)

    def _browse_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(
            self,
            "Elegir carpeta de destino",
            str(self.target_folder()),
        )
        if folder:
            self.folder_edit.setText(folder)

    # ------------------------------------------------------------- actions
    def _on_export_clicked(self) -> None:
        error = self._validate()
        if error:
            self._show_error(error)
            return
        self.error_banner.hide()
        self.success_banner.hide()
        self.open_folder_button.hide()
        target = self.target_path()
        if target.exists():
            target = self._ask_collision(target)
            if target is None:
                return
        self._start_export(target)

    def _ask_collision(self, target: Path) -> Path | None:
        suggestion = ffmpeg.next_available_path(target)
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Question)
        box.setWindowTitle("El archivo ya existe")
        box.setText(f"«{target.name}» ya existe en esta carpeta.")
        box.setInformativeText("¿Quieres sobrescribirlo o crear un archivo nuevo?")
        overwrite = box.addButton("Sobrescribir", QMessageBox.ButtonRole.DestructiveRole)
        create = box.addButton(f"Crear nuevo ({suggestion.name})", QMessageBox.ButtonRole.AcceptRole)
        box.addButton("Cancelar", QMessageBox.ButtonRole.RejectRole)
        box.setDefaultButton(create)
        box.exec()
        clicked = box.clickedButton()
        if clicked is create:
            self.name_edit.setText(suggestion.stem)
            self.extension_combo.setCurrentIndex(self.extension_combo.findData(suggestion.suffix))
            self._refresh_warning()
            return suggestion
        if clicked is overwrite:
            return target
        return None

    def _start_export(self, target: Path) -> None:
        self._success = False
        self._last_output = str(target)
        plan = ffmpeg.ExportPlan(
            source=self.info.path,
            output=str(target),
            start=self.in_point,
            duration=self.duration,
            video_codec=self.info.video_codec,
            audio_codec=self.info.audio_codec,
            pix_fmt=self.info.pix_fmt,
            has_audio=self.info.has_audio,
        )
        self.error_banner.hide()
        self.warning_banner.hide()
        self.success_banner.hide()
        self.progress.setValue(0)
        self.status_label.setText("Iniciando FFmpeg…")
        self.progress_box.show()
        self._set_busy(True)

        worker = ExportWorker(plan, self)
        worker.progress.connect(self._on_progress)
        worker.status.connect(self.status_label.setText)
        worker.succeeded.connect(self._on_success)
        worker.failed.connect(self._on_failure)
        worker.cancelled.connect(self._on_cancelled)
        worker.finished.connect(worker.deleteLater)
        self._worker = worker
        worker.start()

    def _set_busy(self, busy: bool) -> None:
        for widget in (
            self.folder_edit,
            self.name_edit,
            self.extension_combo,
            self.browse_button,
        ):
            widget.setEnabled(not busy)
        self.export_button.setEnabled(not busy)
        self.cancel_button.setText("Cancelar exportación" if busy else "Cancelar")
        self.cancel_button.setEnabled(True)

    def _on_progress(self, value: int, detail: str) -> None:
        self.progress.setValue(max(0, min(100, value)))
        self.status_label.setText(f"Exportando… {detail}")

    def _on_success(self, output: str) -> None:
        self._worker = None
        self._success = True
        self._last_output = output
        path = Path(output)
        try:
            size = human_size(path.stat().st_size)
        except OSError:
            size = ""
        self.progress.setValue(100)
        self.progress_box.hide()
        self.status_label.setText("")
        self._set_busy(False)
        self.export_button.setEnabled(False)
        self.cancel_button.setText("Cerrar")
        self.open_folder_button.show()
        for widget in (
            self.folder_edit,
            self.name_edit,
            self.extension_combo,
            self.browse_button,
        ):
            widget.setEnabled(False)
        detail = f"«{path.name}»{(' · ' + size) if size else ''} · corte preciso · alta calidad"
        self._set_banner(self.success_banner, "Clip exportado", detail)
        self.exported.emit(output)

    def _on_failure(self, message: str) -> None:
        self._worker = None
        self.progress_box.hide()
        self._set_busy(False)
        self._show_error(message)

    def _on_cancelled(self) -> None:
        self._worker = None
        self.progress_box.hide()
        self._set_busy(False)
        self._set_banner(
            self.warning_banner,
            "Exportación cancelada",
            "No se creó ningún archivo. Puedes ajustar los datos y volver a intentarlo.",
        )

    def _show_error(self, message: str) -> None:
        self._set_banner(self.error_banner, "No se pudo exportar", message)

    def _on_cancel(self) -> None:
        worker = self._worker
        if worker is not None and worker.isRunning():
            self.cancel_button.setEnabled(False)
            self.status_label.setText("Cancelando…")
            worker.cancel()
            return
        self.reject()

    def _open_folder(self) -> None:
        target = self.target_path()
        folder = target.parent if target else Path(self.folder_edit.text())
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))

    def closeEvent(self, event) -> None:  # noqa: N802
        worker = self._worker
        if worker is not None and worker.isRunning():
            box = QMessageBox(self)
            box.setIcon(QMessageBox.Icon.Warning)
            box.setWindowTitle("Exportación en curso")
            box.setText("Hay una exportación en curso.")
            box.setInformativeText("¿Quieres cancelarla y cerrar?")
            cancel = box.addButton("Seguir exportando", QMessageBox.ButtonRole.RejectRole)
            close = box.addButton("Cancelar y cerrar", QMessageBox.ButtonRole.DestructiveRole)
            box.exec()
            if box.clickedButton() is not close:
                event.ignore()
                return
            worker.cancel()
            worker.wait(3000)
        event.accept()

    def done(self, result: int) -> None:  # noqa: D102
        worker = self._worker
        if worker is not None and worker.isRunning():
            worker.cancel()
            worker.wait(3000)
        super().done(result)
