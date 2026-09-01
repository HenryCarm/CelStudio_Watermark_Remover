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
from .dialogs import *
from .panels import *
from .tabs import *
from .components import *

# ─── Main Window ──────────────────────────────────────────────────────────────

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("CelStudio Watermark Remover")
        self.setWindowIcon(get_app_icon())
        self.setMinimumSize(760, 540)
        self.resize(1220, 760)
        self._hbs: list[HelpBubble] = []
        self._s   = load_settings()
        self._kb  = self._s.get("keybinds", DEFAULT_SETTINGS["keybinds"])
        self._presets_visible = False
        self._build_ui()
        self._apply_settings_quiet()

    def _get_wallpaper_pixmap(self) -> QPixmap | None:
        wp_path = get_wallpaper_path()
        if not wp_path.exists():
            return None
        cache_key = str(wp_path)
        if not hasattr(self, "_wp_cache_key") or self._wp_cache_key != cache_key or not hasattr(self, "_cached_wp_pm"):
            self._wp_cache_key = cache_key
            self._cached_wp_pm = QPixmap(cache_key)
        return self._cached_wp_pm

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        s = self._s
        if s.get("wallpaper_enabled", True):
            pm = self._get_wallpaper_pixmap()
            if pm and not pm.isNull():
                rect = self.rect()
                mode = s.get("wallpaper_mode", "fill")
                if mode == "fill":
                    scaled = pm.scaled(rect.size(), Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation)
                    sx = max(0, (scaled.width() - rect.width()) // 2)
                    sy = max(0, (scaled.height() - rect.height()) // 2)
                    painter.drawPixmap(0, 0, scaled, sx, sy, rect.width(), rect.height())
                else:
                    scaled = pm.scaled(rect.size(), Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation)
                    painter.drawPixmap(0, 0, scaled)
                
                # Dark overlay tint (protects button / text contrast)
                tint_pct = max(0, min(95, s.get("wallpaper_tint", 65))) / 100.0
                tint_alpha = int(255 * tint_pct)
                painter.fillRect(rect, QColor(0, 0, 0, tint_alpha))
            else:
                painter.fillRect(self.rect(), QColor(BG_DEEP))
        else:
            painter.fillRect(self.rect(), QColor(BG_DEEP))
        super().paintEvent(event)

    # ── UI construction ───────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        central = QWidget()
        central.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        central.setStyleSheet("background: transparent;")
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Top bar: logo + tool pills + size + undo/redo + right actions ──────
        topbar = QFrame()
        topbar.setFixedHeight(44)
        topbar.setStyleSheet(
            f"background:rgba(12, 10, 24, 0.78);border-bottom:1px solid rgba(167, 139, 250, 0.22);")
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
        logo2 = QLabel("CelStudio Watermark Remover")
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
            ("🪄", "Smart Snap  [S]", BaseCanvas.TOOL_SMART,   "sb_tool"),
            ("🖌", "Brush  [B]",      BaseCanvas.TOOL_BRUSH,   "bb"),
            ("🧽", "Eraser  [X]",     BaseCanvas.TOOL_ERASER,  "eb"),
            ("▭",  "Rectangle  [R]",  BaseCanvas.TOOL_SQUARE,  "rb"),
            ("⭕", "Ellipse  [E]",    BaseCanvas.TOOL_CIRCLE,  "cb"),
            ("✋", "Pan / Move  [H]", BaseCanvas.TOOL_PAN,     "pb_tool"),
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

        # Mode picker (compact purple pill)
        self._lvl_box = QComboBox()
        self._lvl_box.setObjectName("lvl_box")
        self._lvl_box.addItems(["⚡ Quick", "🧠 Smart", "🔬 Precision", "✨ Cel AI"])
        saved_lvl = self._s.get("last_inpaint_level", self._s.get("default_level", 0))
        self._lvl_box.setCurrentIndex(saved_lvl)
        self._lvl_box.setFixedWidth(132)
        self._lvl_box.setFixedHeight(30)
        self._lvl_box.currentIndexChanged.connect(self._on_level_changed)
        mh = HelpBubble(
            "⚡ Quick — Fast TELEA. Good for small logos.\n\n"
            "🧠 Smart — Ring-by-ring fill. No blur on large areas.\n\n"
            "🔬 Precision — Exemplar Patch-Match.\n\n"
            "✨ Cel AI — Powerful 100% Offline AI Engine.\n"
            "   Multi-Scale Neural Structural Gradient Flow, Translucent De-Hazing & Texture Synthesis.\n"
            "   Runs locally on your device with 0 cloud dependencies & 100% privacy.")
        self._hbs.append(mh)
        mlayout = QHBoxLayout(); mlayout.setSpacing(3); mlayout.setContentsMargins(0,0,0,0)
        mlayout.addWidget(self._lvl_box); mlayout.addWidget(mh)
        tl.addLayout(mlayout)

        # Remove button moved to topbar right beside Method dropdown (green CTA)
        self._remove_btn = QPushButton("✨  Remove")
        self._remove_btn.setObjectName("remove_btn")
        self._remove_btn.setFixedHeight(30)
        self._remove_btn.setToolTip("Run inpainting on marked watermark area  [Ctrl+Enter / Space]")
        self._remove_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self._remove_btn.clicked.connect(self._do_inpaint)
        tl.addWidget(self._remove_btn)

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
        self._tabs.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._tabs.setStyleSheet(f"""
            QTabWidget {{ background: transparent; border: none; }}
            QTabWidget::pane {{ border: none; background: transparent; }}
            QTabBar {{
                background: rgba(10, 8, 20, 0.65);
                border-bottom: 1px solid rgba(167, 139, 250, 0.2);
            }}
            QTabBar::tab {{
                background: transparent; color: {TEXT_DIM};
                padding: 8px 18px; border: none;
                border-bottom: 2px solid transparent;
                font-size: 11px; font-weight: 600;
                min-width: 64px;
            }}
            QTabBar::tab:selected {{
                color: {PURPLE_LIGHT}; border-bottom: 2px solid {PURPLE};
                font-weight: 700;
                background: rgba(28, 14, 55, 0.85);
            }}
            QTabBar::tab:hover:!selected {{
                color: {TEXT_MAIN}; background: rgba(30, 22, 50, 0.6);
            }}
        """)
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
            f"background:rgba(12, 10, 24, 0.78);border-top:1px solid rgba(167, 139, 250, 0.22);")
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
        self._save_btn.clicked.connect(self._save_image)

        # Status bar
        self._sb = QStatusBar()
        self._sb.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._sb.setStyleSheet(f"""
            QStatusBar {{
                background: {BG_DEEP};
                color: {PURPLE_LIGHT};
                border-top: 1px solid {BORDER};
                font-size: 11px;
                font-weight: 500;
                padding: 0 8px;
            }}
            QStatusBar QLabel {{
                color: {PURPLE_LIGHT};
                background: transparent;
                font-weight: 500;
            }}
        """)
        self.setStatusBar(self._sb)
        self._set_status("  Ready — open an image or drop it onto the canvas")

    def _update_tasks_tab_title(self) -> None:
        cnt = TaskManager.instance().active_count()
        tab_txt = f"⏳  Files In Progress ({cnt})" if cnt > 0 else "⏳  Files In Progress"
        if self._tabs.count() >= 4:
            self._tabs.setTabText(3, tab_txt)

        # ── More menu ─────────────────────────────────────────────────────────────

    def _show_more_menu(self) -> None:
        from PySide6.QtWidgets import QMenu
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

    def _on_level_changed(self, idx: int) -> None:
        self._s["last_inpaint_level"] = idx
        self._s["default_level"] = idx
        save_settings(self._s)

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
            print(f"[ACTION] User requested image save (format: {fmt})")
            path = self.canvas.save_result(fmt=fmt)
            if path:
                self._set_status(f"  💾  Saved → {path.name}")
                try:
                    self._gv.refresh()
                except Exception:
                    pass
            else:
                # Open standard file save dialog if auto-save fails
                print("[SAVE FALLBACK] Opening File Save Dialog as fallback...")
                ext = fmt.lower().strip(".")
                default_name = f"edit_{datetime.now().strftime('%Y%m%d_%H%M%S')}.{ext}"
                save_dir = get_save_dir()
                chosen, _ = QFileDialog.getSaveFileName(
                    self, "Save Image As", str(save_dir / default_name),
                    f"{ext.upper()} Files (*.{ext});;All Files (*.*)")
                if chosen:
                    ok = cv2.imwrite(chosen, self.canvas.cv_cur)
                    if ok:
                        self._set_status(f"  💾  Saved → {Path(chosen).name}")
                        print(f"[SAVE SUCCESS] Saved via dialog to: {chosen}")
                        try:
                            self._gv.refresh()
                        except Exception:
                            pass
                    else:
                        self._set_status(f"  ❌  Could not write to {Path(chosen).name}")
                        print(f"[SAVE ERROR] Could not write to {chosen}")
                else:
                    self._set_status("  ⚠️  Save cancelled.")
        except Exception as exc:
            print(f"[SAVE EXCEPTION] {exc}\n{traceback.format_exc()}")
            self._set_status(f"  ❌  Save error: {exc}")

    def _open_save_folder(self) -> None:
        launch_system_file(str(get_save_dir()))

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
        if hasattr(self, "_cached_wp_pm"):
            delattr(self, "_cached_wp_pm")
        if hasattr(self, "_wp_cache_key"):
            delattr(self, "_wp_cache_key")
        self._kb = self._s.get("keybinds", DEFAULT_SETTINGS["keybinds"])
        self.canvas._max_undo = self._s.get("max_undo", 30)
        self.canvas.canvas_bg_opacity = self._s.get("canvas_bg_opacity", 67)
        if hasattr(self, "_vt") and hasattr(self._vt, "vc"):
            self._vt.vc._max_undo = self._s.get("max_undo", 30)
            self._vt.vc.canvas_bg_opacity = self._s.get("canvas_bg_opacity", 67)
        self._lvl_box.setCurrentIndex(self._s.get("last_inpaint_level", self._s.get("default_level", 0)))
        hv = self._s.get("tooltip_hover", 250)
        hd = self._s.get("tooltip_hide",  750)
        for bbl in self._hbs:
            bbl.hover_ms = hv
            bbl.hide_ms  = hd
        self.update()
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
                                         self._set_tool(BaseCanvas.TOOL_SMART))),
            ("brush",           lambda: (self._bb.setChecked(True),
                                         self._set_tool(BaseCanvas.TOOL_BRUSH))),
            ("eraser",          lambda: (self._eb.setChecked(True),
                                         self._set_tool(BaseCanvas.TOOL_ERASER))),
            ("rect",            lambda: (self._rb.setChecked(True),
                                         self._set_tool(BaseCanvas.TOOL_SQUARE))),
            ("ellipse",         lambda: (self._cb.setChecked(True),
                                         self._set_tool(BaseCanvas.TOOL_CIRCLE))),
            ("pan",             lambda: (self._pb_tool.setChecked(True),
                                         self._set_tool(BaseCanvas.TOOL_PAN))),
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

    def _active_canvas(self) -> "BaseCanvas | None":
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

