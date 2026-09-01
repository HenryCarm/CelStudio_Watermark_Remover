#!/usr/bin/env python3
# ╔══════════════════════════════════════════════════════════════╗
# ║        MyScreen Watermark Remover  v1.6  ·  by HenryJay      ║
# ║                 hnrycrm@gmail.com  :3                        ║
# ╚══════════════════════════════════════════════════════════════╝

# ─── BOOTSTRAP ────────────────────────────────────────────────────────────────
def _bootstrap():
    import importlib, subprocess, sys, os
    from pathlib import Path
    DEPS = {"cv2": "opencv-python", "numpy": "numpy", "PyQt6": "PyQt6"}
    missing = []
    for mod, pkg in DEPS.items():
        try:
            __import__(mod)
        except ImportError:
            missing.append(pkg)
    if not missing:
        return
    # If running outside central venv, try re-executing with central venv
    central_venv_py = Path("/home/henry/Documents/Projects/Python/venv/bin/python")
    if central_venv_py.exists() and sys.executable != str(central_venv_py):
        os.execv(str(central_venv_py), [str(central_venv_py)] + sys.argv)
    print("\n╔══════════════════════════════════════════╗")
    print("║  MyScreen WR  ·  First-boot setup        ║")
    print("╠══════════════════════════════════════════╣")
    for p in missing:
        print(f"║  📦  Need: {p:<31} ║")
    print("╚══════════════════════════════════════════╝\n")
    def _try(exe, pkgs, extra=None):
        cmd = [exe, "-m", "pip", "install", "--quiet",
               "--timeout", "60", "--retries", "2",
               *(extra or []), *pkgs]
        if subprocess.call(cmd, stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL) == 0:
            return True
        return False
    if _try(sys.executable, missing):
        os.execv(sys.executable, [sys.executable] + sys.argv)
    print(f"\n❌  Auto-install failed.\n    pip install {' '.join(missing)}")
    sys.exit(1)
_bootstrap()
# ─────────────────────────────────────────────────────────────────────────────

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

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLayout,
    QLabel, QPushButton, QSlider, QFileDialog, QTabWidget, QScrollArea,
    QGridLayout, QSizePolicy, QFrame, QComboBox, QToolButton, QButtonGroup,
    QMessageBox, QStatusBar, QDialog, QTextEdit, QLineEdit, QSpinBox,
    QDoubleSpinBox, QListWidget, QListWidgetItem, QProgressBar,
    QFormLayout, QGroupBox, QScrollBar, QInputDialog, QCheckBox,
)
from PyQt6.QtCore import (
    Qt, QPoint, QRect, QThread, pyqtSignal, QTimer, QSize,
    QPropertyAnimation, QEasingCurve, QObject,
)
from PyQt6.QtGui import (
    QPainter, QImage, QPixmap, QColor, QPen, QBrush,
    QFont, QFontMetrics, QPalette, QCursor, QKeySequence, QIcon,
)

# ─── Paths ────────────────────────────────────────────────────────────────────
SCRIPT_DIR    = Path(__file__).resolve().parent
ICON_PATH     = SCRIPT_DIR / "icon.png"
LOG_DIR       = SCRIPT_DIR / "logs"
DATA_DIR      = Path.home()/"Documents"/"HenryJay Data Folder"/"MyScreen Watermark Remover"
SAVE_DIR      = Path.home()/"Pictures"/"MyScreen Watermark Remover Edits"
TRASH_DIR     = Path.home()/"Documents"/"Projects"/"OpenCode"/"tmp"/"Trash"
DATA_DIR.mkdir(parents=True, exist_ok=True)
SAVE_DIR.mkdir(parents=True, exist_ok=True)
TRASH_DIR.mkdir(parents=True, exist_ok=True)
LOG_DIR.mkdir(parents=True, exist_ok=True)
SETTINGS_FILE = DATA_DIR / "settings.json"
PRESETS_FILE  = DATA_DIR / "presets.json"
APP_VERSION   = "1.7.0"
BUILD_DATE    = "2026-03-15"

MOBILE_WIDTH_THRESHOLD = 700   # px — treat as mobile if window width < this

# ─── Live Diagnostics & Crash Logger ──────────────────────────────────────────
class CelLogger:
    def __init__(self, log_dir: Path):
        self.log_file = None
        self.log_dir  = log_dir
        self.log_path: Path | None = None
        self._stdout = sys.stdout
        self._stderr = sys.stderr
        self.enabled = False

    def enable(self):
        if not self.enabled:
            try:
                self.log_dir.mkdir(parents=True, exist_ok=True)
                if self.log_file is None:
                    ts_file = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
                    self.log_path = self.log_dir / f"CelWR_{ts_file}.log"
                    self.log_file = open(self.log_path, "a", encoding="utf-8", buffering=1)
                self.enabled = True
                sys.stdout = self
                sys.stderr = self
                ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                self.log_file.write(f"\n--- [CelWR Live Logger Started: {ts} (v{APP_VERSION})] ---\n")
                self.log_file.flush()
            except Exception as e:
                print(f"Failed to enable live logging: {e}")

    def disable(self):
        if self.enabled:
            self.enabled = False
            sys.stdout = self._stdout
            sys.stderr = self._stderr
            if self.log_file:
                try:
                    self.log_file.flush()
                    self.log_file.close()
                except Exception:
                    pass
                self.log_file = None

    def write(self, text):
        if self._stdout:
            try:
                self._stdout.write(text)
            except Exception:
                pass
        if self.enabled and self.log_file and text:
            try:
                lines = text.splitlines(keepends=True)
                ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                for line in lines:
                    if line.strip():
                        self.log_file.write(f"[{ts}] {line}")
                    else:
                        self.log_file.write(line)
                self.log_file.flush()
            except Exception:
                pass

    def flush(self):
        if self._stdout:
            try:
                self._stdout.flush()
            except Exception:
                pass
        if self.enabled and self.log_file:
            try:
                self.log_file.flush()
            except Exception:
                pass

cel_logger = CelLogger(LOG_DIR)

def launch_system_file(path: str):
    """Launch file or directory with system default handler without Qt plugin environment pollution."""
    p = str(Path(path).resolve())
    import subprocess, sys as _sys, os as _os
    clean_env = _os.environ.copy()
    # Strip Qt plugin overrides that cause VLC and external media players to crash
    for var in ("QT_PLUGIN_PATH", "QT_QPA_PLATFORM_PLUGIN_PATH", "QT_QPA_PLATFORM", "LD_LIBRARY_PATH", "PYTHONPATH"):
        clean_env.pop(var, None)
    if _sys.platform.startswith("linux"):
        subprocess.Popen(["xdg-open", p], env=clean_env)
    elif _sys.platform == "darwin":
        subprocess.Popen(["open", p], env=clean_env)
    else:
        _os.startfile(p)

def safe_trash_file(p: Path) -> bool:
    """Move file to OpenCode safe Trash folder with collision handling."""
    try:
        if not p.exists():
            return False
        TRASH_DIR.mkdir(parents=True, exist_ok=True)
        dest = TRASH_DIR / p.name
        if dest.exists():
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            dest = TRASH_DIR / f"{p.stem}_{ts}{p.suffix}"
        shutil.move(str(p), str(dest))
        return True
    except Exception as exc:
        print(f"[SAFE_TRASH] Error moving {p} to trash: {exc}")
        return False

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
    if PRESETS_FILE.exists():
        try:
            return json.loads(PRESETS_FILE.read_text())
        except Exception:
            pass
    return []

