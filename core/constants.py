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

# ─── Paths ────────────────────────────────────────────────────────────────────
SCRIPT_DIR    = Path(__file__).resolve().parent
ICON_PATH     = SCRIPT_DIR / "icon.png"
BANNER_PATH   = SCRIPT_DIR / "banner.png"
WALLPAPER_PATH = SCRIPT_DIR / "wallpaper.webp"
LOG_DIR       = SCRIPT_DIR / "logs"
DATA_DIR      = Path.home()/"Documents"/"HenryJay Data Folder"/"CelStudio Watermark Remover"
OLD_DATA_DIR  = Path.home()/"Documents"/"HenryJay Data Folder"/"MyScreen Watermark Remover"
SAVE_DIR      = Path.home()/"Pictures"/"CelStudio Watermark Remover Edits"
OLD_SAVE_DIR  = Path.home()/"Pictures"/"MyScreen Watermark Remover Edits"
TRASH_DIR     = Path.home()/"Documents"/"Projects"/"OpenCode"/"tmp"/"Trash"
DATA_DIR.mkdir(parents=True, exist_ok=True)
SAVE_DIR.mkdir(parents=True, exist_ok=True)
TRASH_DIR.mkdir(parents=True, exist_ok=True)
SETTINGS_FILE = DATA_DIR / "settings.json"
PRESETS_FILE  = DATA_DIR / "presets.json"
APP_VERSION   = "1.7.0"
BUILD_DATE    = "2026-03-15"

MOBILE_WIDTH_THRESHOLD = 700   # px — treat as mobile if window width < this

def get_data_dir() -> Path:
    try:
        s = load_settings()
        c = s.get("custom_data_dir")
        if c:
            p = Path(c)
            p.mkdir(parents=True, exist_ok=True)
            return p
    except Exception:
        pass
    return DATA_DIR

def get_save_dir() -> Path:
    try:
        s = load_settings()
        c = s.get("custom_save_dir")
        if c:
            p = Path(c)
            p.mkdir(parents=True, exist_ok=True)
            return p
    except Exception:
        pass
    return SAVE_DIR

def get_log_dir() -> Path:
    try:
        s = load_settings()
        c = s.get("custom_log_dir")
        if c:
            p = Path(c)
            p.mkdir(parents=True, exist_ok=True)
            return p
    except Exception:
        pass
    return LOG_DIR

