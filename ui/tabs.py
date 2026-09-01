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
from .canvas import *
from .components import *

# ─── Video Tab ────────────────────────────────────────────────────────────────

class VideoTab(QWidget):
    status_msg = Signal(str)

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
        level = self._lb2.currentIndex()
        level_tags = {LEVEL_QUICK: "Quick", LEVEL_SMART: "Smart",
                      LEVEL_PRECISION: "Precision", LEVEL_CEL_AI: "Cel_AI"}
        lvl_tag = level_tags.get(level, "Cel_AI")
        src_stem = Path(self._vpath).stem if self._vpath else "video"
        ts = datetime.now().strftime('%Y%m%d_%H%M%S')
        save_dir = get_save_dir()
        save_dir.mkdir(parents=True, exist_ok=True)
        out = str(save_dir / f"{src_stem}_{lvl_tag}_{ts}.{ext}")

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
    open_clicked   = Signal(str)
    delete_clicked = Signal(str)

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
    open_in_editor = Signal(str)

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

