"""Paleta y hoja de estilos oscura estilo Kick/Vice para QuickClip."""

from __future__ import annotations

from PyQt6.QtGui import QColor, QFont, QPalette
from PyQt6.QtWidgets import QApplication

COLORS = {
    "bg": "#08080c",
    "panel": "#0f0f15",
    "panel_alt": "#14141c",
    "elevated": "#1a1a24",
    "border": "#262633",
    "border_soft": "#1e1e29",
    "text": "#ececf4",
    "muted": "#8c8ca2",
    "dim": "#5f5f74",
    "accent": "#2bff88",
    "accent_dim": "#1fbf67",
    "violet": "#9b6bff",
    "violet_dim": "#7448d6",
    "danger": "#ff5470",
    "warning": "#ffb84d",
    "black": "#000000",
}


def accent_color() -> QColor:
    return QColor(COLORS["accent"])


def violet_color() -> QColor:
    return QColor(COLORS["violet"])


STYLESHEET = f"""
* {{
    outline: none;
}}

QWidget {{
    background-color: {COLORS['bg']};
    color: {COLORS['text']};
    font-family: "Inter", "Noto Sans", "Ubuntu", "Segoe UI", sans-serif;
    font-size: 13px;
}}

QMainWindow, QDialog {{
    background-color: {COLORS['bg']};
}}

QToolTip {{
    background-color: {COLORS['elevated']};
    color: {COLORS['text']};
    border: 1px solid {COLORS['border']};
    border-radius: 6px;
    padding: 6px 8px;
}}

QLabel {{
    background: transparent;
}}

QLabel#AppTitle {{
    font-size: 15px;
    font-weight: 800;
    letter-spacing: 1px;
    color: {COLORS['text']};
}}

QLabel#AppBadge {{
    color: {COLORS['bg']};
    background-color: {COLORS['accent']};
    border-radius: 5px;
    padding: 2px 6px;
    font-size: 10px;
    font-weight: 900;
    letter-spacing: 1px;
}}

QLabel#PanelTitle {{
    color: {COLORS['muted']};
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 1.5px;
    text-transform: uppercase;
}}

QLabel#Muted, QLabel#MutedSmall {{
    color: {COLORS['muted']};
}}

QLabel#MutedSmall {{
    font-size: 11px;
}}

QLabel#Timecode {{
    font-family: "JetBrains Mono", "Ubuntu Mono", "DejaVu Sans Mono", monospace;
    font-size: 13px;
    font-weight: 600;
    color: {COLORS['text']};
    background-color: {COLORS['panel_alt']};
    border: 1px solid {COLORS['border_soft']};
    border-radius: 7px;
    padding: 4px 10px;
}}

QLabel#TimecodeMuted {{
    font-family: "JetBrains Mono", "Ubuntu Mono", "DejaVu Sans Mono", monospace;
    font-size: 12px;
    color: {COLORS['muted']};
}}

QLabel#SelectionIn {{
    color: {COLORS['accent']};
    font-family: "JetBrains Mono", "Ubuntu Mono", "DejaVu Sans Mono", monospace;
}}

QLabel#SelectionOut {{
    color: {COLORS['violet']};
    font-family: "JetBrains Mono", "Ubuntu Mono", "DejaVu Sans Mono", monospace;
}}

QFrame#Panel {{
    background-color: {COLORS['panel']};
    border: 1px solid {COLORS['border_soft']};
    border-radius: 12px;
}}

QFrame#TopBar {{
    background-color: {COLORS['panel']};
    border-bottom: 1px solid {COLORS['border_soft']};
}}

QWidget#FileExplorer, QWidget#PreviewColumn, QWidget#Content, QWidget#Central {{
    background-color: transparent;
}}

QFrame#ExplorerHeader {{
    background-color: transparent;
    border-bottom: 1px solid {COLORS['border_soft']};
}}

QFrame#Transport {{
    background-color: {COLORS['panel']};
    border: 1px solid {COLORS['border_soft']};
    border-radius: 12px;
}}

QFrame#Divider {{
    background-color: {COLORS['border_soft']};
    max-height: 1px;
    min-height: 1px;
    border: none;
}}

QPushButton {{
    background-color: {COLORS['elevated']};
    color: {COLORS['text']};
    border: 1px solid {COLORS['border']};
    border-radius: 8px;
    padding: 7px 14px;
    font-weight: 600;
}}

QPushButton:hover {{
    background-color: #23232f;
    border-color: #343445;
}}

QPushButton:pressed {{
    background-color: #101018;
}}

QPushButton:disabled {{
    color: {COLORS['dim']};
    background-color: {COLORS['panel_alt']};
    border-color: {COLORS['border_soft']};
}}

QPushButton[variant="primary"] {{
    background-color: {COLORS['accent']};
    color: #04140b;
    border: 1px solid {COLORS['accent']};
    font-weight: 800;
}}

QPushButton[variant="primary"]:hover {{
    background-color: #5bffa3;
    border-color: #5bffa3;
}}

QPushButton[variant="primary"]:pressed {{
    background-color: {COLORS['accent_dim']};
}}

QPushButton[variant="primary"]:disabled {{
    background-color: #143326;
    color: {COLORS['dim']};
    border-color: #143326;
}}

QPushButton[variant="violet"] {{
    background-color: {COLORS['violet']};
    color: #120a24;
    border: 1px solid {COLORS['violet']};
    font-weight: 800;
}}

QPushButton[variant="violet"]:hover {{
    background-color: #b18aff;
    border-color: #b18aff;
}}

QPushButton[variant="ghost"] {{
    background-color: transparent;
    border: 1px solid transparent;
    color: {COLORS['muted']};
    padding: 6px 10px;
}}

QPushButton[variant="ghost"]:hover {{
    background-color: {COLORS['elevated']};
    color: {COLORS['text']};
}}

QPushButton[variant="danger"] {{
    background-color: transparent;
    border: 1px solid rgba(255, 84, 112, 0.45);
    color: {COLORS['danger']};
}}

QPushButton[variant="danger"]:hover {{
    background-color: rgba(255, 84, 112, 0.12);
}}

QPushButton[variant="chip"] {{
    background-color: transparent;
    border: 1px solid {COLORS['border']};
    border-radius: 14px;
    padding: 4px 11px;
    color: {COLORS['muted']};
    font-size: 11px;
    font-weight: 600;
}}

QPushButton[variant="chip"]:hover {{
    color: {COLORS['text']};
    border-color: {COLORS['accent_dim']};
    background-color: rgba(43, 255, 136, 0.06);
}}

QPushButton[variant="iconChip"] {{
    background-color: transparent;
    border: 1px solid {COLORS['border']};
    border-radius: 14px;
    padding: 0px;
}}

QPushButton[variant="iconChip"]:hover {{
    border-color: {COLORS['accent_dim']};
    background-color: rgba(43, 255, 136, 0.06);
}}

QPushButton[variant="iconChip"]:pressed {{
    background-color: rgba(43, 255, 136, 0.12);
}}

QPushButton[variant="iconChip"]:disabled {{
    border-color: {COLORS['border_soft']};
    background-color: transparent;
}}

QPushButton#PlayButton {{
    background-color: {COLORS['accent']};
    color: #04140b;
    border: none;
    border-radius: 19px;
    font-size: 15px;
    font-weight: 900;
    min-width: 38px;
    max-width: 38px;
    min-height: 38px;
    max-height: 38px;
}}

QPushButton#PlayButton:hover {{
    background-color: #5bffa3;
}}

QPushButton#TransportButton {{
    background-color: transparent;
    border: 1px solid transparent;
    border-radius: 7px;
    color: {COLORS['muted']};
    padding: 5px 8px;
    font-size: 13px;
}}

QPushButton#TransportButton:hover {{
    color: {COLORS['text']};
    background-color: {COLORS['elevated']};
}}

QPushButton#MuteButton {{
    background-color: transparent;
    border: 1px solid {COLORS['border']};
    border-radius: 13px;
    padding: 0px;
}}

QPushButton#MuteButton:hover {{
    color: {COLORS['text']};
    border-color: {COLORS['border']};
    background-color: {COLORS['elevated']};
}}

QPushButton#MuteButton:checked {{
    color: {COLORS['danger']};
    border-color: rgba(255, 84, 112, 0.45);
    background-color: rgba(255, 84, 112, 0.1);
}}

QPushButton#MuteButton:disabled {{
    color: {COLORS['dim']};
    border-color: {COLORS['border_soft']};
}}

QLineEdit, QComboBox, QSpinBox {{
    background-color: {COLORS['panel_alt']};
    border: 1px solid {COLORS['border']};
    border-radius: 8px;
    padding: 7px 10px;
    selection-background-color: {COLORS['accent_dim']};
    selection-color: #04140b;
}}

QLineEdit:hover, QComboBox:hover {{
    border-color: #383849;
}}

QLineEdit:focus, QComboBox:focus {{
    border-color: {COLORS['accent']};
    background-color: #101019;
}}

QLineEdit:disabled {{
    color: {COLORS['dim']};
}}

QLineEdit[invalid="true"] {{
    border-color: {COLORS['danger']};
}}

QComboBox::drop-down {{
    border: none;
    width: 22px;
}}

QComboBox QAbstractItemView {{
    background-color: {COLORS['elevated']};
    border: 1px solid {COLORS['border']};
    border-radius: 8px;
    padding: 4px;
    selection-background-color: rgba(43, 255, 136, 0.16);
    selection-color: {COLORS['accent']};
    outline: none;
}}

QCheckBox {{
    spacing: 8px;
    color: {COLORS['muted']};
    background: transparent;
}}

QCheckBox:hover {{
    color: {COLORS['text']};
}}

QCheckBox::indicator {{
    width: 16px;
    height: 16px;
    border-radius: 5px;
    border: 1px solid {COLORS['border']};
    background-color: {COLORS['panel_alt']};
}}

QCheckBox::indicator:hover {{
    border-color: {COLORS['accent_dim']};
}}

QCheckBox::indicator:checked {{
    background-color: {COLORS['accent']};
    border-color: {COLORS['accent']};
    image: none;
}}

QTreeView {{
    background-color: transparent;
    border: none;
    show-decoration-selected: 0;
    alternate-background-color: transparent;
    padding: 2px;
}}

QTreeView::item {{
    height: 28px;
    border-radius: 6px;
    padding-left: 2px;
    color: {COLORS['text']};
}}

QTreeView::item:hover {{
    background-color: {COLORS['elevated']};
}}

QTreeView::item:selected {{
    background-color: rgba(43, 255, 136, 0.13);
    color: {COLORS['accent']};
}}

QTreeView::branch {{
    background: transparent;
}}

QHeaderView::section {{
    background-color: transparent;
    color: {COLORS['muted']};
    border: none;
    padding: 4px;
    font-size: 11px;
}}

QScrollBar:vertical {{
    background: transparent;
    width: 10px;
    margin: 2px;
}}

QScrollBar::handle:vertical {{
    background: #2b2b3a;
    border-radius: 4px;
    min-height: 28px;
}}

QScrollBar::handle:vertical:hover {{
    background: #3c3c4f;
}}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical,
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
    background: none;
    height: 0;
}}

QScrollBar:horizontal {{
    background: transparent;
    height: 10px;
    margin: 2px;
}}

QScrollBar::handle:horizontal {{
    background: #2b2b3a;
    border-radius: 4px;
    min-width: 28px;
}}

QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal,
QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{
    background: none;
    width: 0;
}}

QSplitter::handle {{
    background-color: transparent;
    width: 8px;
}}

QSplitter::handle:hover {{
    background-color: {COLORS['border_soft']};
}}

QSlider {{
    background: transparent;
}}

QSlider::groove:horizontal {{
    height: 4px;
    background: {COLORS['elevated']};
    border-radius: 2px;
}}

QSlider::sub-page:horizontal {{
    background: {COLORS['accent']};
    border-radius: 2px;
}}

QSlider::add-page:horizontal {{
    background: {COLORS['elevated']};
    border-radius: 2px;
}}

QSlider::handle:horizontal {{
    width: 12px;
    height: 12px;
    margin: -5px 0;
    border-radius: 6px;
    background: {COLORS['accent']};
}}

QSlider::handle:horizontal:hover {{
    background: #ffffff;
}}

QProgressBar {{
    background-color: {COLORS['panel_alt']};
    border: 1px solid {COLORS['border_soft']};
    border-radius: 6px;
    height: 10px;
    text-align: center;
    color: transparent;
}}

QProgressBar::chunk {{
    background-color: {COLORS['accent']};
    border-radius: 5px;
}}

QProgressBar[variant="violet"]::chunk {{
    background-color: {COLORS['violet']};
}}

QMenuBar {{
    background-color: {COLORS['panel']};
    border-bottom: 1px solid {COLORS['border_soft']};
    padding: 2px 6px;
}}

QMenuBar::item {{
    background: transparent;
    padding: 5px 10px;
    border-radius: 6px;
    color: {COLORS['muted']};
}}

QMenuBar::item:selected {{
    background-color: {COLORS['elevated']};
    color: {COLORS['text']};
}}

QMenu {{
    background-color: {COLORS['elevated']};
    border: 1px solid {COLORS['border']};
    border-radius: 10px;
    padding: 6px;
}}

QMenu::item {{
    padding: 7px 26px 7px 14px;
    border-radius: 6px;
    color: {COLORS['text']};
}}

QMenu::item:selected {{
    background-color: rgba(43, 255, 136, 0.12);
    color: {COLORS['accent']};
}}

QMenu::separator {{
    height: 1px;
    background: {COLORS['border_soft']};
    margin: 5px 8px;
}}

QStatusBar {{
    background-color: {COLORS['panel']};
    border-top: 1px solid {COLORS['border_soft']};
    color: {COLORS['muted']};
    font-size: 11px;
}}

QStatusBar::item {{
    border: none;
}}

QDialog#ExportDialog {{
    background-color: {COLORS['bg']};
}}

QFrame#Card {{
    background-color: {COLORS['panel']};
    border: 1px solid {COLORS['border_soft']};
    border-radius: 10px;
}}

QFrame#WarningBanner {{
    background-color: rgba(255, 184, 77, 0.08);
    border: 1px solid rgba(255, 184, 77, 0.35);
    border-radius: 8px;
}}

QFrame#SuccessBanner {{
    background-color: rgba(43, 255, 136, 0.08);
    border: 1px solid rgba(43, 255, 136, 0.35);
    border-radius: 8px;
}}

QFrame#ErrorBanner {{
    background-color: rgba(255, 84, 112, 0.08);
    border: 1px solid rgba(255, 84, 112, 0.35);
    border-radius: 8px;
}}

QLabel#BannerTitle {{
    font-weight: 700;
    background: transparent;
}}

QLabel#BannerText {{
    color: {COLORS['muted']};
    background: transparent;
    font-size: 11px;
}}

QLabel#WarningTitle {{ color: {COLORS['warning']}; }}
QLabel#SuccessTitle {{ color: {COLORS['accent']}; }}
QLabel#ErrorTitle {{ color: {COLORS['danger']}; }}

QLabel#DropHintTitle {{
    color: {COLORS['muted']};
    font-size: 15px;
    font-weight: 600;
}}

QLabel#VideoView {{
    background-color: #030305;
    border: 1px solid {COLORS['border_soft']};
    border-radius: 10px;
}}

QMessageBox {{
    background-color: {COLORS['panel']};
}}

QToolBar {{
    background: transparent;
    border: none;
}}
"""


