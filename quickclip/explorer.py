"""Explorador de archivos integrado con acceso rápido a carpetas de video."""

from __future__ import annotations

import os
from pathlib import Path

from PyQt6.QtCore import QDir, QModelIndex, QStandardPaths, Qt, pyqtSignal
from PyQt6.QtGui import QAction, QDesktopServices, QFileSystemModel
from PyQt6.QtWidgets import (
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QPushButton,
    QTreeView,
    QVBoxLayout,
    QWidget,
)
from PyQt6.QtCore import QUrl

from .config import VIDEO_EXTENSIONS, default_video_dirs, is_video_file


def _video_name_filters() -> list[str]:
    patterns: list[str] = []
    for ext in VIDEO_EXTENSIONS:
        patterns.append(f"*{ext}")
        patterns.append(f"*{ext.upper()}")
    return patterns


class FileExplorer(QWidget):
    file_activated = pyqtSignal(str)
    status_message = pyqtSignal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("FileExplorer")
        self._root_path = str(Path.home())

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 8, 8)
        layout.setSpacing(8)

        header = QHBoxLayout()
        header.setSpacing(6)
        title = QLabel("EXPLORADOR")
        title.setObjectName("PanelTitle")
        header.addWidget(title)
        header.addStretch(1)
        self.up_button = QPushButton("↑")
        self.up_button.setObjectName("TransportButton")
        self.up_button.setToolTip("Subir un nivel")
        self.up_button.clicked.connect(self.go_up)
        self.home_button = QPushButton("⌂")
        self.home_button.setObjectName("TransportButton")
        self.home_button.setToolTip("Ir a la carpeta personal")
        self.home_button.clicked.connect(lambda: self.set_root(Path.home()))
        header.addWidget(self.up_button)
        header.addWidget(self.home_button)
        layout.addLayout(header)

        self.path_edit = QLineEdit()
        self.path_edit.setPlaceholderText("/home/usuario/Videos")
        self.path_edit.setClearButtonEnabled(False)
        self.path_edit.returnPressed.connect(self._navigate_from_text)
        layout.addWidget(self.path_edit)

        chips = QGridLayout()
        chips.setHorizontalSpacing(4)
        chips.setVerticalSpacing(4)
        folders = default_video_dirs()[:4]
        for index, folder in enumerate(folders):
            button = QPushButton(self._folder_label(folder))
            button.setProperty("variant", "chip")
            button.setToolTip(str(folder))
            button.clicked.connect(lambda _checked=False, p=folder: self.set_root(p))
            chips.addWidget(button, index // 2, index % 2)
        chips.setColumnStretch(0, 1)
        chips.setColumnStretch(1, 1)
        layout.addLayout(chips)

        self.model = QFileSystemModel(self)
        self.model.setFilter(QDir.Filter.AllDirs | QDir.Filter.Files | QDir.Filter.NoDotAndDotDot)
        self.model.setNameFilters(_video_name_filters())
        self.model.setNameFilterDisables(False)
        self.model.setReadOnly(True)
        home = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.HomeLocation)
        self.model.setRootPath(home or str(Path.home()))

        self.tree = QTreeView()
        self.tree.setModel(self.model)
        self.tree.setRootIndex(self.model.index(self._root_path))
        self.tree.setHeaderHidden(True)
        self.tree.setAnimated(False)
        self.tree.setIndentation(14)
        self.tree.setUniformRowHeights(True)
        self.tree.setSortingEnabled(False)
        self.tree.setDragEnabled(True)
        self.tree.setDragDropMode(QTreeView.DragDropMode.DragOnly)
        self.tree.setEditTriggers(QTreeView.EditTrigger.NoEditTriggers)
        self.tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tree.setColumnHidden(1, True)
        self.tree.setColumnHidden(2, True)
        self.tree.setColumnHidden(3, True)
        self.tree.doubleClicked.connect(self._on_double_click)
        self.tree.selectionModel().currentChanged.connect(self._on_current_changed)
        self.tree.customContextMenuRequested.connect(self._show_menu)
        layout.addWidget(self.tree, 1)

        self._update_path()

    @staticmethod
    def _folder_label(path: Path) -> str:
        name = path.name
        mapping = {
            "Videos": "Videos",
            "Vídeos": "Vídeos",
            "Captures": "Capturas",
            "Desktop": "Escritorio",
            "Escritorio": "Escritorio",
            "Downloads": "Descargas",
            "Descargas": "Descargas",
        }
        if path == Path.home():
            return "Inicio"
        return mapping.get(name, name)

    def current_folder(self) -> str:
        return self._root_path

    def set_root(self, path: str | Path) -> None:
        path = Path(path).expanduser()
        if not path.is_dir():
            self.status_message.emit(f"La carpeta no existe: {path}")
            return
        self._root_path = str(path)
        index = self.model.index(self._root_path)
        self.tree.setRootIndex(index)
        self.tree.setCurrentIndex(index)
        self._update_path()
        self.status_message.emit(f"Carpeta: {self._root_path}")

    def go_up(self) -> None:
        parent = Path(self._root_path).parent
        if parent != Path(self._root_path):
            self.set_root(parent)

    def _update_path(self) -> None:
        self.path_edit.setText(self._root_path)

    def _navigate_from_text(self) -> None:
        raw = self.path_edit.text().strip()
        if not raw:
            return
        self.set_root(Path(os.path.expandvars(raw)).expanduser())

    def _on_double_click(self, index: QModelIndex) -> None:
        path = self.model.filePath(index)
        if self.model.isDir(index):
            self.set_root(path)
        elif is_video_file(path):
            self.file_activated.emit(path)

    def _on_current_changed(self, current: QModelIndex, _previous: QModelIndex) -> None:
        if not current.isValid():
            return
        path = self.model.filePath(current)
        if not self.model.isDir(current) and is_video_file(path):
            self.status_message.emit(path)

    def _show_menu(self, position) -> None:
        index = self.tree.indexAt(position)
        if not index.isValid():
            return
        path = self.model.filePath(index)
        menu = QMenu(self)
        if self.model.isDir(index):
            open_action = QAction("Abrir carpeta", menu)
            open_action.triggered.connect(lambda: self.set_root(path))
        else:
            open_action = QAction("Cargar en QuickClip", menu)
            open_action.triggered.connect(lambda: self.file_activated.emit(path))
        reveal = QAction("Abrir con el sistema", menu)
        reveal.triggered.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(path)))
        menu.addAction(open_action)
        menu.addAction(reveal)
        menu.exec(self.tree.viewport().mapToGlobal(position))
