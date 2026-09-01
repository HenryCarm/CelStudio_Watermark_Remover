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

# ─── HelpBubble ───────────────────────────────────────────────────────────────

class HelpBubble(QLabel):
    """Small ⓘ that shows a tooltip with configurable timing and pin on click."""
    def __init__(self, text: str, hover_ms: int = 250,
                 hide_ms: int = 750, parent=None):
        super().__init__("ⓘ", parent)
        self._tip     = text
        self.hover_ms = hover_ms
        self.hide_ms  = hide_ms
        self._pinned  = False
        self._st = QTimer(self, singleShot=True)
        self._st.timeout.connect(self._do_show)
        self._ht = QTimer(self, singleShot=True)
        self._ht.timeout.connect(self._do_hide)
        self.setFixedSize(15, 15)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setCursor(Qt.CursorShape.WhatsThisCursor)
        self._paint(False)

    def _paint(self, hov: bool) -> None:
        c = PURPLE_LIGHT if hov else TEXT_FAINT
        self.setStyleSheet(
            f"color:{c};font-size:10px;font-weight:700;"
            f"background:transparent;border:none;")

    def _do_show(self) -> None:
        from PySide6.QtWidgets import QToolTip
        QToolTip.showText(self.mapToGlobal(QPoint(18, -4)), self._tip, self)

    def _do_hide(self) -> None:
        from PySide6.QtWidgets import QToolTip
        if not self._pinned:
            QToolTip.hideText()

    def enterEvent(self, _) -> None:
        self._paint(True)
        self._ht.stop()
        if not self._pinned:
            self._st.start(self.hover_ms)

    def leaveEvent(self, _) -> None:
        self._paint(False)
        self._st.stop()
        if not self._pinned:
            self._ht.start(self.hide_ms)

    def mousePressEvent(self, e) -> None:
        if e.button() == Qt.MouseButton.LeftButton:
            self._pinned = not self._pinned
            if self._pinned:
                self._st.stop()
                self._ht.stop()
                self._do_show()
            else:
                self._ht.start(self.hide_ms)
# ─── KeyCapture button ────────────────────────────────────────────────────────

class KeyCapture(QPushButton):
    key_captured = Signal(str)

    def __init__(self, key_str: str, parent=None):
        super().__init__(key_str, parent)
        self._rec = False
        self.setFixedWidth(110)
        self.clicked.connect(self._toggle)

    def _toggle(self) -> None:
        self._rec = not self._rec
        if self._rec:
            self.setText("▶  press key…")
            self.setStyleSheet(
                f"background:{ORANGE_DIM};color:{ORANGE_SOFT};"
                f"border:1px solid #4a2800;border-radius:6px;")
        else:
            self.setStyleSheet("")

    def keyPressEvent(self, event) -> None:
        if not self._rec:
            super().keyPressEvent(event)
            return
        key = event.key()
        if key in (Qt.Key.Key_Control, Qt.Key.Key_Shift,
                   Qt.Key.Key_Alt, Qt.Key.Key_Meta):
            return
        mods  = event.modifiers()
        parts = []
        if mods & Qt.KeyboardModifier.ControlModifier: parts.append("Ctrl")
        if mods & Qt.KeyboardModifier.ShiftModifier:   parts.append("Shift")
        if mods & Qt.KeyboardModifier.AltModifier:     parts.append("Alt")
        k = QKeySequence(key).toString()
        if k:
            parts.append(k)
        result = "+".join(parts)
        self.setText(result or "?")
        self._rec = False
        self.setStyleSheet("")
        if result:
            self.key_captured.emit(result)
# ─── Compact tool button ──────────────────────────────────────────────────────

class ToolBtn(QToolButton):
    def __init__(self, icon: str, tip: str):
        super().__init__()
        self.setCheckable(True)
        self.setFixedSize(38, 38)
        self.setToolTip(tip)
        self.setText(icon)
        self.setFont(QFont("Segoe UI", 16))

