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
    MIRRORS = [None,
               "https://pypi.tuna.tsinghua.edu.cn/simple",
               "https://mirrors.aliyun.com/pypi/simple/",
               "https://pypi.mirrors.ustc.edu.cn/simple/"]
    missing = []
    for mod, pkg in DEPS.items():
        try:
            __import__(mod)
        except ImportError:
            missing.append(pkg)
    if not missing:
        return
    print("\n╔══════════════════════════════════════════╗")
    print("║  MyScreen WR  ·  First-boot setup        ║")
    print("╠══════════════════════════════════════════╣")
    for p in missing:
        print(f"║  📦  Need: {p:<31} ║")
    print("╚══════════════════════════════════════════╝\n")
    def _try(exe, pkgs, extra=None):
        for mirror in MIRRORS:
            cmd = [exe, "-m", "pip", "install", "--quiet",
                   "--timeout", "60", "--retries", "2",
                   *(["--index-url", mirror] if mirror else []),
                   *(extra or []), *pkgs]
            print(f"  ⏳  {mirror or 'pypi.org'} …", flush=True)
            if subprocess.call(cmd, stdout=subprocess.DEVNULL,
                               stderr=subprocess.DEVNULL) == 0:
                print("  ✅  OK\n"); return True
        return False
    if _try(sys.executable, missing):
        os.execv(sys.executable, [sys.executable] + sys.argv)
    if _try(sys.executable, missing, ["--break-system-packages"]):
        os.execv(sys.executable, [sys.executable] + sys.argv)
    venv = Path(sys.argv[0]).resolve().parent / ".mswr_venv"
    subprocess.call([sys.executable, "-m", "venv", str(venv)],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    vpy = str(venv / "bin" / "python") if (venv / "bin").exists() \
          else str(venv / "Scripts" / "python.exe")
    if _try(vpy, missing):
        os.execv(vpy, [vpy] + sys.argv)
    print(f"\n❌  Auto-install failed.\n    pip install {' '.join(missing)}")
    sys.exit(1)
_bootstrap()
# ─────────────────────────────────────────────────────────────────────────────

import sys, os, json, base64, traceback
from pathlib import Path
from datetime import datetime

import cv2
import numpy as np

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QSlider, QFileDialog, QTabWidget, QScrollArea,
    QGridLayout, QSizePolicy, QFrame, QComboBox, QToolButton, QButtonGroup,
    QMessageBox, QStatusBar, QDialog, QTextEdit, QLineEdit, QSpinBox,
    QDoubleSpinBox, QListWidget, QListWidgetItem, QProgressBar,
    QFormLayout, QGroupBox, QScrollBar, QInputDialog,
)
from PyQt6.QtCore import (
    Qt, QPoint, QRect, QThread, pyqtSignal, QTimer, QSize,
    QPropertyAnimation, QEasingCurve,
)
from PyQt6.QtGui import (
    QPainter, QImage, QPixmap, QColor, QPen, QBrush,
    QFont, QPalette, QCursor, QKeySequence, QIcon,
)

# ─── Paths ────────────────────────────────────────────────────────────────────
DATA_DIR      = Path.home()/"Documents"/"HenryJay Data Folder"/"MyScreen Watermark Remover"
SAVE_DIR      = Path.home()/"Pictures"/"MyScreen Watermark Remover Edits"
DATA_DIR.mkdir(parents=True, exist_ok=True)
SAVE_DIR.mkdir(parents=True, exist_ok=True)
SETTINGS_FILE = DATA_DIR / "settings.json"
PRESETS_FILE  = DATA_DIR / "presets.json"
APP_VERSION   = "1.7.0"
BUILD_DATE    = "2026-03-15"

MOBILE_WIDTH_THRESHOLD = 700   # px — treat as mobile if window width < this

