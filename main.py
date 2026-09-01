#!/usr/bin/env python3
# ╔══════════════════════════════════════════════════════════════╗
# ║        MyScreen Watermark Remover  v1.6  ·  by HenryJay      ║
# ║                 hnrycrm@gmail.com  :3                        ║
# ╚══════════════════════════════════════════════════════════════╝

# ─── BOOTSTRAP ────────────────────────────────────────────────────────────────
def _bootstrap():
    import importlib, subprocess, sys, os
    from pathlib import Path
    DEPS = {"cv2": "opencv-python", "numpy": "numpy", "PySide6": "PySide6"}
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
from ui import *

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
    app.setApplicationName("CelStudio Watermark Remover")
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
    app.setWindowIcon(get_app_icon())
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

