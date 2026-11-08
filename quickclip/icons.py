"""Iconos vectoriales dibujados con QPainter para la interfaz."""

from __future__ import annotations

from collections.abc import Callable

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap, QPolygonF

from .theme import COLORS

DrawFunc = Callable[[QPainter, QColor], None]
_SIZES = (16, 20, 24, 32, 48, 64)


def _render(draw: DrawFunc, color: str, size: int) -> QPixmap:
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.scale(size / 64.0, size / 64.0)
    draw(painter, QColor(color))
    painter.end()
    return pixmap


def _icon(draw: DrawFunc, color: str, disabled_color: str = COLORS["dim"]) -> QIcon:
    icon = QIcon()
    for size in _SIZES:
        icon.addPixmap(_render(draw, color, size), QIcon.Mode.Normal)
        icon.addPixmap(_render(draw, color, size), QIcon.Mode.Active)
        icon.addPixmap(_render(draw, disabled_color, size), QIcon.Mode.Disabled)
    return icon


def trim_in_icon() -> QIcon:
    def draw(painter: QPainter, color: QColor) -> None:
        pen = QPen(color, 6.0, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        path = QPainterPath(QPointF(34.0, 12.0))
        path.lineTo(18.0, 12.0)
        path.lineTo(18.0, 52.0)
        path.lineTo(34.0, 52.0)
        painter.drawPath(path)

    return _icon(draw, COLORS["accent"])


def trim_out_icon() -> QIcon:
    def draw(painter: QPainter, color: QColor) -> None:
        pen = QPen(color, 6.0, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        path = QPainterPath(QPointF(30.0, 12.0))
        path.lineTo(46.0, 12.0)
        path.lineTo(46.0, 52.0)
        path.lineTo(30.0, 52.0)
        painter.drawPath(path)

    return _icon(draw, COLORS["violet"])


def full_range_icon() -> QIcon:
    def draw(painter: QPainter, color: QColor) -> None:
        pen = QPen(color, 6.0, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawLine(QPointF(16.0, 12.0), QPointF(16.0, 52.0))
        painter.drawLine(QPointF(48.0, 12.0), QPointF(48.0, 52.0))
        painter.drawLine(QPointF(16.0, 32.0), QPointF(48.0, 32.0))
        painter.drawLine(QPointF(24.0, 24.0), QPointF(16.0, 32.0))
        painter.drawLine(QPointF(24.0, 40.0), QPointF(16.0, 32.0))
        painter.drawLine(QPointF(40.0, 24.0), QPointF(48.0, 32.0))
        painter.drawLine(QPointF(40.0, 40.0), QPointF(48.0, 32.0))

    return _icon(draw, COLORS["text"], COLORS["dim"])


def volume_icon(muted: bool = False) -> QIcon:
    def draw(painter: QPainter, color: QColor) -> None:
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(color)
        speaker = QPolygonF(
            [
                QPointF(10.0, 26.0),
                QPointF(18.0, 26.0),
                QPointF(28.0, 16.0),
                QPointF(28.0, 48.0),
                QPointF(18.0, 38.0),
                QPointF(10.0, 38.0),
            ]
        )
        painter.drawPolygon(speaker)

        pen = QPen(color, 5.0, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        if muted:
            painter.drawLine(QPointF(36.0, 18.0), QPointF(56.0, 46.0))
        else:
            painter.drawArc(QRectF(28.0, 22.0, 20.0, 20.0), -60 * 16, 120 * 16)
            painter.drawArc(QRectF(24.0, 14.0, 34.0, 36.0), -55 * 16, 110 * 16)

    color = COLORS["danger"] if muted else COLORS["muted"]
    return _icon(draw, color)
