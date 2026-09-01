import sys, os, json, base64, traceback, shutil, subprocess, time, signal, threading
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
                self.log_dir = get_log_dir()
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
                print(f"[LOGGER] Live diagnostic logging started at {self.log_path}")
            except Exception as e:
                self._stdout.write(f"Failed to enable live logging: {e}\n")

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

def install_hard_crash_handler():
    """Installs a strict global crash handler that catches any error, writes full traceback to a log file, and immediately hard-crashes."""
    def _handle_exception(exc_type, exc_value, exc_tb):
        try:
            log_dir = get_log_dir()
            log_dir.mkdir(parents=True, exist_ok=True)
            ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            crash_file = log_dir / f"CRASH_{ts}.log"
            tb_str = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
            
            crash_msg = (
                f"\n======================= [FATAL CRASH DUMP] =======================\n"
                f"Timestamp: {datetime.now().isoformat()}\n"
                f"Error Type: {getattr(exc_type, '__name__', str(exc_type))}\n"
                f"Error Message: {exc_value}\n\n"
                f"Traceback:\n{tb_str}\n"
                f"Dumped To: {crash_file}\n"
                f"==================================================================\n"
            )
            with open(crash_file, "w", encoding="utf-8") as f:
                f.write(crash_msg)
        except Exception:
            pass
            
        sys.stderr.write(crash_msg if 'crash_msg' in locals() else f"Fatal error: {exc_value}\n")
        sys.stderr.flush()
        os._exit(1)
        
    sys.excepthook = _handle_exception
    if hasattr(threading, "excepthook"):
        threading.excepthook = lambda args: _handle_exception(args.exc_type, args.exc_value, args.exc_traceback)
    return _handle_exception


