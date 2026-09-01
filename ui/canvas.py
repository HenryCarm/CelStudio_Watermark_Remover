import sys, os, json, base64, traceback, shutil, subprocess, time, signal
from pathlib import Path
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor

try:
    if hasattr(signal, "SIGPIPE"):
        signal.signal(signal.SIGPIPE, signal.SIG_IGN)
except Exception:
    pass

import cv2
import numpy as np

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLayout,
    QLabel, QPushButton, QSlider, QFileDialog, QTabWidget, QScrollArea,
    QGridLayout, QSizePolicy, QFrame, QComboBox, QToolButton, QButtonGroup,
    QMessageBox, QStatusBar, QDialog, QTextEdit, QLineEdit, QSpinBox,
    QDoubleSpinBox, QListWidget, QListWidgetItem, QProgressBar,
    QFormLayout, QGroupBox, QScrollBar, QInputDialog, QCheckBox,
)
from PySide6.QtCore import (
    Qt, QPoint, QRect, QThread, Signal, QTimer, QSize,
    QPropertyAnimation, QEasingCurve, QObject,
)
from PySide6.QtGui import (
    QPainter, QImage, QPixmap, QColor, QPen, QBrush,
    QFont, QFontMetrics, QPalette, QCursor, QKeySequence, QIcon,
)

from core import *

# ─── Base Canvas ──────────────────────────────────────────────────────────────