# ─── Settings ─────────────────────────────────────────────────────────────────
DEFAULT_SETTINGS: dict = {
    "keybinds": {
        "brush":      "B",
        "eraser":     "X",
        "rect":       "R",
        "ellipse":    "E",
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
QTabWidget::pane {{ border: none; background: {BG_BASE}; }}
QTabBar {{
    background: {BG_DEEP};
    border-bottom: 1px solid {BORDER};
}}
QTabBar::tab {{
    background: transparent; color: {TEXT_DIM};
    padding: 8px 18px; border: none;
    border-bottom: 2px solid transparent;
    font-size: 11px; font-weight: 500;
    min-width: 64px;
}}
QTabBar::tab:selected {{
    color: {PURPLE_LIGHT}; border-bottom: 2px solid {PURPLE};
    font-weight: 600;
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
    MAX = 96
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

# ─── Inpaint ──────────────────────────────────────────────────────────────────

LEVEL_QUICK     = 0
LEVEL_SMART     = 1
LEVEL_PRECISION = 2

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
        # FIX: proper multi-line loop (old one-liner was a bug)
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

def run_inpaint(img: np.ndarray, mask: np.ndarray,
                level: int, cb=None) -> np.ndarray:
    if level == LEVEL_QUICK:
        return _inpaint_quick(img, mask)
    elif level == LEVEL_SMART:
        return _inpaint_smart(img, mask, cb)
    else:
        return _inpaint_precision(img, mask, cb)

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


class VideoWorker(QThread):
    frame_done = pyqtSignal(int, int)
    finished   = pyqtSignal(str)
    error      = pyqtSignal(str)

    def __init__(self, src: str, dst: str,
                 method: str, data: dict, level: int):
        super().__init__()
        self._src    = src
        self._dst    = dst
        self._method = method
        self._data   = data
        self._level  = level
        self._stop   = False

    def stop(self) -> None:
        self._stop = True

    def run(self) -> None:
        cap = out = None
        try:
            cap = cv2.VideoCapture(self._src)
            if not cap.isOpened():
                self.error.emit("Cannot open video file."); return
            fps   = cap.get(cv2.CAP_PROP_FPS) or 30.0
            W     = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            H     = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            total = max(int(cap.get(cv2.CAP_PROP_FRAME_COUNT)), 1)
            out   = None
            for codec in ("mp4v", "avc1", "XVID", "MJPG"):
                out = cv2.VideoWriter(
                    self._dst,
                    cv2.VideoWriter_fourcc(*codec), fps, (W, H))
                if out.isOpened():
                    break
            if not out or not out.isOpened():
                self.error.emit("Cannot create output file."); return
            if self._method == "auto_track":
                self._auto_track(cap, out, W, H, total)
            else:
                self._timeline(cap, out, W, H, total)
            if not self._stop:
                self.finished.emit(self._dst)
        except Exception:
            self.error.emit(traceback.format_exc())
        finally:
            if cap is not None:
                cap.release()
            if out is not None:
                out.release()

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
        for i in range(total):
            if self._stop:
                break
            ret, frame = cap.read()
            if not ret:
                break
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            if gray.shape[0] >= rh and gray.shape[1] >= rw:
                res         = cv2.matchTemplate(gray, tmpl, cv2.TM_CCOEFF_NORMED)
                _, mv, _, ml = cv2.minMaxLoc(res)
                if mv >= thr:
                    fx, fy = ml
                    fm     = np.zeros((H, W), np.uint8)
                    eh, ew = min(rh, H - fy), min(rw, W - fx)
                    if eh > 0 and ew > 0:
                        fm[fy:fy+eh, fx:fx+ew] = cv2.resize(
                            mask_crop[:eh, :ew], (ew, eh),
                            interpolation=cv2.INTER_NEAREST)
                    if fm.any():
                        try:
                            frame = run_inpaint(frame, fm, self._level)
                        except Exception:
                            pass
            out.write(frame)
            self.frame_done.emit(i + 1, total)

    def _timeline(self, cap, out, W, H, total):
        segs = self._data.get("segments", [])
        cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
        for i in range(total):
            if self._stop:
                break
            ret, frame = cap.read()
            if not ret:
                break
            for seg in segs:
                if seg["start"] <= i <= seg["end"]:
                    m = seg.get("mask")
                    if m is not None and m.any():
                        if m.shape != (H, W):
                            m = cv2.resize(m, (W, H),
                                           interpolation=cv2.INTER_NEAREST)
                        try:
                            frame = run_inpaint(frame, m, self._level)
                        except Exception:
                            pass
                    break
            out.write(frame)
            self.frame_done.emit(i + 1, total)


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
    ("brush",           "Paint Brush"),
    ("eraser",          "Eraser"),
    ("rect",            "Rectangle Select"),
    ("ellipse",         "Ellipse Select"),
    ("clear_mask",      "Clear Mask"),
    ("undo",            "Undo"),
    ("redo",            "Redo"),
    ("save",            "Save to Gallery"),
    ("open",            "Open Image"),
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
        self.setMinimumSize(500, 440)
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
        self._lb.addItems(["⚡ Quick", "🧠 Smart", "🔬 Precision"])
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
                              ("Image gallery saves:", SAVE_DIR)]:
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
        self._lb.addItems(["⚡  Quick", "🧠  Smart", "🔬  Precision"])
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
        tl = QLabel("🪄  MyScreen Watermark Remover")
        tl.setStyleSheet(
            f"font-size:17px;font-weight:800;color:{PURPLE_LIGHT};letter-spacing:-0.3px;")
        bl.addWidget(tl)
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
        vr.addWidget(bg); bl.addLayout(vr)
        ar = QHBoxLayout()
        ar.addWidget(QLabel("By  <b>HenryJay</b>"))
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
        self._ct.setFixedHeight(240)
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
        cb = QPushButton("Close")
        cb.setObjectName("cta"); cb.setFixedWidth(90); cb.setFixedHeight(28)
        cb.clicked.connect(self.accept)
        b2.addWidget(cb, alignment=Qt.AlignmentFlag.AlignRight)
        root.addWidget(body)
        self._render(False)

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


# ─── Base Canvas ──────────────────────────────────────────────────────────────

class _BaseCanvas(QWidget):
    status_msg   = pyqtSignal(str)
    mask_changed = pyqtSignal()

    TOOL_BRUSH  = "brush"
    TOOL_ERASER = "eraser"
    TOOL_SQUARE = "square"
    TOOL_CIRCLE = "circle"

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
        # Pan
        self._panning   = False
        self._space     = False
        self._pan_start: QPoint | None = None
        self._pan_off   = QPoint(0, 0)
        # Undo
        self._undo: list[np.ndarray] = []
        self._redo: list[np.ndarray] = []
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
        # Invalidate overlay cache whenever mask changes
        self.mask_changed.connect(self._invalidate_overlay)

    # ── Geometry ──────────────────────────────────────────────────────────────

    def _set_size(self, w: int, h: int) -> None:
        self._iw = max(w, 1); self._ih = max(h, 1)
        # Old caches are wrong size — drop them
        self._mask_overlay  = None
        self._checker_cache = None
        self._checker_size  = QSize(0, 0)

    def _fit(self) -> None:
        wr = self.width()  / self._iw
        hr = self.height() / self._ih
        self.scale = min(wr, hr, 1.0) * 0.94
        self._recenter()

    def _recenter(self) -> None:
        iw = int(self._iw * self.scale)
        ih = int(self._ih * self.scale)
        self.offset = QPoint(
            (self.width()  - iw) // 2,
            (self.height() - ih) // 2,
        )

    def _to_img(self, pos: QPoint) -> QPoint:
        x = int((pos.x() - self.offset.x()) / self.scale)
        y = int((pos.y() - self.offset.y()) / self.scale)
        return QPoint(max(0, min(x, self._iw - 1)),
                      max(0, min(y, self._ih - 1)))

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
        # Mask overlay — use cached QImage, only rebuild on mask_changed
        if self.mask is not None and self.mask.any():
            if self._mask_overlay is None:
                self._rebuild_overlay()
            if self._mask_overlay is not None:
                p.drawImage(ir, self._mask_overlay)
        # Shape preview
        if (self.preview_rect and
                self.tool in (self.TOOL_SQUARE, self.TOOL_CIRCLE)):
            r  = self.preview_rect
            wr = QRect(
                int(r.x() * self.scale) + self.offset.x(),
                int(r.y() * self.scale) + self.offset.y(),
                int(r.width()  * self.scale),
                int(r.height() * self.scale),
            )
            p.setPen(QPen(QColor(PURPLE_LIGHT), 1.5, Qt.PenStyle.DashLine))
            p.setBrush(QBrush(QColor(167, 139, 250, 28)))
            if self.tool == self.TOOL_SQUARE:
                p.drawRect(wr)
            else:
                p.drawEllipse(wr)

    def _rebuild_overlay(self) -> None:
        """Rebuild the cached mask overlay. Called on mask_changed, not every repaint."""
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
        """Draw checker background. Uses a cached QPixmap — zero Python loops per repaint."""
        needed = QSize(r.width(), r.height())
        if self._checker_cache is None or self._checker_size != needed:
            # Build once, cache forever until size changes
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
        if (e.button() == Qt.MouseButton.MiddleButton or
                (e.button() == Qt.MouseButton.LeftButton and self._space)):
            self._panning   = True
            self._pan_start = e.position().toPoint()
            self._pan_off   = QPoint(self.offset)
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            return
        if e.button() != Qt.MouseButton.LeftButton:
            return
        if not self._has_content():
            return
        self._push_undo()
        self.drawing    = True
        self.drag_start = e.position().toPoint()
        if self.tool in (self.TOOL_BRUSH, self.TOOL_ERASER):
            self._brush(e.position().toPoint())
            self.last_pos = e.position().toPoint()

    def mouseMoveEvent(self, e) -> None:
        if self._panning and self._pan_start is not None:
            self.offset = self._pan_off + (e.position().toPoint() - self._pan_start)
            self.update()
            return
        if not self.drawing:
            return
        pos = e.position().toPoint()
        if self.tool in (self.TOOL_BRUSH, self.TOOL_ERASER):
            self._stroke(self.last_pos, pos)
            self.last_pos = pos
        else:
            self._preview_update(self.drag_start, pos)

    def mouseReleaseEvent(self, e) -> None:
        if self._panning and e.button() in (
                Qt.MouseButton.MiddleButton, Qt.MouseButton.LeftButton):
            self._panning = False
            self.setCursor(
                Qt.CursorShape.OpenHandCursor if self._space
                else Qt.CursorShape.CrossCursor)
            return
        if not self.drawing:
            return
        self.drawing = False
        pos = e.position().toPoint()
        if (self.tool in (self.TOOL_SQUARE, self.TOOL_CIRCLE)
                and self.drag_start and self.mask is not None):
            p1 = self._to_img(self.drag_start)
            p2 = self._to_img(pos)
            x1, x2 = min(p1.x(), p2.x()), max(p1.x(), p2.x())
            y1, y2 = min(p1.y(), p2.y()), max(p1.y(), p2.y())
            if self.tool == self.TOOL_SQUARE:
                cv2.rectangle(self.mask, (x1, y1), (x2, y2), 255, -1)
            else:
                cx, cy = (x1 + x2) // 2, (y1 + y2) // 2
                cv2.ellipse(self.mask, (cx, cy),
                            (max(1, (x2-x1)//2), max(1, (y2-y1)//2)),
                            0, 0, 360, 255, -1)
        self.preview_rect = None
        self.last_pos     = None
        self.mask_changed.emit()
        self.update()

    def wheelEvent(self, e) -> None:
        """Zoom anchored to cursor position — pan state preserved."""
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
        # Canvas size changed — checker cache is wrong dimensions
        self._checker_cache = None
        self._checker_size  = QSize(0, 0)
        super().resizeEvent(e)

    def keyPressEvent(self, e) -> None:
        if e.key() == Qt.Key.Key_Space and not e.isAutoRepeat():
            self._space = True
            if not self._panning:
                self.setCursor(Qt.CursorShape.OpenHandCursor)
        super().keyPressEvent(e)

    def keyReleaseEvent(self, e) -> None:
        if e.key() == Qt.Key.Key_Space and not e.isAutoRepeat():
            self._space = False
            if not self._panning:
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

    def _invalidate_overlay(self) -> None:
        """Clear cached mask overlay so it is rebuilt on next repaint."""
        self._mask_overlay = None

    def undo(self) -> None:
        if not self._undo:
            self.status_msg.emit("  ℹ️  Nothing to undo")
            return
        self._redo.append(self.mask.copy())
        self.mask = self._undo.pop()
        self.mask_changed.emit()
        self.update()
        self.status_msg.emit(
            f"  ↩  Undo  ({len(self._undo)} step{'s' if len(self._undo)!=1 else ''} left)")

    def redo(self) -> None:
        if not self._redo:
            self.status_msg.emit("  ℹ️  Nothing to redo")
            return
        self._undo.append(self.mask.copy())
        self.mask = self._redo.pop()
        self.mask_changed.emit()
        self.update()
        self.status_msg.emit("  ↪  Redo")

    def clear_mask(self) -> None:
        if self.mask is not None:
            self._push_undo()
            self.mask.fill(0)
            self.mask_changed.emit()
            self.update()
            self.status_msg.emit("  🧹  Mask cleared")

    def undo_count(self) -> int:
        return len(self._undo)


# ─── Image Canvas ─────────────────────────────────────────────────────────────

class Canvas(_BaseCanvas):
    inpaint_done = pyqtSignal()
    busy_changed = pyqtSignal(bool)

    def __init__(self):
        super().__init__()
        self.cv_orig:   np.ndarray | None = None
        self.cv_cur:    np.ndarray | None = None
        self._qi:       QImage    | None  = None
        self._busy      = False
        self._worker:   InpaintWorker | None = None
        self.setAcceptDrops(True)

    def _display_img(self)  -> QImage | None:
        if self._show_orig and self._qi_orig is not None:
            return self._qi_orig
        return self._qi
    def _has_content(self)  -> bool: return self.cv_orig is not None

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
        # Brush / eraser circle cursor
        if (self._has_content() and not self._panning and
                self.tool in (self.TOOL_BRUSH, self.TOOL_ERASER) and
                self._mouse_pos is not None):
            r = max(2, int(self.brush_size * self.scale))
            pc = QPainter(self)
            col = QColor(255, 90, 90, 200) if self.tool == self.TOOL_ERASER \
                  else QColor(167, 139, 250, 200)
            pc.setPen(QPen(col, 1.2))
            pc.setBrush(Qt.BrushStyle.NoBrush)
            pc.setRenderHint(QPainter.RenderHint.Antialiasing)
            pc.drawEllipse(self._mouse_pos, r, r)

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

    def mouseMoveEvent(self, e) -> None:
        self._mouse_pos = e.position().toPoint()
        super().mouseMoveEvent(e)
        if self.tool in (self.TOOL_BRUSH, self.TOOL_ERASER) and self._has_content():
            self.update()  # redraw brush cursor circle

    def leaveEvent(self, e) -> None:
        self._mouse_pos = None
        self.update()  # erase brush cursor

    def dragEnterEvent(self, e) -> None:
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e) -> None:
        for url in e.mimeData().urls():
            fp = url.toLocalFile()
            if fp.lower().endswith((".png",".jpg",".jpeg",".bmp",".webp")):
                self.load_image(fp)
                break

    def reset_to_original(self) -> None:
        if self.cv_orig is None:
            return
        self.cv_cur   = self.cv_orig.copy()
        self._qi      = cv2_to_qimage(self.cv_cur)
        self._qi_orig = self._qi
        self._show_orig = False
        self.mask.fill(0)
        self._undo.clear()
        self._redo.clear()
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
        names = {LEVEL_QUICK: "Quick", LEVEL_SMART: "Smart",
                 LEVEL_PRECISION: "Precision"}
        self.status_msg.emit(
            f"  ⏳  {names[level]} inpaint…  0%")
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
    def __init__(self):
        super().__init__()
        self._frame: np.ndarray | None = None
        self._qf:    QImage    | None  = None

    def _display_img(self) -> QImage | None: return self._qf
    def _has_content(self) -> bool: return self._frame is not None

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

    def load_frame(self, frame: np.ndarray) -> None:
        h, w     = frame.shape[:2]
        self._set_size(w, h)
        self._frame = frame
        self._qf    = cv2_to_qimage(frame)
        if self.mask is None or self.mask.shape != (h, w):
            self.mask = np.zeros((h, w), dtype=np.uint8)
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
        self._lb2.addItems(["⚡ Quick", "🧠 Smart", "🔬 Precision"])
        lr.addWidget(self._lb2); pl.addLayout(lr)

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

    def _load(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Open Video", str(Path.home() / "Videos"),
            "Videos (*.mp4 *.avi *.mkv *.mov *.webm)")
        if not path:
            return
        self._release_cap()
        self._cap = cv2.VideoCapture(path)
        if not self._cap.isOpened():
            self._cap = None
            QMessageBox.critical(self, "Error", "Cannot open video.")
            return
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
        self._seek(0)

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
        # Guard: stop existing worker
        if self._worker is not None and self._worker.isRunning():
            self._worker.stop()
            self._worker.wait(300)
        s   = load_settings()
        ext = s.get("video_format", "mp4")
        out = str(SAVE_DIR /
                  f"video_{datetime.now().strftime('%Y%m%d_%H%M%S')}.{ext}")
        self._worker = VideoWorker(
            self._vpath, out, method, data, self._lb2.currentIndex())
        self._worker.frame_done.connect(self._prog)
        self._worker.finished.connect(self._vdone)
        self._worker.error.connect(self._verr)
        self._pb.setRange(0, 100)
        self._pb.setValue(0)
        self._pb.show()
        self._can_btn.show()
        self._ol.setText(f"→ {out}")
        self._worker.start()
        self.status_msg.emit("  🎬  Video processing started…")

    def _prog(self, cur: int, tot: int) -> None:
        pct = int(cur / max(tot, 1) * 100)
        self._pb.setValue(pct)
        self.status_msg.emit(f"  🎬  Frame {cur}/{tot}  ({pct}%)")

    def _vdone(self, path: str) -> None:
        self._pb.hide(); self._can_btn.hide()
        self.status_msg.emit(f"  ✅  Saved → {path}")
        QMessageBox.information(self, "Done!", f"Video saved:\n{path}")

    def _verr(self, msg: str) -> None:
        self._pb.hide(); self._can_btn.hide()
        self.status_msg.emit(f"  ❌  {msg.splitlines()[0]}")
        QMessageBox.critical(self, "Error", msg)

    def _cancel(self) -> None:
        if self._worker is not None:
            self._worker.stop()
        self._pb.hide(); self._can_btn.hide()
        self.status_msg.emit("  ⛔  Cancelled")

    def cleanup(self) -> None:
        """Call before close."""
        self._stop_play()
        self._release_cap()
        if self._worker is not None and self._worker.isRunning():
            self._worker.stop()
            self._worker.wait(500)


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
        imgs = (list(SAVE_DIR.glob("*.png")) +
                list(SAVE_DIR.glob("*.jpg")) +
                list(SAVE_DIR.glob("*.mp4")) +
                list(SAVE_DIR.glob("*.avi")))
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
            if p.suffix.lower() in (".mp4", ".avi"):
                l2 = QLabel(f"🎬  {p.name}")
                l2.setStyleSheet(
                    f"color:{TEXT_DIM};font-size:10px;padding:4px;")
                self._grid.addWidget(l2, i // cols, i % cols)
            else:
                th = GalleryThumb(str(p))
                th.open_clicked.connect(self.open_in_editor.emit)
                th.delete_clicked.connect(self._del)
                self._grid.addWidget(th, i // cols, i % cols)

    def _del(self, path: str) -> None:
        if QMessageBox.question(
                self, "Delete?", f"Delete '{Path(path).name}'?",
                QMessageBox.StandardButton.Yes |
                QMessageBox.StandardButton.No
        ) == QMessageBox.StandardButton.Yes:
            Path(path).unlink(missing_ok=True)
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
        logo = QLabel("🪄")
        logo.setStyleSheet(f"font-size:16px;")
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
        pill_frame.setStyleSheet(
            f"background:{BG_RAISED};border:1px solid {BORDER_LIT};"
            f"border-radius:7px;")
        pfl = QHBoxLayout(pill_frame)
        pfl.setContentsMargins(2, 2, 2, 2)
        pfl.setSpacing(1)

        TOOL_DEFS = [
            ("🖌", "Brush  [B]",      _BaseCanvas.TOOL_BRUSH,   "bb"),
            ("🧽", "Eraser  [X]",     _BaseCanvas.TOOL_ERASER,  "eb"),
            ("▭",  "Rectangle  [R]",  _BaseCanvas.TOOL_SQUARE,  "rb"),
            ("⭕", "Ellipse  [E]",    _BaseCanvas.TOOL_CIRCLE,  "cb"),
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
            btn.setCheckable(True); btn.setFixedSize(32, 30)
            btn.setStyleSheet(pill_style)
            pfl.addWidget(btn)
            setattr(self, f"_{attr}", btn)
            self._tg.addButton(btn)
            btn.clicked.connect(lambda _, t=tool: self._set_tool(t))
        self._bb.setChecked(True)
        tl.addWidget(pill_frame)

        # Brush size pill
        sz_frame = QFrame()
        sz_frame.setStyleSheet(
            f"background:{BG_RAISED};border:1px solid {BORDER_LIT};"
            f"border-radius:7px;")
        szl = QHBoxLayout(sz_frame)
        szl.setContentsMargins(6, 2, 6, 2); szl.setSpacing(5)
        sz_icon = QLabel("◎")
        sz_icon.setStyleSheet(f"color:{TEXT_DIM};font-size:13px;")
        szl.addWidget(sz_icon)
        self._sz_sl = QSlider(Qt.Orientation.Horizontal)
        self._sz_sl.setRange(2, 100)
        self._sz_sl.setValue(self._s.get("brush_size", 25))
        self._sz_sl.setFixedWidth(70)
        self._sz_sl.valueChanged.connect(self._set_brush_size)
        szl.addWidget(self._sz_sl)
        self._sz_lbl = QLabel("25")
        self._sz_lbl.setStyleSheet(
            f"color:{PURPLE_LIGHT};font-size:10px;font-weight:600;min-width:20px;")
        szl.addWidget(self._sz_lbl)
        tl.addWidget(sz_frame)

        tl.addWidget(_vdiv())

        # Mode picker (compact pill)
        self._lvl_box = QComboBox()
        self._lvl_box.addItems(["⚡ Quick", "🧠 Smart", "🔬 Precision"])
        self._lvl_box.setCurrentIndex(self._s.get("default_level", 0))
        self._lvl_box.setFixedWidth(118)
        self._lvl_box.setFixedHeight(30)
        mh = HelpBubble(
            "⚡ Quick — Fast TELEA. Good for small logos.\n\n"
            "🧠 Smart — Ring-by-ring fill. No blur on large areas.\n\n"
            "🔬 Precision — Patch-match like Photoshop Content-Aware Fill.\n"
            "   Best quality, slower.")
        self._hbs.append(mh)
        mlayout = QHBoxLayout(); mlayout.setSpacing(3); mlayout.setContentsMargins(0,0,0,0)
        mlayout.addWidget(self._lvl_box); mlayout.addWidget(mh)
        tl.addLayout(mlayout)

        tl.addStretch()

        # Undo / redo + count
        self._undo_btn = QPushButton("↩")
        self._undo_btn.setObjectName("icon_btn"); self._undo_btn.setFixedSize(28,28)
        self._undo_btn.setToolTip("Undo  [Ctrl+Z]")
        self._undo_btn.clicked.connect(lambda: self.canvas.undo())
        tl.addWidget(self._undo_btn)

        self._undo_lbl = QLabel("")
        self._undo_lbl.setStyleSheet(f"color:{TEXT_FAINT};font-size:9px;min-width:18px;")
        tl.addWidget(self._undo_lbl)

        self._redo_btn = QPushButton("↪")
        self._redo_btn.setObjectName("icon_btn"); self._redo_btn.setFixedSize(28,28)
        self._redo_btn.setToolTip("Redo  [Ctrl+Y]")
        self._redo_btn.clicked.connect(lambda: self.canvas.redo())
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
            ("⚡", "Presets  [Ctrl+Shift+P]", self._toggle_presets),
            ("⚙️", "Settings",                self._show_settings),
            ("ℹ",  "About",                   self._show_about),
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
        self._more_btn.setToolTip("More: clear mask, reset, open folder…")
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
        self._cmp_btn.setToolTip("Hold to compare with original")
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
        self._tabs.addTab(self._vt, "🎬  Video")

        # ── GALLERY TAB ──────────────────────────────────────────────────────
        self._gv = GalleryView()
        self._gv.open_in_editor.connect(self._from_gallery)
        self._tabs.addTab(self._gv, "🗂  Gallery")

        self._tabs.currentChanged.connect(self._tab_changed)

        # Wire up
        self._open_btn.clicked.connect(self._open_image)
        self._remove_btn.clicked.connect(self._do_inpaint)
        self._save_btn.clicked.connect(self._save_image)

        # Status bar
        self._sb = QStatusBar(); self.setStatusBar(self._sb)
        self._set_status("  Ready — open an image or drop it onto the canvas")

        # ── More menu ─────────────────────────────────────────────────────────────

    def _show_more_menu(self) -> None:
        from PyQt6.QtWidgets import QMenu
        menu = QMenu(self)
        menu.setStyleSheet(
            f"QMenu{{background:{BG_RAISED};border:1px solid {BORDER_LIT};"
            f"border-radius:7px;padding:4px;}}"
            f"QMenu::item{{padding:5px 14px;border-radius:4px;color:{TEXT_MAIN};}}"
            f"QMenu::item:selected{{background:{PURPLE_DIM};color:{PURPLE_LIGHT};}}")
        menu.addAction("🧹  Clear Mask", self.canvas.clear_mask)
        menu.addAction("↩  Reset to Original", self.canvas.reset_to_original)
        menu.addSeparator()
        menu.addAction("🖼  Fit to Screen", self._zoom_fit)
        menu.addAction("📋  Copy to Clipboard", self.canvas.copy_to_clipboard)
        menu.addAction("📂  Open Saves Folder", self._open_save_folder)
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
        self._sz_sl.setFixedHeight(70 if narrow else 90)

    # ── Slots ─────────────────────────────────────────────────────────────────

    def _set_tool(self, t: str) -> None:
        self.canvas.tool = t

    def _set_brush_size(self, v: int) -> None:
        self.canvas.brush_size = v
        self._sz_lbl.setText(str(v))

    def _set_status(self, msg: str) -> None:
        self._sb.showMessage(msg)

    def _update_undo_label(self) -> None:
        n = self.canvas.undo_count()
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
        c = self.canvas
        old = c.scale
        c.scale = max(0.05, min(16.0, old * f))
        cx = c.width() / 2; cy = c.height() / 2
        ix = (cx - c.offset.x()) / old
        iy = (cy - c.offset.y()) / old
        c.offset = QPoint(int(cx - ix * c.scale),
                          int(cy - iy * c.scale))
        c.update(); self._refresh_zoom_lbl()

    def _zoom_fit(self) -> None:
        self.canvas._fit(); self.canvas.update()
        self._refresh_zoom_lbl()

    def _refresh_zoom_lbl(self) -> None:
        if hasattr(self, "_zoom_lbl"):
            self._zoom_lbl.setText(f"{int(self.canvas.scale * 100)}%")

    def _toggle_presets(self) -> None:
        self._presets_visible = not self._presets_visible
        self._pp.setVisible(self._presets_visible)
        self._presets_btn.setChecked(self._presets_visible)

    def _open_image(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Open Image", str(Path.home() / "Pictures"),
            "Images (*.png *.jpg *.jpeg *.bmp *.webp)")
        if path:
            self.canvas.load_image(path)

    def _do_inpaint(self) -> None:
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
        import subprocess, sys as _sys
        if _sys.platform.startswith("linux"):
            subprocess.Popen(["xdg-open", str(SAVE_DIR)])
        elif _sys.platform == "darwin":
            subprocess.Popen(["open", str(SAVE_DIR)])
        else:
            import os as _os
            _os.startfile(str(SAVE_DIR))

    def _from_gallery(self, path: str) -> None:
        if self.canvas.load_image(path):
            self._tabs.setCurrentIndex(0)

    def _tab_changed(self, i: int) -> None:
        if self._tabs.tabText(i).strip().startswith("🗂"):
            self._gv.refresh()

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

    def _apply_settings(self) -> None:
        self._s  = load_settings()
        self._kb = self._s.get("keybinds", DEFAULT_SETTINGS["keybinds"])
        self.canvas._max_undo = self._s.get("max_undo", 30)
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
        # Map all configurable actions
        action_map = [
            ("brush",           lambda: (self._bb.setChecked(True),
                                         self._set_tool(_BaseCanvas.TOOL_BRUSH))),
            ("eraser",          lambda: (self._eb.setChecked(True),
                                         self._set_tool(_BaseCanvas.TOOL_ERASER))),
            ("rect",            lambda: (self._rb.setChecked(True),
                                         self._set_tool(_BaseCanvas.TOOL_SQUARE))),
            ("ellipse",         lambda: (self._cb.setChecked(True),
                                         self._set_tool(_BaseCanvas.TOOL_CIRCLE))),
            ("clear_mask",      self.canvas.clear_mask),
            ("undo",            self.canvas.undo),
            ("redo",            self.canvas.redo),
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
                fn()  # all items are callable (lambdas or bound methods)
                return
        super().keyPressEvent(event)

    # ── Cleanup ───────────────────────────────────────────────────────────────

    def closeEvent(self, event) -> None:
        """Properly clean up threads and resources before exit."""
        self.canvas.cleanup()
        self._vt.cleanup()
        event.accept()


# ─── Entry point ──────────────────────────────────────────────────────────────

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
        (QPalette.ColorRole.Button,          BG_RAISED),
        (QPalette.ColorRole.ButtonText,      TEXT_MAIN),
        (QPalette.ColorRole.Highlight,       PURPLE),
        (QPalette.ColorRole.HighlightedText, "#ffffff"),
        (QPalette.ColorRole.ToolTipBase,     BG_RAISED),
        (QPalette.ColorRole.ToolTipText,     TEXT_MAIN),
    ]:
        pal.setColor(role, QColor(hex_col))
    app.setPalette(pal)
    win = MainWindow()
    # Mobile: start compact
    screen = app.primaryScreen()
    if screen:
        geo = screen.geometry()
        dpr = screen.devicePixelRatio()
        if min(geo.width(), geo.height()) < 600 or (dpr >= 2.5 and max(geo.width(), geo.height()) < 1200):
            win.resize(480, 700)
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
