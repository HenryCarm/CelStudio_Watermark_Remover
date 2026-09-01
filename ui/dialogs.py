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
    applied = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.setWindowIcon(get_app_icon())
        self.setMinimumSize(680, 520)
        self.resize(680, 530)
        self.setModal(True)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(f"QDialog{{background:{BG_DEEP};color:{TEXT_MAIN};}} {APP_STYLE}")
        self._s  = load_settings()
        self._kw: dict[str, KeyCapture] = {}
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        tabs = QTabWidget()
        tabs.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        tabs.setStyleSheet(
            f"QTabWidget{{background:{BG_DEEP};border:none;}}"
            f"QTabWidget::pane{{border:1px solid {BORDER};background:{BG_BASE};}}"
            f"QTabBar{{background:{BG_DEEP};}}"
            f"QTabBar::tab{{background:{BG_DEEP};color:{TEXT_DIM};padding:8px 14px;font-weight:600;font-size:11px;border-bottom:2px solid transparent;}}"
            f"QTabBar::tab:selected{{background:{BG_BASE};color:{PURPLE_LIGHT};border-bottom:2px solid {PURPLE};font-weight:700;}}"
            f"QTabBar::tab:hover:!selected{{background:{BG_RAISED};color:{TEXT_MAIN};}}"
        )
        root.addWidget(tabs)
        tabs.addTab(self._kb_tab(),        "⌨️  Keybinds")
        tabs.addTab(self._editor_tab(),    "🖌️  Editor")
        tabs.addTab(self._ui_tab(),        "💬  Interface")
        tabs.addTab(self._video_tab(),     "🎬  Video")
        tabs.addTab(self._wallpaper_tab(), "🎨  Wallpaper")
        tabs.addTab(self._paths_tab(),     "📁  Paths")
        
        bot_bar = QFrame()
        bot_bar.setFixedHeight(46)
        bot_bar.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        bot_bar.setStyleSheet(f"background:{BG_DEEP};border-top:1px solid {BORDER};")
        br = QHBoxLayout(bot_bar)
        br.setContentsMargins(14, 8, 14, 8)
        br.setSpacing(8)
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
        root.addWidget(bot_bar)

    def _row(self) -> QWidget:
        w = QWidget()
        w.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        w.setStyleSheet(f"background:{BG_BASE};")
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
        w.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        w.setStyleSheet(f"background:{BG_BASE};")
        lay = QVBoxLayout(w)
        lay.setContentsMargins(18, 12, 18, 12)
        lay.setSpacing(10)

        # 1. Settings & presets folder
        l1 = QLabel("Settings & presets folder:")
        l1.setStyleSheet(f"color:{TEXT_MAIN};font-weight:600;font-size:11px;")
        lay.addWidget(l1)
        r1 = QHBoxLayout(); r1.setSpacing(6)
        self._data_edit = QLineEdit(str(self._s.get("custom_data_dir") or DATA_DIR))
        self._data_edit.setStyleSheet(f"background:{BG_DEEP};border:1px solid {BORDER_LIT};color:{PURPLE_LIGHT};padding:4px 8px;border-radius:5px;font-size:11px;")
        self._data_edit.textChanged.connect(lambda v: self._s.update({"custom_data_dir": v.strip()}))
        r1.addWidget(self._data_edit)
        b1 = QPushButton("📂  Browse…")
        b1.setObjectName("ghost")
        b1.setFixedHeight(28)
        b1.clicked.connect(self._browse_data_dir)
        r1.addWidget(b1)
        lay.addLayout(r1)

        # 2. Image & video saves folder
        l2 = QLabel("Image & video gallery saves folder:")
        l2.setStyleSheet(f"color:{TEXT_MAIN};font-weight:600;font-size:11px;")
        lay.addWidget(l2)
        r2 = QHBoxLayout(); r2.setSpacing(6)
        self._save_edit = QLineEdit(str(self._s.get("custom_save_dir") or SAVE_DIR))
        self._save_edit.setStyleSheet(f"background:{BG_DEEP};border:1px solid {BORDER_LIT};color:{PURPLE_LIGHT};padding:4px 8px;border-radius:5px;font-size:11px;")
        self._save_edit.textChanged.connect(lambda v: self._s.update({"custom_save_dir": v.strip()}))
        r2.addWidget(self._save_edit)
        b2 = QPushButton("📂  Browse…")
        b2.setObjectName("ghost")
        b2.setFixedHeight(28)
        b2.clicked.connect(self._browse_save_dir)
        r2.addWidget(b2)
        lay.addLayout(r2)

        # 3. Diagnostics logs folder
        l3 = QLabel("Diagnostics logs folder:")
        l3.setStyleSheet(f"color:{TEXT_MAIN};font-weight:600;font-size:11px;")
        lay.addWidget(l3)
        r3 = QHBoxLayout(); r3.setSpacing(6)
        self._log_edit = QLineEdit(str(self._s.get("custom_log_dir") or LOG_DIR))
        self._log_edit.setStyleSheet(f"background:{BG_DEEP};border:1px solid {BORDER_LIT};color:{PURPLE_LIGHT};padding:4px 8px;border-radius:5px;font-size:11px;")
        self._log_edit.textChanged.connect(lambda v: self._s.update({"custom_log_dir": v.strip()}))
        r3.addWidget(self._log_edit)
        b3 = QPushButton("📂  Browse…")
        b3.setObjectName("ghost")
        b3.setFixedHeight(28)
        b3.clicked.connect(self._browse_log_dir)
        r3.addWidget(b3)
        lay.addLayout(r3)

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
        open_log_btn.clicked.connect(lambda: launch_system_file(str(get_log_dir())))
        btn_r.addWidget(open_log_btn)
        lbl.addLayout(btn_r)

        lay.addWidget(log_box)
        lay.addStretch()
        return w

    def _browse_data_dir(self):
        curr = self._data_edit.text() or str(DATA_DIR)
        p = QFileDialog.getExistingDirectory(self, "Select Settings & Presets Folder", curr)
        if p:
            self._data_edit.setText(p)
            self._s["custom_data_dir"] = p

    def _browse_save_dir(self):
        curr = self._save_edit.text() or str(SAVE_DIR)
        p = QFileDialog.getExistingDirectory(self, "Select Image & Video Saves Folder", curr)
        if p:
            self._save_edit.setText(p)
            self._s["custom_save_dir"] = p

    def _browse_log_dir(self):
        curr = self._log_edit.text() or str(LOG_DIR)
        p = QFileDialog.getExistingDirectory(self, "Select Diagnostics Logs Folder", curr)
        if p:
            self._log_edit.setText(p)
            self._s["custom_log_dir"] = p

    def _wallpaper_tab(self) -> QWidget:
        w = QWidget()
        w.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        w.setStyleSheet(f"background:{BG_BASE};")
        lay = QVBoxLayout(w)
        lay.setContentsMargins(18, 14, 18, 14)
        lay.setSpacing(12)

        # 1. Enable wallpaper checkbox
        self._wp_enable_cb = QCheckBox("🖼  Enable custom wallpaper background")
        self._wp_enable_cb.setStyleSheet(f"color:{TEXT_MAIN};font-weight:700;font-size:12px;")
        self._wp_enable_cb.setChecked(self._s.get("wallpaper_enabled", True))
        self._wp_enable_cb.toggled.connect(lambda v: self._s.update({"wallpaper_enabled": v}))
        lay.addWidget(self._wp_enable_cb)

        # 2. Wallpaper path box
        box = QFrame()
        box.setStyleSheet(f"background:{BG_CARD};border:1px solid {BORDER};border-radius:8px;")
        bl = QVBoxLayout(box)
        bl.setContentsMargins(12, 10, 12, 10)
        bl.setSpacing(8)

        lbl = QLabel("Wallpaper image file (supports WebP, PNG, JPG):")
        lbl.setStyleSheet(f"color:{TEXT_DIM};font-size:11px;font-weight:600;")
        bl.addWidget(lbl)

        pr = QHBoxLayout(); pr.setSpacing(6)
        curr_wp = self._s.get("wallpaper_path", "")
        self._wp_path_edit = QLineEdit(curr_wp if curr_wp else str(WALLPAPER_PATH))
        self._wp_path_edit.setStyleSheet(f"background:{BG_DEEP};border:1px solid {BORDER_LIT};color:{PURPLE_LIGHT};padding:4px 8px;border-radius:5px;font-size:11px;")
        self._wp_path_edit.textChanged.connect(lambda v: self._s.update({"wallpaper_path": v.strip()}))
        pr.addWidget(self._wp_path_edit)

        browse_btn = QPushButton("📂  Browse…")
        browse_btn.setObjectName("ghost")
        browse_btn.setFixedHeight(28)
        browse_btn.clicked.connect(self._browse_wallpaper)
        pr.addWidget(browse_btn)

        reset_btn = QPushButton("↺ Default")
        reset_btn.setObjectName("ghost")
        reset_btn.setFixedHeight(28)
        reset_btn.clicked.connect(self._reset_wallpaper)
        pr.addWidget(reset_btn)
        bl.addLayout(pr)

        lay.addWidget(box)

        # 3. Scale Mode & Tint Slider Box
        box2 = QFrame()
        box2.setStyleSheet(f"background:{BG_CARD};border:1px solid {BORDER};border-radius:8px;")
        b2 = QVBoxLayout(box2)
        b2.setContentsMargins(12, 10, 12, 10)
        b2.setSpacing(10)

        # Scale Mode
        sr = QHBoxLayout()
        slbl = QLabel("Display scaling mode:")
        slbl.setStyleSheet(f"color:{TEXT_MAIN};font-weight:600;font-size:11px;")
        sr.addWidget(slbl)
        self._wp_mode_box = QComboBox()
        self._wp_mode_box.addItems(["Zoom to Fill (Crop to Window)", "Stretch to Window"])
        self._wp_mode_box.setCurrentIndex(0 if self._s.get("wallpaper_mode", "fill") == "fill" else 1)
        self._wp_mode_box.currentIndexChanged.connect(lambda idx: self._s.update({"wallpaper_mode": "fill" if idx == 0 else "stretch"}))
        sr.addWidget(self._wp_mode_box)
        sr.addStretch()
        b2.addLayout(sr)

        # Black overlay tint slider
        tr = QHBoxLayout()
        tlbl = QLabel("Dark overlay tint (protects text contrast):")
        tlbl.setStyleSheet(f"color:{TEXT_MAIN};font-weight:600;font-size:11px;")
        tr.addWidget(tlbl)
        self._tint_val_lbl = QLabel(f"{self._s.get('wallpaper_tint', 33)}%")
        self._tint_val_lbl.setStyleSheet(f"color:{PURPLE_LIGHT};font-weight:700;font-size:11px;min-width:32px;")
        tr.addWidget(self._tint_val_lbl)
        tr.addStretch()
        b2.addLayout(tr)

        self._tint_sl = QSlider(Qt.Orientation.Horizontal)
        self._tint_sl.setRange(0, 95)
        self._tint_sl.setValue(self._s.get("wallpaper_tint", 33))
        self._tint_sl.valueChanged.connect(self._on_tint_changed)
        b2.addWidget(self._tint_sl)

        hint = QLabel("💡 Tip: A 60%–75% dark tint provides a gorgeous liquid glass aesthetic while keeping all buttons and canvas tools crystal clear.")
        hint.setWordWrap(True)
        hint.setStyleSheet(f"color:{TEXT_FAINT};font-size:10px;")
        b2.addWidget(hint)
        # Canvas Background Opacity Slider
        cr = QHBoxLayout()
        clbl = QLabel("Canvas Background Opacity (Void intensity):")
        clbl.setStyleSheet(f"color:{TEXT_MAIN};font-weight:600;font-size:11px;")
        cr.addWidget(clbl)
        self._canvas_op_val_lbl = QLabel(f"{self._s.get('canvas_bg_opacity', 67)}%")
        self._canvas_op_val_lbl.setStyleSheet(f"color:{PURPLE_LIGHT};font-weight:700;font-size:11px;min-width:32px;")
        cr.addWidget(self._canvas_op_val_lbl)
        cr.addStretch()
        b2.addLayout(cr)

        self._canvas_op_sl = QSlider(Qt.Orientation.Horizontal)
        self._canvas_op_sl.setRange(0, 100)
        self._canvas_op_sl.setValue(self._s.get("canvas_bg_opacity", 67))
        self._canvas_op_sl.valueChanged.connect(self._on_canvas_op_changed)
        b2.addWidget(self._canvas_op_sl)

        lay.addWidget(box2)
        lay.addStretch()
        return w

    def _browse_wallpaper(self):
        last_dir = str(Path.home() / "Pictures")
        chosen, _ = QFileDialog.getOpenFileName(
            self, "Select Wallpaper Image", last_dir,
            "Images (*.webp *.png *.jpg *.jpeg *.bmp)")
        if chosen:
            self._wp_path_edit.setText(chosen)
            self._s["wallpaper_path"] = chosen

    def _reset_wallpaper(self):
        self._wp_path_edit.setText(str(WALLPAPER_PATH))
        self._s["wallpaper_path"] = ""

    def _on_tint_changed(self, v: int):
        self._tint_val_lbl.setText(f"{v}%")
        self._s["wallpaper_tint"] = v

    def _on_canvas_op_changed(self, v: int):
        self._canvas_op_val_lbl.setText(f"{v}%")
        self._s["canvas_bg_opacity"] = v

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
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(f"QDialog{{background:{BG_DEEP};color:{TEXT_MAIN};}} {APP_STYLE}")
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
        self.setWindowIcon(get_app_icon())
        self.setFixedSize(560, 540)
        self.setModal(True)
        self._dec = False
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        # Banner
        banner_container = QFrame()
        banner_container.setFixedHeight(134)
        banner_container.setStyleSheet(f"background:{BG_DEEP};border-bottom:1px solid {BORDER_LIT};")
        bl = QVBoxLayout(banner_container)
        bl.setContentsMargins(0, 0, 0, 0)
        bl.setSpacing(0)

        if BANNER_PATH.exists():
            banner_img = QLabel()
            banner_img.setFixedHeight(104)
            pm = QPixmap(str(BANNER_PATH)).scaled(560, 104, Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation)
            banner_img.setPixmap(pm)
            banner_img.setAlignment(Qt.AlignmentFlag.AlignCenter)
            bl.addWidget(banner_img)
        else:
            thdr = QHBoxLayout()
            thdr.setContentsMargins(14, 10, 14, 10)
            if ICON_PATH.exists():
                icon_lbl = QLabel()
                pm = QPixmap(str(ICON_PATH)).scaled(32, 32, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
                icon_lbl.setPixmap(pm)
                thdr.addWidget(icon_lbl)
            tl = QLabel("CelStudio Watermark Remover")
            tl.setStyleSheet(f"font-size:17px;font-weight:800;color:{PURPLE_LIGHT};letter-spacing:-0.3px;")
            thdr.addWidget(tl); thdr.addStretch()
            bl.addLayout(thdr)

        meta_bar = QWidget()
        meta_bar.setStyleSheet(f"background:rgba(9, 9, 15, 0.95);")
        meta_lay = QHBoxLayout(meta_bar)
        meta_lay.setContentsMargins(14, 3, 14, 3)

        vl = QLabel(f"v{APP_VERSION}  ·  {BUILD_DATE}  ·  <i>(Formerly MyScreen WR 🪄)</i>")
        vl.setStyleSheet("font-size:10px;color:#e2e8f0;")
        meta_lay.addWidget(vl)
        meta_lay.addStretch()

        auth_lbl = QLabel("By  <b style='color:#ffffff;'>Henry Jay C</b>")
        auth_lbl.setStyleSheet("color:#ffffff;font-size:10px;margin-right:6px;")
        meta_lay.addWidget(auth_lbl)

        bg = QLabel("  ✨ STABLE  ")
        bg.setStyleSheet(
            f"background:{GREEN_DIM};color:{GREEN_SOFT};"
            f"border:1px solid #1a3d28;border-radius:4px;"
            f"font-size:9px;font-weight:700;padding:1px 4px;")
        meta_lay.addWidget(bg)

        self._top_log_cb = QCheckBox("📝 Live Log")
        self._top_log_cb.setStyleSheet("color:#ffffff;font-size:10px;font-weight:600;margin-left:6px;")
        _s = load_settings()
        self._top_log_cb.setChecked(_s.get("live_logging", False))
        self._top_log_cb.toggled.connect(self._on_log_toggled)
        meta_lay.addWidget(self._top_log_cb)

        bl.addWidget(meta_bar)
        root.addWidget(banner_container)
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
        for lbl, col in [("Python 3", "#3b82f6"), ("PySide6", "#8b5cf6"),
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
        self.setWindowIcon(get_app_icon())
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