class BaseCanvas(QWidget):
    status_msg   = Signal(str)
    mask_changed = Signal()

    TOOL_SMART  = "smart"
    TOOL_BRUSH  = "brush"
    TOOL_ERASER = "eraser"
    TOOL_SQUARE = "square"
    TOOL_CIRCLE = "circle"
    TOOL_PAN    = "pan"

    def __init__(self):
        super().__init__()
        self.mask:       np.ndarray | None = None
        self._iw = 1;   self._ih = 1
        self.scale  = 1.0
        self.offset = QPoint(0, 0)
        self.tool       = self.TOOL_BRUSH
        self.brush_size = 25
        self.drawing    = False
        self.last_pos:   QPoint | None = None
        self.drag_start: QPoint | None = None
        self.preview_rect: QRect | None = None
        self._smart_rect:  QRect | None = None
        self._active_box:  QRect | None = None
        self._drag_handle: str | None   = None
        self._drag_start_box: QRect | None = None
        # Pan
        self._panning   = False
        self._space     = False
        self._pan_start: QPoint | None = None
        self._pan_off   = QPoint(0, 0)
        self._mouse_pos: QPoint | None = None
        # Mask Undo
        self._undo: list[np.ndarray] = []
        self._redo: list[np.ndarray] = []
        # Image / Video Frame Undo
        self._img_history: list[tuple[np.ndarray, np.ndarray]] = []
        self._img_future:  list[tuple[np.ndarray, np.ndarray]] = []
        self._max_undo = 30
        # Paint caches — rebuilt lazily, avoids per-frame numpy alloc
        self._mask_overlay: QImage | None = None  # cached red overlay
        self._checker_cache: QPixmap | None = None  # cached checker bg
        self._checker_size  = QSize(0, 0)           # size it was built for
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setSizePolicy(QSizePolicy.Policy.Expanding,
                           QSizePolicy.Policy.Expanding)
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.setToolTip("Space+drag, middle-mouse, or Pan tool to move\n"
                        "Scroll to zoom")
        # Invalidate overlay cache whenever mask changes
        self.mask_changed.connect(self._invalidate_overlay)

    def _current_cv_img(self) -> np.ndarray | None:
        return None

    def _apply_cv_img(self, img: np.ndarray) -> None:
        pass

    # ── Geometry ──────────────────────────────────────────────────────────────

    def _set_size(self, w: int, h: int) -> None:
        self._iw = max(w, 1); self._ih = max(h, 1)
        self._mask_overlay  = None
        self._checker_cache = None
        self._checker_size  = QSize(0, 0)

    def _fit(self) -> None:
        if self._iw <= 0 or self._ih <= 0:
            return
        cw = max(self.width(), 100)
        ch = max(self.height(), 100)
        wr = cw / self._iw
        hr = ch / self._ih
        self.scale = min(wr, hr) * 0.92
        self._recenter()

    def _recenter(self) -> None:
        iw = int(self._iw * self.scale)
        ih = int(self._ih * self.scale)
        cw = max(self.width(), 100)
        ch = max(self.height(), 100)
        self.offset = QPoint(
            (cw - iw) // 2,
            (ch - ih) // 2,
        )

    def _to_img(self, pos: QPoint) -> QPoint:
        x = int((pos.x() - self.offset.x()) / max(self.scale, 0.001))
        y = int((pos.y() - self.offset.y()) / max(self.scale, 0.001))
        return QPoint(max(0, min(x, self._iw - 1)),
                      max(0, min(y, self._ih - 1)))

    # ── Handle Geometry ───────────────────────────────────────────────────────

    HANDLE_SIZE = 8

    def _get_handles(self, wr: QRect) -> dict[str, QRect]:
        hs = self.HANDLE_SIZE
        hs2 = hs // 2
        l, r = wr.left(), wr.right()
        t, b = wr.top(), wr.bottom()
        cx, cy = wr.center().x(), wr.center().y()
        return {
            'tl': QRect(l - hs2, t - hs2, hs, hs),
            'tm': QRect(cx - hs2, t - hs2, hs, hs),
            'tr': QRect(r - hs2, t - hs2, hs, hs),
            'ml': QRect(l - hs2, cy - hs2, hs, hs),
            'mr': QRect(r - hs2, cy - hs2, hs, hs),
            'bl': QRect(l - hs2, b - hs2, hs, hs),
            'bm': QRect(cx - hs2, b - hs2, hs, hs),
            'br': QRect(r - hs2, b - hs2, hs, hs),
        }

    def _hit_handle(self, pos: QPoint) -> str | None:
        if not self._active_box or not self._has_content():
            return None
        r = self._active_box
        wr = QRect(
            int(r.x() * self.scale) + self.offset.x(),
            int(r.y() * self.scale) + self.offset.y(),
            int(r.width()  * self.scale),
            int(r.height() * self.scale),
        )
        handles = self._get_handles(wr)
        for name, hrect in handles.items():
            if hrect.contains(pos):
                return name
        if wr.contains(pos):
            return 'move'
        return None

    # ── Subclass overrides ────────────────────────────────────────────────────

    def _display_img(self) -> QImage | None:
        return None

    def _has_content(self) -> bool:
        return False

    def _draw_placeholder(self, p: QPainter) -> None:
        pass

    # ── Paint ─────────────────────────────────────────────────────────────────

    def paintEvent(self, _) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        opacity = getattr(self, "canvas_bg_opacity", 34) / 100.0
        p.fillRect(self.rect(), QColor(10, 8, 20, int(255 * opacity)))
        if not self._has_content():
            self._draw_placeholder(p)
            return
        iw = int(self._iw * self.scale)
        ih = int(self._ih * self.scale)
        ir = QRect(self.offset.x(), self.offset.y(), iw, ih)
        self._checker(p, ir)
        di = self._display_img()
        if di:
            p.drawImage(ir, di)
        # Mask overlay
        if self.mask is not None and self.mask.any():
            if self._mask_overlay is None:
                self._rebuild_overlay()
            if self._mask_overlay is not None:
                p.drawImage(ir, self._mask_overlay)
        # Active selection box with 8 resize handles
        if self.tool in (self.TOOL_SMART, self.TOOL_SQUARE) and self._active_box and self._has_content():
            r = self._active_box
            wr = QRect(
                int(r.x() * self.scale) + self.offset.x(),
                int(r.y() * self.scale) + self.offset.y(),
                int(r.width()  * self.scale),
                int(r.height() * self.scale),
            )
            p.setPen(QPen(QColor(PURPLE_LIGHT), 2.0, Qt.PenStyle.SolidLine))
            p.setBrush(QBrush(QColor(167, 139, 250, 35)))
            p.drawRect(wr)

            handles = self._get_handles(wr)
            p.setPen(QPen(QColor(PURPLE), 1.5))
            p.setBrush(QBrush(QColor("#ffffff")))
            for hrect in handles.values():
                p.drawRoundedRect(hrect, 2, 2)

            tag = f"🪄 {r.width()}×{r.height()} px  (Drag handles to resize)"
            p.setFont(QFont("Segoe UI", 8, QFont.Weight.DemiBold))
            fm = QFontMetrics(p.font())
            tw = fm.horizontalAdvance(tag) + 16
            th = 18
            bx = wr.x()
            by = max(4, wr.y() - th - 4)
            p.setPen(QPen(QColor(PURPLE_LIGHT), 1.0))
            p.setBrush(QBrush(QColor(19, 19, 32, 230)))
            p.drawRoundedRect(bx, by, tw, th, 4, 4)
            p.setPen(QColor("#ffffff"))
            p.drawText(QRect(bx, by, tw, th), Qt.AlignmentFlag.AlignCenter, tag)

        # Dragging shape preview
        if (self.preview_rect and
                self.tool in (self.TOOL_SQUARE, self.TOOL_CIRCLE, self.TOOL_SMART)):
            r  = self.preview_rect
            wr = QRect(
                int(r.x() * self.scale) + self.offset.x(),
                int(r.y() * self.scale) + self.offset.y(),
                int(r.width()  * self.scale),
                int(r.height() * self.scale),
            )
            p.setPen(QPen(QColor(PURPLE_LIGHT), 1.5, Qt.PenStyle.DashLine))
            p.setBrush(QBrush(QColor(167, 139, 250, 28)))
            if self.tool == self.TOOL_CIRCLE:
                p.drawEllipse(wr)
            else:
                p.drawRect(wr)

        # Smart hover snap preview
        if (self.tool == self.TOOL_SMART and self._smart_rect and
                not self.drawing and self._has_content()):
            r = self._smart_rect
            wr = QRect(
                int(r.x() * self.scale) + self.offset.x(),
                int(r.y() * self.scale) + self.offset.y(),
                int(r.width()  * self.scale),
                int(r.height() * self.scale),
            )
            p.setPen(QPen(QColor(GREEN_SOFT), 2.0, Qt.PenStyle.DashLine))
            p.setBrush(QBrush(QColor(74, 222, 128, 40)))
            p.drawRoundedRect(wr, 4, 4)
            p.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
            p.setPen(QColor("#ffffff"))
            p.drawText(QRect(wr.x(), max(0, wr.y() - 16), max(180, wr.width()), 16),
                       Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                       "✨ Click to Snap Watermark")

        # Brush / eraser circle cursor
        if (self._has_content() and not self._panning and
                self.tool in (self.TOOL_BRUSH, self.TOOL_ERASER) and
                self._mouse_pos is not None):
            r = max(2, int(self.brush_size * self.scale))
            col = QColor(255, 90, 90, 200) if self.tool == self.TOOL_ERASER \
                  else QColor(167, 139, 250, 200)
            p.setPen(QPen(col, 1.2))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawEllipse(self._mouse_pos, r, r)

    def _rebuild_overlay(self) -> None:
        if self.mask is None or not self.mask.any():
            self._mask_overlay = None
            return
        ov          = np.zeros((self._ih, self._iw, 4), dtype=np.uint8)
        ov[self.mask > 0] = [255, 80, 80, 140]
        self._mask_overlay = QImage(
            np.ascontiguousarray(ov).tobytes(),
            self._iw, self._ih, self._iw * 4,
            QImage.Format.Format_RGBA8888).copy()

    def _checker(self, p: QPainter, r: QRect) -> None:
        needed = QSize(r.width(), r.height())
        if self._checker_cache is None or self._checker_size != needed:
            sz     = 9
            c1, c2 = QColor("#111120"), QColor("#17172a")
            pm     = QPixmap(needed)
            pm.fill(c1)
            pp = QPainter(pm)
            pp.setPen(Qt.PenStyle.NoPen)
            pp.setBrush(QBrush(c2))
            for row in range(needed.height() // sz + 1):
                for col in range(needed.width() // sz + 1):
                    if (row + col) % 2 == 1:
                        pp.fillRect(col * sz, row * sz,
                                    min(sz, needed.width()  - col * sz),
                                    min(sz, needed.height() - row * sz), c2)
            pp.end()
            self._checker_cache = pm
            self._checker_size  = needed
        p.drawPixmap(r.x(), r.y(), self._checker_cache)

    # ── Mouse ─────────────────────────────────────────────────────────────────

    def mousePressEvent(self, e) -> None:
        if (e.button() in (Qt.MouseButton.MiddleButton, Qt.MouseButton.RightButton) or
                self._space or
                self.tool == self.TOOL_PAN or
                bool(e.modifiers() & Qt.KeyboardModifier.AltModifier)):
            self._panning   = True
            self._pan_start = e.position().toPoint()
            self._pan_off   = QPoint(self.offset)
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            return
        if e.button() != Qt.MouseButton.LeftButton:
            return
        if not self._has_content():
            return

        pos = e.position().toPoint()

        if self.tool in (self.TOOL_SMART, self.TOOL_SQUARE):
            hit = self._hit_handle(pos) if self._active_box else None
            if hit is not None:
                self._push_undo()
                self.drawing = True
                self._drag_handle = hit
                self.drag_start = pos
                self._drag_start_box = QRect(self._active_box)
                return

            if self._smart_rect:
                self._push_undo()
                self._active_box = QRect(self._smart_rect)
                if self.mask is not None:
                    r = self._active_box
                    cv2.rectangle(self.mask, (r.x(), r.y()),
                                  (r.x() + r.width(), r.y() + r.height()), 255, -1)
                    self._invalidate_overlay()
                    self.mask_changed.emit()
                self._smart_rect = None
                self.status_msg.emit(
                    f"  🪄  Watermark snapped ({self._active_box.width()}×{self._active_box.height()} px)! Drag handles to resize.")
                self.update()
                return

            self._push_undo()
            self.drawing = True
            self._drag_handle = None
            self.drag_start = pos
            return

        self._push_undo()
        self.drawing    = True
        self.drag_start = pos
        if self.tool in (self.TOOL_BRUSH, self.TOOL_ERASER):
            self._brush(pos)
            self.last_pos = pos

    def mouseMoveEvent(self, e) -> None:
        pos = e.position().toPoint()
        self._mouse_pos = pos
        if self._panning and self._pan_start is not None:
            self.offset = self._pan_off + (pos - self._pan_start)
            self.update()
            return

        if not self.drawing:
            if self._space or self.tool == self.TOOL_PAN:
                self.setCursor(Qt.CursorShape.OpenHandCursor)
            elif self.tool in (self.TOOL_SMART, self.TOOL_SQUARE) and self._active_box:
                hit = self._hit_handle(pos)
                if hit in ('tl', 'br'):
                    self.setCursor(Qt.CursorShape.SizeFDiagCursor)
                elif hit in ('tr', 'bl'):
                    self.setCursor(Qt.CursorShape.SizeBDiagCursor)
                elif hit in ('tm', 'bm'):
                    self.setCursor(Qt.CursorShape.SizeVerCursor)
                elif hit in ('ml', 'mr'):
                    self.setCursor(Qt.CursorShape.SizeHorCursor)
                elif hit == 'move':
                    self.setCursor(Qt.CursorShape.SizeAllCursor)
                else:
                    self.setCursor(Qt.CursorShape.CrossCursor)
            else:
                self.setCursor(Qt.CursorShape.CrossCursor)

            if self.tool in (self.TOOL_BRUSH, self.TOOL_ERASER) and self._has_content():
                self.update()
            elif self.tool == self.TOOL_SMART and self._has_content():
                hit = self._hit_handle(pos) if self._active_box else None
                if hit is None:
                    img = self._current_cv_img()
                    if img is not None:
                        ip = self._to_img(self._mouse_pos)
                        self._smart_rect = detect_watermark_box_at(img, ip.x(), ip.y())
                        self.update()
                else:
                    if self._smart_rect is not None:
                        self._smart_rect = None
                        self.update()
            return

        if self._drag_handle and self._active_box and self._drag_start_box:
            ip = self._to_img(pos)
            s_ip = self._to_img(self.drag_start)
            dx = ip.x() - s_ip.x()
            dy = ip.y() - s_ip.y()
            sb = self._drag_start_box

            x, y, w, h = sb.x(), sb.y(), sb.width(), sb.height()
            h_type = self._drag_handle

            if h_type == 'move':
                x = max(0, min(self._iw - w, x + dx))
                y = max(0, min(self._ih - h, y + dy))
            elif h_type == 'br':
                w = max(4, min(self._iw - x, w + dx))
                h = max(4, min(self._ih - y, h + dy))
            elif h_type == 'tl':
                new_x = max(0, min(x + w - 4, x + dx))
                new_y = max(0, min(y + h - 4, y + dy))
                w = w + (x - new_x)
                h = h + (y - new_y)
                x = new_x
                y = new_y
            elif h_type == 'tr':
                new_y = max(0, min(y + h - 4, y + dy))
                w = max(4, min(self._iw - x, w + dx))
                h = h + (y - new_y)
                y = new_y
            elif h_type == 'bl':
                new_x = max(0, min(x + w - 4, x + dx))
                w = w + (x - new_x)
                h = max(4, min(self._ih - y, h + dy))
                x = new_x
            elif h_type == 'tm':
                new_y = max(0, min(y + h - 4, y + dy))
                h = h + (y - new_y)
                y = new_y
            elif h_type == 'bm':
                h = max(4, min(self._ih - y, h + dy))
            elif h_type == 'ml':
                new_x = max(0, min(x + w - 4, x + dx))
                w = w + (x - new_x)
                x = new_x
            elif h_type == 'mr':
                w = max(4, min(self._iw - x, w + dx))

            self._active_box = QRect(x, y, w, h)
            self.update()
            return

        if self.tool in (self.TOOL_BRUSH, self.TOOL_ERASER):
            self._stroke(self.last_pos, pos)
            self.last_pos = pos
        else:
            self._preview_update(self.drag_start, pos)

    def leaveEvent(self, e) -> None:
        self._mouse_pos = None
        self._smart_rect = None
        self.update()

    def mouseReleaseEvent(self, e) -> None:
        if self._panning:
            self._panning = False
            self._pan_start = None
            if self._space or self.tool == self.TOOL_PAN:
                self.setCursor(Qt.CursorShape.OpenHandCursor)
            else:
                self.setCursor(Qt.CursorShape.CrossCursor)
            return
        if not self.drawing:
            return
        self.drawing = False
        pos = e.position().toPoint()

        if self._drag_handle and self._active_box:
            self._drag_handle = None
            if self.mask is not None:
                r = self._active_box
                cv2.rectangle(self.mask, (r.x(), r.y()),
                              (r.x() + r.width(), r.y() + r.height()), 255, -1)
                self._invalidate_overlay()
                self.mask_changed.emit()
            self.update()
            return

        if (self.tool in (self.TOOL_SQUARE, self.TOOL_CIRCLE, self.TOOL_SMART)
                and self.drag_start and self.mask is not None):
            p1 = self._to_img(self.drag_start)
            p2 = self._to_img(pos)
            x1, x2 = min(p1.x(), p2.x()), max(p1.x(), p2.x())
            y1, y2 = min(p1.y(), p2.y()), max(p1.y(), p2.y())
            w = max(4, x2 - x1)
            h = max(4, y2 - y1)
            if self.tool == self.TOOL_CIRCLE:
                cx, cy = (x1 + x2) // 2, (y1 + y2) // 2
                cv2.ellipse(self.mask, (cx, cy),
                            (max(1, w // 2), max(1, h // 2)),
                            0, 0, 360, 255, -1)
            else:
                cv2.rectangle(self.mask, (x1, y1), (x1 + w, y1 + h), 255, -1)
                if self.tool in (self.TOOL_SMART, self.TOOL_SQUARE):
                    self._active_box = QRect(x1, y1, w, h)
            self._invalidate_overlay()
            self.mask_changed.emit()

        self.preview_rect = None
        self.last_pos     = None
        self.update()

    def wheelEvent(self, e) -> None:
        dy = e.angleDelta().y()
        if dy == 0: return
        factor    = 1.12 if dy > 0 else 0.89
        old_scale = self.scale
        new_scale = max(0.05, min(16.0, old_scale * factor))
        if new_scale == old_scale: return
        mp = e.position()
        ix = (mp.x() - self.offset.x()) / old_scale
        iy = (mp.y() - self.offset.y()) / old_scale
        self.scale  = new_scale
        self.offset = QPoint(int(mp.x() - ix * new_scale),
                             int(mp.y() - iy * new_scale))
        self.update()

    def resizeEvent(self, e) -> None:
        self._recenter()
        self._checker_cache = None
        self._checker_size  = QSize(0, 0)
        super().resizeEvent(e)

    def keyPressEvent(self, e) -> None:
        if e.key() == Qt.Key.Key_Space and not e.isAutoRepeat():
            self._space = True
            if self.drawing:
                # If space was hit while drawing, cancel stroke and switch to pan immediately
                self.drawing = False
                self.drag_start = None
                self.preview_rect = None
                self.last_pos = None
                if self._undo:
                    self.mask = self._undo.pop()
                    self._invalidate_overlay()
                    self.mask_changed.emit()
            if not self._panning:
                self.setCursor(Qt.CursorShape.OpenHandCursor)
        super().keyPressEvent(e)

    def keyReleaseEvent(self, e) -> None:
        if e.key() == Qt.Key.Key_Space and not e.isAutoRepeat():
            self._space = False
            if not self._panning:
                if self.tool == self.TOOL_PAN:
                    self.setCursor(Qt.CursorShape.OpenHandCursor)
                else:
                    self.setCursor(Qt.CursorShape.CrossCursor)
        super().keyReleaseEvent(e)

    # ── Drawing ───────────────────────────────────────────────────────────────

    def _brush(self, pos: QPoint) -> None:
        ip = self._to_img(pos)
        if self.mask is not None:
            val = 0 if self.tool == self.TOOL_ERASER else 255
            cv2.circle(self.mask, (ip.x(), ip.y()), self.brush_size, val, -1)
            self._invalidate_overlay()
            self.update()

    def _stroke(self, p1: QPoint | None, p2: QPoint) -> None:
        if p1 is None:
            self._brush(p2)
            return
        ip1 = self._to_img(p1)
        ip2 = self._to_img(p2)
        if self.mask is not None:
            val = 0 if self.tool == self.TOOL_ERASER else 255
            cv2.line(self.mask, (ip1.x(), ip1.y()),
                     (ip2.x(), ip2.y()), val, self.brush_size * 2)
        self._brush(p2)

    def _preview_update(self, s: QPoint | None, e: QPoint) -> None:
        if s is None:
            return
        p1 = self._to_img(s)
        p2 = self._to_img(e)
        x1, x2 = min(p1.x(), p2.x()), max(p1.x(), p2.x())
        y1, y2 = min(p1.y(), p2.y()), max(p1.y(), p2.y())
        self.preview_rect = QRect(x1, y1, x2 - x1, y2 - y1)
        self.update()

    # ── Undo / redo ───────────────────────────────────────────────────────────

    def _push_undo(self) -> None:
        if self.mask is not None:
            self._undo.append(self.mask.copy())
            if len(self._undo) > self._max_undo:
                self._undo.pop(0)
            self._redo.clear()

    def _push_img_undo(self) -> None:
        img = self._current_cv_img()
        if img is not None and self.mask is not None:
            self._img_history.append((img.copy(), self.mask.copy()))
            if len(self._img_history) > self._max_undo:
                self._img_history.pop(0)
            self._img_future.clear()

    def _invalidate_overlay(self) -> None:
        self._mask_overlay = None

    def undo(self) -> None:
        if self._img_history:
            prev_img, prev_mask = self._img_history.pop()
            curr_img = self._current_cv_img()
            if curr_img is not None and self.mask is not None:
                self._img_future.append((curr_img.copy(), self.mask.copy()))
            self._apply_cv_img(prev_img)
            self.mask = prev_mask.copy()
            self._invalidate_overlay()
            self.mask_changed.emit()
            self.update()
            self.status_msg.emit(
                f"  ↩  Undo image edit  ({len(self._img_history) + len(self._undo)} steps left)")
            return

        if not self._undo:
            self.status_msg.emit("  ℹ️  Nothing to undo")
            return
        self._redo.append(self.mask.copy())
        self.mask = self._undo.pop()
        self._invalidate_overlay()
        self.mask_changed.emit()
        self.update()
        self.status_msg.emit(
            f"  ↩  Undo  ({len(self._undo)} step{'s' if len(self._undo)!=1 else ''} left)")

    def redo(self) -> None:
        if self._img_future:
            next_img, next_mask = self._img_future.pop()
            curr_img = self._current_cv_img()
            if curr_img is not None and self.mask is not None:
                self._img_history.append((curr_img.copy(), self.mask.copy()))
            self._apply_cv_img(next_img)
            self.mask = next_mask.copy()
            self._invalidate_overlay()
            self.mask_changed.emit()
            self.update()
            self.status_msg.emit(f"  ↪  Redo image edit")
            return

        if not self._redo:
            self.status_msg.emit("  ℹ️  Nothing to redo")
            return
        self._undo.append(self.mask.copy())
        self.mask = self._redo.pop()
        self._invalidate_overlay()
        self.mask_changed.emit()
        self.update()
        self.status_msg.emit("  ↪  Redo")

    def clear_mask(self) -> None:
        if self.mask is not None:
            self._push_undo()
            self.mask.fill(0)
            self._invalidate_overlay()
            self.mask_changed.emit()
            self.update()
            self.status_msg.emit("  🧹  Mask cleared")

    def expand_mask(self, px: int = 2) -> None:
        if self.mask is None or not self.mask.any():
            self.status_msg.emit("  ⚠️  Draw a mask first!")
            return
        self._push_undo()
        k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (px * 2 + 1, px * 2 + 1))
        self.mask = cv2.dilate(self.mask, k)
        self._invalidate_overlay()
        self.mask_changed.emit()
        self.update()
        self.status_msg.emit(f"  ⤢  Mask expanded (+{px}px)")

    def contract_mask(self, px: int = 2) -> None:
        if self.mask is None or not self.mask.any():
            self.status_msg.emit("  ⚠️  Draw a mask first!")
            return
        self._push_undo()
        k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (px * 2 + 1, px * 2 + 1))
        self.mask = cv2.erode(self.mask, k)
        self._invalidate_overlay()
        self.mask_changed.emit()
        self.update()
        self.status_msg.emit(f"  ⤡  Mask contracted (-{px}px)")

    def invert_mask(self) -> None:
        if self.mask is None:
            return
        self._push_undo()
        self.mask = cv2.bitwise_not(self.mask)
        self._invalidate_overlay()
        self.mask_changed.emit()
        self.update()
        self.status_msg.emit("  🔄  Mask inverted")

    def undo_count(self) -> int:
        return len(self._img_history) + len(self._undo)
# ─── Image Canvas ─────────────────────────────────────────────────────────────

class Canvas(BaseCanvas):
    inpaint_done = Signal()
    busy_changed = Signal(bool)

    def __init__(self):
        super().__init__()
        self.cv_orig:   np.ndarray | None = None
        self.cv_cur:    np.ndarray | None = None
        self._qi:       QImage    | None  = None
        self._qi_orig:  QImage    | None  = None
        self._show_orig: bool = False
        self._mouse_pos: QPoint   | None  = None
        self._busy      = False
        self._worker:   InpaintWorker | None = None
        self.setAcceptDrops(True)

    def _display_img(self)  -> QImage | None:
        if self._show_orig and self._qi_orig is not None:
            return self._qi_orig
        return self._qi
    def _has_content(self)  -> bool: return self.cv_orig is not None
    def _current_cv_img(self) -> np.ndarray | None: return self.cv_cur

    def _draw_placeholder(self, p: QPainter) -> None:
        cx, cy = self.width() // 2, self.height() // 2
        box = QRect(cx - 180, cy - 106, 360, 212)
        p.setPen(QPen(QColor(BORDER_LIT), 1.2, Qt.PenStyle.DashLine))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(box, 14, 14)
        p.setFont(QFont("Segoe UI", 28))
        p.setPen(QColor(PURPLE_LIGHT))
        p.drawText(QRect(cx - 22, cy - 60, 44, 44),
                   Qt.AlignmentFlag.AlignCenter, "🪄")
        p.setFont(QFont("Segoe UI", 12, QFont.Weight.Medium))
        p.setPen(QColor(TEXT_MAIN))
        p.drawText(QRect(cx - 180, cy - 8, 360, 24),
                   Qt.AlignmentFlag.AlignCenter, "Drop an image here")
        p.setFont(QFont("Segoe UI", 10))
        p.setPen(QColor(TEXT_DIM))
        p.drawText(QRect(cx - 180, cy + 20, 360, 20),
                   Qt.AlignmentFlag.AlignCenter, "or click Open Image below")
        p.setPen(QColor(TEXT_FAINT))
        p.setFont(QFont("Segoe UI", 9))
        p.drawText(QRect(cx - 180, cy + 46, 360, 18),
                   Qt.AlignmentFlag.AlignCenter,
                   "PNG · JPG · JPEG · BMP · WEBP")

    def paintEvent(self, e) -> None:
        super().paintEvent(e)
        if self._busy:
            p = QPainter(self)
            p.fillRect(self.rect(), QColor(0, 0, 0, 130))
            p.setPen(QColor(PURPLE_LIGHT))
            p.setFont(QFont("Segoe UI", 13, QFont.Weight.Medium))
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter,
                       "✨  Removing watermark…")
            return

    def load_cv_img(self, img: np.ndarray) -> bool:
        if img is None:
            return False
        h, w        = img.shape[:2]
        self.cv_orig = img.copy()
        self.cv_cur  = img.copy()
        self._set_size(w, h)
        self.mask   = np.zeros((h, w), dtype=np.uint8)
        self._undo.clear()
        self._redo.clear()
        self._qi      = cv2_to_qimage(img)
        self._qi_orig = self._qi
        self._show_orig = False
        self._fit()
        self.update()
        return True

    def load_image(self, path: str) -> bool:
        img = cv2.imread(path)
        if img is None:
            self.status_msg.emit(
                f"  ❌  Cannot open: {Path(path).name}")
            return False
        h, w        = img.shape[:2]
        self.cv_orig = img
        self.cv_cur  = img.copy()
        self._set_size(w, h)
        self.mask   = np.zeros((h, w), dtype=np.uint8)
        self._undo.clear()
        self._redo.clear()
        self._qi      = cv2_to_qimage(img)
        self._qi_orig = self._qi  # save original for before/after
        self._show_orig = False
        self._fit()
        self.update()
        kb = Path(path).stat().st_size // 1024
        self.status_msg.emit(
            f"  📂  {Path(path).name}   ·   {w}×{h}   ·   {kb} KB")
        return True
        return True

    def dragEnterEvent(self, e) -> None:
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e) -> None:
        for url in e.mimeData().urls():
            fp = url.toLocalFile()
            if fp.lower().endswith((".png",".jpg",".jpeg",".bmp",".webp")):
                self.load_image(fp)
                break

    def _apply_cv_img(self, img: np.ndarray) -> None:
        self.cv_cur = img.copy()
        self._qi = cv2_to_qimage(self.cv_cur)

    def reset_to_original(self) -> None:
        if self.cv_orig is None:
            return
        self._push_img_undo()
        self.cv_cur   = self.cv_orig.copy()
        self._qi      = cv2_to_qimage(self.cv_cur)
        self._qi_orig = self._qi
        self._show_orig = False
        self.mask.fill(0)
        self._invalidate_overlay()
        self.mask_changed.emit()
        self.update()
        self.status_msg.emit("  ↩  Reset to original")

    def apply_preset(self, preset: dict) -> int | None:
        if self.cv_cur is None:
            self.status_msg.emit("  ⚠️  Load an image first!")
            return None
        h, w = self.cv_cur.shape[:2]
        if self.mask is None or self.mask.shape[:2] != (h, w):
            self.mask = np.zeros((h, w), dtype=np.uint8)
        new_mask = decode_mask(preset, w, h)
        self._push_undo()
        self.mask = np.maximum(self.mask, new_mask)
        self._invalidate_overlay()
        self.mask_changed.emit()
        self.update()
        lvl = preset.get("level", LEVEL_QUICK)
        lvl_names = {LEVEL_QUICK: "Quick", LEVEL_SMART: "Smart", LEVEL_PRECISION: "Precision", LEVEL_CEL_AI: "Cel AI"}
        self.status_msg.emit(
            f"  ✅  Preset '{preset.get('name', 'Preset')}' applied ({lvl_names.get(lvl, 'Quick')}) — click Remove!")
        return lvl

    def do_inpaint(self, level: int = LEVEL_QUICK) -> None:
        if self.cv_cur is None:
            self.status_msg.emit("  ⚠️  No image loaded!"); return
        if self.mask is None or not self.mask.any():
            self.status_msg.emit("  ⚠️  Paint the watermark first!"); return
        # Guard: stop any existing worker
        if self._worker is not None and self._worker.isRunning():
            self._worker.stop()
            self._worker.wait(300)
        self._push_img_undo()
        names = {LEVEL_QUICK: "Quick", LEVEL_SMART: "Smart",
                 LEVEL_PRECISION: "Precision", LEVEL_CEL_AI: "Cel AI"}
        self._last_level_name = names.get(level, "Cel AI").replace(" ", "_")
        self.status_msg.emit(
            f"  ⏳  {names.get(level, 'Inpaint')}…  0%")
        self._busy = True
        self.busy_changed.emit(True)
        self.update()
        self._worker = InpaintWorker(self.cv_cur, self.mask, level)
        self._worker.finished.connect(self._done)
        self._worker.error.connect(self._err)
        self._worker.progress.connect(
            lambda pct: self.status_msg.emit(
                f"  ⏳  Inpainting…  {pct}%"))
        self._worker.start()

    def _done(self, result: np.ndarray) -> None:
        if not self._busy:
            return  # cancelled / cleaned up already
        self.cv_cur = result
        self._qi    = cv2_to_qimage(result)
        if self.mask is not None:
            self.mask.fill(0)
        self._invalidate_overlay()
        self.mask_changed.emit()
        self._busy  = False
        self.busy_changed.emit(False)
        self.update()
        self.status_msg.emit("  ✨  Done! Save to gallery when ready.")
        self.inpaint_done.emit()

    def _err(self, msg: str) -> None:
        self._busy = False
        self.busy_changed.emit(False)
        self.update()
        self.status_msg.emit(f"  ❌  {msg.splitlines()[0]}")

    def save_result(self, fmt: str = "png",
                    quality: int = 95) -> "Path | None":
        if self.cv_cur is None:
            print("[SAVE] No image in memory to save.")
            return None
        try:
            save_dir = get_save_dir()
            save_dir.mkdir(parents=True, exist_ok=True)
            ts  = datetime.now().strftime("%Y%m%d_%H%M%S")
            ext = fmt.lower().strip(".")
            lvl_tag = getattr(self, "_last_level_name", "Cel_AI")
            src_stem = Path(self.file_path).stem if hasattr(self, "file_path") and self.file_path else "image"
            out = save_dir / f"{src_stem}_{lvl_tag}_{ts}.{ext}"
            if ext in ("jpg", "jpeg"):
                params = [cv2.IMWRITE_JPEG_QUALITY, quality]
            elif ext == "webp":
                params = [cv2.IMWRITE_WEBP_QUALITY, quality]
            else:
                params = []
            print(f"[SAVE] Writing image to: {out}")
            ok = cv2.imwrite(str(out), self.cv_cur, params)
            if not ok:
                err = f"cv2.imwrite failed writing to {out}. Check permissions or disk space."
                print(f"[SAVE ERROR] {err}")
                self.status_msg.emit(f"  ❌  imwrite failed: {out.name}")
                return None
            print(f"[SAVE SUCCESS] Successfully saved image to: {out} ({out.stat().st_size / 1024:.1f} KB)")
            return out
        except Exception as exc:
            err = f"Save error: {exc}\n{traceback.format_exc()}"
            print(f"[SAVE ERROR] {err}")
            self.status_msg.emit(f"  ❌  Save error: {exc}")
            return None

    def toggle_compare(self, show: bool) -> None:
        """Show original (True) or edited (False)."""
        if self.cv_orig is None:
            return
        self._show_orig = show
        self.update()

    def copy_to_clipboard(self) -> None:
        if self.cv_cur is None:
            self.status_msg.emit("  ⚠️  No image to copy!")
            return
        QApplication.clipboard().setImage(cv2_to_qimage(self.cv_cur))
        self.status_msg.emit("  📋  Image copied to clipboard!")

    def cleanup(self) -> None:
        """Call before app close to stop any running worker."""
        if self._worker is not None and self._worker.isRunning():
            self._worker.stop()
            self._worker.wait(500)