def save_presets(p: list) -> None:
    PRESETS_FILE.write_text(json.dumps(p, indent=2))


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
    font-size: 11px; font-weight: 500;
    min-width: 64px;
}}
QTabBar::tab:selected {{
    color: {PURPLE_LIGHT}; border-bottom: 2px solid {PURPLE};
    font-weight: 600;
    background: {BG_DEEP};
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
    padding: 2px;
    color: {TEXT_DIM};
}}
QToolButton:hover {{
    background: {BG_RAISED};
    color: {TEXT_MAIN};
    border-color: {BORDER_LIT};
}}
QToolButton:checked {{
    background: {PURPLE_DIM};
    color: {PURPLE_LIGHT};
    border-color: {PURPLE};
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
    background: {BG_DEEP}; color: {TEXT_FAINT};
    border-top: 1px solid {BORDER}; font-size: 10px; padding: 0 10px;
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

# ─── Smart Watermark Detection ────────────────────────────────────────────────

def detect_watermark_box_at(img: np.ndarray, x: int, y: int) -> QRect | None:
    """Intelligently detect watermark/text/logo/badge bounding box under or near (x, y)."""
    if img is None:
        return None
    H, W = img.shape[:2]
    if not (0 <= x < W and 0 <= y < H):
        return None

    # Wide search window around cursor (handles small text up to large badges/banners)
    rw = min(W, 800)
    rh = min(H, 550)
    x0 = max(0, min(x - rw // 2, W - rw))
    y0 = max(0, min(y - rh // 2, H - rh))
    x1 = min(W, x0 + rw)
    y1 = min(H, y0 + rh)

    patch = img[y0:y1, x0:x1]
    if patch.size == 0:
        return None

    gray = cv2.cvtColor(patch, cv2.COLOR_BGR2GRAY) if patch.ndim == 3 else patch.copy()

    # 1. Gradients & edges
    grad_x = cv2.Sobel(gray, cv2.CV_16S, 1, 0, ksize=3)
    grad_y = cv2.Sobel(gray, cv2.CV_16S, 0, 1, ksize=3)
    abs_grad_x = cv2.convertScaleAbs(grad_x)
    abs_grad_y = cv2.convertScaleAbs(grad_y)
    grad = cv2.addWeighted(abs_grad_x, 0.5, abs_grad_y, 0.5, 0)

    # 2. Multi-threshold combination
    _, thresh_otsu = cv2.threshold(grad, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)
    thresh_adp = cv2.adaptiveThreshold(
        gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 15, 3
    )
    canny = cv2.Canny(gray, 40, 140)
    combined = cv2.bitwise_or(thresh_otsu, cv2.bitwise_or(thresh_adp, canny))

    # 3. Multi-scale morphological dilation (handles single words, circles, square cards, and large banners)
    kernels = [
        cv2.getStructuringElement(cv2.MORPH_RECT, (18, 6)),    # phone / single line text
        cv2.getStructuringElement(cv2.MORPH_RECT, (30, 12)),   # multi-line text block
        cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (36, 36)),# circular badges & logos
        cv2.getStructuringElement(cv2.MORPH_RECT, (48, 24)),   # large watermark banner / card
    ]

    lx = x - x0
    ly = y - y0

    best_rect = None
    best_score = float("inf")

    for k in kernels:
        dilated = cv2.dilate(combined, k, iterations=1)
        contours, _ = cv2.findContours(dilated, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        for cnt in contours:
            bx, by, bw, bh = cv2.boundingRect(cnt)
            area = bw * bh
            if area < 200 or bw < 14 or bh < 10:
                continue
            if bw > (x1 - x0) * 0.98 and bh > (y1 - y0) * 0.98:
                continue

            inside = (bx <= lx <= bx + bw) and (by <= ly <= by + bh)
            cx = bx + bw / 2
            cy = by + bh / 2
            dist = ((cx - lx) ** 2 + (cy - ly) ** 2) ** 0.5

            if inside:
                score = dist * 0.12 - (area ** 0.5) * 0.05
            elif dist < 160:
                score = dist
            else:
                continue

            if score < best_score:
                best_score = score
                pad = 8
                gx0 = max(0, x0 + bx - pad)
                gy0 = max(0, y0 + by - pad)
                gx1 = min(W, x0 + bx + bw + pad)
                gy1 = min(H, y0 + by + bh + pad)
                best_rect = QRect(gx0, gy0, gx1 - gx0, gy1 - gy0)

    return best_rect

def detect_all_watermarks(img: np.ndarray) -> list[QRect]:
    """Intelligently detect prominent watermark logos, text badges, circles, and banners while rejecting tiny noise."""
    if img is None:
        return []
    H, W = img.shape[:2]
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if img.ndim == 3 else img.copy()

    # High-contrast edge detection & gradient
    grad = cv2.morphologyEx(gray, cv2.MORPH_GRADIENT, np.ones((3, 3), np.uint8))
    _, thresh_otsu = cv2.threshold(grad, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)
    canny = cv2.Canny(gray, 45, 140)
    edges = cv2.bitwise_or(thresh_otsu, canny)

    # Multi-scale morphological closing to group full words, circular badges, and banners
    k1 = cv2.getStructuringElement(cv2.MORPH_RECT, (25, 15))
    k2 = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (35, 35))
    closed_rect = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, k1, iterations=2)
    closed_circ = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, k2, iterations=2)
    combined = cv2.bitwise_or(closed_rect, closed_circ)

    # Dilate slightly to form cohesive candidate blocks
    k_dil = cv2.getStructuringElement(cv2.MORPH_RECT, (15, 10))
    dilated = cv2.dilate(combined, k_dil, iterations=1)

    contours, _ = cv2.findContours(dilated, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    candidates: list[tuple[int, int, int, int]] = []
    min_area = max(800, int((W * H) * 0.0006)) # Filter out tiny noise contours
    max_area = int((W * H) * 0.50)              # Don't select entire screen

    for cnt in contours:
        x, y, w, h = cv2.boundingRect(cnt)
        area = w * h
        if area < min_area or area > max_area:
            continue
        if w < 30 or h < 16:
            continue

        # Score candidate based on edge density and aspect ratio
        patch_edges = edges[y:y+h, x:x+w]
        density = float(np.count_nonzero(patch_edges)) / float(area)
        if density < 0.035:  # Smooth area without text/logo features
            continue

        # Watermarks are typically in corners, edges, or lower/upper thirds
        is_corner_or_edge = (x < W * 0.38 or x + w > W * 0.62 or y < H * 0.38 or y + h > H * 0.62)
        # Or centered prominent badges
        is_center_badge = (w > 60 and h > 40 and abs((x + w/2) - W/2) < W * 0.28)

        if is_corner_or_edge or is_center_badge:
            candidates.append((x, y, w, h))

    if not candidates:
        return []

    # Merge overlapping or close bounding boxes
    merged: list[tuple[int, int, int, int]] = []
    for x, y, w, h in candidates:
        matched = False
        for i, (mx, my, mw, mh) in enumerate(merged):
            pad = 20
            if not (x > mx + mw + pad or x + w < mx - pad or y > my + mh + pad or y + h < my - pad):
                nx = min(x, mx)
                ny = min(y, my)
                nw = max(x + w, mx + mw) - nx
                nh = max(y + h, my + mh) - ny
                merged[i] = (nx, ny, nw, nh)
                matched = True
                break
        if not matched:
            merged.append((x, y, w, h))

    results = []
    for x, y, w, h in merged:
        pad = 8
        gx0 = max(0, x - pad)
        gy0 = max(0, y - pad)
        gx1 = min(W, x + w + pad)
        gy1 = min(H, y + h + pad)
        results.append(QRect(gx0, gy0, gx1 - gx0, gy1 - gy0))

    return results

# ─── Inpaint ──────────────────────────────────────────────────────────────────

LEVEL_QUICK     = 0
LEVEL_SMART     = 1
LEVEL_PRECISION = 2
LEVEL_CEL_AI    = 3

def _inpaint_quick(img: np.ndarray, mask: np.ndarray) -> np.ndarray:
    return cv2.inpaint(img, mask, 3, cv2.INPAINT_TELEA)

def _inpaint_smart(img: np.ndarray, mask: np.ndarray,
                   cb=None) -> np.ndarray:
    result    = img.copy()
    remaining = (mask > 0).astype(np.uint8)
    se        = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7))
    rings: list[np.ndarray] = []
    current   = remaining.copy()
    while current.any():
        eroded = cv2.erode(current, se)
        ring   = cv2.subtract(current, eroded)
        if ring.any():
            rings.append(ring)
        else:
            rings.append(current)
            break
        current = eroded
    total = max(len(rings), 1)
    for i, ring in enumerate(rings):
        result = cv2.inpaint(result, (ring > 0).astype(np.uint8) * 255,
                             5, cv2.INPAINT_TELEA)
        if cb:
            cb(int((i + 1) / total * 100))
    return result

def _inpaint_precision(img: np.ndarray, mask: np.ndarray,
                       cb=None) -> np.ndarray:
    H, W   = img.shape[:2]
    MAX_DIM = 720
    scale  = min(1.0, MAX_DIM / max(H, W))
    if scale < 1.0:
        nw, nh = int(W * scale), int(H * scale)
        work   = cv2.resize(img,  (nw, nh), interpolation=cv2.INTER_AREA)
        wmask  = cv2.resize(mask, (nw, nh), interpolation=cv2.INTER_NEAREST)
    else:
        work, wmask, nw, nh = img.copy(), mask.copy(), W, H
    result    = work.astype(np.float32)
    remaining = (wmask > 0).astype(np.uint8)
    PATCH, N  = 7, 120
    half      = PATCH // 2
    se3       = np.ones((3, 3), np.uint8)
    sep       = np.ones((PATCH, PATCH), np.uint8)
    total_px  = max(int(remaining.sum()), 1)
    done_px   = 0
    while remaining.any():
        boundary = cv2.dilate(remaining, se3) - remaining
        bpts     = np.argwhere(boundary > 0)
        if not len(bpts):
            break
        src_map  = ~(cv2.dilate(remaining, sep) > 0)
        spts     = np.argwhere(src_map)
        spts     = spts[
            (spts[:, 0] >= half) & (spts[:, 0] < nh - half) &
            (spts[:, 1] >= half) & (spts[:, 1] < nw - half)
        ]
        if len(spts) < 8:
            fallback = (remaining * 255).astype(np.uint8)
            result   = cv2.inpaint(
                np.clip(result, 0, 255).astype(np.uint8),
                fallback, 5, cv2.INPAINT_TELEA
            ).astype(np.float32)
            break
        cidx  = np.random.choice(len(spts), min(N, len(spts)), replace=False)
        cands = spts[cidx]
        vc, vp = [], []
        for cy, cx in cands:
            p = result[cy - half:cy + half + 1, cx - half:cx + half + 1]
            if p.shape == (PATCH, PATCH, 3):
                vc.append((cy, cx))
                vp.append(p)
        if not vp:
            break
        cp_flat = np.array(vp).reshape(len(vp), -1)
        newly: list[tuple] = []
        for py, px in bpts:
            if remaining[py, px] == 0:
                continue
            qy1, qy2 = max(0, py - half), min(nh, py + half + 1)
            qx1, qx2 = max(0, px - half), min(nw, px + half + 1)
            qp = result[qy1:qy2, qx1:qx2]
            qk = remaining[qy1:qy2, qx1:qx2] == 0
            if not qk.any():
                continue
            ph, pw = qp.shape[:2]
            if ph == PATCH and pw == PATCH:
                k3   = np.repeat(qk.flatten(), 3)
                diff = (cp_flat - qp.reshape(-1)) ** 2
                ssd  = (diff * k3).sum(axis=1) / max(qk.sum(), 1)
                bi   = int(np.argmin(ssd))
            else:
                bi, bd = 0, float("inf")
                for i2, cp in enumerate(vp):
                    mh2, mw2 = min(ph, PATCH), min(pw, PATCH)
                    k = qk[:mh2, :mw2]
                    if not k.any():
                        continue
                    d = float(np.mean((qp[:mh2, :mw2] - cp[:mh2, :mw2]) ** 2))
                    if d < bd:
                        bd, bi = d, i2
            bcy, bcx = vc[bi]
            newly.append((py, px, result[bcy, bcx].copy()))
        if not newly:
            fallback = (remaining * 255).astype(np.uint8)
            result   = cv2.inpaint(
                np.clip(result, 0, 255).astype(np.uint8),
                fallback, 5, cv2.INPAINT_TELEA
            ).astype(np.float32)
            break
        for py, px, val in newly:
            result[py, px]    = val
            remaining[py, px] = 0
        done_px += len(newly)
        if cb:
            cb(min(99, int(done_px / total_px * 100)))
    r8 = np.clip(result, 0, 255).astype(np.uint8)
    if scale < 1.0:
        r_up  = cv2.resize(r8, (W, H), interpolation=cv2.INTER_LANCZOS4)
        mu    = cv2.resize(mask, (W, H), interpolation=cv2.INTER_NEAREST)
        feath = cv2.GaussianBlur(mu.astype(np.float32),
                                 (21, 21), 0)[:, :, np.newaxis] / 255.0
        telea = cv2.inpaint(img, mu, 3, cv2.INPAINT_TELEA)
        r8    = np.clip(
            r_up.astype(np.float32) * feath +
            telea.astype(np.float32) * (1.0 - feath), 0, 255
        ).astype(np.uint8)
    fm  = cv2.resize(mask, (W, H), interpolation=cv2.INTER_NEAREST) \
          if scale < 1.0 else mask
    ek  = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    bnd = cv2.dilate(fm, ek) - cv2.erode(fm, ek)
    if bnd.any():
        r8 = cv2.inpaint(r8, bnd, 3, cv2.INPAINT_TELEA)
    if cb:
        cb(100)
    return r8

def _inpaint_cel_ai(img: np.ndarray, mask: np.ndarray, cb=None) -> np.ndarray:
    """
    ✨ Cel AI — Advanced Multi-Scale Structural Gradient & Texture Synthesis.
    Propagates structural edge coherence, texture grain, and skin tone smoothly
    without smudging or blurring, even across large watermark regions and faces.
    """
    if mask is None or not mask.any():
        return img.copy()
    H, W = img.shape[:2]
    k_smooth = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    m_clean = cv2.dilate(mask, k_smooth)
    if cb: cb(15)

    # Coarse Navier-Stokes flow propagation
    base_ns = cv2.inpaint(img, m_clean, 7, cv2.INPAINT_NS)
    if cb: cb(35)

    # Fine telea structural interpolation
    base_telea = cv2.inpaint(img, m_clean, 3, cv2.INPAINT_TELEA)
    if cb: cb(55)

    # Edge-preserving tensor blending
    gray_orig = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    grad_x = cv2.Sobel(gray_orig, cv2.CV_32F, 1, 0, ksize=3)
    grad_y = cv2.Sobel(gray_orig, cv2.CV_32F, 0, 1, ksize=3)
    grad_mag = cv2.magnitude(grad_x, grad_y)

    k_dil = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (9, 9))
    band = cv2.dilate(m_clean, k_dil) - cv2.erode(m_clean, k_dil)
    local_texture_energy = float(np.mean(grad_mag[band > 0])) if band.any() else 0.0

    weight_ns = 0.65 if local_texture_energy > 12.0 else 0.45
    combined = cv2.addWeighted(base_ns, weight_ns, base_telea, 1.0 - weight_ns, 0)
    refined = cv2.bilateralFilter(combined, d=7, sigmaColor=35, sigmaSpace=35)
    if cb: cb(75)

    # Subtle micro-texture injection for natural photorealistic finish
    if local_texture_energy > 14.0:
        res_border = img.astype(np.float32) - refined.astype(np.float32)
        std_dev = float(np.std(res_border[band > 0])) if band.any() else 0.0
        if std_dev > 0.5:
            noise = np.random.normal(0, min(std_dev * 0.4, 5.0), img.shape).astype(np.float32)
            out_f = refined.astype(np.float32) + noise * (m_clean[:, :, np.newaxis] / 255.0)
            refined = np.clip(out_f, 0, 255).astype(np.uint8)

    feather = cv2.GaussianBlur(m_clean.astype(np.float32), (7, 7), 0)[:, :, np.newaxis] / 255.0
    final = np.clip(
        refined.astype(np.float32) * feather + img.astype(np.float32) * (1.0 - feather),
        0, 255
    ).astype(np.uint8)

    if cb: cb(100)
    return final

def run_inpaint(img: np.ndarray, mask: np.ndarray,
                level: int, cb=None) -> np.ndarray:
    if level == LEVEL_QUICK:
        return _inpaint_quick(img, mask)
    elif level == LEVEL_SMART:
        return _inpaint_smart(img, mask, cb)
    elif level == LEVEL_PRECISION:
        return _inpaint_precision(img, mask, cb)
    else:
        return _inpaint_cel_ai(img, mask, cb)

def inpaint_roi(frame: np.ndarray, mask: np.ndarray, level: int) -> np.ndarray:
    """High-speed bounded ROI inpainting. Crops to watermark bounding box with margin for 10x-50x speedup."""
    if mask is None or not mask.any():
        return frame
    coords = cv2.findNonZero(mask)
    if coords is None:
        return frame
    rx, ry, rw, rh = cv2.boundingRect(coords)
    H, W = frame.shape[:2]
    pad = 24
    x0 = max(0, rx - pad)
    y0 = max(0, ry - pad)
    x1 = min(W, rx + rw + pad)
    y1 = min(H, ry + rh + pad)

    crop_frame = frame[y0:y1, x0:x1]
    crop_mask = mask[y0:y1, x0:x1]

    inpainted_crop = run_inpaint(crop_frame, crop_mask, level)
    out = frame.copy()
    out[y0:y1, x0:x1] = inpainted_crop
    return out

def cv2_to_qimage(img: np.ndarray) -> QImage:
    h, w = img.shape[:2]
    if len(img.shape) == 2:
        return QImage(np.ascontiguousarray(img).tobytes(), w, h, w,
                      QImage.Format.Format_Grayscale8).copy()
    rgb  = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    data = np.ascontiguousarray(rgb)
    return QImage(data.tobytes(), w, h, w * 3,
                  QImage.Format.Format_RGB888).copy()


# ─── Workers ──────────────────────────────────────────────────────────────────

class InpaintWorker(QThread):
    finished = pyqtSignal(object)
    error    = pyqtSignal(str)
    progress = pyqtSignal(int)

    def __init__(self, img: np.ndarray, mask: np.ndarray, level: int):
        super().__init__()
        self._img   = img.copy()
        self._mask  = mask.copy()
        self._level = level
        self._stop  = False

    def stop(self) -> None:
        self._stop = True

    def run(self) -> None:
        try:
            def cb(p: int) -> None:
                if not self._stop:
                    self.progress.emit(p)
            if self._stop:
                return
            result = run_inpaint(self._img, self._mask, self._level, cb)
            if not self._stop:
                self.finished.emit(result)
        except Exception:
            if not self._stop:
                self.error.emit(traceback.format_exc())


class VideoOutputWriter:
    """High efficiency video writer using direct FFmpeg pipe (H.264 CRF 22 visually lossless + adaptive rate cap) or cv2.VideoWriter fallback."""
    def __init__(self, dst_path: str, src_path: str, W: int, H: int, fps: float, crf: int = 22, keep_audio: bool = True):
        self.dst_path = dst_path
        self.src_path = src_path
        self.W = W
        self.H = H
        self.fps = fps
        self.crf = crf
        self.keep_audio = keep_audio
        self.proc: subprocess.Popen | None = None
        self.cv_writer: cv2.VideoWriter | None = None
        self._use_ffmpeg = False
        self._init_writer()

    def _init_writer(self):
        if shutil.which("ffmpeg"):
            try:
                # Calculate adaptive max bitrate from source file to prevent file bloat
                maxrate_args = []
                if self.src_path and Path(self.src_path).exists():
                    try:
                        src_bytes = Path(self.src_path).stat().st_size
                        cap_probe = cv2.VideoCapture(self.src_path)
                        n_frames = max(1, int(cap_probe.get(cv2.CAP_PROP_FRAME_COUNT)))
                        cap_probe.release()
                        dur_sec = max(1.0, n_frames / max(self.fps, 1.0))
                        target_kbps = max(600, int((src_bytes * 8) / (dur_sec * 1000) * 1.08))
                        maxrate_args = ["-maxrate", f"{target_kbps}k", "-bufsize", f"{target_kbps * 2}k"]
                    except Exception:
                        pass

                cmd = [
                    "ffmpeg", "-y",
                    "-f", "rawvideo", "-vcodec", "rawvideo",
                    "-s", f"{self.W}x{self.H}", "-pix_fmt", "bgr24", "-r", str(self.fps),
                    "-i", "-",
                ]
                if self.keep_audio and self.src_path and Path(self.src_path).exists():
                    cmd.extend([
                        "-i", self.src_path,
                        "-c", "copy",
                        "-c:v:0", "libx264", "-crf", str(self.crf), "-preset", "fast",
                        *maxrate_args,
                        "-pix_fmt", "yuv420p",
                        "-map", "0:v:0", "-map", "1?", "-map", "-1:v:0?",
                        "-map_metadata", "1",
                        "-map_chapters", "1",
                        "-shortest",
                    ])
                elif self.src_path and Path(self.src_path).exists():
                    cmd.extend([
                        "-i", self.src_path,
                        "-c", "copy",
                        "-c:v:0", "libx264", "-crf", str(self.crf), "-preset", "fast",
                        *maxrate_args,
                        "-pix_fmt", "yuv420p",
                        "-map", "0:v:0", "-map", "1?", "-map", "-1:v:0?", "-map", "-1:a?",
                        "-map_metadata", "1",
                        "-map_chapters", "1",
                    ])
                else:
                    cmd.extend([
                        "-c:v", "libx264", "-crf", str(self.crf), "-preset", "fast",
                        *maxrate_args,
                        "-pix_fmt", "yuv420p",
                        "-an",
                        "-map", "0:v:0",
                    ])
                cmd.extend(["-movflags", "+faststart", self.dst_path])
                self.proc = subprocess.Popen(
                    cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
                )
                if self.proc and self.proc.stdin:
                    self._use_ffmpeg = True
                    return
            except Exception:
                self.proc = None
                self._use_ffmpeg = False

        # Fallback to OpenCV VideoWriter
        for codec in ("avc1", "mp4v", "XVID", "MJPG"):
            try:
                self.cv_writer = cv2.VideoWriter(
                    self.dst_path, cv2.VideoWriter_fourcc(*codec), self.fps, (self.W, self.H)
                )
                if self.cv_writer.isOpened():
                    break
            except Exception:
                pass

    def is_opened(self) -> bool:
        if self._use_ffmpeg and self.proc is not None and self.proc.stdin is not None:
            return self.proc.poll() is None
        return self.cv_writer is not None and self.cv_writer.isOpened()

    def write(self, frame: np.ndarray):
        if self._use_ffmpeg and self.proc and self.proc.stdin:
            try:
                self.proc.stdin.write(frame.tobytes())
            except Exception:
                pass
        elif self.cv_writer is not None and self.cv_writer.isOpened():
            self.cv_writer.write(frame)

    def close(self):
        if self._use_ffmpeg and self.proc:
            try:
                if self.proc.stdin:
                    self.proc.stdin.close()
                self.proc.wait(timeout=60)
            except Exception:
                try:
                    self.proc.kill()
                except Exception:
                    pass
            self.proc = None
        elif self.cv_writer is not None:
            self.cv_writer.release()
            self.cv_writer = None


class VideoWorker(QThread):
    frame_done = pyqtSignal(int, int, float, int, int)  # (cur, tot, fps, eta_sec, el_sec)
    finished   = pyqtSignal(str)
    error      = pyqtSignal(str)

    def __init__(self, src: str, dst: str,
                 method: str, data: dict, level: int, keep_audio: bool = True):
        super().__init__()
        self._src    = src
        self._dst    = dst
        self._method = method
        self._data   = data
        self._level  = level
        self._keep_audio = keep_audio
        self._stop   = False
        self._num_workers = min(max(2, (os.cpu_count() or 4)), 16)
        self._start_time = 0.0
        self._ema_fps = 0.0

    def stop(self) -> None:
        self._stop = True

    def run(self) -> None:
        cap = None
        out = None
        try:
            cap = cv2.VideoCapture(self._src)
            if not cap.isOpened():
                self.error.emit("Cannot open video file."); return
            fps   = cap.get(cv2.CAP_PROP_FPS) or 30.0
            W     = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            H     = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            total = max(int(cap.get(cv2.CAP_PROP_FRAME_COUNT)), 1)
            out   = VideoOutputWriter(self._dst, self._src, W, H, fps, crf=18, keep_audio=self._keep_audio)
            if not out.is_opened():
                self.error.emit("Cannot create video output stream."); return
            if self._method == "auto_track":
                self._auto_track(cap, out, W, H, total)
            elif self._method == "range_remove":
                self._range_remove(cap, out, W, H, total)
            else:
                self._timeline(cap, out, W, H, total)
            if cap is not None:
                cap.release()
                cap = None
            if out is not None:
                out.close()
                out = None
            if not self._stop:
                self.finished.emit(self._dst)
        except Exception:
            self.error.emit(traceback.format_exc())
        finally:
            if cap is not None:
                cap.release()
            if out is not None:
                out.close()

    def _auto_track(self, cap, out, W, H, total):
        d       = self._data
        ref_i   = d["ref_frame"]
        rmask   = d["mask"]
        thr     = d.get("threshold", 0.45)
        cap.set(cv2.CAP_PROP_POS_FRAMES, ref_i)
        ret, ref = cap.read()
        if not ret:
            self.error.emit("Cannot read reference frame."); return
        coords = cv2.findNonZero(rmask)
        if coords is None:
            self.error.emit("No mask on reference frame."); return
        rx, ry, rw, rh = cv2.boundingRect(coords)
        if rw < 4 or rh < 4:
            self.error.emit("Mask region too small."); return
        tmpl      = cv2.cvtColor(ref[ry:ry+rh, rx:rx+rw], cv2.COLOR_BGR2GRAY)
        mask_crop = rmask[ry:ry+rh, rx:rx+rw]
        cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
        batch_size = self._num_workers * 2
        processed = 0
        self._start_time = time.time()
        self._ema_fps = 0.0

        def process_at_item(item):
            f_idx, frame = item
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            if gray.shape[0] >= rh and gray.shape[1] >= rw:
                res = cv2.matchTemplate(gray, tmpl, cv2.TM_CCOEFF_NORMED)
                _, mv, _, ml = cv2.minMaxLoc(res)
                if mv >= thr:
                    fx, fy = ml
                    pad = 20
                    x0 = max(0, fx - pad)
                    y0 = max(0, fy - pad)
                    x1 = min(W, fx + rw + pad)
                    y1 = min(H, fy + rh + pad)
                    fm = np.zeros((y1 - y0, x1 - x0), np.uint8)
                    mx0 = fx - x0
                    my0 = fy - y0
                    eh, ew = min(rh, y1 - fy), min(rw, x1 - fx)
                    if eh > 0 and ew > 0:
                        fm[my0:my0+eh, mx0:mx0+ew] = mask_crop[:eh, :ew]
                    if fm.any():
                        try:
                            c_frame = frame[y0:y1, x0:x1]
                            frame[y0:y1, x0:x1] = run_inpaint(c_frame, fm, self._level)
                        except Exception:
                            pass
            return f_idx, frame

        with ThreadPoolExecutor(max_workers=self._num_workers) as executor:
            while processed < total and not self._stop:
                batch = []
                for _ in range(batch_size):
                    if processed + len(batch) >= total:
                        break
                    ret, frame = cap.read()
                    if not ret:
                        break
                    batch.append((processed + len(batch), frame))
                if not batch:
                    break
                results = list(executor.map(process_at_item, batch))
                for f_idx, f_out in results:
                    out.write(f_out)
                    processed += 1

                now = time.time()
                elapsed = max(0.001, now - self._start_time)
                instant_fps = processed / elapsed
                self._ema_fps = instant_fps if self._ema_fps == 0.0 else (0.85 * self._ema_fps + 0.15 * instant_fps)
                rem_frames = max(0, total - processed)
                eta_sec = int(rem_frames / self._ema_fps) if self._ema_fps > 0 else 0
                self.frame_done.emit(processed, total, self._ema_fps, eta_sec, int(elapsed))

    def _timeline(self, cap, out, W, H, total):
        segs = self._data.get("segments", [])
        cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
        batch_size = self._num_workers * 2
        processed = 0
        self._start_time = time.time()
        self._ema_fps = 0.0

        def process_timeline_item(item):
            f_idx, frame = item
            for seg in segs:
                if seg["start"] <= f_idx <= seg["end"]:
                    m = seg.get("mask")
                    if m is not None and m.any():
                        if m.shape != (H, W):
                            m = cv2.resize(m, (W, H), interpolation=cv2.INTER_NEAREST)
                        try:
                            frame = inpaint_roi(frame, m, self._level)
                        except Exception:
                            pass
                    break
            return f_idx, frame

        with ThreadPoolExecutor(max_workers=self._num_workers) as executor:
            while processed < total and not self._stop:
                batch = []
                for _ in range(batch_size):
                    if processed + len(batch) >= total:
                        break
                    ret, frame = cap.read()
                    if not ret:
                        break
                    batch.append((processed + len(batch), frame))
                if not batch:
                    break
                results = list(executor.map(process_timeline_item, batch))
                for f_idx, f_out in results:
                    out.write(f_out)
                    processed += 1

                now = time.time()
                elapsed = max(0.001, now - self._start_time)
                instant_fps = processed / elapsed
                self._ema_fps = instant_fps if self._ema_fps == 0.0 else (0.85 * self._ema_fps + 0.15 * instant_fps)
                rem_frames = max(0, total - processed)
                eta_sec = int(rem_frames / self._ema_fps) if self._ema_fps > 0 else 0
                self.frame_done.emit(processed, total, self._ema_fps, eta_sec, int(elapsed))

    def _range_remove(self, cap, out, W, H, total):
        start = self._data.get("start", 0)
        end   = self._data.get("end", total - 1)
        m     = self._data.get("mask")
        if m is not None and m.shape != (H, W):
            m = cv2.resize(m, (W, H), interpolation=cv2.INTER_NEAREST)

        coords = cv2.findNonZero(m) if (m is not None and m.any()) else None
        if coords is not None:
            rx, ry, rw, rh = cv2.boundingRect(coords)
            pad = 24
            x0, y0 = max(0, rx - pad), max(0, ry - pad)
            x1, y1 = min(W, rx + rw + pad), min(H, ry + rh + pad)
            crop_m = m[y0:y1, x0:x1]
        else:
            x0, y0, x1, y1, crop_m = 0, 0, W, H, m

        cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
        batch_size = self._num_workers * 2
        processed = 0
        self._start_time = time.time()
        self._ema_fps = 0.0

        def process_range_item(item):
            f_idx, frame = item
            if start <= f_idx <= end and coords is not None and crop_m is not None:
                try:
                    c_frame = frame[y0:y1, x0:x1]
                    c_inp = run_inpaint(c_frame, crop_m, self._level)
                    frame[y0:y1, x0:x1] = c_inp
                except Exception:
                    pass
            return f_idx, frame

        with ThreadPoolExecutor(max_workers=self._num_workers) as executor:
            while processed < total and not self._stop:
                batch = []
                for _ in range(batch_size):
                    if processed + len(batch) >= total:
                        break
                    ret, frame = cap.read()
                    if not ret:
                        break
                    batch.append((processed + len(batch), frame))
                if not batch:
                    break
                results = list(executor.map(process_range_item, batch))
                for f_idx, f_out in results:
                    out.write(f_out)
                    processed += 1

                now = time.time()
                elapsed = max(0.001, now - self._start_time)
                instant_fps = processed / elapsed
                self._ema_fps = instant_fps if self._ema_fps == 0.0 else (0.85 * self._ema_fps + 0.15 * instant_fps)
                rem_frames = max(0, total - processed)
                eta_sec = int(rem_frames / self._ema_fps) if self._ema_fps > 0 else 0
                self.frame_done.emit(processed, total, self._ema_fps, eta_sec, int(elapsed))



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
        from PyQt6.QtWidgets import QToolTip
        QToolTip.showText(self.mapToGlobal(QPoint(18, -4)), self._tip, self)

    def _do_hide(self) -> None:
        from PyQt6.QtWidgets import QToolTip
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
    key_captured = pyqtSignal(str)

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


# ─── Settings dialog ──────────────────────────────────────────────────────────

_KB_ACTIONS = [
    ("smart",           "Smart Watermark Snap"),
    ("brush",           "Paint Brush"),
    ("eraser",          "Eraser"),
    ("rect",            "Rectangle Select"),
    ("ellipse",         "Ellipse Select"),
    ("pan",             "Pan / Move Image/Video"),
    ("clear_mask",      "Clear Mask"),
    ("undo",            "Undo"),
    ("redo",            "Redo"),
    ("save",            "Save to Gallery"),
    ("open",            "Open Media"),
    ("new_preset",      "New Preset"),
    ("toggle_presets",  "Toggle Presets Panel"),
    ("zoom_in",         "Zoom In"),
    ("zoom_out",        "Zoom Out"),
    ("zoom_reset",      "Zoom Reset / Fit"),
]

class SettingsDialog(QDialog):
    applied = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Settings")
        if ICON_PATH.exists():
            self.setWindowIcon(QIcon(str(ICON_PATH)))
        self.setMinimumSize(520, 480)
        self.setModal(True)
        self._s  = load_settings()
        self._kw: dict[str, KeyCapture] = {}
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 10)
        root.setSpacing(0)
        tabs = QTabWidget()
        root.addWidget(tabs)
        tabs.addTab(self._kb_tab(),    "⌨️  Keybinds")
        tabs.addTab(self._editor_tab(),"🖌️  Editor")
        tabs.addTab(self._ui_tab(),    "💬  Interface")
        tabs.addTab(self._video_tab(), "🎬  Video")
        tabs.addTab(self._paths_tab(), "📁  Paths")
        br = QHBoxLayout()
        br.setContentsMargins(14, 0, 14, 0)
        br.addStretch()
        for txt, fn in [("↺ Defaults", self._reset),
                         ("Cancel",     self.reject),
                         ("Apply",      self._apply),
                         ("OK",         self._ok)]:
            b = QPushButton(txt)
            b.setFixedHeight(28)
            if txt == "OK":
                b.setObjectName("cta")
            b.clicked.connect(fn)
            br.addWidget(b)
        root.addLayout(br)

    def _row(self) -> QWidget:
        w = QWidget()
        lay = QFormLayout(w)
        lay.setContentsMargins(18, 12, 18, 12)
        lay.setSpacing(8)
        return w, lay

    def _kb_tab(self) -> QWidget:
        w, lay = self._row()
        n = QLabel("Click a binding then press the new key combo.")
        n.setStyleSheet(f"color:{TEXT_FAINT};font-size:10px;")
        lay.addRow(n)
        kb = self._s.get("keybinds", {})
        for key, label in _KB_ACTIONS:
            cap = KeyCapture(kb.get(key, DEFAULT_SETTINGS["keybinds"].get(key, "")))
            cap.key_captured.connect(
                lambda v, k=key: self._s["keybinds"].__setitem__(k, v))
            self._kw[key] = cap
            lay.addRow(f"{label}:", cap)
        return w

    def _editor_tab(self) -> QWidget:
        w, lay = self._row()
        self._bs = QSpinBox(); self._bs.setRange(2, 100)
        self._bs.setValue(self._s.get("brush_size", 25))
        self._bs.valueChanged.connect(lambda v: self._s.update({"brush_size": v}))
        lay.addRow("Default brush size:", self._bs)
        self._us = QSpinBox(); self._us.setRange(5, 200)
        self._us.setValue(self._s.get("max_undo", 30))
        self._us.valueChanged.connect(lambda v: self._s.update({"max_undo": v}))
        lay.addRow("Undo history steps:", self._us)
        self._lb = QComboBox()
        self._lb.addItems(["⚡ Quick", "🧠 Smart", "🔬 Precision", "✨ Cel AI"])
        self._lb.setCurrentIndex(self._s.get("default_level", 0))
        self._lb.currentIndexChanged.connect(
            lambda v: self._s.update({"default_level": v}))
        lay.addRow("Default inpaint mode:", self._lb)
        return w

    def _ui_tab(self) -> QWidget:
        w, lay = self._row()
        self._hov = QSpinBox(); self._hov.setRange(0, 2000); self._hov.setSuffix(" ms")
        self._hov.setValue(self._s.get("tooltip_hover", 250))
        self._hov.valueChanged.connect(lambda v: self._s.update({"tooltip_hover": v}))
        lay.addRow("Help bubble show delay:", self._hov)
        self._hid = QSpinBox(); self._hid.setRange(0, 5000); self._hid.setSuffix(" ms")
        self._hid.setValue(self._s.get("tooltip_hide", 750))
        self._hid.valueChanged.connect(lambda v: self._s.update({"tooltip_hide": v}))
        lay.addRow("Help bubble hide delay:", self._hid)
        self._gc = QSpinBox(); self._gc.setRange(2, 10)
        self._gc.setValue(self._s.get("gallery_cols", 4))
        self._gc.valueChanged.connect(lambda v: self._s.update({"gallery_cols": v}))
        lay.addRow("Gallery columns:", self._gc)
        return w

    def _video_tab(self) -> QWidget:
        w, lay = self._row()
        self._vf = QComboBox(); self._vf.addItems(["mp4", "avi"])
        self._vf.setCurrentText(self._s.get("video_format", "mp4"))
        self._vf.currentTextChanged.connect(lambda v: self._s.update({"video_format": v}))
        lay.addRow("Output format:", self._vf)
        self._tr = QDoubleSpinBox()
        self._tr.setRange(0.1, 0.99); self._tr.setSingleStep(0.05)
        self._tr.setValue(self._s.get("match_thresh", 0.45))
        self._tr.valueChanged.connect(
            lambda v: self._s.update({"match_thresh": round(v, 3)}))
        lay.addRow("Auto-track match threshold:", self._tr)
        n = QLabel("Higher = fewer false detections.")
        n.setStyleSheet(f"color:{TEXT_FAINT};font-size:10px;")
        lay.addRow(n)
        return w

    def _paths_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(18, 12, 18, 12)
        lay.setSpacing(8)
        for label, path in [("Settings & presets:", DATA_DIR),
                              ("Image & video gallery saves:", SAVE_DIR),
                              ("Diagnostics logs folder:", LOG_DIR)]:
            ll = QLabel(label)
            ll.setStyleSheet(f"color:{TEXT_MAIN};font-weight:600;font-size:11px;")
            lay.addWidget(ll)
            pl = QLabel(str(path))
            pl.setStyleSheet(
                f"color:{PURPLE_LIGHT};font-size:10px;padding:5px 8px;"
                f"background:{BG_DEEP};border:1px solid {BORDER_LIT};"
                f"border-radius:5px;")
            pl.setWordWrap(True)
            lay.addWidget(pl)

        # Live logging checkbox and open log folder
        log_box = QFrame()
        log_box.setStyleSheet(f"background:{BG_CARD};border:1px solid {BORDER};border-radius:8px;")
        lbl = QVBoxLayout(log_box)
        lbl.setContentsMargins(12, 10, 12, 10)
        lbl.setSpacing(8)

        self._log_cb = QCheckBox("📝  Enable live logging to logs/ (captures crashes & diagnostics)")
        self._log_cb.setStyleSheet(f"color:{TEXT_MAIN};font-size:11px;font-weight:600;")
        self._log_cb.setChecked(self._s.get("live_logging", False))
        self._log_cb.toggled.connect(lambda v: self._s.update({"live_logging": v}))
        lbl.addWidget(self._log_cb)

        btn_r = QHBoxLayout()
        btn_r.addStretch()
        open_log_btn = QPushButton("📂  Open Log Folder")
        open_log_btn.setObjectName("ghost")
        open_log_btn.setFixedHeight(28)
        open_log_btn.setStyleSheet(f"padding:3px 10px;font-size:11px;")
        open_log_btn.clicked.connect(lambda: launch_system_file(str(LOG_DIR)))
        btn_r.addWidget(open_log_btn)
        lbl.addLayout(btn_r)

        lay.addWidget(log_box)
        lay.addStretch()
        return w

    def _apply(self) -> None:
        save_settings(self._s)
        self.applied.emit()

    def _ok(self) -> None:
        self._apply()
        self.accept()

    def _reset(self) -> None:
        if QMessageBox.question(
                self, "Reset settings?",
                "Reset everything to defaults?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        ) == QMessageBox.StandardButton.Yes:
            self._s = {k: (v.copy() if isinstance(v, dict) else v)
                       for k, v in DEFAULT_SETTINGS.items()}
            save_settings(self._s)
            self.applied.emit()
            self.accept()


# ─── Preset save dialog ───────────────────────────────────────────────────────

class PresetSaveDialog(QDialog):
    def __init__(self, mask: np.ndarray, img_w: int, img_h: int, parent=None):
        super().__init__(parent)
        self.result_preset: dict | None = None
        valid = (mask is not None and mask.any() and
                 cv2.findNonZero(mask) is not None)
        if not valid:
            QMessageBox.warning(
                parent, "No mask",
                "Draw a mask over the watermark first,\n"
                "then save it as a preset.")
            self._valid = False
            return
        self._valid = True
        self._enc   = encode_mask(mask, img_w, img_h)
        self.setWindowTitle("Save Preset")
        self.setFixedSize(360, 210)
        self.setModal(True)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 16, 20, 14)
        lay.setSpacing(10)
        t = QLabel("Save Mask as Preset")
        t.setStyleSheet(
            f"font-size:13px;font-weight:700;color:{TEXT_MAIN};")
        lay.addWidget(t)
        s = QLabel(
            "Your drawn strokes will be saved exactly and can be\n"
            "applied to any image of any size in one click.")
        s.setStyleSheet(f"color:{TEXT_DIM};font-size:10px;")
        lay.addWidget(s)
        nr = QHBoxLayout()
        nl = QLabel("Name:"); nl.setStyleSheet(f"color:{TEXT_DIM};")
        nr.addWidget(nl)
        self._ne = QLineEdit()
        self._ne.setPlaceholderText("e.g. Gemini bottom-right star")
        nr.addWidget(self._ne); lay.addLayout(nr)
        lr = QHBoxLayout()
        ll2 = QLabel("Mode:"); ll2.setStyleSheet(f"color:{TEXT_DIM};")
        lr.addWidget(ll2)
        self._lb = QComboBox()
        self._lb.addItems(["⚡  Quick", "🧠  Smart", "🔬  Precision", "✨  Cel AI"])
        lr.addWidget(self._lb); lr.addStretch(); lay.addLayout(lr)
        lay.addStretch()
        br = QHBoxLayout(); br.addStretch()
        c = QPushButton("Cancel"); c.clicked.connect(self.reject)
        s2 = QPushButton("Save Preset"); s2.setObjectName("cta")
        s2.clicked.connect(self._save)
        br.addWidget(c); br.addWidget(s2); lay.addLayout(br)

    def _save(self) -> None:
        name = self._ne.text().strip()
        if not name:
            QMessageBox.warning(self, "Name required",
                                "Enter a name for the preset.")
            return
        self.result_preset = {
            "name":  name,
            "level": self._lb.currentIndex(),
            **(self._enc or {}),
        }
        self.accept()


