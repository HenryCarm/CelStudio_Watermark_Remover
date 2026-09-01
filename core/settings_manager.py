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

# ─── Settings ─────────────────────────────────────────────────────────────────
DEFAULT_SETTINGS: dict = {
    "keybinds": {
        "smart":      "S",
        "brush":      "B",
        "eraser":     "X",
        "rect":       "R",
        "ellipse":    "E",
        "pan":        "H",
        "clear_mask": "Delete",
        "undo":       "Ctrl+Z",
        "redo":       "Ctrl+Y",
        "save":       "Ctrl+S",
        "open":       "Ctrl+O",
        "new_preset": "Ctrl+P",
        "toggle_presets": "Ctrl+Shift+P",
        "zoom_in":    "=",
        "zoom_out":   "-",
        "zoom_reset": "0",
        "pan_modifier": "Space",
    },
    "brush_size":    25,
    "default_level": 0,
    "max_undo":      30,
    "tooltip_hover": 250,
    "tooltip_hide":  750,
    "video_format":  "mp4",
    "match_thresh":  0.45,
    "gallery_cols":  4,
    "compact_sidebar": True,
    "live_logging":  False,
    "last_inpaint_level": 0,
    "custom_data_dir": "",
    "custom_save_dir": "",
    "custom_log_dir": "",
    "wallpaper_enabled": True,
    "wallpaper_path": "",
    "wallpaper_tint": 33,
    "wallpaper_mode": "fill",
    "canvas_bg_opacity": 67,
}

def load_settings() -> dict:
    if SETTINGS_FILE.exists():
        try:
            d = json.loads(SETTINGS_FILE.read_text())
            m = DEFAULT_SETTINGS.copy()
            m.update({k: v for k, v in d.items() if k != "keybinds"})
            m["keybinds"] = {**DEFAULT_SETTINGS["keybinds"],
                             **d.get("keybinds", {})}
            return m
        except Exception:
            pass
    return {k: (v.copy() if isinstance(v, dict) else v)
            for k, v in DEFAULT_SETTINGS.items()}

def save_settings(s: dict) -> None:
    SETTINGS_FILE.write_text(json.dumps(s, indent=2))

def load_presets() -> list:
    f = get_data_dir() / "presets.json"
    if f.exists():
        try:
            return json.loads(f.read_text())
        except Exception:
            pass
    if PRESETS_FILE.exists():
        try:
            return json.loads(PRESETS_FILE.read_text())
        except Exception:
            pass
    old_f = OLD_DATA_DIR / "presets.json"
    if old_f.exists():
        try:
            return json.loads(old_f.read_text())
        except Exception:
            pass
    return []

def save_presets(p: list) -> None:
    d = get_data_dir()
    d.mkdir(parents=True, exist_ok=True)
    (d / "presets.json").write_text(json.dumps(p, indent=2))