# ─── Video Canvas ─────────────────────────────────────────────────────────────

class VideoCanvas(BaseCanvas):
    video_dropped = Signal(str)

    def __init__(self):
        super().__init__()
        self._frame: np.ndarray | None = None
        self._qf:    QImage    | None  = None
        self._banner_text: str = ""
        self.setAcceptDrops(True)

    def _apply_cv_img(self, img: np.ndarray) -> None:
        self._frame = img.copy()
        self._qf = cv2_to_qimage(self._frame)

    def set_banner(self, txt: str) -> None:
        self._banner_text = txt
        self.update()

    def dragEnterEvent(self, e) -> None:
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e) -> None:
        for url in e.mimeData().urls():
            fp = url.toLocalFile()
            if fp.lower().endswith((".mp4", ".avi", ".mkv", ".mov", ".webm")):
                self.video_dropped.emit(fp)
                break

    def _display_img(self) -> QImage | None: return self._qf
    def _has_content(self) -> bool: return self._frame is not None
    def _current_cv_img(self) -> np.ndarray | None: return self._frame

    def _draw_placeholder(self, p: QPainter) -> None:
        cx, cy = self.width() // 2, self.height() // 2
        box = QRect(cx - 180, cy - 96, 360, 192)
        p.setPen(QPen(QColor(BORDER_LIT), 1.2, Qt.PenStyle.DashLine))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(box, 14, 14)
        p.setFont(QFont("Segoe UI", 28))
        p.setPen(QColor(PURPLE_LIGHT))
        p.drawText(QRect(cx - 22, cy - 54, 44, 44),
                   Qt.AlignmentFlag.AlignCenter, "🎬")
        p.setFont(QFont("Segoe UI", 12, QFont.Weight.Medium))
        p.setPen(QColor(TEXT_MAIN))
        p.drawText(QRect(cx - 180, cy - 4, 360, 24),
                   Qt.AlignmentFlag.AlignCenter,
                   "Load a video to get started")
        p.setFont(QFont("Segoe UI", 9))
        p.setPen(QColor(TEXT_FAINT))
        p.drawText(QRect(cx - 180, cy + 24, 360, 18),
                   Qt.AlignmentFlag.AlignCenter,
                   "MP4 · AVI · MKV · MOV")

    def paintEvent(self, e) -> None:
        super().paintEvent(e)
        if self._banner_text and self._has_content():
            p = QPainter(self)
            p.setRenderHint(QPainter.RenderHint.Antialiasing)
            font = QFont("Segoe UI", 10, QFont.Weight.DemiBold)
            p.setFont(font)
            fm = QFontMetrics(font)
            tw = fm.horizontalAdvance(self._banner_text) + 32
            th = 32
            bx = (self.width() - tw) // 2
            by = 14
            p.setPen(QPen(QColor(PURPLE_LIGHT), 1.2))
            p.setBrush(QBrush(QColor(19, 19, 32, 235)))
            p.drawRoundedRect(bx, by, tw, th, 16, 16)
            p.setPen(QColor("#ffffff"))
            p.drawText(QRect(bx, by, tw, th), Qt.AlignmentFlag.AlignCenter, self._banner_text)

    def load_frame(self, frame: np.ndarray) -> None:
        is_first = (self._frame is None)
        h, w     = frame.shape[:2]
        self._set_size(w, h)
        self._frame = frame
        self._qf    = cv2_to_qimage(frame)
        if self.mask is None or self.mask.shape != (h, w):
            self.mask = np.zeros((h, w), dtype=np.uint8)
        if is_first:
            self._fit()
        self.update()

    def get_mask(self) -> np.ndarray | None:
        return self.mask.copy() if self.mask is not None else None

