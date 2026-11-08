"""Línea de tiempo interactiva con filmstrip, tiradores In/Out y playhead."""

from __future__ import annotations

import math

from PyQt6.QtCore import QPointF, QRectF, QSize, Qt, pyqtSignal
from PyQt6.QtGui import (
    QColor,
    QFont,
    QImage,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QPolygonF,
)
from PyQt6.QtWidgets import QSizePolicy, QWidget

from . import ffmpeg
from .theme import COLORS

RULER_HEIGHT = 22
FILM_TOP = 26
FILM_HEIGHT = 64
SIDE_MARGIN = 12
HANDLE_HIT = 9
MIN_GAP = 0.04

TICK_STEPS = (0.5, 1, 2, 5, 10, 15, 30, 60, 120, 300, 600, 900, 1800, 3600)


class TimelineWidget(QWidget):
    seeking = pyqtSignal(float)
    seek_committed = pyqtSignal(float)
    drag_started = pyqtSignal()
    drag_ended = pyqtSignal()
    selection_changed = pyqtSignal(float, float)
    error = pyqtSignal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("Timeline")
        self.setMouseTracking(True)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setMinimumHeight(122)
        self.setMaximumHeight(122)
        self.setCursor(Qt.CursorShape.ArrowCursor)

        self._duration = 0.0
        self._fps = 30.0
        self._in_point = 0.0
        self._out_point = 0.0
        self._playhead = 0.0
        self._thumbs: list[QImage | None] = []
        self._loading = False
        self._loading_text = "Generando miniaturas…"
        self._drag: str | None = None
        self._hover: str | None = None
        self._cache: QPixmap | None = None
        self._cache_size = QSize()
        self._has_media = False

    # ------------------------------------------------------------------ API
    @property
    def duration(self) -> float:
        return self._duration

    @property
    def in_point(self) -> float:
        return self._in_point

    @property
    def out_point(self) -> float:
        return self._out_point

    @property
    def playhead(self) -> float:
        return self._playhead

    @property
    def selection_duration(self) -> float:
        return max(0.0, self._out_point - self._in_point)

    @property
    def min_gap(self) -> float:
        return max(MIN_GAP, 1.0 / self._fps if self._fps else MIN_GAP)

    def set_media(self, info: ffmpeg.MediaInfo) -> None:
        self._has_media = True
        self._duration = info.duration
        self._fps = info.safe_fps
        self._in_point = 0.0
        self._out_point = info.duration
        self._playhead = 0.0
        self._thumbs = []
        self._loading = True
        self._loading_text = "Generando miniaturas…"
        self._drag = None
        self._cache = None
        self.update()
        self.selection_changed.emit(self._in_point, self._out_point)

    def clear_media(self) -> None:
        self._has_media = False
        self._duration = 0.0
        self._in_point = 0.0
        self._out_point = 0.0
        self._playhead = 0.0
        self._thumbs = []
        self._loading = False
        self._drag = None
        self._cache = None
        self.update()

    def set_thumbnail(self, index: int, image: QImage) -> None:
        self._thumbs = list(self._thumbs)
        if index >= len(self._thumbs):
            self._thumbs.extend([None] * (index - len(self._thumbs) + 1))
        self._thumbs[index] = image
        self._cache = None
        self.update()

    def set_filmstrip_state(self, loading: bool, text: str = "") -> None:
        self._loading = loading
        if text:
            self._loading_text = text
        self.update()

    def set_playhead(self, seconds: float, from_user: bool = False) -> None:
        self._playhead = max(0.0, min(self._duration, seconds))
        self.update()
        if from_user:
            self.seeking.emit(self._playhead)

    def set_selection(self, in_point: float, out_point: float, emit: bool = True) -> None:
        if not self._has_media:
            return
        start = max(0.0, min(self._duration - self.min_gap, in_point))
        end = max(start + self.min_gap, min(self._duration, out_point))
        if start == self._in_point and end == self._out_point:
            return
        self._in_point = start
        self._out_point = end
        self.update()
        if emit:
            self.selection_changed.emit(start, end)

    # -------------------------------------------------------------- geometry
    def _content_rect(self) -> QRectF:
        return QRectF(
            SIDE_MARGIN,
            FILM_TOP,
            max(1.0, self.width() - SIDE_MARGIN * 2),
            FILM_HEIGHT,
        )

    def _time_to_x(self, seconds: float) -> float:
        if self._duration <= 0:
            return SIDE_MARGIN
        rect = self._content_rect()
        ratio = max(0.0, min(1.0, seconds / self._duration))
        return rect.left() + ratio * rect.width()

    def _x_to_time(self, x: float) -> float:
        if self._duration <= 0:
            return 0.0
        rect = self._content_rect()
        ratio = (x - rect.left()) / rect.width()
        return max(0.0, min(1.0, ratio)) * self._duration

    def _hit_test(self, x: float) -> str:
        in_x = self._time_to_x(self._in_point)
        out_x = self._time_to_x(self._out_point)
        play_x = self._time_to_x(self._playhead)
        if abs(x - in_x) <= HANDLE_HIT:
            return "in"
        if abs(x - out_x) <= HANDLE_HIT:
            return "out"
        if abs(x - play_x) <= 7:
            return "playhead"
        return "body"

    # ----------------------------------------------------------------- paint
    def paintEvent(self, _event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        outer = QRectF(self.rect()).adjusted(1.0, 1.0, -1.0, -1.0)
        bg = QPainterPath()
        bg.addRoundedRect(outer, 10.0, 10.0)
        painter.fillPath(bg, QColor("#0b0b11"))
        painter.setClipping(True)
        painter.setClipPath(bg)

        if self._cache is None or self._cache_size != self.size():
            self._rebuild_cache()
        if self._cache is not None:
            painter.drawPixmap(0, 0, self._cache)

        if not self._has_media:
            painter.setClipping(False)
            painter.setPen(QColor(COLORS["dim"]))
            painter.drawText(
                QRectF(0, 0, self.width(), self.height()),
                Qt.AlignmentFlag.AlignCenter,
                "Abre un video para comenzar a recortar",
            )
            painter.setPen(QPen(QColor(COLORS["border_soft"]), 1.0))
            painter.drawRoundedRect(outer, 10.0, 10.0)
            return

        content = self._content_rect()
        in_x = self._time_to_x(self._in_point)
        out_x = self._time_to_x(self._out_point)
        play_x = self._time_to_x(self._playhead)

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(3, 3, 6, 168))
        if in_x > content.left():
            painter.drawRect(QRectF(content.left(), content.top(), in_x - content.left(), content.height()))
        if out_x < content.right():
            painter.drawRect(QRectF(out_x, content.top(), content.right() - out_x, content.height()))

        selection = QRectF(in_x, content.top(), max(1.0, out_x - in_x), content.height())
        painter.setPen(QPen(QColor(COLORS["accent"]), 1.6))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(selection.adjusted(0.5, 0.5, -0.5, -0.5), 4.0, 4.0)

        self._draw_handle(painter, in_x, QColor(COLORS["accent"]), "I", self._hover == "in")
        self._draw_handle(painter, out_x, QColor(COLORS["violet"]), "O", self._hover == "out")

        glow = QColor(COLORS["violet"])
        glow.setAlpha(55)
        painter.setPen(QPen(glow, 6.0))
        painter.drawLine(QPointF(play_x, content.top() - 2), QPointF(play_x, content.bottom() + 2))
        painter.setPen(QPen(QColor("#ffffff"), 1.6))
        painter.drawLine(QPointF(play_x, content.top() - 2), QPointF(play_x, content.bottom() + 2))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#ffffff"))
        painter.drawEllipse(QPointF(play_x, content.top() - 2), 4.0, 4.0)

        if self._loading:
            painter.setClipping(False)
            badge = QRectF(
                content.center().x() - 78,
                content.center().y() - 13,
                156,
                26,
            )
            painter.setBrush(QColor(8, 8, 12, 205))
            painter.setPen(QPen(QColor(COLORS["border"]), 1.0))
            painter.drawRoundedRect(badge, 13.0, 13.0)
            painter.setPen(QColor(COLORS["muted"]))
            small = QFont(self.font())
            small.setPointSizeF(max(8.0, small.pointSizeF() - 1.5))
            painter.setFont(small)
            painter.drawText(badge, Qt.AlignmentFlag.AlignCenter, self._loading_text)

        painter.setClipping(False)
        painter.setPen(QPen(QColor(COLORS["border_soft"]), 1.0))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(outer, 10.0, 10.0)

    def _draw_handle(self, painter: QPainter, x: float, color: QColor, label: str, hover: bool) -> None:
        content = self._content_rect()
        width = 7.0 if hover else 5.0
        bar = QRectF(x - width / 2.0, content.top() - 4.0, width, content.height() + 8.0)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(color)
        painter.drawRoundedRect(bar, 3.0, 3.0)

        flag = QPolygonF(
            [
                QPointF(x - 9.0, content.top() - 17.0),
                QPointF(x + 9.0, content.top() - 17.0),
                QPointF(x + 9.0, content.top() - 6.0),
                QPointF(x, content.top() - 2.0),
                QPointF(x - 9.0, content.top() - 6.0),
            ]
        )
        painter.setBrush(color)
        painter.drawPolygon(flag)
        small = QFont(self.font())
        small.setPointSizeF(7.5)
        small.setBold(True)
        painter.setFont(small)
        painter.setPen(QColor("#06060a"))
        painter.drawText(
            QRectF(x - 9.0, content.top() - 17.0, 18.0, 12.0),
            Qt.AlignmentFlag.AlignCenter,
            label,
        )

    def _rebuild_cache(self) -> None:
        size = self.size()
        if size.width() <= 0 or size.height() <= 0:
            return
        pixmap = QPixmap(size)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        self._cache_size = size
        self._cache = pixmap
        if not self._has_media:
            painter.end()
            return

        self._draw_ruler(painter)
        self._draw_filmstrip(painter)
        painter.end()

    def _draw_ruler(self, painter: QPainter) -> None:
        content = self._content_rect()
        painter.setFont(self._ruler_font())
        width = content.width()
        step = TICK_STEPS[-1]
        for candidate in TICK_STEPS:
            if self._duration / candidate <= max(2.0, width / 78.0):
                step = candidate
                break
        ticks = int(math.floor(self._duration / step))
        for index in range(ticks + 1):
            seconds = index * step
            x = self._time_to_x(seconds)
            if seconds > self._duration:
                break
            major = index % 2 == 0 or step >= 60
            tick_height = 6.0 if major else 3.0
            painter.setPen(QPen(QColor(COLORS["border"]), 1.0))
            painter.drawLine(
                QPointF(x, RULER_HEIGHT - tick_height),
                QPointF(x, RULER_HEIGHT - 1),
            )
            if major:
                painter.setPen(QColor(COLORS["dim"]))
                painter.drawText(
                    QRectF(x + 4, 1, 60, 14),
                    Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                    ffmpeg.format_short_time(seconds),
                )

    def _draw_filmstrip(self, painter: QPainter) -> None:
        content = self._content_rect()
        clip = QPainterPath()
        clip.addRoundedRect(content, 5.0, 5.0)
        painter.save()
        painter.setClipPath(clip)

        gradient = QLinearGradient(content.topLeft(), content.bottomLeft())
        gradient.setColorAt(0.0, QColor("#121219"))
        gradient.setColorAt(1.0, QColor("#0c0c12"))
        painter.fillRect(content, gradient)

        thumbs = [thumb for thumb in self._thumbs if thumb is not None]
        if thumbs:
            tile_width = max(58.0, content.width() / max(1, int(content.width() // 92)))
            tiles = max(1, int(math.ceil(content.width() / tile_width)))
            actual_width = content.width() / tiles
            for index in range(tiles):
                frac = (index + 0.5) / tiles
                thumb_index = min(len(thumbs) - 1, int(frac * len(thumbs)))
                image = thumbs[thumb_index]
                x = content.left() + index * actual_width
                target = QRectF(x, content.top(), actual_width + 0.6, content.height())
                self._draw_cover_image(painter, image, target)
                if index:
                    painter.setPen(QPen(QColor(4, 4, 7, 150), 1.0))
                    painter.drawLine(QPointF(x, content.top()), QPointF(x, content.bottom()))
        else:
            painter.setPen(QPen(QColor("#191922"), 1.0))
            offset = 0
            while offset < content.width() + content.height():
                painter.drawLine(
                    QPointF(content.left() + offset, content.bottom()),
                    QPointF(content.left() + offset - content.height(), content.top()),
                )
                offset += 18

        painter.setPen(QPen(QColor(COLORS["border_soft"]), 1.0))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(content.adjusted(0.5, 0.5, -0.5, -0.5), 5.0, 5.0)
        painter.restore()

    @staticmethod
    def _draw_cover_image(painter: QPainter, image: QImage, target: QRectF) -> None:
        if image.isNull():
            return
        scaled = image.scaled(
            QSize(int(math.ceil(target.width())), int(math.ceil(target.height()))),
            Qt.AspectRatioMode.KeepAspectRatioByExpanding,
            Qt.TransformationMode.SmoothTransformation,
        )
        source_x = max(0, (scaled.width() - int(target.width())) // 2)
        source_y = max(0, (scaled.height() - int(target.height())) // 2)
        crop = scaled.copy(
            source_x,
            source_y,
            max(1, int(target.width())),
            max(1, int(target.height())),
        )
        painter.drawImage(target.topLeft(), crop)

    def _ruler_font(self) -> QFont:
        font = QFont(self.font())
        font.setPointSizeF(8.0)
        font.setWeight(QFont.Weight.Medium)
        return font

    # ---------------------------------------------------------------- events
    def resizeEvent(self, _event) -> None:  # noqa: N802
        self._cache = None
        self.update()

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if not self._has_media or event.button() != Qt.MouseButton.LeftButton:
            return
        x = event.position().x()
        target = self._hit_test(x)
        self._drag = target
        self.drag_started.emit()
        if target == "in":
            self._drag_handle(x)
        elif target == "out":
            self._drag_handle(x)
        else:
            self._seek_to(x)
        self.update()

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        if not self._has_media:
            return
        x = event.position().x()
        if self._drag is None:
            hover = self._hit_test(x)
            new_hover = hover if hover in ("in", "out", "playhead") else None
            if new_hover != self._hover:
                self._hover = new_hover
                self._update_cursor()
                self.update()
            time = self._x_to_time(x)
            self.setToolTip(ffmpeg.format_timecode(time))
            return

        if self._drag in ("in", "out"):
            self._drag_handle(x)
        elif self._drag == "playhead":
            self._seek_to(x)
        else:
            self._seek_to(x)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if self._drag is None:
            return
        drag = self._drag
        self._drag = None
        self._update_cursor()
        if drag in ("in", "out"):
            self.seek_committed.emit(self._playhead)
            self.selection_changed.emit(self._in_point, self._out_point)
        else:
            self.seek_committed.emit(self._playhead)
        self.drag_ended.emit()
        self.update()

    def leaveEvent(self, _event) -> None:  # noqa: N802
        self._hover = None
        self._update_cursor()
        self.update()

    def wheelEvent(self, event) -> None:  # noqa: N802
        if not self._has_media:
            return
        delta = event.angleDelta().y()
        if delta == 0:
            return
        step = 1.0 / self._fps if self._fps else 1.0
        direction = 1 if delta > 0 else -1
        self.drag_started.emit()
        self._seek_to(self._time_to_x(self._playhead + direction * step * 3))
        self.seek_committed.emit(self._playhead)
        self.drag_ended.emit()

    def _update_cursor(self) -> None:
        if self._drag in ("in", "out"):
            self.setCursor(Qt.CursorShape.SizeHorCursor)
        elif self._hover in ("in", "out"):
            self.setCursor(Qt.CursorShape.SizeHorCursor)
        elif self._hover == "playhead":
            self.setCursor(Qt.CursorShape.PointingHandCursor)
        else:
            self.setCursor(Qt.CursorShape.ArrowCursor)

    def _seek_to(self, x: float) -> None:
        self._playhead = self._x_to_time(x)
        self.seeking.emit(self._playhead)
        self.update()

    def _drag_handle(self, x: float) -> None:
        time = self._x_to_time(x)
        gap = self.min_gap
        if self._drag == "in":
            self._in_point = max(0.0, min(time, self._out_point - gap))
            self._playhead = self._in_point
        else:
            self._out_point = min(self._duration, max(time, self._in_point + gap))
            self._playhead = self._out_point
        self.selection_changed.emit(self._in_point, self._out_point)
        self.seeking.emit(self._playhead)
        self.update()
