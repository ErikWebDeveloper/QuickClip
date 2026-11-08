#!/usr/bin/env python3
"""Punto de entrada de QuickClip."""

from __future__ import annotations

import os
import signal
import sys

from PyQt6.QtCore import QPointF, QRectF, Qt, QTimer
from PyQt6.QtGui import QColor, QFont, QIcon, QPainter, QPen, QPixmap, QPolygonF
from PyQt6.QtWidgets import QApplication

from quickclip.config import APP_NAME, APP_VERSION, ORG_NAME, debug_exit_log
from quickclip.main_window import MainWindow
from quickclip.theme import COLORS, apply_theme


def make_app_icon() -> QIcon:
    pixmap = QPixmap(128, 128)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor("#0b0b12"))
    painter.drawRoundedRect(QRectF(4, 4, 120, 120), 28, 28)
    painter.setBrush(QColor(COLORS["accent"]))
    painter.drawRoundedRect(QRectF(12, 12, 104, 104), 22, 22)

    painter.setBrush(QColor("#06120b"))
    triangle = QPolygonF(
        [QPointF(48, 42), QPointF(48, 86), QPointF(88, 64)]
    )
    painter.drawPolygon(triangle)

    painter.setPen(QPen(QColor("#06120b"), 7, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
    painter.drawLine(QPointF(26, 96), QPointF(64, 96))

    font = QFont("Inter", 16)
    font.setWeight(QFont.Weight.Black)
    painter.setFont(font)
    painter.end()
    return QIcon(pixmap)


def main() -> int:
    debug_exit_log(f"start argv={sys.argv!r}")
    signal.signal(signal.SIGINT, signal.SIG_DFL)
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setOrganizationName(ORG_NAME)
    app.setApplicationDisplayName(APP_NAME)
    app.setApplicationVersion(APP_VERSION)
    app.setWindowIcon(make_app_icon())
    apply_theme(app)

    window = MainWindow()
    window.show()
    debug_exit_log("window shown")

    if len(sys.argv) > 1:
        target = sys.argv[1]
        QTimer.singleShot(120, lambda: window.open_path(target))

    keepalive = QTimer()
    keepalive.start(400)
    keepalive.timeout.connect(lambda: None)

    rc = app.exec()
    debug_exit_log(f"app.exec returned {rc}")
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(rc)


if __name__ == "__main__":
    raise SystemExit(main())