def get_app_icon() -> QIcon:
    if not ICON_PATH.exists():
        return QIcon()
    base_pixmap = QPixmap(str(ICON_PATH))
    if base_pixmap.isNull():
        return QIcon()
    icon = QIcon()
    for size in (16, 24, 32, 48, 64, 128, 256):
        scaled = base_pixmap.scaled(size, size, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
        icon.addPixmap(scaled)
    return icon

def get_wallpaper_path() -> Path:
    try:
        s = load_settings()
        c = s.get("wallpaper_path")
        if c and Path(c).exists():
            return Path(c)
    except Exception:
        pass
    if WALLPAPER_PATH.exists():
        return WALLPAPER_PATH
    fallback = Path("/home/henry/Documents/Projects/Python/cel-weave-1600x900-q90.webp")
    if fallback.exists():
        return fallback
    return WALLPAPER_PATH
# ─── Colors ───────────────────────────────────────────────────────────────────
BG_DEEP      = "#09090f"
BG_BASE      = "#0e0e1a"
BG_CARD      = "#131320"
BG_RAISED    = "#1a1a2c"
BG_HOVER     = "#22223a"
BORDER       = "#1e1e38"
BORDER_LIT   = "#2c2c50"
PURPLE       = "#7c3aed"
PURPLE_LIGHT = "#a78bfa"
PURPLE_DIM   = "#2a1d5a"
TEXT_MAIN    = "#e4e4f0"
TEXT_DIM     = "#7070a0"
TEXT_FAINT   = "#3a3a60"
RED_ACCENT   = "#ef4444"
RED_SOFT     = "#f87171"
RED_DIM      = "#250d0d"
RED_BORDER   = "#3a1010"
GREEN_SOFT   = "#4ade80"
GREEN_DIM    = "#0c2016"
ORANGE_SOFT  = "#fb923c"
ORANGE_DIM   = "#261000"

APP_STYLE = f"""
* {{
    font-family: 'Inter', 'SF Pro Display', 'Segoe UI', system-ui, sans-serif;
    font-size: 12px;
    color: {TEXT_MAIN};
    outline: none;
}}
QMainWindow, QDialog {{ background: {BG_DEEP}; }}
QWidget {{ background: transparent; }}

/* ── Tabs ─────────────────────────────────────────── */
QTabWidget {{ background: {BG_DEEP}; border: none; }}
QTabWidget::pane {{ border: none; background: {BG_BASE}; }}
QTabBar {{
    background: {BG_DEEP};
    qproperty-drawBase: 0;
    border-bottom: 1px solid {BORDER};
}}
QTabBar::tab {{
    background: {BG_DEEP}; color: {TEXT_DIM};
    padding: 8px 18px; border: none;
    border-bottom: 2px solid transparent;
    font-size: 11px; font-weight: 600;
    min-width: 64px;
}}
QTabBar::tab:selected {{
    color: {PURPLE_LIGHT}; border-bottom: 2px solid {PURPLE};
    font-weight: 700;
    background: #140b29;
}}
QTabBar::tab:hover:!selected {{
    color: {TEXT_MAIN}; background: {BG_RAISED};
}}

/* ── Buttons ──────────────────────────────────────── */
QPushButton {{
    background: {BG_RAISED};
    color: {TEXT_MAIN};
    border: 1px solid {BORDER_LIT};
    border-radius: 6px;
    padding: 5px 12px;
    font-size: 11px;
    font-weight: 500;
    min-height: 14px;
}}
QPushButton:hover {{
    background: {BG_HOVER};
    border-color: {PURPLE_LIGHT};
    color: #fff;
}}
QPushButton:pressed {{ background: {PURPLE}; border-color: {PURPLE}; }}
QPushButton:disabled {{
    background: {BG_CARD};
    color: {TEXT_FAINT};
    border-color: {BORDER};
}}
QPushButton#cta {{
    background: {PURPLE};
    color: #fff;
    border: none;
    border-radius: 6px;
    font-weight: 700;
    font-size: 12px;
    padding: 7px 16px;
    min-height: 20px;
}}
QPushButton#cta:hover {{
    background: #8b5cf6;
}}
QPushButton#cta:pressed {{ background: #6d28d9; }}
QPushButton#cta:disabled {{
    background: {PURPLE_DIM}; color: {TEXT_FAINT};
}}
QPushButton#remove_btn {{
    background: #10b981;
    color: #ffffff;
    border: 1px solid #059669;
    border-radius: 6px;
    font-weight: 700;
    font-size: 12px;
    padding: 5px 16px;
    min-height: 18px;
}}
QPushButton#remove_btn:hover {{
    background: #059669;
    border-color: #34d399;
}}
QPushButton#remove_btn:pressed {{
    background: #047857;
}}
QPushButton#remove_btn:disabled {{
    background: #064e3b;
    color: #6ee7b7;
    border-color: #065f46;
}}
QPushButton#ghost {{
    background: transparent;
    color: {TEXT_DIM};
    border: 1px solid transparent;
    border-radius: 5px;
    padding: 4px 8px;
    font-size: 11px;
}}
QPushButton#ghost:hover {{
    background: {BG_RAISED};
    color: {TEXT_MAIN};
    border-color: {BORDER_LIT};
}}
QPushButton#ghost:pressed {{ background: {BG_HOVER}; }}
QPushButton#icon_btn {{
    background: transparent;
    border: none;
    color: {TEXT_DIM};
    padding: 4px;
    border-radius: 5px;
    font-size: 15px;
}}
QPushButton#icon_btn:hover {{
    background: {BG_RAISED};
    color: {PURPLE_LIGHT};
}}
QPushButton#icon_btn:pressed {{ color: #fff; }}
QPushButton#danger {{
    background: {RED_DIM};
    color: {RED_SOFT};
    border: 1px solid {RED_BORDER};
}}
QPushButton#danger:hover {{ background: #381212; border-color: #ef4444; }}
QPushButton#save_btn {{
    background: {GREEN_DIM};
    color: {GREEN_SOFT};
    border: 1px solid #1a3d28;
    font-weight: 600;
    padding: 7px 14px;
    min-height: 20px;
}}
QPushButton#save_btn:hover {{ background: #0f2a1c; border-color: {GREEN_SOFT}; }}

/* ── Sidebar tool buttons ─────────────────────────── */
QFrame#topbar_pill {{
    background: {BG_RAISED};
    border: 1px solid {BORDER_LIT};
    border-radius: 7px;
}}
QToolButton {{
    background: transparent;
    border: 1px solid transparent;
    border-radius: 7px;
    color: {TEXT_DIM};
    padding: 2px;
}}
QToolButton:hover {{
    background: {BG_HOVER};
    color: {TEXT_MAIN};
    border-color: {BORDER_LIT};
}}
QToolButton:checked {{
    background: {PURPLE};
    color: #ffffff;
    border-color: {PURPLE_LIGHT};
}}

/* ── Inputs ───────────────────────────────────────── */
QSlider::groove:horizontal {{
    height: 2px; background: {BORDER_LIT}; border-radius: 1px;
}}
QSlider::handle:horizontal {{
    background: {PURPLE_LIGHT}; width: 12px; height: 12px;
    margin: -5px 0; border-radius: 6px; border: 2px solid {BG_BASE};
}}
QSlider::sub-page:horizontal {{ background: {PURPLE}; border-radius: 1px; }}
QSlider::groove:vertical {{ width: 2px; background: {BORDER_LIT}; border-radius: 1px; }}
QSlider::handle:vertical {{
    background: {PURPLE_LIGHT}; width: 12px; height: 12px;
    margin: 0 -5px; border-radius: 6px; border: 2px solid {BG_BASE};
}}
QSlider::sub-page:vertical {{ background: {PURPLE}; border-radius: 1px; }}
QComboBox {{
    background: {BG_RAISED}; color: {TEXT_MAIN};
    border: 1px solid {BORDER_LIT}; border-radius: 6px;
    padding: 4px 10px; font-size: 11px; font-weight: 500;
}}
QComboBox:hover {{ border-color: {PURPLE_LIGHT}; }}
QComboBox::drop-down {{ width: 16px; border: none; }}
QComboBox QAbstractItemView {{
    background: {BG_RAISED}; color: {TEXT_MAIN};
    selection-background-color: {PURPLE};
    border: 1px solid {BORDER_LIT}; border-radius: 6px;
    padding: 3px; outline: none;
}}
QComboBox#lvl_box {{
    background: #1d0f36;
    color: {PURPLE_LIGHT};
    border: 1px solid {PURPLE};
    border-radius: 6px;
    padding: 4px 10px;
    font-weight: 700;
    font-size: 11px;
}}
QComboBox#lvl_box:hover {{
    background: #2b144f;
    border-color: #a855f7;
}}
QComboBox#lvl_box::drop-down {{
    width: 18px;
    border: none;
}}
QComboBox#lvl_box QAbstractItemView {{
    background: #140b26;
    color: #f1f5f9;
    selection-background-color: {PURPLE};
    selection-color: #ffffff;
    border: 1px solid {BORDER_LIT};
    border-radius: 6px;
    padding: 4px;
    outline: none;
}}
QLineEdit, QSpinBox, QDoubleSpinBox {{
    background: {BG_DEEP}; color: {TEXT_MAIN};
    border: 1px solid {BORDER_LIT}; border-radius: 6px;
    padding: 4px 8px; font-size: 11px;
    selection-background-color: {PURPLE};
}}
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus {{
    border-color: {PURPLE_LIGHT};
}}

/* ── Lists / scrollbars ───────────────────────────── */
QListWidget {{
    background: {BG_DEEP}; color: {TEXT_MAIN};
    border: 1px solid {BORDER_LIT}; border-radius: 7px; outline: none;
}}
QListWidget::item {{ padding: 5px 8px; border-radius: 4px; }}
QListWidget::item:selected {{ background: {PURPLE_DIM}; color: {PURPLE_LIGHT}; }}
QListWidget::item:hover:!selected {{ background: {BG_RAISED}; }}
QScrollArea {{ border: none; background: transparent; }}
QScrollBar:vertical {{ background: {BG_BASE}; width: 4px; border-radius: 2px; }}
QScrollBar::handle:vertical {{
    background: {BORDER_LIT}; border-radius: 2px; min-height: 24px;
}}
QScrollBar::handle:vertical:hover {{ background: {PURPLE}; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QScrollBar:horizontal {{ background: {BG_BASE}; height: 4px; border-radius: 2px; }}
QScrollBar::handle:horizontal {{
    background: {BORDER_LIT}; border-radius: 2px; min-width: 24px;
}}
QScrollBar::handle:horizontal:hover {{ background: {PURPLE}; }}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}

/* ── Misc ─────────────────────────────────────────── */
QStatusBar {{
    background: {BG_DEEP}; color: {PURPLE_LIGHT};
    border-top: 1px solid {BORDER}; font-size: 11px; font-weight: 500; padding: 0 10px;
}}
QStatusBar QLabel {{
    color: {PURPLE_LIGHT}; font-weight: 500;
}}
QProgressBar {{
    background: {BG_DEEP}; border: none;
    border-radius: 3px; height: 4px;
}}
QProgressBar::chunk {{ background: {PURPLE}; border-radius: 3px; }}
QTextEdit {{
    background: {BG_DEEP}; color: {GREEN_SOFT};
    border: 1px solid {BORDER_LIT}; border-radius: 6px;
    font-family: 'JetBrains Mono', 'Consolas', monospace;
    font-size: 11px; padding: 6px;
    selection-background-color: {PURPLE};
}}
QGroupBox {{
    border: 1px solid {BORDER_LIT}; border-radius: 7px;
    margin-top: 8px; padding-top: 8px;
    font-size: 10px; font-weight: 700; color: {TEXT_FAINT};
    letter-spacing: 0.8px;
}}
QGroupBox::title {{ subcontrol-origin: margin; left: 10px; color: {TEXT_FAINT}; }}
QLabel {{ background: transparent; color: {TEXT_DIM}; }}
QMessageBox {{ background: {BG_RAISED}; }}
QMessageBox QPushButton {{ min-width: 70px; }}
"""