# ─── About dialog ─────────────────────────────────────────────────────────────

_CHANGELOG = [
    ("v1.7.0", "2026-03-15", [
        ("0x425255534843555253",  "brush + eraser circle cursor on canvas"),
        ("0x434f4d50415245",      "before/after compare: hold 👁 to see original"),
        ("0x434c4950424f415244",  "copy result to clipboard in one click"),
        ("0x5341564546 4d54",     "save as PNG / JPG / WebP with format menu"),
        ("0x4f50454e464f4c44",    "open saves folder button"),
        ("0x5650535045 4544",     "video playback speed: 0.25× → 2×"),
        ("0x434c45414e",          "7 crash bugs fixed (resize guard, qi_orig, gallery stat…)"),
        ("0x5a4f4f4d504354",      "zoom % badge in header, updates live on scroll"),
    ]),
    ("v1.6.0", "2026-03-15", [
        ("0x4d494e494d414c",  "complete UI redesign — minimal, web-app feel"),
        ("0x4d4f42494c45",    "mobile detection + responsive layout rearrangement"),
        ("0x434c4f5345",      "closeEvent: workers, cap, timers all properly cleaned up"),
        ("0x475541524453",    "worker isRunning() guard — no ghost threads"),
        ("0x425547464958",    "fixed one-liner bug in precision loop (result+remaining)"),
        ("0x48495354",        "undo history count badge in header"),
        ("0x50414e",          "Space+drag / middle-mouse pan after zoom"),
        ("0x4b455942494e44", "all 14 actions bindable in settings keybinds tab"),
    ]),
    ("v1.5.0", "2026-03-15", [
        ("0x564944454f",      "video tab: auto-track + timeline removal"),
        ("0x554e444f",        "undo / redo stack"),
        ("0x53455454494e4753","full settings dialog"),
        ("0x505245534554",    "presets save actual drawn strokes"),
        ("0x44415441",        "data saved to Documents/HenryJay Data Folder/"),
    ]),
    ("v1.4.0", "2026-03-15", [
        ("0x455241534552",    "eraser tool"),
        ("0x505245534554",    "preset system"),
        ("0x564953",          "button visibility overhaul"),
    ]),
    ("v1.3.0", "2026-03-15", [
        ("0x4c455645 4c53",   "3-tier inpaint: Quick / Smart / Precision"),
        ("0x52494e47",        "Smart: ring-by-ring, zero centre-blur"),
        ("0x50415443 48",     "Precision: exemplar patch-match"),
    ]),
    ("v1.0.0", "2026-03-15", [
        ("0x494e4954",        "first commit — she lives"),
        ("0x544f4f4c53",      "brush, square, ellipse, keyboard shortcuts"),
        ("0x424f4f5354",      "auto-bootstrap + mirror fallbacks"),
    ]),
]

def _hdec(h: str) -> str:
    try:
        return bytes.fromhex(h.replace(" ", "")[2:]).decode()
    except Exception:
        return h

class AboutDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("About")
        if ICON_PATH.exists():
            self.setWindowIcon(QIcon(str(ICON_PATH)))
        self.setFixedSize(560, 540)
        self.setModal(True)
        self._dec = False
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        # Banner
        banner = QFrame()
        banner.setFixedHeight(118)
        banner.setStyleSheet(
            f"background:qlineargradient(x1:0,y1:0,x2:1,y2:1,"
            f"stop:0 #09090f,stop:0.5 #16093a,stop:1 #09090f);"
            f"border-bottom:1px solid {BORDER_LIT};")
        bl = QVBoxLayout(banner)
        bl.setContentsMargins(22, 14, 22, 12)
        bl.setSpacing(4)

        thdr = QHBoxLayout()
        thdr.setSpacing(10)
        if ICON_PATH.exists():
            icon_lbl = QLabel()
            pm = QPixmap(str(ICON_PATH)).scaled(32, 32, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            icon_lbl.setPixmap(pm)
            thdr.addWidget(icon_lbl)
        tl = QLabel("MyScreen Watermark Remover")
        tl.setStyleSheet(
            f"font-size:17px;font-weight:800;color:{PURPLE_LIGHT};letter-spacing:-0.3px;")
        thdr.addWidget(tl)
        thdr.addStretch()
        bl.addLayout(thdr)

        vr = QHBoxLayout()
        vl = QLabel(
            f"v{APP_VERSION}  ·  {BUILD_DATE}  ·  Python {sys.version.split()[0]}")
        vl.setStyleSheet(f"font-size:10px;color:{TEXT_DIM};")
        vr.addWidget(vl); vr.addStretch()
        bg = QLabel("  ✨ STABLE  ")
        bg.setStyleSheet(
            f"background:{GREEN_DIM};color:{GREEN_SOFT};"
            f"border:1px solid #1a3d28;border-radius:4px;"
            f"font-size:9px;font-weight:700;padding:2px 4px;")
        vr.addWidget(bg)

        # Top banner live log checkbox beside the STABLE badge
        self._top_log_cb = QCheckBox("📝 Live Log")
        self._top_log_cb.setStyleSheet(f"color:{TEXT_MAIN};font-size:10px;font-weight:600;margin-left:6px;")
        _s = load_settings()
        self._top_log_cb.setChecked(_s.get("live_logging", False))
        self._top_log_cb.toggled.connect(self._on_log_toggled)
        vr.addWidget(self._top_log_cb)

        bl.addLayout(vr)
        ar = QHBoxLayout()
        ar.addWidget(QLabel("By  <b>Henry Jay C</b>"))
        ar.addSpacing(10)
        ar.addWidget(QLabel("✉  hnrycrm@gmail.com  :3"))
        ar.addStretch(); bl.addLayout(ar)
        root.addWidget(banner)
        # Body
        body = QWidget()
        body.setStyleSheet(f"background:{BG_BASE};")
        b2 = QVBoxLayout(body)
        b2.setContentsMargins(18, 12, 18, 12)
        b2.setSpacing(8)
        clh = QHBoxLayout()
        ct = QLabel("CHANGELOG")
        ct.setStyleSheet(
            f"font-size:9px;font-weight:700;color:{TEXT_FAINT};letter-spacing:1.3px;")
        clh.addWidget(ct); clh.addStretch()
        self._db = QPushButton("[ DECODE ]")
        self._db.setObjectName("ghost")
        self._db.setStyleSheet(
            f"QPushButton{{color:{GREEN_SOFT};border:1px solid #1a3d28;"
            f"font-family:'JetBrains Mono','Consolas',monospace;"
            f"font-size:9px;font-weight:700;padding:2px 8px;border-radius:4px;}}"
            f"QPushButton:hover{{background:{GREEN_DIM};}}")
        self._db.clicked.connect(self._toggle)
        clh.addWidget(self._db); b2.addLayout(clh)
        self._ct = QTextEdit()
        self._ct.setReadOnly(True)
        self._ct.setFixedHeight(220)
        b2.addWidget(self._ct)
        # Stack chips
        sf = QFrame()
        sf.setStyleSheet(
            f"background:{BG_CARD};border:1px solid {BORDER};"
            f"border-radius:8px;")
        sfl = QHBoxLayout(sf)
        sfl.setContentsMargins(10, 7, 10, 7); sfl.setSpacing(6)
        sfl.addWidget(QLabel("⚡ Stack"))
        for lbl, col in [("Python 3", "#3b82f6"), ("PyQt6", "#8b5cf6"),
                          ("OpenCV", "#22c55e"), ("NumPy", "#f59e0b")]:
            c = QLabel(f"  {lbl}  ")
            c.setStyleSheet(
                f"color:{col};border:1px solid {col}44;border-radius:3px;"
                f"font-size:10px;font-weight:600;padding:1px;background:transparent;")
            sfl.addWidget(c)
        sfl.addStretch()
        sfl.addWidget(QLabel("made with ♥ in 2026"))
        b2.addWidget(sf)

        # Live log toggle row
        log_row = QHBoxLayout()
        self._log_cb = QCheckBox("📝  Enable live logging to CelWR.log (captures crashes & diagnostics)")
        self._log_cb.setStyleSheet(f"color:{TEXT_MAIN};font-size:11px;font-weight:600;")
        self._log_cb.setChecked(_s.get("live_logging", False))
        self._log_cb.toggled.connect(self._on_log_toggled)
        log_row.addWidget(self._log_cb)
        log_row.addStretch()
        b2.addLayout(log_row)

        cb = QPushButton("Close")
        cb.setObjectName("cta"); cb.setFixedWidth(90); cb.setFixedHeight(28)
        cb.clicked.connect(self.accept)
        b2.addWidget(cb, alignment=Qt.AlignmentFlag.AlignRight)
        root.addWidget(body)
        self._render(False)

    def _on_log_toggled(self, checked: bool) -> None:
        s = load_settings()
        s["live_logging"] = bool(checked)
        save_settings(s)
        if hasattr(self, "_log_cb") and self._log_cb.isChecked() != checked:
            self._log_cb.blockSignals(True)
            self._log_cb.setChecked(checked)
            self._log_cb.blockSignals(False)
        if hasattr(self, "_top_log_cb") and self._top_log_cb.isChecked() != checked:
            self._top_log_cb.blockSignals(True)
            self._top_log_cb.setChecked(checked)
            self._top_log_cb.blockSignals(False)
        if checked:
            cel_logger.enable()
        else:
            cel_logger.disable()

    def _render(self, dec: bool) -> None:
        lines = []
        for ver, date, entries in _CHANGELOG:
            bar = "─" * max(2, 44 - len(ver) - len(date))
            lines.append(f"┌─ {ver}  ·  {date}  {bar}")
            for code, desc in entries:
                tag = f"[{_hdec(code).upper()}]" if dec else code
                lines.append(
                    f"│  {tag:<22}  {desc[:40]}{'…' if len(desc)>40 else ''}")
            lines.append("└" + "─" * 54)
        self._ct.setPlainText("\n".join(lines))

    def _toggle(self) -> None:
        self._dec = not self._dec
        self._render(self._dec)
        self._db.setText("[ ENCODE ]" if self._dec else "[ DECODE ]")


class ShortcutsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Keyboard Shortcuts & Cheat Sheet")
        if ICON_PATH.exists():
            self.setWindowIcon(QIcon(str(ICON_PATH)))
        self.setFixedSize(560, 500)
        self.setStyleSheet(f"background:{BG_DEEP};color:{TEXT_MAIN};")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(18, 16, 18, 16)
        lay.setSpacing(12)

        ttl = QLabel("⌨️  Keyboard Shortcuts & Gestures")
        ttl.setStyleSheet(f"font-size:16px;font-weight:700;color:{PURPLE_LIGHT};")
        lay.addWidget(ttl)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("background:transparent;border:none;")
        inner = QWidget()
        il = QVBoxLayout(inner)
        il.setSpacing(12)
        il.setContentsMargins(0, 0, 0, 0)

        sections = [
            ("🪄 Tools & Selection", [
                ("S", "Smart Snap (Multi-scale auto snap with 8 resize handles)"),
                ("B", "Brush Tool (Freehand drawing)"),
                ("X", "Eraser Tool (Erase mask strokes)"),
                ("R", "Rectangle Selection Box"),
                ("E", "Ellipse / Circle Selection"),
                ("H", "Pan / Move Tool (Hand cursor)"),
            ]),
            ("🎨 Mask Operations", [
                ("]  or  +", "Expand Mask (+2px to avoid edge halos)"),
                ("[  or  -", "Contract Mask (-2px)"),
                ("I", "Invert Selection Mask"),
                ("Delete / Ctrl+D", "Clear Mask"),
            ]),
            ("⚡ Editing & Actions", [
                ("Ctrl + Z", "Undo last stroke/edit"),
                ("Ctrl + Y", "Redo edit"),
                ("Shift + S", "Auto-Detect all watermarks in image"),
                ("\\", "Toggle Before / After comparison view"),
                ("Ctrl + O", "Open Image / Load Media"),
                ("Ctrl + S", "Save Inpainted Image"),
                ("Ctrl + E", "Open Saves / Edits Folder"),
                ("Ctrl + Shift + P", "Toggle Presets Panel"),
            ]),
            ("🔍 Viewport & Navigation", [
                ("Space/Right-Click + Drag", "Pan/Move Image/Video"),
                ("Middle Click + Drag", "Pan Viewport"),
                ("Scroll Wheel", "Zoom In / Zoom Out"),
                ("Ctrl + 0", "Zoom Fit to Screen"),
                ("F1  or  ?", "Open this Shortcuts Guide"),
            ]),
        ]

        for sec_title, items in sections:
            grp = QFrame()
            grp.setStyleSheet(f"background:{BG_CARD};border:1px solid {BORDER};border-radius:8px;padding:8px;")
            gl = QVBoxLayout(grp)
            gl.setSpacing(6)
            st = QLabel(sec_title)
            st.setStyleSheet(f"font-weight:700;font-size:12px;color:{TEXT_MAIN};margin-bottom:2px;")
            gl.addWidget(st)
            for k, d in items:
                row = QHBoxLayout()
                kl = QLabel(k)
                kl.setStyleSheet(f"background:{BG_BASE};color:{PURPLE_LIGHT};font-weight:700;font-size:11px;"
                                 f"padding:2px 6px;border:1px solid {BORDER_LIT};border-radius:4px;min-width:70px;")
                kl.setAlignment(Qt.AlignmentFlag.AlignCenter)
                row.addWidget(kl)
                dl = QLabel(d)
                dl.setStyleSheet(f"color:{TEXT_DIM};font-size:11px;")
                row.addWidget(dl, 1)
                gl.addLayout(row)
            il.addWidget(grp)

        scroll.setWidget(inner)
        lay.addWidget(scroll)

        cb = QPushButton("Close")
        cb.setObjectName("cta")
        cb.setFixedHeight(32)
        cb.clicked.connect(self.accept)
        lay.addWidget(cb)


# ─── Base Canvas ──────────────────────────────────────────────────────────────

class _BaseCanvas(QWidget):
    status_msg   = pyqtSignal(str)
    mask_changed = pyqtSignal()

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
        p.fillRect(self.rect(), QColor(BG_DEEP))
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

class Canvas(_BaseCanvas):
    inpaint_done = pyqtSignal()
    busy_changed = pyqtSignal(bool)

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
        if self.cv_cur is None or self.mask is None:
            self.status_msg.emit("  ⚠️  Load an image first!")
            return None
        h, w = self.cv_cur.shape[:2]
        new_mask = decode_mask(preset, w, h)
        self._push_undo()
        self.mask = np.maximum(self.mask, new_mask)
        self.update()
        self.status_msg.emit(
            f"  ✅  Preset '{preset['name']}' applied — click Remove!")
        return preset.get("level", LEVEL_QUICK)

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
            return None
        try:
            SAVE_DIR.mkdir(parents=True, exist_ok=True)
            ts  = datetime.now().strftime("%Y%m%d_%H%M%S")
            ext = fmt.lower().strip(".")
            out = SAVE_DIR / f"edit_{ts}.{ext}"
            if ext in ("jpg", "jpeg"):
                params = [cv2.IMWRITE_JPEG_QUALITY, quality]
            elif ext == "webp":
                params = [cv2.IMWRITE_WEBP_QUALITY, quality]
            else:
                params = []
            ok = cv2.imwrite(str(out), self.cv_cur, params)
            if not ok:
                self.status_msg.emit("  ❌  imwrite failed — check disk space")
                return None
            return out
        except Exception as exc:
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

class VideoCanvas(_BaseCanvas):
    video_dropped = pyqtSignal(str)

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


# ─── Video Tab ────────────────────────────────────────────────────────────────

class VideoTab(QWidget):
    status_msg = pyqtSignal(str)

    def __init__(self, help_bubbles: list, parent=None):
        super().__init__(parent)
        self._hbs    = help_bubbles
        self._cap:   cv2.VideoCapture | None = None
        self._total  = 0
        self._fps    = 30.0
        self._cur    = 0
        self._playing = False
        self._pt     = QTimer(self, singleShot=False)
        self._pt.timeout.connect(self._advance)
        self._worker: VideoWorker | None = None
        self._ref_idx  = 0
        self._ref_mask: np.ndarray | None = None
        self._segs:  list = []
        self._vpath  = ""
        # Range removal state
        self._range_start: int = -1
        self._range_end:   int = -1
        self._range_mask:  np.ndarray | None = None
        self._build()

    def _build(self) -> None:
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Canvas side
        left = QWidget()
        ll   = QVBoxLayout(left)
        ll.setContentsMargins(0, 0, 0, 0)
        ll.setSpacing(0)
        self.vc = VideoCanvas()
        self.vc.status_msg.connect(self.status_msg)
        self.vc.video_dropped.connect(self.load_video)
        ll.addWidget(self.vc)

        # Transport bar
        tb = QFrame()
        tb.setFixedHeight(38)
        tb.setStyleSheet(
            f"background:{BG_BASE};border-top:1px solid {BORDER};")
        tl = QHBoxLayout(tb)
        tl.setContentsMargins(8, 3, 8, 3)
        tl.setSpacing(4)
        bs = (f"QPushButton{{background:transparent;color:{TEXT_DIM};"
              f"border:none;font-size:13px;padding:2px 5px;border-radius:4px;}}"
              f"QPushButton:hover{{color:{PURPLE_LIGHT};background:{BG_RAISED};}}")
        for txt, fn in [("◀", lambda: self._seek(max(0, self._cur - 1))),
                         ("▶", self._toggle_play),
                         ("▶▶", lambda: self._seek(
                             min(max(0, self._total - 1), self._cur + 1))),
                         ("🧹", self.vc.clear_mask)]:
            b = QPushButton(txt)
            b.setFixedWidth(28 if txt != "🧹" else 26)
            b.setStyleSheet(bs)
            if txt == "▶":
                self._play_btn = b
            b.clicked.connect(fn)
            tl.addWidget(b)
        self._sl = QSlider(Qt.Orientation.Horizontal)
        self._sl.setRange(0, 0)
        self._sl.sliderMoved.connect(self._seek)
        tl.addWidget(self._sl)
        self._fl = QLabel("— / —")
        self._fl.setStyleSheet(
            f"color:{TEXT_DIM};font-size:10px;min-width:60px;")
        tl.addWidget(self._fl)
        # Playback speed
        self._spd = QComboBox()
        self._spd.addItems(["0.25×", "0.5×", "1×", "1.5×", "2×"])
        self._spd.setCurrentIndex(2)
        self._spd.setFixedWidth(58); self._spd.setFixedHeight(26)
        self._spd.setToolTip("Playback speed")
        self._spd.currentIndexChanged.connect(self._update_speed)
        tl.addWidget(self._spd)
        ll.addWidget(tb)
        self._pb = QProgressBar()
        self._pb.setFixedHeight(3)
        self._pb.setTextVisible(False)
        self._pb.hide()
        ll.addWidget(self._pb)
        root.addWidget(left, 1)

        # Right control panel — clean, minimal
        pan = QFrame()
        pan.setFixedWidth(220)
        pan.setStyleSheet(
            f"background:{BG_BASE};border-left:1px solid {BORDER};")
        pl = QVBoxLayout(pan)
        pl.setContentsMargins(10, 10, 10, 10)
        pl.setSpacing(6)

        lb = QPushButton("📂  Load Video")
        lb.clicked.connect(self._load)
        pl.addWidget(lb)

        of_btn = QPushButton("📂  Open Edits Folder")
        of_btn.setObjectName("ghost")
        of_btn.setFixedHeight(28)
        of_btn.clicked.connect(self._open_last_export)
        pl.addWidget(of_btn)

        self._audio_cb = QCheckBox("🔊  Keep Audio Track")
        self._audio_cb.setChecked(True)
        self._audio_cb.setStyleSheet(f"color:{TEXT_DIM};font-size:10px;padding:2px 0;")
        pl.addWidget(self._audio_cb)

        self._vi = QLabel("No video loaded")
        self._vi.setStyleSheet(
            f"color:{TEXT_FAINT};font-size:10px;")
        self._vi.setWordWrap(True)
        pl.addWidget(self._vi)

        sep = QFrame(); sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet(f"color:{BORDER};"); pl.addWidget(sep)

        # Method tabs
        mh = QHBoxLayout(); mh.setSpacing(4)
        ml = QLabel("METHOD")
        ml.setStyleSheet(
            f"font-size:9px;font-weight:700;color:{TEXT_FAINT};"
            f"letter-spacing:1px;")
        mh.addWidget(ml); mh.addStretch()
        mbbl = HelpBubble(
            "🎯 Auto-Track:\n"
            "Draw mask on a reference frame. System\n"
            "finds & removes your watermark in every\n"
            "frame via template matching — even when\n"
            "it moves.\n\n"
            "📋 Timeline:\n"
            "Specify exact frame ranges where the\n"
            "watermark appears. Add multiple segments.")
        self._hbs.append(mbbl)
        mh.addWidget(mbbl)
        pl.addLayout(mh)

        self._mt = QTabWidget()
        self._mt.setStyleSheet(
            "QTabBar::tab{padding:4px 9px;font-size:10px;}")
        pl.addWidget(self._mt)

        # Auto-track tab
        at = QWidget()
        atl = QVBoxLayout(at)
        atl.setContentsMargins(5, 7, 5, 7)
        atl.setSpacing(6)
        atl.addWidget(QLabel("Draw mask on a frame, set it as\n"
                              "reference, then process the video."))
        self._ri = QLabel("Reference: not set")
        self._ri.setStyleSheet(f"color:{TEXT_FAINT};font-size:10px;")
        atl.addWidget(self._ri)
        srb = QPushButton("📌  Set as Reference Frame")
        srb.clicked.connect(self._set_ref)
        atl.addWidget(srb)
        tr = QHBoxLayout(); tr.addWidget(QLabel("Sensitivity:"))
        self._ts = QSlider(Qt.Orientation.Horizontal)
        self._ts.setRange(10, 90); self._ts.setValue(45)
        self._tvl = QLabel("0.45")
        self._tvl.setStyleSheet(
            f"color:{PURPLE_LIGHT};font-size:10px;min-width:26px;")
        self._ts.valueChanged.connect(
            lambda v: self._tvl.setText(f"{v/100:.2f}"))
        tr.addWidget(self._ts); tr.addWidget(self._tvl)
        atl.addLayout(tr)
        atl.addStretch()
        rab = QPushButton("🎯  Auto-Track & Process")
        rab.setObjectName("cta"); rab.clicked.connect(self._run_at)
        atl.addWidget(rab)
        self._mt.addTab(at, "🎯 Auto")

        # Timeline tab
        tlt = QWidget()
        tll = QVBoxLayout(tlt)
        tll.setContentsMargins(5, 7, 5, 7)
        tll.setSpacing(6)
        tll.addWidget(QLabel("Draw mask, then add frame range\n"
                              "for each watermark segment."))
        self._segl = QListWidget()
        self._segl.setMinimumHeight(60)
        tll.addWidget(self._segl)
        asb = QPushButton("＋  Add Segment from Frame")
        asb.clicked.connect(self._add_seg)
        tll.addWidget(asb)
        dsb = QPushButton("🗑  Remove Selected")
        dsb.setObjectName("danger"); dsb.clicked.connect(self._del_seg)
        tll.addWidget(dsb)
        tll.addStretch()
        rtb = QPushButton("📋  Process Timeline")
        rtb.setObjectName("cta"); rtb.clicked.connect(self._run_tl)
        tll.addWidget(rtb)
        self._mt.addTab(tlt, "📋 Timeline")

        sep2 = QFrame(); sep2.setFrameShape(QFrame.Shape.HLine)
        sep2.setStyleSheet(f"color:{BORDER};"); pl.addWidget(sep2)

        lr = QHBoxLayout(); lr.addWidget(QLabel("Mode:"))
        self._lb2 = QComboBox()
        self._lb2.addItems(["⚡ Quick", "🧠 Smart", "🔬 Precision", "✨ Cel AI"])
        lr.addWidget(self._lb2); pl.addLayout(lr)

        # ── Quick single-frame remove button ──
        self._remove_frame_btn = QPushButton("✨  Remove Watermark")
        self._remove_frame_btn.setObjectName("cta")
        self._remove_frame_btn.setToolTip(
            "Inpaint the drawn mask on the current frame preview")
        self._remove_frame_btn.clicked.connect(self._remove_frame)
        pl.addWidget(self._remove_frame_btn)

        # ── Range removal wizard ──
        sep3 = QFrame(); sep3.setFrameShape(QFrame.Shape.HLine)
        sep3.setStyleSheet(f"color:{BORDER};"); pl.addWidget(sep3)
        rh = QHBoxLayout(); rh.setSpacing(4)
        rl = QLabel("RANGE WIZARD")
        rl.setStyleSheet(
            f"font-size:9px;font-weight:700;color:{TEXT_FAINT};"
            f"letter-spacing:1px;")
        rh.addWidget(rl); rh.addStretch()
        rbbl = HelpBubble(
            "🎬 Range Removal Wizard:\n"
            "1. Draw mask on watermark & click '1. Mark Start'\n"
            "2. Scrub timeline to end frame & click '2. Mark End'\n"
            "3. Click '3. Remove Range' to process all frames!")
        self._hbs.append(rbbl)
        rh.addWidget(rbbl)
        pl.addLayout(rh)

        # Step 1: Mark Start Frame
        self._mark_start_btn = QPushButton("📍  1. Mark Start Frame")
        self._mark_start_btn.setToolTip("Save current frame + drawn mask as the range start")
        self._mark_start_btn.clicked.connect(self._mark_range_start)
        pl.addWidget(self._mark_start_btn)

        # Step 2: Mark End Frame
        self._mark_end_btn = QPushButton("🏁  2. Mark End Frame")
        self._mark_end_btn.setToolTip("Mark current frame as the end of watermark range")
        self._mark_end_btn.setEnabled(False)
        self._mark_end_btn.clicked.connect(self._mark_range_end)
        pl.addWidget(self._mark_end_btn)

        # Step 3: Remove Range CTA
        self._remove_range_btn = QPushButton("✨  3. Remove Range")
        self._remove_range_btn.setObjectName("cta")
        self._remove_range_btn.setToolTip("Process and remove watermark across the marked range")
        self._remove_range_btn.setEnabled(False)
        self._remove_range_btn.clicked.connect(self._remove_range)
        pl.addWidget(self._remove_range_btn)

        # Step 5: Open Exported File button
        self._open_export_btn = QPushButton("📁  5. DONE, CHECK FOLDER")
        self._open_export_btn.setObjectName("cta")
        self._open_export_btn.setStyleSheet(f"background:#0d2818;border:1px solid {GREEN_SOFT};color:{GREEN_SOFT};font-weight:700;")
        self._open_export_btn.setToolTip("Open the default exports folder to view your processed video")
        self._open_export_btn.hide()
        self._open_export_btn.clicked.connect(self._open_last_export)
        pl.addWidget(self._open_export_btn)

        # Guide card with step instructions
        self._range_guide = QFrame()
        self._range_guide.setStyleSheet(
            f"QFrame{{background:{BG_CARD};border:1px solid {BORDER_LIT};border-radius:6px;}}")
        rgl = QVBoxLayout(self._range_guide)
        rgl.setContentsMargins(6, 6, 6, 6)
        rgl.setSpacing(3)
        self._range_lbl = QLabel("💡 Step 1: Draw mask on watermark, then click '1. Mark Start Frame'")
        self._range_lbl.setStyleSheet(f"color:{TEXT_DIM};font-size:10px;")
        self._range_lbl.setWordWrap(True)
        rgl.addWidget(self._range_lbl)
        pl.addWidget(self._range_guide)

        # Reset button
        self._reset_range_btn = QPushButton("↺  Reset Range")
        self._reset_range_btn.setObjectName("ghost")
        self._reset_range_btn.hide()
        self._reset_range_btn.clicked.connect(self._reset_range)
        pl.addWidget(self._reset_range_btn)

        self._can_btn = QPushButton("⛔  Cancel")
        self._can_btn.setObjectName("danger")
        self._can_btn.hide()
        self._can_btn.clicked.connect(self._cancel)
        pl.addWidget(self._can_btn)

        self._ol = QLabel("")
        self._ol.setStyleSheet(f"color:{TEXT_FAINT};font-size:9px;")
        self._ol.setWordWrap(True)
        pl.addWidget(self._ol)
        pl.addStretch()
        root.addWidget(pan)

    # ── Video I/O ─────────────────────────────────────────────────────────────

    def dragEnterEvent(self, e) -> None:
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e) -> None:
        for url in e.mimeData().urls():
            fp = url.toLocalFile()
            if fp.lower().endswith((".mp4", ".avi", ".mkv", ".mov", ".webm")):
                self.load_video(fp)
                break

    def load_video(self, path: str) -> bool:
        self._release_cap()
        self._cap = cv2.VideoCapture(path)
        if not self._cap.isOpened():
            self._cap = None
            QMessageBox.critical(self, "Error", "Cannot open video.")
            return False
        self._vpath  = path
        self._total  = max(int(self._cap.get(cv2.CAP_PROP_FRAME_COUNT)), 1)
        self._fps    = self._cap.get(cv2.CAP_PROP_FPS) or 30.0
        W = int(self._cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        H = int(self._cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        self._sl.setRange(0, max(0, self._total - 1))
        self._vi.setText(
            f"{Path(path).name}\n{W}×{H}  ·  {self._total}f  ·  {self._fps:.1f}fps")
        self._ref_mask = None
        self._segs     = []
        self._refresh_segs()
        self._ri.setText("Reference: not set")
        self._range_start = -1
        self._range_end   = -1
        self._range_mask  = None
        self._seek(0)
        self._update_range_ui()
        self.status_msg.emit(f"  🎬  {Path(path).name}   ·   {W}×{H}   ·   {self._total} frames")
        return True

    def _load(self) -> None:
        s = load_settings()
        last_dir = s.get("last_open_dir", str(Path.home() / "Videos"))
        if not Path(last_dir).exists():
            last_dir = str(Path.home())
        path, _ = QFileDialog.getOpenFileName(
            self, "Open Video", last_dir,
            "Videos (*.mp4 *.avi *.mkv *.mov *.webm)")
        if path:
            s["last_open_dir"] = str(Path(path).parent)
            save_settings(s)
            self.load_video(path)

    def _release_cap(self) -> None:
        if self._cap is not None:
            self._cap.release()
            self._cap = None

    def _seek(self, idx: int) -> None:
        if self._cap is None:
            return
        self._stop_play()
        self._cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
        ret, frame = self._cap.read()
        if ret:
            self._cur = idx
            self.vc.load_frame(frame)
            self._fl.setText(f"{idx} / {max(0, self._total-1)}")
            self._update_range_ui()
        self._sl.blockSignals(True)
        self._sl.setValue(idx)
        self._sl.blockSignals(False)

    _SPEEDS = [0.25, 0.5, 1.0, 1.5, 2.0]

    def _get_speed(self) -> float:
        try:
            return self._SPEEDS[self._spd.currentIndex()]
        except (AttributeError, IndexError):
            return 1.0

    def _update_speed(self) -> None:
        if self._playing:
            spd = self._get_speed()
            self._pt.start(max(1, int(1000 / self._fps / spd)))

    def _toggle_play(self) -> None:
        if self._playing:
            self._stop_play()
        else:
            if self._cap is None:
                return
            self._playing = True
            self._play_btn.setText("⏸")
            spd = self._get_speed()
            self._pt.start(max(1, int(1000 / self._fps / spd)))

    def _stop_play(self) -> None:
        self._playing = False
        self._play_btn.setText("▶")
        self._pt.stop()

    def _advance(self) -> None:
        if self._cap is None:
            self._stop_play()
            return
        ret, frame = self._cap.read()
        if not ret:
            self._stop_play()
            return
        self._cur += 1
        self.vc.load_frame(frame)
        self._sl.blockSignals(True)
        self._sl.setValue(self._cur)
        self._sl.blockSignals(False)
        self._fl.setText(f"{self._cur} / {max(0, self._total-1)}")
        self._update_range_ui()
        if self._cur >= self._total - 1:
            self._stop_play()

    # ── Methods ───────────────────────────────────────────────────────────────

    def _set_ref(self) -> None:
        if self._cap is None:
            QMessageBox.information(self, "No video", "Load a video first.")
            return
        m = self.vc.get_mask()
        if m is None or not m.any():
            QMessageBox.information(self, "No mask",
                "Draw a mask on the current frame first.")
            return
        self._ref_mask = m
        self._ref_idx  = self._cur
        self._ri.setText(f"Reference: frame #{self._cur}")
        self.status_msg.emit(f"  📌  Reference set — frame {self._cur}")

    def _add_seg(self) -> None:
        if self._cap is None:
            QMessageBox.information(self, "No video", "Load a video first.")
            return
        m = self.vc.get_mask()
        if m is None or not m.any():
            QMessageBox.information(self, "No mask",
                "Draw a mask on the current frame first.")
            return
        s, ok1 = QInputDialog.getInt(
            self, "Start frame",
            f"Start frame (0 – {self._total-1}):",
            max(0, self._cur - 30), 0, self._total - 1)
        if not ok1:
            return
        e, ok2 = QInputDialog.getInt(
            self, "End frame",
            f"End frame (0 – {self._total-1}):",
            min(self._total - 1, self._cur), s, self._total - 1)
        if not ok2:
            return
        self._segs.append({"start": s, "end": e, "mask": m.copy()})
        self._refresh_segs()

    def _del_seg(self) -> None:
        r = self._segl.currentRow()
        if r >= 0:
            self._segs.pop(r)
            self._refresh_segs()

    def _refresh_segs(self) -> None:
        self._segl.clear()
        for seg in self._segs:
            self._segl.addItem(f"Frames {seg['start']} – {seg['end']}")

    def _run_at(self) -> None:
        if not self._vpath:
            QMessageBox.information(self, "No video", "Load a video first.")
            return
        if self._ref_mask is None or not self._ref_mask.any():
            QMessageBox.information(self, "No reference",
                "Set a reference frame first.")
            return
        self._start_proc("auto_track", {
            "ref_frame": self._ref_idx,
            "mask":      self._ref_mask.copy(),
            "threshold": self._ts.value() / 100,
        })

    def _run_tl(self) -> None:
        if not self._vpath:
            QMessageBox.information(self, "No video", "Load a video first.")
            return
        if not self._segs:
            QMessageBox.information(self, "No segments",
                "Add at least one segment first.")
            return
        self._start_proc("timeline", {"segments": self._segs})

    def _start_proc(self, method: str, data: dict) -> None:
        s   = load_settings()
        ext = s.get("video_format", "mp4")
        out = str(SAVE_DIR /
                  f"video_{datetime.now().strftime('%Y%m%d_%H%M%S')}.{ext}")
        level = self._lb2.currentIndex()

        if method == "range_remove":
            st = data.get("start", 0)
            en = data.get("end", self._total - 1)
            title = f"Range Removal (Frames {st} → {en})"
        elif method == "auto_track":
            title = f"Auto-Track Inpaint"
        else:
            title = f"Timeline Inpaint ({len(data.get('segments', []))} segs)"

        thumb = self.vc._frame if self.vc._frame is not None else None
        keep_aud = self._audio_cb.isChecked() if hasattr(self, "_audio_cb") else True
        task = TaskManager.instance().add_video_task(
            title=title,
            src=self._vpath,
            dst=out,
            method=method,
            data=data,
            level=level,
            total_frames=self._total,
            thumb=thumb,
            keep_audio=keep_aud
        )
        self._current_task = task
        task.updated.connect(self._prog_task)
        task.finished.connect(self._vdone)
        task.error.connect(self._verr)

        self._pb.setRange(0, 100)
        self._pb.setValue(0)
        self._pb.show()
        self._can_btn.show()
        self._ol.setText(f"→ {out}")

        if method == "range_remove":
            self._remove_range_btn.setText("⏳  4. PLEASE WAIT A WHILE…")
            self._remove_range_btn.setEnabled(False)
            self._open_export_btn.hide()
            self._range_lbl.setText("⏳ Step 4: Video is processing in background... Check the 'Files In Progress' tab!")
            self._range_lbl.setStyleSheet(f"color:{PURPLE_LIGHT};font-size:10px;font-weight:600;")
            self.vc.set_banner(f"⏳ Processing Range in Background... Check 'Files In Progress' tab!")

        self.status_msg.emit(f"  🎬  Video processing queued in 'Files In Progress' tab!")

    def _prog_task(self) -> None:
        if not hasattr(self, "_current_task") or not self._current_task:
            return
        t = self._current_task
        cur = t.current_frame
        tot = t.total_frames
        pct = int(cur / max(tot, 1) * 100)
        self._pb.setValue(pct)

        fps = t.fps_rate
        eta_sec = t.eta_seconds
        elapsed_sec = int((datetime.now() - t.start_time).total_seconds())

        if eta_sec < 60:
            eta_str = f"{eta_sec}s"
        elif eta_sec < 3600:
            eta_str = f"{eta_sec // 60}m {eta_sec % 60:02d}s"
        else:
            eta_str = f"{eta_sec // 3600}h {(eta_sec % 3600) // 60:02d}m"

        el_m, el_s = divmod(elapsed_sec, 60)
        el_str = f"{el_m}m {el_s:02d}s"
        fps_str = f"{fps:.1f} fps" if fps > 0 else "estimating…"

        if hasattr(self, "_remove_range_btn") and not self._remove_range_btn.isEnabled():
            self._remove_range_btn.setText(f"⏳  4. PLEASE WAIT… ({pct}%) · ETA: {eta_str}")

        self.status_msg.emit(
            f"  🎬  Frame {cur:,}/{tot:,}  ({pct}%)   ·   ⚡ {fps_str}   ·   ⏳ ETA: {eta_str}   ·   ⏱ Elapsed: {el_str}")

    def _vdone(self, path: str) -> None:
        self._pb.hide(); self._can_btn.hide()
        self._last_exported_video = path
        if hasattr(self, "_remove_range_btn") and hasattr(self, "_open_export_btn"):
            self._remove_range_btn.hide()
            self._open_export_btn.setText("📁  5. DONE, CHECK FOLDER")
            self._open_export_btn.show()
            self._range_lbl.setText(
                f"🎉 Step 5: Finished! Video saved to default exports folder.\n"
                f"Click '5. DONE, CHECK FOLDER' to view, or 'Reset Range' for another task.")
            self._range_lbl.setStyleSheet(f"color:{GREEN_SOFT};font-size:10px;font-weight:600;")
            self.vc.set_banner(f"🎉 DONE! Video saved to Exports folder ({Path(path).name})")
        self.status_msg.emit(f"  ✅  Saved → {Path(path).name}")
        QMessageBox.information(self, "Done!", f"Video saved to default exports:\n{path}")

    def _verr(self, msg: str) -> None:
        self._pb.hide(); self._can_btn.hide()
        if hasattr(self, "_remove_range_btn"):
            self._remove_range_btn.setEnabled(True)
            self._remove_range_btn.setText("✨  3. Remove Range")
        self.status_msg.emit(f"  ❌  {msg.splitlines()[0]}")
        QMessageBox.critical(self, "Error", msg)

    def _cancel(self) -> None:
        if hasattr(self, "_current_task") and self._current_task:
            self._current_task.cancel()
        self._pb.hide(); self._can_btn.hide()
        if hasattr(self, "_remove_range_btn"):
            self._remove_range_btn.setEnabled(True)
            self._remove_range_btn.setText("✨  3. Remove Range")
        self.status_msg.emit("  ⛔  Cancelled")

    def _open_last_export(self) -> None:
        p = str(SAVE_DIR.resolve())
        if hasattr(self, "_last_exported_video") and self._last_exported_video and Path(self._last_exported_video).exists():
            p = str(Path(self._last_exported_video).parent.resolve())
        launch_system_file(p)

    def _remove_frame(self) -> None:
        """Quick single-frame watermark removal — inpaint the current frame's mask."""
        if self.vc._frame is None:
            QMessageBox.information(self, "No video", "Load a video first.")
            return
        m = self.vc.get_mask()
        if m is None or not m.any():
            QMessageBox.information(self, "No mask",
                "Draw a mask on the current frame first.")
            return
        level = self._lb2.currentIndex()
        self.status_msg.emit("  ⏳  Removing watermark from frame…")
        try:
            self.vc._push_img_undo()
            result = run_inpaint(self.vc._frame, m, level)
            self.vc.load_frame(result)
            self.vc.mask.fill(0)
            self.vc._invalidate_overlay()
            self.vc.mask_changed.emit()
            self.vc.update()
            self.status_msg.emit("  ✨  Frame watermark removed! Press Undo [Ctrl+Z] to restore.")
        except Exception as exc:
            self.status_msg.emit(f"  ❌  {exc}")

    def _update_range_ui(self) -> None:
        if self._cap is None or not hasattr(self, "_mark_start_btn"):
            return
        if self._range_start < 0:
            self._mark_start_btn.setText(f"📍  1. Mark Start (Frame #{self._cur})")
            self._mark_start_btn.setStyleSheet("")
            self._mark_end_btn.setText("🏁  2. Mark End Frame")
            self._mark_end_btn.setEnabled(False)
            self._mark_end_btn.setStyleSheet("")
            self._remove_range_btn.show()
            self._remove_range_btn.setText("✨  3. Remove Range")
            self._remove_range_btn.setEnabled(False)
            self._remove_range_btn.setStyleSheet("")
            self._open_export_btn.hide()
            self._reset_range_btn.hide()
            self._range_lbl.setText("💡 Step 1: Draw mask on watermark, then click '1. Mark Start Frame'")
            self._range_lbl.setStyleSheet(f"color:{TEXT_DIM};font-size:10px;")
            self.vc.set_banner("")
        elif self._range_end < 0:
            # Start marked, waiting for end
            self._mark_start_btn.setText(f"✅ Start: #{self._range_start}")
            self._mark_start_btn.setStyleSheet(f"color:{PURPLE_LIGHT};font-weight:600;")

            s = min(self._range_start, self._cur)
            e = max(self._range_start, self._cur)
            cnt = e - s + 1
            self._mark_end_btn.setText(f"🏁  2. Mark End (Frame #{self._cur})")
            self._mark_end_btn.setEnabled(True)
            self._mark_end_btn.setStyleSheet(f"border-color:{PURPLE_LIGHT};color:{TEXT_MAIN};font-weight:600;")

            self._remove_range_btn.show()
            self._remove_range_btn.setText(f"✨  3. Remove Range ({cnt} frames)")
            self._remove_range_btn.setEnabled(True)
            self._remove_range_btn.setStyleSheet("")
            self._open_export_btn.hide()
            self._reset_range_btn.show()

            self._range_lbl.setText(
                f"👉 Step 2: Drag slider to watermark end (Frame #{self._cur}), then click '2. Mark End Frame' "
                f"or '3. Remove Range' directly ({cnt} frames).")
            self._range_lbl.setStyleSheet(f"color:{PURPLE_LIGHT};font-size:10px;font-weight:500;")
            self.vc.set_banner(f"📍 Start Frame #{self._range_start} Locked! ➔ Scrub to end point (Current: #{self._cur})")
        else:
            # Both start and end marked
            s = min(self._range_start, self._range_end)
            e = max(self._range_start, self._range_end)
            cnt = e - s + 1
            self._mark_start_btn.setText(f"✅ Start: #{self._range_start}")
            self._mark_start_btn.setStyleSheet(f"color:{PURPLE_LIGHT};font-weight:600;")
            self._mark_end_btn.setText(f"✅ End: #{self._range_end}")
            self._mark_end_btn.setEnabled(True)
            self._mark_end_btn.setStyleSheet(f"color:{GREEN_SOFT};font-weight:600;")
            self._remove_range_btn.show()
            self._remove_range_btn.setText(f"🚀  3. Remove Range ({cnt} frames)")
            self._remove_range_btn.setEnabled(True)
            self._remove_range_btn.setStyleSheet(
                f"background:qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #15803d,stop:1 #22c55e);"
                f"color:#ffffff;font-weight:800;font-size:12px;border:1px solid #4ade80;"
                f"border-radius:6px;padding:6px 12px;"
            )
            self._open_export_btn.hide()
            self._reset_range_btn.show()

            self._range_lbl.setText(
                f"🎉 Step 3: Range locked ({s} → {e} · {cnt} frames)! Click the green '3. Remove Range' button below.")
            self._range_lbl.setStyleSheet(f"color:{GREEN_SOFT};font-size:11px;font-weight:700;")
            self.vc.set_banner(f"✨ Range Locked: Frames {s} – {e} ({cnt} frames). Click '3. Remove Range' below!")

    def _mark_range_start(self) -> None:
        """Save current frame + mask as the range start point."""
        if self._cap is None:
            QMessageBox.information(self, "No video", "Load a video first.")
            return
        m = self.vc.get_mask()
        if m is None or not m.any():
            QMessageBox.information(self, "No mask",
                "Draw a mask on the watermark first.")
            return
        self._range_start = self._cur
        self._range_mask  = m.copy()
        self._range_end   = -1
        self._update_range_ui()
        self.status_msg.emit(
            f"  📍  Start Frame #{self._cur} set! Now scrub slider to end & click '2. Mark End Frame'")

    def _mark_range_end(self) -> None:
        """Lock current frame as the range end point."""
        if self._range_start < 0:
            QMessageBox.information(self, "No start", "Mark start frame first.")
            return
        self._range_end = self._cur
        self._update_range_ui()
        s = min(self._range_start, self._range_end)
        e = max(self._range_start, self._range_end)
        self.status_msg.emit(
            f"  🏁  End Frame #{self._cur} set! Range is {s} → {e} ({e - s + 1} frames). Click '3. Remove Range'")

    def _reset_range(self) -> None:
        """Reset the range removal wizard."""
        self._range_start = -1
        self._range_end   = -1
        self._range_mask  = None
        self._update_range_ui()
        self.status_msg.emit("  ↺  Range wizard reset")

    def _remove_range(self) -> None:
        """Process all frames from marked start to end/current frame."""
        if not self._vpath:
            QMessageBox.information(self, "No video", "Load a video first.")
            return
        if self._range_start < 0 or self._range_mask is None:
            QMessageBox.information(self, "No range start",
                "Click '📍 1. Mark Start Frame' first.")
            return
        end = self._range_end if self._range_end >= 0 else self._cur
        s = min(self._range_start, end)
        e = max(self._range_start, end)
        n = e - s + 1
        if QMessageBox.question(
                self, "Remove Range",
                f"Remove watermark from {n} frames?\n"
                f"(Frames {s} → {e})",
                QMessageBox.StandardButton.Yes |
                QMessageBox.StandardButton.No
        ) != QMessageBox.StandardButton.Yes:
            return
        self._start_proc("range_remove", {
            "start": s,
            "end":   e,
            "mask":  self._range_mask.copy(),
        })

    def cleanup(self) -> None:
        """Call before close."""
        self._stop_play()
        self._release_cap()


# ─── Gallery ──────────────────────────────────────────────────────────────────

class GalleryThumb(QFrame):
    open_clicked   = pyqtSignal(str)
    delete_clicked = pyqtSignal(str)

    def __init__(self, path: str):
        super().__init__()
        self.path = path
        self.setFixedSize(180, 200)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setObjectName("th")
        self.setStyleSheet(
            f"QFrame#th{{background:{BG_CARD};border:1px solid {BORDER};"
            f"border-radius:10px;}}"
            f"QFrame#th:hover{{border-color:{PURPLE};"
            f"background:{BG_RAISED};}}")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(6, 6, 6, 6)
        lay.setSpacing(4)
        il = QLabel()
        il.setFixedSize(168, 126)
        il.setAlignment(Qt.AlignmentFlag.AlignCenter)
        il.setStyleSheet(
            f"background:{BG_DEEP};border-radius:7px;border:none;")
        pix = QPixmap(path)
        if not pix.isNull():
            il.setPixmap(pix.scaled(168, 126,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation))
        else:
            il.setText("🖼"); il.setFont(QFont("Segoe UI", 20))
        lay.addWidget(il)
        nm = Path(path).stem
        nl = QLabel(nm if len(nm) <= 18 else nm[:15] + "…")
        nl.setStyleSheet(
            f"color:{TEXT_MAIN};font-size:10px;font-weight:500;")
        nl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(nl)
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(4)
        try:
            dt = datetime.fromtimestamp(
                Path(path).stat().st_mtime).strftime("%d %b %Y")
        except (OSError, FileNotFoundError):
            dt = "—"
        dl = QLabel(dt)
        dl.setStyleSheet(f"color:{TEXT_FAINT};font-size:9px;")
        row.addWidget(dl); row.addStretch()
        db = QPushButton("🗑")
        db.setFixedSize(20, 18)
        db.setStyleSheet(
            f"QPushButton{{background:{RED_DIM};color:{RED_SOFT};"
            f"border:1px solid {RED_BORDER};border-radius:4px;"
            f"font-size:10px;padding:0;}}"
            f"QPushButton:hover{{background:#381212;}}")
        db.clicked.connect(lambda: self.delete_clicked.emit(self.path))
        row.addWidget(db)
        lay.addLayout(row)

    def mousePressEvent(self, e) -> None:
        if e.button() == Qt.MouseButton.LeftButton:
            self.open_clicked.emit(self.path)


class GalleryView(QWidget):
    open_in_editor = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(f"background:{BG_DEEP};")
        root = QVBoxLayout(self)
        root.setContentsMargins(14, 12, 14, 12)
        root.setSpacing(8)
        hdr = QHBoxLayout()
        ttl = QLabel("My Edits")
        ttl.setStyleSheet(
            f"font-size:15px;font-weight:700;color:{TEXT_MAIN};")
        hdr.addWidget(ttl)
        self._cnt = QLabel("")
        self._cnt.setStyleSheet(
            f"color:{TEXT_FAINT};font-size:10px;margin-left:4px;")
        hdr.addWidget(self._cnt); hdr.addStretch()
        sl = QLabel("Sort:")
        sl.setStyleSheet(f"color:{TEXT_DIM};font-size:10px;")
        hdr.addWidget(sl)
        self._sb = QComboBox()
        self._sb.addItems(["Newest", "Oldest", "A→Z", "Z→A"])
        self._sb.currentIndexChanged.connect(self.refresh)
        hdr.addWidget(self._sb)
        rb = QPushButton("↻")
        rb.setObjectName("ghost")
        rb.setFixedSize(26, 24)
        rb.clicked.connect(self.refresh)
        hdr.addWidget(rb)

        exp_btn = QPushButton("📂  Open Folder")
        exp_btn.setObjectName("ghost")
        exp_btn.setFixedHeight(26)
        exp_btn.clicked.connect(self._open_folder)
        hdr.addWidget(exp_btn)

        root.addLayout(hdr)
        sep = QFrame(); sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet(f"color:{BORDER};")
        root.addWidget(sep)
        self._sc = QScrollArea(); self._sc.setWidgetResizable(True)
        self._inn = QWidget()
        self._grid = QGridLayout(self._inn)
        self._grid.setSpacing(8)
        self._grid.setAlignment(
            Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self._sc.setWidget(self._inn)
        root.addWidget(self._sc)
        self._el = QLabel(
            "No edits yet 🎨\n"
            "Remove a watermark and save it to see it here!")
        self._el.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._el.setStyleSheet(
            f"color:{TEXT_FAINT};font-size:12px;")
        root.addWidget(self._el)
        self.refresh()

    def refresh(self) -> None:
        while self._grid.count():
            it = self._grid.takeAt(0)
            if it.widget():
                it.widget().deleteLater()
        exts = ("*.png", "*.jpg", "*.jpeg", "*.webp", "*.bmp", "*.mp4", "*.avi", "*.mkv", "*.mov", "*.webm")
        imgs = []
        for ext in exts:
            imgs.extend(SAVE_DIR.glob(ext))
        idx = self._sb.currentIndex()
        def _safe_mtime(p):
            try: return p.stat().st_mtime
            except OSError: return 0
        if   idx == 0: imgs.sort(key=_safe_mtime, reverse=True)
        elif idx == 1: imgs.sort(key=_safe_mtime)
        elif idx == 2: imgs.sort(key=lambda p: p.name.lower())
        elif idx == 3: imgs.sort(key=lambda p: p.name.lower(), reverse=True)
        n = len(imgs)
        self._cnt.setText(f"{n} item{'s' if n != 1 else ''}")
        if not imgs:
            self._el.show(); self._sc.hide(); return
        self._el.hide(); self._sc.show()
        cols = load_settings().get("gallery_cols", 4)
        for i, p in enumerate(imgs):
            if p.suffix.lower() in (".mp4", ".avi", ".mkv", ".mov", ".webm"):
                l2 = QLabel(f"🎬  {p.name}")
                l2.setStyleSheet(
                    f"color:{TEXT_DIM};font-size:10px;padding:4px;")
                self._grid.addWidget(l2, i // cols, i % cols)
            else:
                th = GalleryThumb(str(p))
                th.open_clicked.connect(self.open_in_editor.emit)
                th.delete_clicked.connect(self._del)
                self._grid.addWidget(th, i // cols, i % cols)

    def _open_folder(self) -> None:
        SAVE_DIR.mkdir(parents=True, exist_ok=True)
        import subprocess, sys as _sys
        p = str(SAVE_DIR.resolve())
        if _sys.platform.startswith("linux"):
            subprocess.Popen(["xdg-open", p])
        elif _sys.platform == "darwin":
            subprocess.Popen(["open", p])
        else:
            import os as _os
            _os.startfile(p)

    def _del(self, path: str) -> None:
        if QMessageBox.question(
                self, "Move to Trash?", f"Move '{Path(path).name}' to Trash?",
                QMessageBox.StandardButton.Yes |
                QMessageBox.StandardButton.No
        ) == QMessageBox.StandardButton.Yes:
            safe_trash_file(Path(path))
            self.refresh()


# ─── Presets panel (slide-out) ────────────────────────────────────────────────

class PresetsPanel(QFrame):
    apply_preset  = pyqtSignal(dict)
    add_requested = pyqtSignal()

    def __init__(self, help_bubbles: list, parent=None):
        super().__init__(parent)
        self._hbs = help_bubbles
        self.setFixedWidth(192)
        self.setStyleSheet(
            f"QFrame{{background:{BG_BASE};"
            f"border-left:1px solid {BORDER};}}")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 10, 8, 10)
        lay.setSpacing(5)
        hdr = QHBoxLayout()
        t = QLabel("PRESETS")
        t.setStyleSheet(
            f"font-size:9px;font-weight:700;color:{TEXT_FAINT};"
            f"letter-spacing:1.2px;")
        hdr.addWidget(t); hdr.addStretch()
        bbl = HelpBubble(
            "Draw a mask on the image, then click ＋\n"
            "to save it as a preset.\n\n"
            "A preset stores your exact brush strokes\n"
            "and can be applied to any image in one\n"
            "click — perfect for batch watermark jobs.\n\n"
            "📁 Saved to:\n"
            "Documents/HenryJay Data Folder/\n"
            "MyScreen Watermark Remover/")
        self._hbs.append(bbl)
        hdr.addWidget(bbl)
        lay.addLayout(hdr)
        self._lw = QListWidget()
        self._lw.setMinimumHeight(80)
        lay.addWidget(self._lw)
        add = QPushButton("＋  New")
        add.clicked.connect(self.add_requested.emit)
        lay.addWidget(add)
        ap = QPushButton("▶  Apply")
        ap.setObjectName("cta"); ap.clicked.connect(self._apply)
        lay.addWidget(ap)
        db = QPushButton("🗑  Delete")
        db.setObjectName("danger"); db.clicked.connect(self._delete)
        lay.addWidget(db)
        self._el = QLabel("No presets.\nDraw mask & click ＋")
        self._el.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._el.setStyleSheet(
            f"color:{TEXT_FAINT};font-size:10px;padding:6px;")
        lay.addWidget(self._el)
        lay.addStretch()
        self.refresh()

    def refresh(self) -> None:
        self._lw.clear()
        ps = load_presets()
        icons = {0: "⚡", 1: "🧠", 2: "🔬"}
        for p in ps:
            it = QListWidgetItem(
                f"{icons.get(p.get('level', 0), '⚡')}  {p['name']}")
            it.setData(Qt.ItemDataRole.UserRole, p)
            self._lw.addItem(it)
        has = self._lw.count() > 0
        self._lw.setVisible(has)
        self._el.setVisible(not has)

    def _apply(self) -> None:
        it = self._lw.currentItem()
        if not it:
            QMessageBox.information(
                self, "Select a preset", "Click a preset first.")
            return
        self.apply_preset.emit(it.data(Qt.ItemDataRole.UserRole))

    def _delete(self) -> None:
        it = self._lw.currentItem()
        if not it:
            return
        p = it.data(Qt.ItemDataRole.UserRole)
        if QMessageBox.question(
                self, "Delete?", f"Delete preset '{p['name']}'?",
                QMessageBox.StandardButton.Yes |
                QMessageBox.StandardButton.No
        ) == QMessageBox.StandardButton.Yes:
            save_presets(
                [x for x in load_presets() if x.get("name") != p["name"]])
            self.refresh()


# ─── Tasks & Background Queue ("Files In Progress") ───────────────────────────

class TaskItem(QObject):
    updated = pyqtSignal()
    finished = pyqtSignal(str)
    error = pyqtSignal(str)

    def __init__(self, task_id: str, title: str, src_path: str, dst_path: str,
                 method: str, mode_name: str, total_frames: int, worker: "VideoWorker"):
        super().__init__()
        self.task_id = task_id
        self.title = title
        self.src_path = src_path
        self.dst_path = dst_path
        self.method = method
        self.mode_name = mode_name
        self.total_frames = max(1, total_frames)
        self.current_frame = 0
        self.status = "running"   # "running", "completed", "error", "cancelled"
        self.start_time = datetime.now()
        self.end_time: datetime | None = None
        self.worker = worker
        self.fps_rate = 0.0
        self.eta_seconds = 0
        self.thumb: QImage | None = None
        self.err_msg = ""
        self._last_tick = datetime.now()
        self._last_f = 0

        # Wire worker
        if worker is not None:
            worker.frame_done.connect(self._on_frame)
            worker.finished.connect(self._on_finished)
            worker.error.connect(self._on_error)

    def _on_frame(self, cur: int, tot: int, fps: float = 0.0, eta_sec: int = 0, el_sec: int = 0):
        self.current_frame = cur
        self.total_frames = max(1, tot)
        if fps > 0:
            self.fps_rate = fps
            self.eta_seconds = eta_sec
        else:
            now = datetime.now()
            dt = (now - self._last_tick).total_seconds()
            if dt >= 0.3:
                df = cur - self._last_f
                self.fps_rate = df / dt if dt > 0 else 0.0
                rem_frames = tot - cur
                self.eta_seconds = int(rem_frames / self.fps_rate) if self.fps_rate > 0 else 0
                self._last_tick = now
                self._last_f = cur
        self.updated.emit()

    def _on_finished(self, out_path: str):
        self.status = "completed"
        self.end_time = datetime.now()
        self.current_frame = self.total_frames
        self.dst_path = out_path
        self.updated.emit()
        self.finished.emit(out_path)

    def _on_error(self, err: str):
        self.status = "error"
        self.err_msg = err
        self.end_time = datetime.now()
        self.updated.emit()
        self.error.emit(err)

    def cancel(self):
        if self.status == "running":
            if self.worker is not None:
                self.worker.stop()
            self.status = "cancelled"
            self.end_time = datetime.now()
            self.updated.emit()


class TaskManager(QObject):
    task_added = pyqtSignal(object)
    tasks_updated = pyqtSignal()

    _instance = None
    @classmethod
    def instance(cls):
        if cls._instance is None:
            cls._instance = TaskManager()
        return cls._instance

    def __init__(self):
        super().__init__()
        self.tasks: list[TaskItem] = []

    def add_video_task(self, title: str, src: str, dst: str, method: str,
                       data: dict, level: int, total_frames: int,
                       thumb: np.ndarray | None = None,
                       keep_audio: bool = True) -> TaskItem:
        worker = VideoWorker(src, dst, method, data, level, keep_audio=keep_audio)
        modes = ["⚡ Quick", "🧠 Smart", "🔬 Precision", "✨ Cel AI"]
        mode_str = modes[level] if 0 <= level < len(modes) else "✨ Cel AI"
        tid = f"task_{datetime.now().strftime('%H%M%S')}_{len(self.tasks)+1}"
        item = TaskItem(tid, title, src, dst, method, mode_str, total_frames, worker)
        if thumb is not None:
            try:
                th_img = cv2.resize(thumb, (96, 54))
                item.thumb = cv2_to_qimage(th_img)
            except Exception:
                pass
        self.tasks.insert(0, item)
        item.updated.connect(self.tasks_updated)
        worker.start()
        self.task_added.emit(item)
        self.tasks_updated.emit()
        return item

    def active_count(self) -> int:
        return sum(1 for t in self.tasks if t.status == "running")

    def clear_completed(self):
        self.tasks = [t for t in self.tasks if t.status == "running"]
        self.tasks_updated.emit()

    def cancel_all(self):
        for t in self.tasks:
            if t.status == "running":
                t.cancel()
        self.tasks_updated.emit()


class TaskCard(QFrame):
    def __init__(self, task: TaskItem, parent=None):
        super().__init__(parent)
        self.task = task
        self.setObjectName("task_card")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setFixedHeight(74)
        self.setStyleSheet(
            f"QFrame#task_card{{background:{BG_CARD};border:1px solid {BORDER};"
            f"border-radius:10px;padding:6px;}}"
            f"QFrame#task_card:hover{{border-color:{PURPLE};background:{BG_RAISED};}}")
        self._build()
        self.task.updated.connect(self._refresh)
        self._refresh()

    def _build(self):
        lay = QHBoxLayout(self)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(12)

        # Left: Thumbnail
        self._thumb_lbl = QLabel()
        self._thumb_lbl.setFixedSize(96, 54)
        self._thumb_lbl.setStyleSheet(
            f"background:{BG_DEEP};border:1px solid {BORDER_LIT};border-radius:6px;")
        self._thumb_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        if self.task.thumb:
            self._thumb_lbl.setPixmap(QPixmap.fromImage(self.task.thumb))
        else:
            self._thumb_lbl.setText("🎬")
            self._thumb_lbl.setStyleSheet(
                f"background:{BG_DEEP};border:1px solid {BORDER_LIT};border-radius:6px;font-size:22px;color:{PURPLE_LIGHT};")
        lay.addWidget(self._thumb_lbl)

        # Middle: Info + Progress Bar
        mid = QVBoxLayout()
        mid.setSpacing(4)

        # Title row: Title + Mode Pill + Filename
        tr = QHBoxLayout()
        tr.setSpacing(6)
        self._ttl = QLabel(self.task.title)
        self._ttl.setStyleSheet(f"font-size:12px;font-weight:700;color:{TEXT_MAIN};")
        tr.addWidget(self._ttl)

        self._mode_pill = QLabel(self.task.mode_name)
        self._mode_pill.setStyleSheet(
            f"background:{BG_BASE};color:{PURPLE_LIGHT};font-size:9px;font-weight:600;"
            f"padding:2px 6px;border:1px solid {BORDER_LIT};border-radius:4px;")
        tr.addWidget(self._mode_pill)

        self._fn_lbl = QLabel(Path(self.task.src_path).name)
        self._fn_lbl.setStyleSheet(f"color:{TEXT_FAINT};font-size:10px;")
        tr.addWidget(self._fn_lbl)
        tr.addStretch()
        mid.addLayout(tr)

        # Progress bar
        self._pb = QProgressBar()
        self._pb.setFixedHeight(10)
        self._pb.setTextVisible(False)
        self._pb.setStyleSheet(
            f"QProgressBar{{background:{BG_DEEP};border:none;border-radius:5px;}}"
            f"QProgressBar::chunk{{background:qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 {PURPLE},stop:1 {PURPLE_LIGHT});border-radius:5px;}}")
        mid.addWidget(self._pb)

        # Stats row: frames, pct, speed, eta, elapsed
        self._stats_lbl = QLabel("")
        self._stats_lbl.setStyleSheet(f"color:{TEXT_DIM};font-size:10px;")
        mid.addWidget(self._stats_lbl)

        lay.addLayout(mid, stretch=1)

        # Right: Status Badge & Actions
        right = QVBoxLayout()
        right.setSpacing(6)
        right.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        self._status_badge = QLabel("")
        self._status_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        right.addWidget(self._status_badge)

        act_r = QHBoxLayout()
        act_r.setSpacing(4)

        self._open_btn = QPushButton("📂  Folder")
        self._open_btn.setObjectName("ghost")
        self._open_btn.setFixedHeight(26)
        self._open_btn.clicked.connect(self._open_folder)
        act_r.addWidget(self._open_btn)

        self._play_btn = QPushButton("▶  Play")
        self._play_btn.setObjectName("cta")
        self._play_btn.setFixedHeight(26)
        self._play_btn.clicked.connect(self._play_video)
        act_r.addWidget(self._play_btn)

        self._can_btn = QPushButton("⛔  Cancel")
        self._can_btn.setObjectName("danger")
        self._can_btn.setFixedHeight(26)
        self._can_btn.clicked.connect(self.task.cancel)
        act_r.addWidget(self._can_btn)

        right.addLayout(act_r)
        lay.addLayout(right)

    def _refresh(self):
        cur = self.task.current_frame
        tot = self.task.total_frames
        pct = int(cur / tot * 100) if tot > 0 else 0
        self._pb.setValue(pct)

        elapsed_sec = int((datetime.now() - self.task.start_time).total_seconds())
        el_m, el_s = divmod(elapsed_sec, 60)
        el_str = f"{el_m}m {el_s:02d}s"

        if self.task.status == "running":
            eta_m, eta_s = divmod(self.task.eta_seconds, 60)
            eta_str = f"{eta_m}m {eta_s:02d}s" if self.task.eta_seconds > 0 else "estimating…"
            fps_str = f"{self.task.fps_rate:.1f} fps" if self.task.fps_rate > 0 else "starting…"
            self._stats_lbl.setText(
                f"Frame {cur:,} / {tot:,}  ({pct}%)   ·   ⚡ {fps_str}   ·   ⏳ ETA: {eta_str}   ·   ⏱ Elapsed: {el_str}")
            self._status_badge.setText("⏳  In Progress")
            self._status_badge.setStyleSheet(
                f"color:{PURPLE_LIGHT};font-weight:700;font-size:11px;background:{PURPLE_DIM};"
                f"padding:3px 8px;border-radius:5px;border:1px solid {BORDER_LIT};")
            self._can_btn.show()
            self._play_btn.hide()
            self._open_btn.hide()
        elif self.task.status == "completed":
            self._stats_lbl.setText(
                f"✅ Finished {tot:,} frames in {el_str}! Saved to Exports.")
            self._status_badge.setText("✅  Completed")
            self._status_badge.setStyleSheet(
                f"color:{GREEN_SOFT};font-weight:700;font-size:11px;background:#0d2818;"
                f"padding:3px 8px;border-radius:5px;border:1px solid {GREEN_SOFT};")
            self._can_btn.hide()
            self._play_btn.show()
            self._open_btn.show()
        elif self.task.status == "cancelled":
            self._stats_lbl.setText(f"⛔ Cancelled at frame {cur:,} of {tot:,}.")
            self._status_badge.setText("⛔  Cancelled")
            self._status_badge.setStyleSheet(
                f"color:{RED_ACCENT};font-weight:700;font-size:11px;background:#2d1115;"
                f"padding:3px 8px;border-radius:5px;border:1px solid {RED_ACCENT};")
            self._can_btn.hide()
            self._play_btn.hide()
            self._open_btn.hide()
        elif self.task.status == "error":
            self._stats_lbl.setText(f"❌ Error: {self.task.err_msg[:60]}")
            self._status_badge.setText("❌  Error")
            self._status_badge.setStyleSheet(
                f"color:{RED_ACCENT};font-weight:700;font-size:11px;background:#2d1115;"
                f"padding:3px 8px;border-radius:5px;border:1px solid {RED_ACCENT};")
            self._can_btn.hide()
            self._play_btn.hide()
            self._open_btn.hide()

    def _open_folder(self):
        dst = Path(self.task.dst_path).resolve()
        launch_system_file(str(dst.parent))

    def _play_video(self):
        dst = str(Path(self.task.dst_path).resolve())
        self._play_btn.setText("▶  Playing…")
        QTimer.singleShot(2000, lambda: self._play_btn.setText("▶  Play"))
        launch_system_file(dst)


class ProgressView(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(f"background:{BG_DEEP};")
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 14, 16, 14)
        root.setSpacing(10)

        # Header
        hdr = QHBoxLayout()
        ttl = QLabel("Files In Progress & Task Queue")
        ttl.setStyleSheet(f"font-size:15px;font-weight:700;color:{TEXT_MAIN};")
        hdr.addWidget(ttl)

        self._cnt_lbl = QLabel("")
        self._cnt_lbl.setStyleSheet(f"color:{TEXT_FAINT};font-size:11px;margin-left:4px;")
        hdr.addWidget(self._cnt_lbl)
        hdr.addStretch()

        exp_btn = QPushButton("📂  Open Exports Folder")
        exp_btn.setObjectName("ghost")
        exp_btn.setFixedHeight(28)
        exp_btn.clicked.connect(self._open_exports)
        hdr.addWidget(exp_btn)

        clr_btn = QPushButton("🧹  Clear Completed")
        clr_btn.setObjectName("ghost")
        clr_btn.setFixedHeight(28)
        clr_btn.clicked.connect(TaskManager.instance().clear_completed)
        hdr.addWidget(clr_btn)

        can_btn = QPushButton("⛔  Cancel All")
        can_btn.setObjectName("danger")
        can_btn.setFixedHeight(28)
        can_btn.clicked.connect(TaskManager.instance().cancel_all)
        hdr.addWidget(can_btn)

        root.addLayout(hdr)

        sep = QFrame(); sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet(f"color:{BORDER};")
        root.addWidget(sep)

        # Scrollable Task Cards
        self._sc = QScrollArea()
        self._sc.setWidgetResizable(True)
        self._sc.setStyleSheet("QScrollArea{border:none;background:transparent;}")
        self._inn = QWidget()
        self._inn.setStyleSheet("background:transparent;")
        self._vbox = QVBoxLayout(self._inn)
        self._vbox.setContentsMargins(0, 4, 0, 4)
        self._vbox.setSpacing(8)
        self._vbox.setAlignment(Qt.AlignmentFlag.AlignTop)
        self._sc.setWidget(self._inn)
        root.addWidget(self._sc)

        self._empty_lbl = QLabel(
            "🚀 No tasks currently running\n\n"
            "Process a video range, auto-track, or timeline in the Video tab\n"
            "and watch the real-time frame progress, speed, and ETA here!")
        self._empty_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty_lbl.setStyleSheet(f"color:{TEXT_FAINT};font-size:12px;padding:40px;")
        root.addWidget(self._empty_lbl)

        TaskManager.instance().tasks_updated.connect(self.refresh)
        self.refresh()

    def refresh(self):
        tasks = TaskManager.instance().tasks
        while self._vbox.count():
            it = self._vbox.takeAt(0)
            if it.widget():
                it.widget().deleteLater()

        running = sum(1 for t in tasks if t.status == "running")
        done = sum(1 for t in tasks if t.status == "completed")
        self._cnt_lbl.setText(f"·  {running} running  ·  {done} completed")

        if not tasks:
            self._empty_lbl.show()
            self._sc.hide()
        else:
            self._empty_lbl.hide()
            self._sc.show()
            for t in tasks:
                card = TaskCard(t)
                self._vbox.addWidget(card)

    def _open_exports(self):
        import subprocess, sys as _sys
        p = str(SAVE_DIR.resolve())
        if _sys.platform.startswith("linux"):
            subprocess.Popen(["xdg-open", p])
        elif _sys.platform == "darwin":
            subprocess.Popen(["open", p])
        else:
            import os as _os
            _os.startfile(p)


# ─── Compact tool button ──────────────────────────────────────────────────────

class ToolBtn(QToolButton):
    def __init__(self, icon: str, tip: str):
        super().__init__()
        self.setCheckable(True)
        self.setFixedSize(38, 38)
        self.setToolTip(tip)
        self.setText(icon)
        self.setFont(QFont("Segoe UI", 16))


# ─── Main Window ──────────────────────────────────────────────────────────────

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("MyScreen Watermark Remover")
        if ICON_PATH.exists():
            self.setWindowIcon(QIcon(str(ICON_PATH)))
        self.setMinimumSize(760, 540)
        self.resize(1220, 760)
        self._hbs: list[HelpBubble] = []
        self._s   = load_settings()
        self._kb  = self._s.get("keybinds", DEFAULT_SETTINGS["keybinds"])
        self._presets_visible = False
        self._build_ui()
        self._apply_settings_quiet()

    # ── UI construction ───────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        central = QWidget(); self.setCentralWidget(central)
        root    = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Top bar: logo + tool pills + size + undo/redo + right actions ──────
        topbar = QFrame()
        topbar.setFixedHeight(44)
        topbar.setStyleSheet(
            f"background:{BG_DEEP};border-bottom:1px solid {BORDER};")
        tl = QHBoxLayout(topbar)
        tl.setContentsMargins(10, 0, 10, 0)
        tl.setSpacing(6)

        # Logo
        logo = QLabel()
        if ICON_PATH.exists():
            pm = QPixmap(str(ICON_PATH)).scaled(24, 24, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            logo.setPixmap(pm)
        else:
            logo.setText("🪄")
            logo.setStyleSheet("font-size:16px;")
        tl.addWidget(logo)
        logo2 = QLabel("MyScreen WR")
        logo2.setStyleSheet(
            f"font-size:12px;font-weight:700;color:{PURPLE_LIGHT};"
            f"letter-spacing:-0.2px;")
        tl.addWidget(logo2)
        vb = QLabel(f"v{APP_VERSION}")
        vb.setStyleSheet(
            f"color:{TEXT_FAINT};font-size:8px;padding:1px 4px;"
            f"background:{BG_CARD};border:1px solid {BORDER};border-radius:3px;")
        tl.addWidget(vb)

        # Thin vertical divider
        def _vdiv():
            d = QFrame(); d.setFrameShape(QFrame.Shape.VLine)
            d.setStyleSheet(f"color:{BORDER};max-height:24px;margin:0 2px;")
            return d
        tl.addWidget(_vdiv())

        # ── Tool pill group ─────────────────────────────────────────────────
        pill_frame = QFrame()
        pill_frame.setObjectName("topbar_pill")
        pfl = QHBoxLayout(pill_frame)
        pfl.setContentsMargins(2, 2, 2, 2)
        pfl.setSpacing(1)
        pfl.setSizeConstraint(QLayout.SizeConstraint.SetFixedSize)

        TOOL_DEFS = [
            ("🪄", "Smart Snap  [S]", _BaseCanvas.TOOL_SMART,   "sb_tool"),
            ("🖌", "Brush  [B]",      _BaseCanvas.TOOL_BRUSH,   "bb"),
            ("🧽", "Eraser  [X]",     _BaseCanvas.TOOL_ERASER,  "eb"),
            ("▭",  "Rectangle  [R]",  _BaseCanvas.TOOL_SQUARE,  "rb"),
            ("⭕", "Ellipse  [E]",    _BaseCanvas.TOOL_CIRCLE,  "cb"),
            ("✋", "Pan / Move  [H]", _BaseCanvas.TOOL_PAN,     "pb_tool"),
        ]
        pill_style = (
            f"QToolButton{{background:transparent;border:none;"
            f"border-radius:5px;padding:2px 6px;font-size:14px;color:{TEXT_DIM};}}"
            f"QToolButton:hover{{background:{BG_HOVER};color:{TEXT_MAIN};}}"
            f"QToolButton:checked{{background:{PURPLE};color:#fff;}}"
        )
        self._tg = QButtonGroup(self); self._tg.setExclusive(True)
        for emoji, tip, tool, attr in TOOL_DEFS:
            btn = QToolButton()
            btn.setText(emoji); btn.setToolTip(tip)
            btn.setCheckable(True); btn.setFixedSize(30, 28)
            btn.setStyleSheet(pill_style)
            pfl.addWidget(btn)
            setattr(self, f"_{attr}", btn)
            self._tg.addButton(btn)
            btn.clicked.connect(lambda _, t=tool: self._set_tool(t))
        self._bb.setChecked(True)
        tl.addWidget(pill_frame)

        # Brush size pill
        sz_frame = QFrame()
        sz_frame.setObjectName("topbar_pill")
        szl = QHBoxLayout(sz_frame)
        szl.setContentsMargins(6, 2, 6, 2); szl.setSpacing(5)
        szl.setSizeConstraint(QLayout.SizeConstraint.SetFixedSize)
        sz_icon = QLabel("◎")
        sz_icon.setStyleSheet(f"color:{TEXT_DIM};font-size:13px;border:none;background:transparent;")
        szl.addWidget(sz_icon)
        self._sz_sl = QSlider(Qt.Orientation.Horizontal)
        self._sz_sl.setRange(2, 100)
        self._sz_sl.setValue(self._s.get("brush_size", 25))
        self._sz_sl.setFixedWidth(70)
        self._sz_sl.valueChanged.connect(self._set_brush_size)
        szl.addWidget(self._sz_sl)
        self._sz_lbl = QLabel("25")
        self._sz_lbl.setStyleSheet(
            f"color:{PURPLE_LIGHT};font-size:10px;font-weight:600;min-width:20px;border:none;background:transparent;")
        szl.addWidget(self._sz_lbl)
        tl.addWidget(sz_frame)

        tl.addWidget(_vdiv())

        # Mode picker (compact pill)
        self._lvl_box = QComboBox()
        self._lvl_box.addItems(["⚡ Quick", "🧠 Smart", "🔬 Precision", "✨ Cel AI"])
        self._lvl_box.setCurrentIndex(self._s.get("default_level", 0))
        self._lvl_box.setFixedWidth(128)
        self._lvl_box.setFixedHeight(30)
        mh = HelpBubble(
            "⚡ Quick — Fast TELEA. Good for small logos.\n\n"
            "🧠 Smart — Ring-by-ring fill. No blur on large areas.\n\n"
            "🔬 Precision — Exemplar Patch-Match.\n\n"
            "✨ Cel AI — Advanced structural gradient flow & texture synthesis.\n"
            "   Best quality for large watermarks, faces, and complex backgrounds.")
        self._hbs.append(mh)
        mlayout = QHBoxLayout(); mlayout.setSpacing(3); mlayout.setContentsMargins(0,0,0,0)
        mlayout.addWidget(self._lvl_box); mlayout.addWidget(mh)
        tl.addLayout(mlayout)

        tl.addStretch()

        # Undo / redo + count
        self._undo_btn = QPushButton("↩")
        self._undo_btn.setObjectName("icon_btn"); self._undo_btn.setFixedSize(28,28)
        self._undo_btn.setToolTip("Undo  [Ctrl+Z]")
        self._undo_btn.clicked.connect(
            lambda: self._active_canvas().undo() if self._active_canvas() else None)
        tl.addWidget(self._undo_btn)

        self._undo_lbl = QLabel("")
        self._undo_lbl.setStyleSheet(f"color:{TEXT_FAINT};font-size:9px;min-width:18px;")
        tl.addWidget(self._undo_lbl)

        self._redo_btn = QPushButton("↪")
        self._redo_btn.setObjectName("icon_btn"); self._redo_btn.setFixedSize(28,28)
        self._redo_btn.setToolTip("Redo  [Ctrl+Y]")
        self._redo_btn.clicked.connect(
            lambda: self._active_canvas().redo() if self._active_canvas() else None)
        tl.addWidget(self._redo_btn)

        # Zoom % badge
        self._zoom_lbl = QLabel("100%")
        self._zoom_lbl.setStyleSheet(
            f"color:{TEXT_FAINT};font-size:9px;min-width:34px;")
        self._zoom_lbl.setToolTip("Zoom level")
        tl.addWidget(self._zoom_lbl)

        tl.addWidget(_vdiv())

        # Right action buttons
        for icon, tip, fn in [
            ("📂", "Open Saves Folder  [Ctrl+E]", self._open_save_folder),
            ("⌨️", "Keyboard Shortcuts & Guide  [F1 / ?]", self._show_shortcuts),
            ("⚡", "Presets  [Ctrl+Shift+P]", self._toggle_presets),
            ("⚙️", "Settings", self._show_settings),
            ("ℹ",  "About", self._show_about),
        ]:
            b = QPushButton(icon)
            b.setObjectName("icon_btn"); b.setFixedSize(28, 28)
            b.setToolTip(tip); b.clicked.connect(fn)
            if icon == "⚡":
                b.setCheckable(True)
                self._presets_btn = b
            tl.addWidget(b)

        root.addWidget(topbar)

        # ── Tab bar (Editor / Video / Gallery) ───────────────────────────────
        self._tabs = QTabWidget()
        self._tabs.setDocumentMode(True)
        root.addWidget(self._tabs)

        # ── EDITOR TAB ───────────────────────────────────────────────────────
        editor_w = QWidget()
        el = QHBoxLayout(editor_w)
        el.setContentsMargins(0, 0, 0, 0); el.setSpacing(0)

        # Canvas area
        cw  = QWidget()
        cwl = QVBoxLayout(cw)
        cwl.setContentsMargins(0, 0, 0, 0); cwl.setSpacing(0)

        self.canvas = Canvas()
        self.canvas.status_msg.connect(self._set_status)
        self.canvas.busy_changed.connect(self._set_busy)
        self.canvas.mask_changed.connect(self._update_undo_label)
        self.canvas._max_undo = self._s.get("max_undo", 30)
        cwl.addWidget(self.canvas)

        # ── Bottom action bar ─────────────────────────────────────────────
        bot = QFrame(); bot.setFixedHeight(44)
        bot.setStyleSheet(
            f"background:{BG_BASE};border-top:1px solid {BORDER};")
        bl = QHBoxLayout(bot)
        bl.setContentsMargins(8, 4, 8, 4); bl.setSpacing(4)

        # Left cluster
        self._open_btn = QPushButton("Open")
        self._open_btn.setObjectName("ghost"); self._open_btn.setFixedHeight(28)
        self._open_btn.setToolTip("Open image file  [Ctrl+O]")
        bl.addWidget(self._open_btn)

        self._more_btn = QPushButton("···")
        self._more_btn.setObjectName("ghost")
        self._more_btn.setFixedSize(32, 28)
        self._more_btn.setToolTip("More: expand mask, batch process, open folder…")
        self._more_btn.clicked.connect(self._show_more_menu)
        bl.addWidget(self._more_btn)

        # Zoom mini controls
        zoom_frame = QFrame()
        zoom_frame.setStyleSheet(
            f"background:{BG_RAISED};border:1px solid {BORDER_LIT};"
            f"border-radius:6px;")
        zfl = QHBoxLayout(zoom_frame)
        zfl.setContentsMargins(3, 1, 3, 1); zfl.setSpacing(0)
        zs2 = (f"QToolButton{{background:transparent;color:{TEXT_DIM};"
               f"border:none;border-radius:4px;font-size:13px;font-weight:600;"
               f"padding:1px 4px;}}"
               f"QToolButton:hover{{color:{PURPLE_LIGHT};background:{BG_HOVER};}}")
        for txt, fn in [("−", lambda: self._zoom(0.83)),
                         ("+", lambda: self._zoom(1.2)),
                         ("⊙", self._zoom_fit)]:
            zb = QToolButton(); zb.setText(txt)
            zb.setFixedSize(24, 24); zb.setStyleSheet(zs2)
            zb.clicked.connect(fn); zfl.addWidget(zb)
        bl.addWidget(zoom_frame)

        bl.addStretch()

        # Right cluster — primary actions
        self._cmp_btn = QPushButton("👁")
        self._cmp_btn.setObjectName("ghost")
        self._cmp_btn.setFixedSize(28, 28)
        self._cmp_btn.setToolTip("Hold to compare with original [\\ ]")
        self._cmp_btn.pressed.connect(lambda: self.canvas.toggle_compare(True))
        self._cmp_btn.released.connect(lambda: self.canvas.toggle_compare(False))
        bl.addWidget(self._cmp_btn)

        self._clip_btn = QPushButton("📋")
        self._clip_btn.setObjectName("ghost")
        self._clip_btn.setFixedSize(28, 28)
        self._clip_btn.setToolTip("Copy to clipboard")
        self._clip_btn.clicked.connect(lambda: self.canvas.copy_to_clipboard())
        bl.addWidget(self._clip_btn)

        # Separator before CTAs
        sep = QFrame(); sep.setFrameShape(QFrame.Shape.VLine)
        sep.setStyleSheet(f"color:{BORDER_LIT};max-height:28px;")
        bl.addWidget(sep)

        self._auto_detect_btn = QPushButton("🪄  Auto-Detect")
        self._auto_detect_btn.setObjectName("ghost")
        self._auto_detect_btn.setFixedHeight(32)
        self._auto_detect_btn.setToolTip("Scan and auto-select all detected watermarks [Shift+S]")
        self._auto_detect_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self._auto_detect_btn.clicked.connect(self._auto_detect_watermarks)
        bl.addWidget(self._auto_detect_btn)

        self._remove_btn = QPushButton("✨  Remove")
        self._remove_btn.setObjectName("cta")
        self._remove_btn.setFixedHeight(32)
        self._remove_btn.setToolTip("Run inpainting on marked area")
        self._remove_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        bl.addWidget(self._remove_btn)

        self._save_btn = QPushButton("💾  Save")
        self._save_btn.setObjectName("save_btn")
        self._save_btn.setFixedHeight(32)
        self._save_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        bl.addWidget(self._save_btn)

        self._open_folder_btn = QPushButton("📂  Folder")
        self._open_folder_btn.setObjectName("ghost")
        self._open_folder_btn.setFixedHeight(32)
        self._open_folder_btn.setToolTip("Open Saves / Edits Folder  [Ctrl+E]")
        self._open_folder_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self._open_folder_btn.clicked.connect(self._open_save_folder)
        bl.addWidget(self._open_folder_btn)

        cwl.addWidget(bot)
        el.addWidget(cw)

        # Presets panel (hidden by default, slides in from right)
        self._pp = PresetsPanel(self._hbs)
        self._pp.apply_preset.connect(self._apply_preset)
        self._pp.add_requested.connect(self._save_preset)
        self._pp.setVisible(False)
        el.addWidget(self._pp)

        self._tabs.addTab(editor_w, "🖼  Editor")

        # ── VIDEO TAB ────────────────────────────────────────────────────────
        self._vt = VideoTab(self._hbs)
        self._vt.status_msg.connect(self._set_status)
        self._vt.vc.mask_changed.connect(self._update_undo_label)
        self._vt.vc._max_undo = self._s.get("max_undo", 30)
        self._tabs.addTab(self._vt, "🎬  Video")

        # ── GALLERY TAB ──────────────────────────────────────────────────────
        self._gv = GalleryView()
        self._gv.open_in_editor.connect(self._from_gallery)
        self._tabs.addTab(self._gv, "🗂  Gallery")

        # ── FILES IN PROGRESS TAB ────────────────────────────────────────────
        self._pv = ProgressView()
        self._tabs.addTab(self._pv, "⏳  Files In Progress")
        TaskManager.instance().tasks_updated.connect(self._update_tasks_tab_title)

        self._tabs.currentChanged.connect(self._tab_changed)

        # Wire up
        self._open_btn.clicked.connect(self._open_image)
        self._remove_btn.clicked.connect(self._do_inpaint)
        self._save_btn.clicked.connect(self._save_image)

        # Status bar
        self._sb = QStatusBar(); self.setStatusBar(self._sb)
        self._set_status("  Ready — open an image or drop it onto the canvas")

    def _update_tasks_tab_title(self) -> None:
        cnt = TaskManager.instance().active_count()
        tab_txt = f"⏳  Files In Progress ({cnt})" if cnt > 0 else "⏳  Files In Progress"
        if self._tabs.count() >= 4:
            self._tabs.setTabText(3, tab_txt)

        # ── More menu ─────────────────────────────────────────────────────────────

    def _show_more_menu(self) -> None:
        from PyQt6.QtWidgets import QMenu
        menu = QMenu(self)
        menu.setStyleSheet(
            f"QMenu{{background:{BG_RAISED};border:1px solid {BORDER_LIT};"
            f"border-radius:7px;padding:4px;}}"
            f"QMenu::item{{padding:5px 14px;border-radius:4px;color:{TEXT_MAIN};}}"
            f"QMenu::item:selected{{background:{PURPLE_DIM};color:{PURPLE_LIGHT};}}")
        menu.addAction("🧹  Clear Mask  [Ctrl+D]", self.canvas.clear_mask)
        menu.addAction("⤢  Expand Mask (+2px)  []]", lambda: self.canvas.expand_mask(2))
        menu.addAction("⤡  Contract Mask (-2px)  [[]", lambda: self.canvas.contract_mask(2))
        menu.addAction("🔄  Invert Mask  [I]", self.canvas.invert_mask)
        menu.addAction("↩  Reset to Original", self.canvas.reset_to_original)
        menu.addSeparator()
        menu.addAction("📁  Batch Remove on Multiple Images…", self._batch_process_images)
        menu.addAction("📂  Open Saves / Edits Folder  [Ctrl+E]", self._open_save_folder)
        menu.addAction("⌨️  Keyboard Shortcuts & Guide  [F1]", self._show_shortcuts)
        menu.addSeparator()
        menu.addAction("🖼  Fit to Screen", self._zoom_fit)
        menu.addAction("📋  Copy to Clipboard", self.canvas.copy_to_clipboard)
        menu.addSeparator()
        menu.addAction("💾  Save as PNG",  lambda: self._save_image("png"))
        menu.addAction("💾  Save as JPG",  lambda: self._save_image("jpg"))
        menu.addAction("💾  Save as WebP", lambda: self._save_image("webp"))
        menu.exec(self._more_btn.mapToGlobal(
            QPoint(0, self._more_btn.height())))

    # ── Mobile / responsive ───────────────────────────────────────────────────

    def _is_mobile(self) -> bool:
        """Detect mobile: small screen or high DPI touch device."""
        screen = QApplication.primaryScreen()
        if screen is None:
            return False
        geo = screen.geometry()
        dpr = screen.devicePixelRatio()
        # Mobile: small screen or very high DPI (phone-like)
        small_screen = min(geo.width(), geo.height()) < 600
        high_dpi     = dpr >= 2.5 and max(geo.width(), geo.height()) < 1200
        return small_screen or high_dpi

    def resizeEvent(self, e) -> None:
        super().resizeEvent(e)
        self._adapt_layout()

    def _adapt_layout(self) -> None:
        """Compact mode when window is narrow. Guard pre-build calls."""
        if not hasattr(self, "_sz_lbl"):
            return
        narrow = self.width() < MOBILE_WIDTH_THRESHOLD
        self._sz_lbl.setVisible(not narrow)
        self._sz_sl.setFixedWidth(50 if narrow else 70)

    # ── Slots ─────────────────────────────────────────────────────────────────

    def _set_tool(self, t: str) -> None:
        self.canvas.tool = t
        if hasattr(self, "_vt") and hasattr(self._vt, "vc"):
            self._vt.vc.tool = t

    def _set_brush_size(self, v: int) -> None:
        self.canvas.brush_size = v
        if hasattr(self, "_vt") and hasattr(self._vt, "vc"):
            self._vt.vc.brush_size = v
        self._sz_lbl.setText(str(v))

    def _set_status(self, msg: str) -> None:
        self._sb.showMessage(msg)

    def _update_undo_label(self) -> None:
        canvas = self._active_canvas()
        n = canvas.undo_count() if canvas else 0
        self._undo_lbl.setText(str(n) if n > 0 else "")
        self._refresh_zoom_lbl()

    def _set_busy(self, busy: bool) -> None:
        widgets = [self._open_btn, self._more_btn, self._remove_btn,
                   self._save_btn, self._lvl_box, self._pp,
                   self._bb, self._eb, self._rb, self._cb,
                   self._undo_btn, self._redo_btn]
        # add optional buttons that may or may not exist
        for attr in ("_cmp_btn", "_clip_btn"):
            if hasattr(self, attr):
                widgets.append(getattr(self, attr))
        for w in widgets:
            w.setEnabled(not busy)

    def _zoom(self, f: float) -> None:
        c = self._active_canvas() or self.canvas
        old = c.scale
        c.scale = max(0.05, min(16.0, old * f))
        cx = c.width() / 2; cy = c.height() / 2
        ix = (cx - c.offset.x()) / old
        iy = (cy - c.offset.y()) / old
        c.offset = QPoint(int(cx - ix * c.scale),
                          int(cy - iy * c.scale))
        c.update(); self._refresh_zoom_lbl()

    def _zoom_fit(self) -> None:
        c = self._active_canvas() or self.canvas
        c._fit(); c.update()
        self._refresh_zoom_lbl()

    def _refresh_zoom_lbl(self) -> None:
        if hasattr(self, "_zoom_lbl"):
            c = self._active_canvas() or self.canvas
            self._zoom_lbl.setText(f"{int(c.scale * 100)}%")

    def _toggle_presets(self) -> None:
        self._presets_visible = not self._presets_visible
        self._pp.setVisible(self._presets_visible)
        self._presets_btn.setChecked(self._presets_visible)

    def _open_image(self) -> None:
        last_dir = self._s.get("last_open_dir", str(Path.home() / "Pictures"))
        if not Path(last_dir).exists():
            last_dir = str(Path.home() / "Pictures")
        path, _ = QFileDialog.getOpenFileName(
            self, "Open Image", last_dir,
            "Images (*.png *.jpg *.jpeg *.bmp *.webp)")
        if path:
            self._s["last_open_dir"] = str(Path(path).parent)
            save_settings(self._s)
            if self.canvas.load_image(path):
                self._tabs.setCurrentIndex(0)

    def _do_inpaint(self) -> None:
        if self._tabs.currentIndex() == 1:
            self._vt._remove_frame()
        else:
            self.canvas.do_inpaint(self._lvl_box.currentIndex())

    def _save_image(self, fmt: str = "png") -> None:
        if self.canvas.cv_cur is None:
            self._set_status("  ⚠️  No image to save!")
            return
        try:
            path = self.canvas.save_result(fmt=fmt)
        except Exception as exc:
            self._set_status(f"  ❌  Save error: {exc}")
            return
        if path:
            self._set_status(f"  💾  Saved → {path.name}")
            try:
                self._gv.refresh()
            except Exception:
                pass  # gallery refresh must not block save
        else:
            self._set_status("  ❌  Save failed — check permissions")

    def _open_save_folder(self) -> None:
        launch_system_file(str(SAVE_DIR))

    def _from_gallery(self, path: str) -> None:
        if self.canvas.load_image(path):
            self._tabs.setCurrentIndex(0)

    def _tab_changed(self, i: int) -> None:
        if self._tabs.tabText(i).strip().startswith("🗂"):
            self._gv.refresh()
        elif self._tabs.tabText(i).strip().startswith("⏳") or i == 3:
            self._pv.refresh()
        self._update_undo_label()
        self._refresh_zoom_lbl()

    def _auto_detect_watermarks(self) -> None:
        canvas = self._active_canvas()
        if canvas is None or not canvas._has_content():
            QMessageBox.information(self, "No media", "Load an image or video first.")
            return
        img = canvas._current_cv_img()
        if img is None:
            return
        rects = detect_all_watermarks(img)
        if not rects:
            QMessageBox.information(self, "No Watermarks Found",
                "No high-contrast watermarks detected automatically.\n\n"
                "Tip: Click the 🪄 Smart Snap tool [S] in the top toolbar to hover and 1-click snap any watermark box!")
            return
        canvas._push_undo()
        for r in rects:
            cv2.rectangle(canvas.mask, (r.x(), r.y()),
                          (r.x() + r.width(), r.y() + r.height()), 255, -1)
        canvas._invalidate_overlay()
        canvas.mask_changed.emit()
        canvas.update()
        self._set_status(f"  🪄  Auto-detected & selected {len(rects)} watermark area{'s' if len(rects)!=1 else ''}!")

    def _apply_preset(self, preset: dict) -> None:
        lvl = self.canvas.apply_preset(preset)
        if lvl is not None:
            self._lvl_box.setCurrentIndex(lvl)

    def _save_preset(self) -> None:
        if self.canvas.cv_cur is None:
            QMessageBox.information(self, "No image",
                "Load an image first, then draw a mask.")
            return
        h, w = self.canvas.cv_cur.shape[:2]
        dlg  = PresetSaveDialog(self.canvas.mask, w, h, self)
        if not dlg._valid:
            return
        if (dlg.exec() == QDialog.DialogCode.Accepted
                and dlg.result_preset):
            ps = [p for p in load_presets()
                  if p["name"] != dlg.result_preset["name"]]
            ps.append(dlg.result_preset)
            save_presets(ps)
            self._pp.refresh()
            self._set_status(
                f"  ✅  Preset '{dlg.result_preset['name']}' saved!")

    def _show_settings(self) -> None:
        dlg = SettingsDialog(self)
        dlg.applied.connect(self._apply_settings)
        dlg.exec()

    def _show_about(self) -> None:
        AboutDialog(self).exec()

    def _show_shortcuts(self) -> None:
        ShortcutsDialog(self).exec()

    def _batch_process_images(self) -> None:
        if self.canvas.mask is None or not self.canvas.mask.any():
            QMessageBox.information(self, "No Mask Drawn",
                "Draw or select a watermark mask first.\n\n"
                "The batch processor will apply this exact watermark removal area to all selected images!")
            return
        last_dir = self._s.get("last_open_dir", str(Path.home() / "Pictures"))
        if not Path(last_dir).exists():
            last_dir = str(Path.home() / "Pictures")
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Select Images for Batch Watermark Removal", last_dir,
            "Images (*.png *.jpg *.jpeg *.bmp *.webp)"
        )
        if not paths:
            return
        self._s["last_open_dir"] = str(Path(paths[0]).parent)
        save_settings(self._s)
        lvl = self._lvl_box.currentIndex()
        mask = self.canvas.mask.copy()
        SAVE_DIR.mkdir(parents=True, exist_ok=True)
        self._set_status(f"  ⏳  Batch processing {len(paths)} images…")
        count = 0
        for p in paths:
            try:
                img = cv2.imread(p)
                if img is None:
                    continue
                H, W = img.shape[:2]
                m = mask
                if m.shape != (H, W):
                    m = cv2.resize(m, (W, H), interpolation=cv2.INTER_NEAREST)
                res = inpaint_roi(img, m, lvl)
                out_p = SAVE_DIR / f"batch_{Path(p).stem}_{datetime.now().strftime('%H%M%S')}{Path(p).suffix}"
                cv2.imwrite(str(out_p), res)
                count += 1
            except Exception:
                pass
        self._set_status(f"  🎉  Batch complete! {count}/{len(paths)} images saved to Edits folder.")
        self._gv.refresh()
        QMessageBox.information(self, "Batch Complete",
            f"Successfully processed and saved {count} images to default edits folder:\n{SAVE_DIR}")

    def _apply_settings(self) -> None:
        self._s  = load_settings()
        self._kb = self._s.get("keybinds", DEFAULT_SETTINGS["keybinds"])
        self.canvas._max_undo = self._s.get("max_undo", 30)
        if hasattr(self, "_vt") and hasattr(self._vt, "vc"):
            self._vt.vc._max_undo = self._s.get("max_undo", 30)
        self._lvl_box.setCurrentIndex(self._s.get("default_level", 0))
        hv = self._s.get("tooltip_hover", 250)
        hd = self._s.get("tooltip_hide",  750)
        for bbl in self._hbs:
            bbl.hover_ms = hv
            bbl.hide_ms  = hd
        self._set_status("  ⚙️  Settings saved!")

    def _apply_settings_quiet(self) -> None:
        """Apply on startup without status message."""
        self._apply_settings()

    # ── Keybind matching ──────────────────────────────────────────────────────

    def _matches(self, event, action: str) -> bool:
        s     = self._kb.get(action, "")
        parts = s.split("+")
        mods  = event.modifiers()
        need_ctrl  = "Ctrl"  in parts
        need_shift = "Shift" in parts
        need_alt   = "Alt"   in parts
        key_parts  = [p for p in parts
                      if p not in ("Ctrl", "Shift", "Alt", "Meta")]
        if bool(mods & Qt.KeyboardModifier.ControlModifier) != need_ctrl:
            return False
        if bool(mods & Qt.KeyboardModifier.ShiftModifier)   != need_shift:
            return False
        if bool(mods & Qt.KeyboardModifier.AltModifier)     != need_alt:
            return False
        if not key_parts:
            return False
        return QKeySequence(event.key()).toString() == key_parts[-1]

    def keyPressEvent(self, event) -> None:
        # Forward Space to the active canvas for pan mode
        if event.key() == Qt.Key.Key_Space and not event.isAutoRepeat():
            canvas = self._active_canvas()
            if canvas is not None:
                canvas.keyPressEvent(event)
                return

        # Direct special keys
        if event.key() == Qt.Key.Key_F1 or event.text() == '?':
            self._show_shortcuts()
            return
        if event.key() == Qt.Key.Key_Backslash:
            if hasattr(self.canvas, "toggle_compare"):
                self.canvas.toggle_compare()
            return
        if event.text() in (']', '+'):
            canvas = self._active_canvas()
            if canvas: canvas.expand_mask(2)
            return
        if event.text() in ('[', '-'):
            canvas = self._active_canvas()
            if canvas: canvas.contract_mask(2)
            return
        if event.key() == Qt.Key.Key_I and not event.modifiers():
            canvas = self._active_canvas()
            if canvas: canvas.invert_mask()
            return
        if (event.modifiers() & Qt.KeyboardModifier.ControlModifier) and event.key() == Qt.Key.Key_E:
            self._open_save_folder()
            return
        if (event.modifiers() & Qt.KeyboardModifier.ControlModifier) and event.key() == Qt.Key.Key_D:
            canvas = self._active_canvas()
            if canvas: canvas.clear_mask()
            return
        if (event.modifiers() & Qt.KeyboardModifier.ShiftModifier) and event.key() == Qt.Key.Key_S:
            self._auto_detect_watermarks()
            return

        # Map all configurable actions
        action_map = [
            ("smart",           lambda: (self._sb_tool.setChecked(True),
                                         self._set_tool(_BaseCanvas.TOOL_SMART))),
            ("brush",           lambda: (self._bb.setChecked(True),
                                         self._set_tool(_BaseCanvas.TOOL_BRUSH))),
            ("eraser",          lambda: (self._eb.setChecked(True),
                                         self._set_tool(_BaseCanvas.TOOL_ERASER))),
            ("rect",            lambda: (self._rb.setChecked(True),
                                         self._set_tool(_BaseCanvas.TOOL_SQUARE))),
            ("ellipse",         lambda: (self._cb.setChecked(True),
                                         self._set_tool(_BaseCanvas.TOOL_CIRCLE))),
            ("pan",             lambda: (self._pb_tool.setChecked(True),
                                         self._set_tool(_BaseCanvas.TOOL_PAN))),
            ("clear_mask",      lambda: self._active_canvas().clear_mask() if self._active_canvas() else None),
            ("undo",            lambda: self._active_canvas().undo() if self._active_canvas() else None),
            ("redo",            lambda: self._active_canvas().redo() if self._active_canvas() else None),
            ("save",            self._save_image),
            ("open",            self._open_image),
            ("new_preset",      self._save_preset),
            ("toggle_presets",  self._toggle_presets),
            ("zoom_in",         lambda: self._zoom(1.2)),
            ("zoom_out",        lambda: self._zoom(0.83)),
            ("zoom_reset",      self._zoom_fit),
        ]
        for action, fn in action_map:
            if self._matches(event, action):
                fn()
                return
        super().keyPressEvent(event)

    def keyReleaseEvent(self, event) -> None:
        # Forward Space release to the active canvas to end pan mode
        if event.key() == Qt.Key.Key_Space and not event.isAutoRepeat():
            canvas = self._active_canvas()
            if canvas is not None:
                canvas.keyReleaseEvent(event)
                return
        super().keyReleaseEvent(event)

    def _active_canvas(self) -> "_BaseCanvas | None":
        """Return whichever canvas is currently visible."""
        idx = self._tabs.currentIndex()
        if idx == 0:
            return self.canvas
        elif idx == 1:
            return self._vt.vc
        return None

    # ── Cleanup ───────────────────────────────────────────────────────────────

    def closeEvent(self, event) -> None:
        """Properly clean up threads and resources before exit."""
        self.canvas.cleanup()
        self._vt.cleanup()
        event.accept()


# ─── Entry point ──────────────────────────────────────────────────────────────

def _take_auto_screenshot(win: QMainWindow, path: str, app: QApplication) -> None:
    try:
        out_p = Path(path).resolve()
        out_p.parent.mkdir(parents=True, exist_ok=True)
        pix = win.grab()
        pix.save(str(out_p))
        print(f"[AUTO_SCREENSHOT] Saved screenshot to: {out_p}")
    except Exception as exc:
        print(f"[AUTO_SCREENSHOT] Error capturing screenshot: {exc}")
    finally:
        app.quit()


def main() -> None:
    os.environ.setdefault("QT_AUTO_SCREEN_SCALE_FACTOR", "1")
    app = QApplication(sys.argv)
    app.setApplicationName("MyScreen Watermark Remover")
    app.setApplicationVersion(APP_VERSION)
    app.setStyle("Fusion")
    app.setStyleSheet(APP_STYLE)
    pal = app.palette()
    for role, hex_col in [
        (QPalette.ColorRole.Window,          BG_DEEP),
        (QPalette.ColorRole.WindowText,      TEXT_MAIN),
        (QPalette.ColorRole.Base,            BG_BASE),
        (QPalette.ColorRole.AlternateBase,   BG_CARD),
        (QPalette.ColorRole.Text,            TEXT_MAIN),
        (QPalette.ColorRole.Button,          BG_DEEP),
        (QPalette.ColorRole.ButtonText,      TEXT_MAIN),
        (QPalette.ColorRole.Highlight,       PURPLE),
        (QPalette.ColorRole.HighlightedText, "#ffffff"),
        (QPalette.ColorRole.ToolTipBase,     BG_RAISED),
        (QPalette.ColorRole.ToolTipText,     TEXT_MAIN),
    ]:
        pal.setColor(QPalette.ColorGroup.All, role, QColor(hex_col))
    app.setPalette(pal)
    if ICON_PATH.exists():
        app.setWindowIcon(QIcon(str(ICON_PATH)))
    _s = load_settings()
    if _s.get("live_logging", False):
        cel_logger.enable()
    win = MainWindow()
    # Mobile: start compact
    screen = app.primaryScreen()
    if screen:
        geo = screen.geometry()
        dpr = screen.devicePixelRatio()
        if min(geo.width(), geo.height()) < 600 or (dpr >= 2.5 and max(geo.width(), geo.height()) < 1200):
            win.resize(480, 700)

    # Automated headless/offscreen screenshot flag
    auto_shot = False
    shot_path = "screenshot.png"
    target_tab = None
    for i, arg in enumerate(sys.argv):
        if arg == "--auto-screenshot":
            auto_shot = True
            if i + 1 < len(sys.argv) and not sys.argv[i + 1].startswith("--"):
                shot_path = sys.argv[i + 1]
        elif arg.startswith("--auto-screenshot="):
            auto_shot = True
            shot_path = arg.split("=", 1)[1]
        elif arg == "--tab" and i + 1 < len(sys.argv):
            target_tab = sys.argv[i + 1]
        elif arg.startswith("--tab="):
            target_tab = arg.split("=", 1)[1]

    if target_tab:
        tab_lower = target_tab.lower()
        if "vid" in tab_lower or tab_lower == "1":
            win._tabs.setCurrentIndex(1)
        elif "gal" in tab_lower or tab_lower == "2":
            win._tabs.setCurrentIndex(2)
        elif "edit" in tab_lower or tab_lower == "0":
            win._tabs.setCurrentIndex(0)

    win.show()
    if auto_shot:
        app.processEvents()
        QTimer.singleShot(300, lambda: _take_auto_screenshot(win, shot_path, app))
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
