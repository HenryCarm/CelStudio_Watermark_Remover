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

from .constants import *
from .settings_manager import *

# ─── Mask encode/decode ───────────────────────────────────────────────────────

def encode_mask(mask: np.ndarray, img_w: int, img_h: int) -> dict | None:
    if mask is None or not mask.any():
        return None
    coords = cv2.findNonZero(mask)
    if coords is None:
        return None
    x, y, w, h = cv2.boundingRect(coords)
    w, h = max(w, 1), max(h, 1)
    region = mask[y:y+h, x:x+w]
    MAX = 512
    if max(w, h) > MAX:
        sc = MAX / max(w, h)
        nw, nh = max(1, int(w*sc)), max(1, int(h*sc))
        region = cv2.resize(region, (nw, nh), interpolation=cv2.INTER_NEAREST)
    rh, rw = region.shape
    bits  = (region.flatten() > 0).astype(np.uint8)
    pad   = (8 - len(bits) % 8) % 8
    packed = np.packbits(np.pad(bits, (0, pad)))
    b64   = base64.b64encode(packed.tobytes()).decode()
    return {
        "x_pct": round(x / img_w * 100, 3),
        "y_pct": round(y / img_h * 100, 3),
        "w_pct": round(w / img_w * 100, 3),
        "h_pct": round(h / img_h * 100, 3),
        "mask_data": f"{b64}|{rw}|{rh}",
    }

def decode_mask(preset: dict, img_w: int, img_h: int) -> np.ndarray:
    full = np.zeros((img_h, img_w), dtype=np.uint8)
    x  = max(0, min(int(preset["x_pct"] / 100 * img_w), img_w - 1))
    y  = max(0, min(int(preset["y_pct"] / 100 * img_h), img_h - 1))
    w  = max(1, min(int(preset["w_pct"] / 100 * img_w), img_w - x))
    h  = max(1, min(int(preset["h_pct"] / 100 * img_h), img_h - y))
    md = preset.get("mask_data", "")
    if md and "|" in md:
        parts = md.split("|")
        b64, rw, rh = parts[0], int(parts[1]), int(parts[2])
        packed = np.frombuffer(base64.b64decode(b64), dtype=np.uint8)
        bits   = np.unpackbits(packed)[:rw * rh].reshape(rh, rw)
        region = cv2.resize((bits * 255).astype(np.uint8), (w, h),
                            interpolation=cv2.INTER_NEAREST)
        full[y:y+h, x:x+w] = region
    else:
        full[y:y+h, x:x+w] = 255
    return full