def apply_theme(app: QApplication) -> None:
    app.setStyle("Fusion")
    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, QColor(COLORS["bg"]))
    palette.setColor(QPalette.ColorRole.WindowText, QColor(COLORS["text"]))
    palette.setColor(QPalette.ColorRole.Base, QColor(COLORS["panel"]))
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor(COLORS["panel_alt"]))
    palette.setColor(QPalette.ColorRole.Text, QColor(COLORS["text"]))
    palette.setColor(QPalette.ColorRole.Button, QColor(COLORS["elevated"]))
    palette.setColor(QPalette.ColorRole.ButtonText, QColor(COLORS["text"]))
    palette.setColor(QPalette.ColorRole.Highlight, QColor(COLORS["accent"]))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor("#04140b"))
    palette.setColor(QPalette.ColorRole.ToolTipBase, QColor(COLORS["elevated"]))
    palette.setColor(QPalette.ColorRole.ToolTipText, QColor(COLORS["text"]))
    palette.setColor(QPalette.ColorRole.PlaceholderText, QColor(COLORS["dim"]))
    app.setPalette(palette)

    font = QFont("Inter", 10)
    font.setStyleHint(QFont.StyleHint.SansSerif)
    app.setFont(font)
    app.setStyleSheet(STYLESHEET)
