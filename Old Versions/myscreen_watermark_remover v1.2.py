#!/usr/bin/env python3
# ╔══════════════════════════════════════════════════════════════╗
# ║          MyScreen Watermark Remover  ·  by HenryJay          ║
# ║                  hnrycrm@gmail.com  :3                       ║
# ╚══════════════════════════════════════════════════════════════╝

# ─── BOOTSTRAP: auto-install missing deps before anything else ────────────────
def _bootstrap():
    """
    Install missing deps automatically.
    Tries multiple PyPI mirrors so slow/blocked connections (common outside
    the US/EU) don't stall forever. Falls back to a local venv on
    externally-managed Linux (Mint, Ubuntu 23+, Debian 12+).
    """
    import importlib, subprocess, sys, os
    from pathlib import Path

    DEPS = {"cv2": "opencv-python", "numpy": "numpy", "PyQt6": "PyQt6"}

    # Mirrors tried in order — first reachable one wins
    MIRRORS = [
        None,                                          # default PyPI
        "https://pypi.tuna.tsinghua.edu.cn/simple",   # Tsinghua (fast globally)
        "https://mirrors.aliyun.com/pypi/simple/",    # Aliyun
        "https://pypi.mirrors.ustc.edu.cn/simple/",   # USTC
        "https://mirror.baidu.com/pypi/simple/",      # Baidu
    ]

    def _missing():
        out = []
        for mod, pkg in DEPS.items():
            try:
                importlib.import_module(mod)
            except ImportError:
                out.append(pkg)
        return out

    pkgs = _missing()
    if not pkgs:
        return  # ✅ nothing to do

    print("\n╔══════════════════════════════════════════╗")
    print("║  MyScreen WR  ·  First-boot setup        ║")
    print("╠══════════════════════════════════════════╣")
    for p in pkgs:
        print(f"║  📦  Need: {p:<31} ║")
    print("╚══════════════════════════════════════════╝\n")

    def _try_install(python_exe, packages, extra_flags=None):
        """Try every mirror until one succeeds. Returns True on success."""
        for mirror in MIRRORS:
            mirror_flags = ["--index-url", mirror] if mirror else []
            cmd = [
                python_exe, "-m", "pip", "install",
                "--quiet",
                "--timeout", "60",
                "--retries", "2",
                *mirror_flags,
                *(extra_flags or []),
                *packages,
            ]
            src = mirror or "pypi.org"
            print(f"  ⏳  Trying {src} …", flush=True)
            rc = subprocess.call(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            if rc == 0:
                print(f"  ✅  Got it from {src}!\n")
                return True
            print(f"  ✗  {src} failed or timed out, trying next mirror…")
        return False

    # ── Strategy 1: plain pip (works in venvs, Windows, macOS) ──
    if _try_install(sys.executable, pkgs):
        print("✅  All installed!  Restarting app…\n")
        os.execv(sys.executable, [sys.executable] + sys.argv)

    # ── Strategy 2: --break-system-packages (some managed envs allow it) ──
    print("  ℹ️   Retrying with --break-system-packages …")
    if _try_install(sys.executable, pkgs, ["--break-system-packages"]):
        print("✅  All installed!  Restarting app…\n")
        os.execv(sys.executable, [sys.executable] + sys.argv)

    # ── Strategy 3: local .myscreen_venv (for externally-managed Python) ──
    script_dir  = Path(sys.argv[0]).resolve().parent
    venv_dir    = script_dir / ".myscreen_venv"
    print(f"\n📁  Creating local venv at:\n    {venv_dir}\n")

    if subprocess.call([sys.executable, "-m", "venv", str(venv_dir)],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL) != 0:
        print("  ⚠️   venv failed — trying: apt install python3-venv python3-full")
        subprocess.call(
            ["sudo", "apt-get", "install", "-y", "python3-venv", "python3-full"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        subprocess.call([sys.executable, "-m", "venv", str(venv_dir)])

    venv_py = (
        str(venv_dir / "bin"     / "python") if (venv_dir / "bin").exists()
        else str(venv_dir / "Scripts" / "python.exe")
    )

    if _try_install(venv_py, pkgs):
        print("✅  All installed in venv!  Re-launching…\n")
        os.execv(venv_py, [venv_py] + sys.argv)

    # ── All strategies failed ──
    print("\n❌  Every auto-install strategy failed.")
    print("    Your network is probably timing out on package downloads.")
    print("    Fix: install manually using an existing venv, e.g.:\n")
    print("    # If you have another venv (like oblivion_env):")
    print(f"    /path/to/your/venv/bin/pip install {' '.join(pkgs)}")
    print(f"    /path/to/your/venv/bin/python3 \"{sys.argv[0]}\"\n")
    print("    # Or create a fresh venv:")
    print("    python3 -m venv .myscreen_venv")
    print("    source .myscreen_venv/bin/activate")
    print(f"    pip install {' '.join(pkgs)}")
    print(f"    python3 \"{sys.argv[0]}\"\n")
    sys.exit(1)


_bootstrap()
# ─────────────────────────────────────────────────────────────────────────────

import sys
import os
import cv2
import numpy as np
from pathlib import Path
from datetime import datetime

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QSlider, QFileDialog, QTabWidget,
    QScrollArea, QGridLayout, QSizePolicy, QFrame, QComboBox,
    QToolButton, QButtonGroup, QMessageBox, QStatusBar, QDialog,
    QTextEdit,
)
from PyQt6.QtCore import Qt, QPoint, QRect, QThread, pyqtSignal
from PyQt6.QtGui import (
    QPainter, QImage, QPixmap, QColor, QPen, QBrush,
    QFont, QPalette,
)

# ─────────────────────────────────────────────
APP_VERSION = "1.0.0"
BUILD_DATE  = "2026-03-15"
SAVE_DIR    = Path.home() / "Pictures" / "MyScreen Watermark Remover Edits"
SAVE_DIR.mkdir(parents=True, exist_ok=True)

PURPLE       = "#7c3aed"
PURPLE_LIGHT = "#a78bfa"
PURPLE_DIM   = "#2d2060"
BG_DEEP      = "#08080f"
BG_BASE      = "#0d0d18"
BG_CARD      = "#12121e"
BG_RAISED    = "#1a1a2e"
BORDER       = "#1e1e35"
BORDER_LIT   = "#2d2d55"
TEXT_MAIN    = "#e8e8f5"
TEXT_DIM     = "#888899"
TEXT_FAINT   = "#44445a"
RED_SOFT     = "#f87171"
RED_DIM      = "#2a1010"
RED_BORDER   = "#451515"
GREEN_SOFT   = "#4ade80"
GREEN_DIM    = "#0d2a1a"

APP_STYLE = f"""
* {{
    font-family: 'Segoe UI', 'SF Pro Display', 'Helvetica Neue', Arial, sans-serif;
    font-size: 13px;
    color: {TEXT_MAIN};
}}
QMainWindow, QWidget {{ background: {BG_DEEP}; }}
QTabWidget::pane {{ border: none; background: {BG_BASE}; }}
QTabBar {{ background: {BG_DEEP}; border-bottom: 1px solid {BORDER}; }}
QTabBar::tab {{
    background: transparent; color: {TEXT_DIM};
    padding: 11px 28px; border: none;
    border-bottom: 2px solid transparent;
    font-size: 13px; font-weight: 500; letter-spacing: 0.3px;
}}
QTabBar::tab:selected {{ color: {PURPLE_LIGHT}; border-bottom: 2px solid {PURPLE}; }}
QTabBar::tab:hover:!selected {{ color: #b8b8d0; background: {BG_RAISED}; }}
QPushButton {{
    background: {BG_RAISED}; color: {PURPLE_LIGHT};
    border: 1px solid {BORDER_LIT}; border-radius: 8px;
    padding: 8px 16px; font-size: 13px; font-weight: 500; min-height: 18px;
}}
QPushButton:hover {{ background: #20203c; border-color: {PURPLE}; color: #c4b5fd; }}
QPushButton:pressed {{ background: {PURPLE}; color: white; border-color: {PURPLE}; }}
QPushButton:disabled {{ background: {BG_CARD}; color: {TEXT_FAINT}; border-color: {BORDER}; }}
QPushButton#primary {{
    background: qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #7c3aed,stop:1 #6d28d9);
    color: white; border: none; font-weight: 600;
}}
QPushButton#primary:hover {{
    background: qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #8b5cf6,stop:1 #7c3aed);
}}
QPushButton#primary:pressed {{ background: #5b21b6; }}
QPushButton#danger {{
    background: {RED_DIM}; color: {RED_SOFT}; border: 1px solid {RED_BORDER};
}}
QPushButton#danger:hover {{ background: #3a1515; border-color: #ef4444; }}
QSlider::groove:horizontal {{ height: 3px; background: {BORDER_LIT}; border-radius: 2px; }}
QSlider::handle:horizontal {{
    background: {PURPLE_LIGHT}; width: 14px; height: 14px;
    margin: -6px 0; border-radius: 7px; border: 2px solid {BG_BASE};
}}
QSlider::sub-page:horizontal {{ background: {PURPLE}; border-radius: 2px; }}
QSlider::groove:vertical {{ width: 3px; background: {BORDER_LIT}; border-radius: 2px; }}
QSlider::handle:vertical {{
    background: {PURPLE_LIGHT}; width: 14px; height: 14px;
    margin: 0 -6px; border-radius: 7px; border: 2px solid {BG_BASE};
}}
QSlider::sub-page:vertical {{ background: {PURPLE}; border-radius: 2px; }}
QComboBox {{
    background: {BG_RAISED}; color: {PURPLE_LIGHT};
    border: 1px solid {BORDER_LIT}; border-radius: 7px;
    padding: 6px 12px; min-width: 130px;
}}
QComboBox::drop-down {{ subcontrol-origin: padding; subcontrol-position: right; width: 20px; border: none; }}
QComboBox QAbstractItemView {{
    background: {BG_RAISED}; color: {TEXT_MAIN};
    selection-background-color: {PURPLE};
    border: 1px solid {BORDER_LIT}; border-radius: 7px; padding: 4px; outline: none;
}}
QScrollArea {{ border: none; background: transparent; }}
QScrollBar:vertical {{ background: {BG_BASE}; width: 5px; border-radius: 3px; }}
QScrollBar::handle:vertical {{ background: {BORDER_LIT}; border-radius: 3px; min-height: 30px; }}
QScrollBar::handle:vertical:hover {{ background: {PURPLE}; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QScrollBar:horizontal {{ background: {BG_BASE}; height: 5px; border-radius: 3px; }}
QScrollBar::handle:horizontal {{ background: {BORDER_LIT}; border-radius: 3px; min-width: 30px; }}
QScrollBar::handle:horizontal:hover {{ background: {PURPLE}; }}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}
QStatusBar {{
    background: {BG_DEEP}; color: {TEXT_FAINT};
    border-top: 1px solid {BORDER}; font-size: 12px; padding: 0 12px;
}}
QToolButton {{
    background: transparent; border: 1px solid transparent;
    border-radius: 10px; padding: 0; color: {TEXT_DIM};
}}
QToolButton:hover {{ background: {BG_RAISED}; color: {PURPLE_LIGHT}; border-color: {BORDER_LIT}; }}
QToolButton:checked {{ background: {PURPLE_DIM}; color: {PURPLE_LIGHT}; border-color: {PURPLE}; }}
QLabel {{ background: transparent; }}
QMessageBox {{ background: {BG_RAISED}; }}
QMessageBox QPushButton {{ min-width: 80px; }}
QDialog {{ background: {BG_BASE}; }}
QTextEdit {{
    background: {BG_DEEP}; color: {GREEN_SOFT};
    border: 1px solid {BORDER_LIT}; border-radius: 8px;
    font-family: 'Consolas', 'Courier New', monospace;
    font-size: 12px; padding: 8px;
    selection-background-color: {PURPLE};
}}
"""


# ─── Helpers ──────────────────────────────────

def cv2_to_qimage(cv_img: np.ndarray) -> QImage:
    h, w = cv_img.shape[:2]
    if len(cv_img.shape) == 2:
        data = np.ascontiguousarray(cv_img)
        return QImage(data.tobytes(), w, h, w, QImage.Format.Format_Grayscale8).copy()
    rgb  = cv2.cvtColor(cv_img, cv2.COLOR_BGR2RGB)
    data = np.ascontiguousarray(rgb)
    return QImage(data.tobytes(), w, h, w * 3, QImage.Format.Format_RGB888).copy()


# ─── Inpaint Worker Thread ────────────────────

class InpaintWorker(QThread):
    finished = pyqtSignal(object)
    error    = pyqtSignal(str)

    def __init__(self, img: np.ndarray, mask: np.ndarray, radius: int = 3):
        super().__init__()
        self.img    = img
        self.mask   = mask
        self.radius = radius

    def run(self):
        try:
            result = cv2.inpaint(self.img, self.mask, self.radius, cv2.INPAINT_TELEA)
            self.finished.emit(result)
        except Exception as e:
            self.error.emit(str(e))


# ─── About Dialog ─────────────────────────────
#
#  Changelog is stored as (hex_tag, description) tuples.
#  Hit [DECODE] to reveal the decoded tag names — just a fun
#  lil easter egg for curious devs who poke around :3
#
_CHANGELOG = [
    ("v1.0.0", "2026-03-15", [
        ("0x494e4954",       "spawned the beast — first commit, dark mode only, obviously"),
        ("0x44524f50",       "drag & drop image support wired up, no more boring file dialogs"),
        ("0x544f4f4c53",     "brush + square + ellipse tools born, keyboard shortcuts added"),
        ("0x494e5041494e54", "OpenCV TELEA inpainting threaded — UI never freezes again"),
        ("0x47414c4c455259", "gallery tab shipped: sort, view, delete your edits"),
        ("0x424f4f5354",     "auto-dep bootstrap added — first-boot just works™"),
        ("0x41424f5554",     "the very about screen you are reading right now. meta af"),
        ("0x46495845534c4f54", "zoom reset, Ctrl+S/O shortcuts, save error handling"),
    ]),
]

def _hex_decode(h: str) -> str:
    try:
        return bytes.fromhex(h[2:]).decode()
    except Exception:
        return h


class AboutDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("About  ·  MyScreen Watermark Remover")
        self.setFixedSize(600, 570)
        self.setModal(True)
        self._decoded = False

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Banner ──
        banner = QFrame()
        banner.setFixedHeight(138)
        banner.setStyleSheet(f"""
            background: qlineargradient(x1:0,y1:0,x2:1,y2:1,
                stop:0 #0a0a18, stop:0.45 #180e35, stop:1 #0a0a18);
            border-bottom: 1px solid {BORDER_LIT};
        """)
        b_lay = QVBoxLayout(banner)
        b_lay.setContentsMargins(28, 16, 28, 14)
        b_lay.setSpacing(5)

        title_lbl = QLabel("🪄  MyScreen Watermark Remover")
        title_lbl.setStyleSheet(
            f"font-size: 21px; font-weight: 800; color: {PURPLE_LIGHT}; letter-spacing: -0.4px;"
        )
        b_lay.addWidget(title_lbl)

        ver_row = QHBoxLayout()
        ver_lbl = QLabel(f"v{APP_VERSION}  ·  built {BUILD_DATE}  ·  Python {sys.version.split()[0]}")
        ver_lbl.setStyleSheet(f"font-size: 11px; color: {TEXT_DIM};")
        ver_row.addWidget(ver_lbl)
        ver_row.addStretch()

        badge = QLabel("  ✨ STABLE  ")
        badge.setStyleSheet(f"""
            background: {GREEN_DIM}; color: {GREEN_SOFT};
            border: 1px solid #1a4a2a; border-radius: 5px;
            font-size: 10px; font-weight: 700; padding: 2px 4px;
        """)
        ver_row.addWidget(badge)
        b_lay.addLayout(ver_row)

        author_row = QHBoxLayout()
        author_lbl = QLabel("By  <b>HenryJay</b>")
        author_lbl.setStyleSheet(f"font-size: 13px; color: {TEXT_MAIN};")
        author_row.addWidget(author_lbl)
        author_row.addSpacing(14)

        contact_lbl = QLabel("✉  hnrycrm@gmail.com  :3")
        contact_lbl.setStyleSheet(f"font-size: 12px; color: {TEXT_DIM};")
        author_row.addWidget(contact_lbl)
        author_row.addStretch()
        b_lay.addLayout(author_row)

        root.addWidget(banner)

        # ── Body ──
        body = QWidget()
        body.setStyleSheet(f"background: {BG_BASE};")
        b2 = QVBoxLayout(body)
        b2.setContentsMargins(22, 16, 22, 16)
        b2.setSpacing(10)

        # Changelog header
        cl_hdr = QHBoxLayout()
        cl_title = QLabel("📋  CHANGELOG  //  COMMIT LOG")
        cl_title.setStyleSheet(
            f"font-size: 10px; font-weight: 700; color: {TEXT_FAINT}; letter-spacing: 1.3px;"
        )
        cl_hdr.addWidget(cl_title)
        cl_hdr.addStretch()

        self.decode_btn = QPushButton("  [ DECODE ]  ")
        self.decode_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; color: {GREEN_SOFT};
                border: 1px solid #1a4a2a; border-radius: 5px;
                font-family: 'Consolas', monospace;
                font-size: 10px; font-weight: 700;
                padding: 3px 10px;
            }}
            QPushButton:hover {{ background: {GREEN_DIM}; border-color: {GREEN_SOFT}; }}
        """)
        self.decode_btn.clicked.connect(self._toggle_decode)
        cl_hdr.addWidget(self.decode_btn)
        b2.addLayout(cl_hdr)

        self.cl_text = QTextEdit()
        self.cl_text.setReadOnly(True)
        self.cl_text.setFixedHeight(230)
        b2.addWidget(self.cl_text)

        # Tech stack row
        stack_frame = QFrame()
        stack_frame.setStyleSheet(f"""
            background: {BG_CARD}; border: 1px solid {BORDER}; border-radius: 10px;
        """)
        sf_lay = QHBoxLayout(stack_frame)
        sf_lay.setContentsMargins(14, 10, 14, 10)
        sf_lay.setSpacing(10)

        stack_title = QLabel("⚡ Stack")
        stack_title.setStyleSheet(
            f"color: {PURPLE_LIGHT}; font-weight: 700; font-size: 12px;"
        )
        sf_lay.addWidget(stack_title)

        chips = [
            ("Python 3",  "#3b82f6"),
            ("PyQt6",     "#8b5cf6"),
            ("OpenCV",    "#22c55e"),
            ("NumPy",     "#f59e0b"),
        ]
        for label, color in chips:
            chip = QLabel(f"  {label}  ")
            chip.setStyleSheet(f"""
                color: {color}; border: 1px solid {color}55;
                border-radius: 4px; font-size: 11px; font-weight: 600;
                padding: 2px 2px; background: transparent;
            """)
            sf_lay.addWidget(chip)

        sf_lay.addStretch()
        made_lbl = QLabel("made with ♥ in 2026")
        made_lbl.setStyleSheet(f"color: {TEXT_FAINT}; font-size: 11px;")
        sf_lay.addWidget(made_lbl)
        b2.addWidget(stack_frame)

        # Close button
        close_btn = QPushButton("  Close  ")
        close_btn.setObjectName("primary")
        close_btn.setFixedWidth(110)
        close_btn.clicked.connect(self.accept)
        b2.addWidget(close_btn, alignment=Qt.AlignmentFlag.AlignRight)

        root.addWidget(body)

        self._render_changelog(decoded=False)

    def _render_changelog(self, decoded: bool):
        lines = []
        for version, date, entries in _CHANGELOG:
            bar = "─" * max(2, 50 - len(version) - len(date))
            lines.append(f"┌─ {version}  ·  {date}  {bar}")
            for code, desc in entries:
                if decoded:
                    tag = f"[{_hex_decode(code).upper()}]"
                    lines.append(f"│  {tag:<18}  {desc}")
                else:
                    lines.append(f"│  {code:<26}  {desc[:44]}{'…' if len(desc)>44 else ''}")
            lines.append("└" + "─" * 58)
        self.cl_text.setPlainText("\n".join(lines))

    def _toggle_decode(self):
        self._decoded = not self._decoded
        self._render_changelog(self._decoded)
        if self._decoded:
            self.decode_btn.setText("  [ ENCODE ]  ")
            self.decode_btn.setStyleSheet(self.decode_btn.styleSheet()
                .replace(GREEN_SOFT, RED_SOFT)
                .replace("#1a4a2a", RED_BORDER)
                .replace(GREEN_DIM, RED_DIM))
        else:
            self.decode_btn.setText("  [ DECODE ]  ")
            self.decode_btn.setStyleSheet(self.decode_btn.styleSheet()
                .replace(RED_SOFT, GREEN_SOFT)
                .replace(RED_BORDER, "#1a4a2a")
                .replace(RED_DIM, GREEN_DIM))


# ─── Canvas Widget ────────────────────────────

class Canvas(QWidget):
    status_msg   = pyqtSignal(str)
    inpaint_done = pyqtSignal()
    busy_changed = pyqtSignal(bool)

    TOOL_BRUSH  = "brush"
    TOOL_SQUARE = "square"
    TOOL_CIRCLE = "circle"

    def __init__(self):
        super().__init__()
        self.setMinimumSize(400, 360)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setAcceptDrops(True)
        self.setMouseTracking(True)

        self.cv_original: np.ndarray | None = None
        self.cv_current:  np.ndarray | None = None
        self.mask:        np.ndarray | None = None
        self.qimage:      QImage    | None  = None

        self.scale  = 1.0
        self.offset = QPoint(0, 0)

        self.tool       = self.TOOL_BRUSH
        self.brush_size = 25

        self.drawing     = False
        self.last_pos:   QPoint | None = None
        self.drag_start: QPoint | None = None
        self.preview_rect: QRect | None = None

        self._worker: InpaintWorker | None = None
        self._busy = False

        self.setCursor(Qt.CursorShape.CrossCursor)

    # ── Image loading ──

    def load_image(self, path: str) -> bool:
        img = cv2.imread(path)
        if img is None:
            self.status_msg.emit(f"  ❌  Could not open: {Path(path).name}")
            return False
        self.cv_original = img
        self.cv_current  = img.copy()
        self.mask        = np.zeros(img.shape[:2], dtype=np.uint8)
        self.qimage      = cv2_to_qimage(img)
        self._fit()
        self.update()
        h, w    = img.shape[:2]
        size_kb = Path(path).stat().st_size // 1024
        self.status_msg.emit(
            f"  📂  {Path(path).name}   ·   {w} × {h} px   ·   {size_kb} KB"
        )
        return True

    # ── View helpers ──

    def _fit(self):
        if self.cv_original is None:
            return
        h, w = self.cv_original.shape[:2]
        wr = self.width()  / max(w, 1)
        hr = self.height() / max(h, 1)
        self.scale = min(wr, hr, 1.0) * 0.94
        self._recenter()

    def _recenter(self):
        if self.cv_original is None:
            return
        h, w = self.cv_original.shape[:2]
        iw, ih = int(w * self.scale), int(h * self.scale)
        self.offset = QPoint(
            (self.width()  - iw) // 2,
            (self.height() - ih) // 2,
        )

    def _widget_to_img(self, pos: QPoint) -> QPoint | None:
        if self.cv_original is None:
            return None
        h, w = self.cv_original.shape[:2]
        x = int((pos.x() - self.offset.x()) / self.scale)
        y = int((pos.y() - self.offset.y()) / self.scale)
        return QPoint(max(0, min(x, w - 1)), max(0, min(y, h - 1)))

    # ── Paint ──

    def paintEvent(self, _):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), QColor(BG_DEEP))

        if self.cv_original is None:
            self._paint_placeholder(painter)
            return

        h, w = self.cv_original.shape[:2]
        iw, ih = int(w * self.scale), int(h * self.scale)
        img_rect = QRect(self.offset.x(), self.offset.y(), iw, ih)

        self._paint_checker(painter, img_rect)
        painter.drawImage(img_rect, self.qimage)

        # Red mask overlay
        if self.mask is not None and self.mask.any():
            overlay = np.zeros((h, w, 4), dtype=np.uint8)
            overlay[self.mask > 0] = [255, 80, 80, 150]
            overlay_img = QImage(
                np.ascontiguousarray(overlay).tobytes(),
                w, h, w * 4, QImage.Format.Format_RGBA8888,
            )
            painter.drawImage(img_rect, overlay_img)

        # Shape preview while dragging (square/circle)
        if self.preview_rect and self.tool in (self.TOOL_SQUARE, self.TOOL_CIRCLE):
            r = self.preview_rect
            wr = QRect(
                int(r.x()      * self.scale) + self.offset.x(),
                int(r.y()      * self.scale) + self.offset.y(),
                int(r.width()  * self.scale),
                int(r.height() * self.scale),
            )
            painter.setPen(QPen(QColor(PURPLE_LIGHT), 2, Qt.PenStyle.DashLine))
            painter.setBrush(QBrush(QColor(167, 139, 250, 35)))
            if self.tool == self.TOOL_SQUARE:
                painter.drawRect(wr)
            else:
                painter.drawEllipse(wr)

        # Busy overlay
        if self._busy:
            painter.fillRect(self.rect(), QColor(0, 0, 0, 150))
            painter.setPen(QColor(PURPLE_LIGHT))
            painter.setFont(QFont("Segoe UI", 16, QFont.Weight.Medium))
            painter.drawText(
                self.rect(), Qt.AlignmentFlag.AlignCenter,
                "✨  Removing watermark…"
            )

    def _paint_placeholder(self, painter: QPainter):
        cx, cy = self.width() // 2, self.height() // 2
        bw, bh = 380, 230
        box = QRect(cx - bw // 2, cy - bh // 2, bw, bh)
        painter.setPen(QPen(QColor(BORDER_LIT), 1.5, Qt.PenStyle.DashLine))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(box, 18, 18)

        painter.setPen(QColor(PURPLE_LIGHT))
        painter.setFont(QFont("Segoe UI", 36))
        painter.drawText(
            QRect(cx - 30, cy - 72, 60, 58),
            Qt.AlignmentFlag.AlignCenter, "🪄"
        )

        painter.setFont(QFont("Segoe UI", 16, QFont.Weight.Medium))
        painter.setPen(QColor(TEXT_MAIN))
        painter.drawText(
            QRect(cx - 200, cy - 4, 400, 30),
            Qt.AlignmentFlag.AlignCenter, "Drop an image here"
        )

        painter.setFont(QFont("Segoe UI", 12))
        painter.setPen(QColor(TEXT_DIM))
        painter.drawText(
            QRect(cx - 200, cy + 30, 400, 24),
            Qt.AlignmentFlag.AlignCenter, "or click  📂 Open Image  below"
        )

        painter.setFont(QFont("Segoe UI", 11))
        painter.setPen(QColor(TEXT_FAINT))
        painter.drawText(
            QRect(cx - 200, cy + 62, 400, 22),
            Qt.AlignmentFlag.AlignCenter, "PNG · JPG · JPEG · BMP · WEBP"
        )

    def _paint_checker(self, painter: QPainter, rect: QRect):
        size = 10
        c1, c2 = QColor("#141420"), QColor("#1a1a2c")
        for row in range(rect.height() // size + 1):
            for col in range(rect.width() // size + 1):
                color = c1 if (row + col) % 2 == 0 else c2
                painter.fillRect(
                    rect.x() + col * size,
                    rect.y() + row * size,
                    min(size, rect.right()  - (rect.x() + col * size) + 1),
                    min(size, rect.bottom() - (rect.y() + row * size) + 1),
                    color,
                )

    # ── Mouse events ──

    def mousePressEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton:
            return
        if self.cv_original is None or self._busy:
            return
        self.drawing    = True
        self.drag_start = event.position().toPoint()
        if self.tool == self.TOOL_BRUSH:
            self._apply_brush(event.position().toPoint())
            self.last_pos = event.position().toPoint()

    def mouseMoveEvent(self, event):
        if not self.drawing or self.cv_original is None:
            return
        pos = event.position().toPoint()
        if self.tool == self.TOOL_BRUSH:
            self._stroke_brush(self.last_pos, pos)
            self.last_pos = pos
        else:
            self._update_preview(self.drag_start, pos)

    def mouseReleaseEvent(self, event):
        if not self.drawing:
            return
        self.drawing = False
        pos = event.position().toPoint()

        if self.tool in (self.TOOL_SQUARE, self.TOOL_CIRCLE) and self.drag_start:
            ip1 = self._widget_to_img(self.drag_start)
            ip2 = self._widget_to_img(pos)
            if ip1 and ip2:
                x1 = min(ip1.x(), ip2.x()); x2 = max(ip1.x(), ip2.x())
                y1 = min(ip1.y(), ip2.y()); y2 = max(ip1.y(), ip2.y())
                if self.tool == self.TOOL_SQUARE:
                    cv2.rectangle(self.mask, (x1, y1), (x2, y2), 255, -1)
                else:
                    cx = (x1 + x2) // 2
                    cy = (y1 + y2) // 2
                    rx = max(1, (x2 - x1) // 2)
                    ry = max(1, (y2 - y1) // 2)
                    cv2.ellipse(self.mask, (cx, cy), (rx, ry), 0, 0, 360, 255, -1)

        self.preview_rect = None
        self.last_pos     = None
        self.update()

    def wheelEvent(self, event):
        if self.cv_original is None:
            return
        factor = 1.12 if event.angleDelta().y() > 0 else 0.89
        self.scale = max(0.08, min(12.0, self.scale * factor))
        self._recenter()
        self.update()

    def resizeEvent(self, event):
        self._recenter()
        super().resizeEvent(event)

    # ── Drag & Drop ──

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        for url in event.mimeData().urls():
            path = url.toLocalFile()
            if path.lower().endswith((".png", ".jpg", ".jpeg", ".bmp", ".webp")):
                self.load_image(path)
                break

    # ── Drawing helpers ──

    def _apply_brush(self, pos: QPoint):
        ip = self._widget_to_img(pos)
        if ip and self.mask is not None:
            cv2.circle(self.mask, (ip.x(), ip.y()), self.brush_size, 255, -1)
            self.update()

    def _stroke_brush(self, p1: QPoint | None, p2: QPoint):
        if p1 is None:
            self._apply_brush(p2)
            return
        ip1 = self._widget_to_img(p1)
        ip2 = self._widget_to_img(p2)
        if ip1 and ip2 and self.mask is not None:
            cv2.line(
                self.mask,
                (ip1.x(), ip1.y()), (ip2.x(), ip2.y()),
                255, self.brush_size * 2,
            )
        self._apply_brush(p2)

    def _update_preview(self, start: QPoint | None, end: QPoint):
        if start is None:
            return
        ip1 = self._widget_to_img(start)
        ip2 = self._widget_to_img(end)
        if ip1 and ip2:
            x1 = min(ip1.x(), ip2.x()); x2 = max(ip1.x(), ip2.x())
            y1 = min(ip1.y(), ip2.y()); y2 = max(ip1.y(), ip2.y())
            self.preview_rect = QRect(x1, y1, x2 - x1, y2 - y1)
        self.update()

    # ── Public actions ──

    def clear_mask(self):
        if self.mask is not None:
            self.mask.fill(0)
            self.update()
            self.status_msg.emit("  🧹  Mask cleared")

    def reset_to_original(self):
        if self.cv_original is not None:
            self.cv_current = self.cv_original.copy()
            self.qimage     = cv2_to_qimage(self.cv_current)
            self.mask.fill(0)
            self.update()
            self.status_msg.emit("  ↩  Reset to original image")

    def do_inpaint(self):
        if self.cv_current is None:
            self.status_msg.emit("  ⚠️  No image loaded!")
            return
        if self.mask is None or not self.mask.any():
            self.status_msg.emit("  ⚠️  Paint over the watermark first!")
            return
        self._busy = True
        self.busy_changed.emit(True)
        self.update()
        self._worker = InpaintWorker(self.cv_current, self.mask)
        self._worker.finished.connect(self._on_inpaint_done)
        self._worker.error.connect(self._on_inpaint_error)
        self._worker.start()

    def _on_inpaint_done(self, result: np.ndarray):
        self.cv_current = result
        self.qimage     = cv2_to_qimage(result)
        self.mask.fill(0)
        self._busy = False
        self.busy_changed.emit(False)
        self.update()
        self.status_msg.emit("  ✨  Watermark removed!  Save to gallery when you're ready.")
        self.inpaint_done.emit()

    def _on_inpaint_error(self, msg: str):
        self._busy = False
        self.busy_changed.emit(False)
        self.update()
        self.status_msg.emit(f"  ❌  Inpaint error: {msg}")

    def save_result(self) -> Path | None:
        if self.cv_current is None:
            return None
        ts  = datetime.now().strftime("%Y%m%d_%H%M%S")
        out = SAVE_DIR / f"edit_{ts}.png"
        ok  = cv2.imwrite(str(out), self.cv_current)
        return out if ok else None


# ─── Gallery Thumbnail ────────────────────────

class GalleryThumb(QFrame):
    open_clicked   = pyqtSignal(str)
    delete_clicked = pyqtSignal(str)

    def __init__(self, path: str):
        super().__init__()
        self.path = path
        self.setFixedSize(192, 215)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setObjectName("thumb")
        self.setStyleSheet(f"""
            QFrame#thumb {{
                background: {BG_CARD};
                border: 1px solid {BORDER};
                border-radius: 14px;
            }}
            QFrame#thumb:hover {{
                border-color: {PURPLE};
                background: {BG_RAISED};
            }}
        """)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(5)

        self.img_label = QLabel()
        self.img_label.setFixedSize(176, 140)
        self.img_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.img_label.setStyleSheet(
            f"background: {BG_DEEP}; border-radius: 10px; border: none;"
        )

        pix = QPixmap(path)
        if not pix.isNull():
            pix = pix.scaled(
                176, 140,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            self.img_label.setPixmap(pix)
        else:
            self.img_label.setText("🖼")
            self.img_label.setFont(QFont("Segoe UI", 28))

        lay.addWidget(self.img_label)

        name     = Path(path).stem
        name_lbl = QLabel(name if len(name) <= 20 else name[:17] + "…")
        name_lbl.setStyleSheet(f"color: {TEXT_MAIN}; font-size: 11px; font-weight: 500;")
        name_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(name_lbl)

        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(4)

        mtime    = Path(path).stat().st_mtime
        date_str = datetime.fromtimestamp(mtime).strftime("%d %b %Y")
        date_lbl = QLabel(date_str)
        date_lbl.setStyleSheet(f"color: {TEXT_FAINT}; font-size: 10px;")
        row.addWidget(date_lbl)
        row.addStretch()

        del_btn = QPushButton("🗑")
        del_btn.setFixedSize(26, 22)
        del_btn.setStyleSheet(f"""
            QPushButton {{
                background: {RED_DIM}; color: {RED_SOFT};
                border: 1px solid {RED_BORDER}; border-radius: 6px;
                font-size: 11px; padding: 0;
            }}
            QPushButton:hover {{ background: #3a1515; }}
        """)
        del_btn.clicked.connect(lambda: self.delete_clicked.emit(self.path))
        row.addWidget(del_btn)
        lay.addLayout(row)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.open_clicked.emit(self.path)


# ─── Gallery View ─────────────────────────────

class GalleryView(QWidget):
    open_in_editor = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 18, 20, 18)
        root.setSpacing(14)

        hdr = QHBoxLayout()
        title = QLabel("My Edits")
        title.setStyleSheet(
            f"font-size: 20px; font-weight: 700; color: {PURPLE_LIGHT}; letter-spacing: -0.3px;"
        )
        hdr.addWidget(title)

        self.count_lbl = QLabel("")
        self.count_lbl.setStyleSheet(
            f"color: {TEXT_FAINT}; font-size: 12px; margin-left: 8px;"
        )
        hdr.addWidget(self.count_lbl)
        hdr.addStretch()

        sort_lbl = QLabel("Sort:")
        sort_lbl.setStyleSheet(f"color: {TEXT_DIM}; font-size: 12px;")
        hdr.addWidget(sort_lbl)

        self.sort_box = QComboBox()
        self.sort_box.addItems(["Newest First", "Oldest First", "Name A→Z", "Name Z→A"])
        self.sort_box.currentIndexChanged.connect(self.refresh)
        hdr.addWidget(self.sort_box)

        ref_btn = QPushButton("↻  Refresh")
        ref_btn.clicked.connect(self.refresh)
        hdr.addWidget(ref_btn)
        root.addLayout(hdr)

        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setStyleSheet(f"color: {BORDER};")
        root.addWidget(line)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.inner  = QWidget()
        self.grid   = QGridLayout(self.inner)
        self.grid.setSpacing(14)
        self.grid.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self.scroll.setWidget(self.inner)
        root.addWidget(self.scroll)

        self.empty_lbl = QLabel(
            "No edits yet 🎨\nRemove a watermark and save it to see it here!"
        )
        self.empty_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_lbl.setStyleSheet(
            f"color: {TEXT_FAINT}; font-size: 15px; line-height: 2;"
        )
        root.addWidget(self.empty_lbl)

        self.refresh()

    def refresh(self):
        while self.grid.count():
            item = self.grid.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        images = list(SAVE_DIR.glob("*.png")) + list(SAVE_DIR.glob("*.jpg"))

        idx = self.sort_box.currentIndex()
        if   idx == 0: images.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        elif idx == 1: images.sort(key=lambda p: p.stat().st_mtime)
        elif idx == 2: images.sort(key=lambda p: p.name.lower())
        elif idx == 3: images.sort(key=lambda p: p.name.lower(), reverse=True)

        n = len(images)
        self.count_lbl.setText(f"{n} edit{'s' if n != 1 else ''}")

        if not images:
            self.empty_lbl.show()
            self.scroll.hide()
            return

        self.empty_lbl.hide()
        self.scroll.show()

        cols = 5
        for i, p in enumerate(images):
            thumb = GalleryThumb(str(p))
            thumb.open_clicked.connect(self.open_in_editor.emit)
            thumb.delete_clicked.connect(self._delete)
            self.grid.addWidget(thumb, i // cols, i % cols)

    def _delete(self, path: str):
        ret = QMessageBox.question(
            self, "Delete edit?",
            f"Permanently delete  '{Path(path).name}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if ret == QMessageBox.StandardButton.Yes:
            Path(path).unlink(missing_ok=True)
            self.refresh()


# ─── Tool Button ──────────────────────────────

class ToolBtn(QToolButton):
    def __init__(self, emoji: str, label: str, tip: str):
        super().__init__()
        self.setCheckable(True)
        self.setFixedSize(52, 52)
        self.setToolTip(tip)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 6, 0, 4)
        lay.setSpacing(1)

        icon_lbl = QLabel(emoji)
        icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_lbl.setStyleSheet("font-size: 20px; background: transparent;")

        name_lbl = QLabel(label)
        name_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        name_lbl.setStyleSheet(
            f"font-size: 9px; color: {TEXT_DIM}; background: transparent;"
        )

        lay.addWidget(icon_lbl)
        lay.addWidget(name_lbl)


# ─── Main Window ──────────────────────────────

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("MyScreen Watermark Remover")
        self.setMinimumSize(1050, 680)
        self.resize(1280, 800)

        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── App header ──
        header = QFrame()
        header.setFixedHeight(52)
        header.setStyleSheet(
            f"background: {BG_DEEP}; border-bottom: 1px solid {BORDER};"
        )
        hdr_lay = QHBoxLayout(header)
        hdr_lay.setContentsMargins(20, 0, 20, 0)

        logo = QLabel("🪄  MyScreen Watermark Remover")
        logo.setStyleSheet(
            f"font-size: 15px; font-weight: 700; color: {PURPLE_LIGHT}; letter-spacing: -0.2px;"
        )
        hdr_lay.addWidget(logo)
        hdr_lay.addStretch()

        about_btn = QPushButton("ℹ  About")
        about_btn.setFixedHeight(30)
        about_btn.clicked.connect(self._show_about)
        hdr_lay.addWidget(about_btn)

        root.addWidget(header)

        # ── Tabs ──
        self.tabs = QTabWidget()
        root.addWidget(self.tabs)

        # ── Editor tab ──
        editor_widget = QWidget()
        ed_lay = QHBoxLayout(editor_widget)
        ed_lay.setContentsMargins(0, 0, 0, 0)
        ed_lay.setSpacing(0)

        # Left sidebar
        sidebar = QFrame()
        sidebar.setFixedWidth(74)
        sidebar.setStyleSheet(
            f"background: {BG_BASE}; border-right: 1px solid {BORDER};"
        )
        sb_lay = QVBoxLayout(sidebar)
        sb_lay.setContentsMargins(8, 14, 8, 14)
        sb_lay.setSpacing(4)
        sb_lay.setAlignment(Qt.AlignmentFlag.AlignTop)

        tools_label = QLabel("TOOLS")
        tools_label.setStyleSheet(
            f"color: {TEXT_FAINT}; font-size: 9px; font-weight: 700; letter-spacing: 1px;"
        )
        tools_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sb_lay.addWidget(tools_label)
        sb_lay.addSpacing(6)

        self.btn_brush  = ToolBtn("🖌", "Brush",  "Freehand brush  [B]")
        self.btn_square = ToolBtn("⬜", "Square", "Rectangle select  [R]")
        self.btn_circle = ToolBtn("⭕", "Circle", "Ellipse select  [E]")
        self.btn_brush.setChecked(True)

        self.tool_grp = QButtonGroup(self)
        self.tool_grp.setExclusive(True)
        for btn in [self.btn_brush, self.btn_square, self.btn_circle]:
            self.tool_grp.addButton(btn)
            sb_lay.addWidget(btn)

        self.btn_brush.clicked.connect(lambda: self._set_tool(Canvas.TOOL_BRUSH))
        self.btn_square.clicked.connect(lambda: self._set_tool(Canvas.TOOL_SQUARE))
        self.btn_circle.clicked.connect(lambda: self._set_tool(Canvas.TOOL_CIRCLE))

        div1 = QFrame()
        div1.setFrameShape(QFrame.Shape.HLine)
        div1.setStyleSheet(f"color: {BORDER};")
        sb_lay.addSpacing(6)
        sb_lay.addWidget(div1)
        sb_lay.addSpacing(6)

        size_lbl = QLabel("SIZE")
        size_lbl.setStyleSheet(
            f"color: {TEXT_FAINT}; font-size: 9px; font-weight: 700; letter-spacing: 1px;"
        )
        size_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sb_lay.addWidget(size_lbl)

        self.size_val = QLabel("25")
        self.size_val.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.size_val.setStyleSheet(
            f"color: {PURPLE_LIGHT}; font-size: 12px; font-weight: 600;"
        )
        sb_lay.addWidget(self.size_val)

        self.size_slider = QSlider(Qt.Orientation.Vertical)
        self.size_slider.setRange(2, 100)
        self.size_slider.setValue(25)
        self.size_slider.setFixedHeight(120)
        self.size_slider.valueChanged.connect(self._update_brush_size)
        sb_lay.addWidget(self.size_slider, alignment=Qt.AlignmentFlag.AlignHCenter)

        sb_lay.addStretch()

        div2 = QFrame()
        div2.setFrameShape(QFrame.Shape.HLine)
        div2.setStyleSheet(f"color: {BORDER};")
        sb_lay.addWidget(div2)
        sb_lay.addSpacing(4)

        zoom_lbl = QLabel("ZOOM")
        zoom_lbl.setStyleSheet(
            f"color: {TEXT_FAINT}; font-size: 9px; font-weight: 700; letter-spacing: 1px;"
        )
        zoom_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sb_lay.addWidget(zoom_lbl)

        _zoom_style = f"""
            QToolButton {{
                font-size: 16px; font-weight: 600;
                color: {TEXT_DIM}; background: transparent;
                border: 1px solid {BORDER}; border-radius: 7px;
            }}
            QToolButton:hover {{
                color: {PURPLE_LIGHT}; background: {BG_RAISED};
                border-color: {PURPLE};
            }}
        """
        zoom_in  = QToolButton(); zoom_in.setText("+");  zoom_in.setFixedSize(36, 28)
        zoom_out = QToolButton(); zoom_out.setText("−"); zoom_out.setFixedSize(36, 28)
        zoom_rst = QToolButton(); zoom_rst.setText("⊙"); zoom_rst.setFixedSize(36, 28)

        zoom_in.clicked.connect(lambda: self._zoom(1.25))
        zoom_out.clicked.connect(lambda: self._zoom(0.8))
        zoom_rst.clicked.connect(self._zoom_reset)

        for z in [zoom_in, zoom_out, zoom_rst]:
            z.setStyleSheet(_zoom_style)
            sb_lay.addWidget(z, alignment=Qt.AlignmentFlag.AlignHCenter)

        ed_lay.addWidget(sidebar)

        # Canvas area
        canvas_wrap = QWidget()
        cw_lay = QVBoxLayout(canvas_wrap)
        cw_lay.setContentsMargins(0, 0, 0, 0)
        cw_lay.setSpacing(0)

        self.canvas = Canvas()
        self.canvas.status_msg.connect(self._set_status)
        self.canvas.busy_changed.connect(self._set_busy)
        cw_lay.addWidget(self.canvas)

        # Bottom action bar
        bot = QFrame()
        bot.setFixedHeight(58)
        bot.setStyleSheet(
            f"background: {BG_BASE}; border-top: 1px solid {BORDER};"
        )
        bot_lay = QHBoxLayout(bot)
        bot_lay.setContentsMargins(16, 8, 16, 8)
        bot_lay.setSpacing(8)

        self.open_btn    = QPushButton("📂  Open Image")
        self.clear_btn   = QPushButton("🧹  Clear Mask")
        self.reset_btn   = QPushButton("↩  Reset")
        self.inpaint_btn = QPushButton("✨  Remove Watermark")
        self.save_btn    = QPushButton("💾  Save to Gallery")
        self.inpaint_btn.setObjectName("primary")

        self.open_btn.clicked.connect(self._open_image)
        self.clear_btn.clicked.connect(self.canvas.clear_mask)
        self.reset_btn.clicked.connect(self.canvas.reset_to_original)
        self.inpaint_btn.clicked.connect(self.canvas.do_inpaint)
        self.save_btn.clicked.connect(self._save_image)

        for btn in [self.open_btn, self.clear_btn, self.reset_btn]:
            bot_lay.addWidget(btn)
        bot_lay.addStretch()
        bot_lay.addWidget(self.inpaint_btn)
        bot_lay.addWidget(self.save_btn)

        cw_lay.addWidget(bot)
        ed_lay.addWidget(canvas_wrap)

        self.tabs.addTab(editor_widget, "🖼   Editor")

        # ── Gallery tab ──
        self.gallery = GalleryView()
        self.gallery.open_in_editor.connect(self._open_from_gallery)
        self.tabs.addTab(self.gallery, "🗂   Gallery")

        self.tabs.currentChanged.connect(self._on_tab_change)

        # ── Status bar ──
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self._set_status(
            "  ✨  Ready — open an image or drop one onto the canvas to get started!"
        )

    # ── Slots ──

    def _set_tool(self, tool: str):
        self.canvas.tool = tool

    def _update_brush_size(self, val: int):
        self.canvas.brush_size = val
        self.size_val.setText(str(val))

    def _set_status(self, msg: str):
        self.status_bar.showMessage(msg)

    def _set_busy(self, busy: bool):
        for w in [self.open_btn, self.clear_btn, self.reset_btn,
                  self.inpaint_btn, self.save_btn,
                  self.btn_brush, self.btn_square, self.btn_circle]:
            w.setEnabled(not busy)

    def _zoom(self, factor: float):
        self.canvas.scale = max(0.08, min(12.0, self.canvas.scale * factor))
        self.canvas._recenter()
        self.canvas.update()

    def _zoom_reset(self):
        self.canvas._fit()
        self.canvas.update()

    def _open_image(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Open Image",
            str(Path.home() / "Pictures"),
            "Images (*.png *.jpg *.jpeg *.bmp *.webp)",
        )
        if path:
            self.canvas.load_image(path)

    def _save_image(self):
        if self.canvas.cv_current is None:
            self._set_status("  ⚠️  No image to save!")
            return
        path = self.canvas.save_result()
        if path:
            self._set_status(f"  💾  Saved → {path}")
        else:
            self._set_status("  ❌  Save failed — check permissions on the Pictures folder")

    def _open_from_gallery(self, path: str):
        if self.canvas.load_image(path):
            self.tabs.setCurrentIndex(0)

    def _on_tab_change(self, idx: int):
        if idx == 1:
            self.gallery.refresh()

    def _show_about(self):
        AboutDialog(self).exec()

    def keyPressEvent(self, event):
        key  = event.key()
        mods = event.modifiers()
        if key == Qt.Key.Key_B:
            self.btn_brush.setChecked(True);  self._set_tool(Canvas.TOOL_BRUSH)
        elif key == Qt.Key.Key_R:
            self.btn_square.setChecked(True); self._set_tool(Canvas.TOOL_SQUARE)
        elif key == Qt.Key.Key_E:
            self.btn_circle.setChecked(True); self._set_tool(Canvas.TOOL_CIRCLE)
        elif key in (Qt.Key.Key_Delete, Qt.Key.Key_Escape):
            self.canvas.clear_mask()
        elif key == Qt.Key.Key_S and mods & Qt.KeyboardModifier.ControlModifier:
            self._save_image()
        elif key == Qt.Key.Key_O and mods & Qt.KeyboardModifier.ControlModifier:
            self._open_image()
        else:
            super().keyPressEvent(event)


# ─── Entry point ──────────────────────────────

def main():
    os.environ.setdefault("QT_AUTO_SCREEN_SCALE_FACTOR", "1")

    app = QApplication(sys.argv)
    app.setApplicationName("MyScreen Watermark Remover")
    app.setApplicationVersion(APP_VERSION)
    app.setStyle("Fusion")
    app.setStyleSheet(APP_STYLE)

    palette = app.palette()
    palette.setColor(QPalette.ColorRole.Window,          QColor(BG_DEEP))
    palette.setColor(QPalette.ColorRole.WindowText,      QColor(TEXT_MAIN))
    palette.setColor(QPalette.ColorRole.Base,            QColor(BG_BASE))
    palette.setColor(QPalette.ColorRole.AlternateBase,   QColor(BG_CARD))
    palette.setColor(QPalette.ColorRole.Text,            QColor(TEXT_MAIN))
    palette.setColor(QPalette.ColorRole.Button,          QColor(BG_RAISED))
    palette.setColor(QPalette.ColorRole.ButtonText,      QColor(PURPLE_LIGHT))
    palette.setColor(QPalette.ColorRole.Highlight,       QColor(PURPLE))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor("#ffffff"))
    palette.setColor(QPalette.ColorRole.ToolTipBase,     QColor(BG_RAISED))
    palette.setColor(QPalette.ColorRole.ToolTipText,     QColor(TEXT_MAIN))
    app.setPalette(palette)

    win = MainWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
