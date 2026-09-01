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
from .components import *

# ─── Presets panel (slide-out) ────────────────────────────────────────────────

class PresetsPanel(QFrame):
    apply_preset  = Signal(dict)
    add_requested = Signal()

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
            "CelStudio Watermark Remover/")
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
        icons = {0: "⚡", 1: "🧠", 2: "🔬", 3: "✨"}
        for p in ps:
            lvl = p.get("level", 0)
            it = QListWidgetItem(
                f"{icons.get(lvl, '✨')}  {p['name']}")
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
    updated = Signal()
    finished = Signal(str)
    error = Signal(str)

    def __init__(self, task_id: str, title: str, src_path: str, dst_path: str,
                 method: str, mode_name: str, total_frames: int, worker: "VideoWorker" = None):
        super().__init__()
        self.task_id = task_id
        self.title = title
        self.src_path = src_path
        self.dst_path = dst_path
        self.method = method
        self.mode_name = mode_name
        self.total_frames = max(1, total_frames)
        self.current_frame = 0
        self.status = "running"   # "running", "paused", "completed", "error", "cancelled"
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
        TaskManager.instance().tasks_updated.emit()

    def _on_error(self, err: str):
        self.status = "error"
        self.err_msg = err
        self.end_time = datetime.now()
        self.updated.emit()
        self.error.emit(err)
        TaskManager.instance().tasks_updated.emit()

    def toggle_pause(self):
        if self.status == "running":
            if self.worker is not None:
                self.worker.pause()
            self.status = "paused"
            self.updated.emit()
            TaskManager.instance().tasks_updated.emit()
        elif self.status == "paused":
            if self.worker is not None:
                self.worker.resume()
            self.status = "running"
            self.updated.emit()
            TaskManager.instance().tasks_updated.emit()

    def pause(self):
        if self.status == "running":
            if self.worker is not None:
                self.worker.pause()
            self.status = "paused"
            self.updated.emit()
            TaskManager.instance().tasks_updated.emit()

    def resume(self):
        if self.status == "paused":
            if self.worker is not None:
                self.worker.resume()
            self.status = "running"
            self.updated.emit()
            TaskManager.instance().tasks_updated.emit()

    def cancel(self):
        if self.status in ("running", "paused"):
            if self.worker is not None:
                self.worker.stop()
            self.status = "cancelled"
            self.end_time = datetime.now()
            self.updated.emit()
            TaskManager.instance().tasks_updated.emit()


class TaskManager(QObject):
    task_added = Signal(object)
    tasks_updated = Signal()

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
        worker.start()
        self.task_added.emit(item)
        self.tasks_updated.emit()
        return item

    def active_count(self) -> int:
        return sum(1 for t in self.tasks if t.status in ("running", "paused"))

    def clear_completed(self):
        self.tasks = [t for t in self.tasks if t.status in ("running", "paused")]
        self.tasks_updated.emit()

    def cancel_all(self):
        for t in self.tasks:
            if t.status in ("running", "paused"):
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

        self._pause_btn = QPushButton("⏸  Pause")
        self._pause_btn.setObjectName("ghost")
        self._pause_btn.setFixedHeight(26)
        self._pause_btn.setStyleSheet(f"color:{ORANGE_SOFT};border:1px solid {ORANGE_SOFT};background:transparent;padding:2px 8px;border-radius:4px;font-size:11px;")
        self._pause_btn.clicked.connect(self.task.toggle_pause)
        act_r.addWidget(self._pause_btn)

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
            self._pause_btn.setText("⏸  Pause")
            self._pause_btn.setStyleSheet(f"color:{ORANGE_SOFT};border:1px solid {ORANGE_SOFT};background:transparent;padding:2px 8px;border-radius:4px;font-size:11px;")
            self._pause_btn.show()
            self._can_btn.show()
            self._play_btn.hide()
            self._open_btn.hide()
        elif self.task.status == "paused":
            self._stats_lbl.setText(
                f"⏸ PAUSED at frame {cur:,} / {tot:,}  ({pct}%)   ·   ⏱ Elapsed: {el_str}")
            self._status_badge.setText("⏸  Paused")
            self._status_badge.setStyleSheet(
                f"color:{ORANGE_SOFT};font-weight:700;font-size:11px;background:{ORANGE_DIM};"
                f"padding:3px 8px;border-radius:5px;border:1px solid {ORANGE_SOFT};")
            self._pause_btn.setText("▶  Resume")
            self._pause_btn.setStyleSheet(f"color:{GREEN_SOFT};border:1px solid {GREEN_SOFT};background:transparent;padding:2px 8px;border-radius:4px;font-size:11px;")
            self._pause_btn.show()
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
            self._pause_btn.hide()
            self._can_btn.hide()
            self._play_btn.show()
            self._open_btn.show()
        elif self.task.status == "cancelled":
            self._stats_lbl.setText(f"⛔ Cancelled at frame {cur:,} of {tot:,}.")
            self._status_badge.setText("⛔  Cancelled")
            self._status_badge.setStyleSheet(
                f"color:{RED_ACCENT};font-weight:700;font-size:11px;background:#2d1115;"
                f"padding:3px 8px;border-radius:5px;border:1px solid {RED_ACCENT};")
            self._pause_btn.hide()
            self._can_btn.hide()
            self._play_btn.hide()
            self._open_btn.hide()
        elif self.task.status == "error":
            self._stats_lbl.setText(f"❌ Error: {self.task.err_msg[:60]}")
            self._status_badge.setText("❌  Error")
            self._status_badge.setStyleSheet(
                f"color:{RED_ACCENT};font-weight:700;font-size:11px;background:#2d1115;"
                f"padding:3px 8px;border-radius:5px;border:1px solid {RED_ACCENT};")
            self._pause_btn.hide()
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
        self._cards: dict[str, TaskCard] = {}
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

        TaskManager.instance().tasks_updated.connect(self.sync_tasks)
        TaskManager.instance().task_added.connect(self._on_task_added)
        self.sync_tasks()

    def _on_task_added(self, task: TaskItem):
        self.sync_tasks()

    def sync_tasks(self):
        tasks = TaskManager.instance().tasks
        current_ids = {t.task_id for t in tasks}

        # Remove cards for tasks that were cleared/removed
        for tid in list(self._cards.keys()):
            if tid not in current_ids:
                card = self._cards.pop(tid)
                self._vbox.removeWidget(card)
                card.deleteLater()

        # Add any new tasks without destroying existing cards!
        for i, t in enumerate(tasks):
            if t.task_id not in self._cards:
                card = TaskCard(t)
                self._cards[t.task_id] = card
                self._vbox.insertWidget(i, card)

        running = sum(1 for t in tasks if t.status == "running")
        paused = sum(1 for t in tasks if t.status == "paused")
        done = sum(1 for t in tasks if t.status == "completed")
        pause_txt = f"  ·  {paused} paused" if paused > 0 else ""
        self._cnt_lbl.setText(f"·  {running} running{pause_txt}  ·  {done} completed")

        if not tasks:
            self._empty_lbl.show()
            self._sc.hide()
        else:
            self._empty_lbl.hide()
            self._sc.show()

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

