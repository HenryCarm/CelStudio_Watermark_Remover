#!/usr/bin/env python3
# ╔══════════════════════════════════════════════════════════════╗
# ║        MyScreen Watermark Remover  ·  Gem's Edition 💖       ║
# ║               Made exclusively for Henny :3                  ║
# ╚══════════════════════════════════════════════════════════════╝

def _bootstrap():
    import importlib, importlib.util, subprocess, sys, os
    from pathlib import Path
    DEPS = {"cv2": "opencv-python", "numpy": "numpy", "PyQt6": "PyQt6"}
    MIRRORS = [None, "https://pypi.tuna.tsinghua.edu.cn/simple"]
    
    def _missing():
        return [pkg for mod, pkg in DEPS.items() if not importlib.util.find_spec(mod)]

    pkgs = _missing()
    if not pkgs: return
    
    print("\n💖 Gem's First-Boot Setup for Henny! 💖")
    for p in pkgs: print(f"📦 Installing {p}...")
    
    for mirror in MIRRORS:
        cmd = [sys.executable, "-m", "pip", "install", "--quiet"] + (["--index-url", mirror] if mirror else []) + pkgs
        if subprocess.call(cmd, stdout=subprocess.DEVNULL) == 0:
            print("✅ Done! Restarting...\n")
            os.execv(sys.executable, [sys.executable] + sys.argv)
    sys.exit(1)

_bootstrap()

import sys, os, json, cv2, numpy as np
from pathlib import Path
from datetime import datetime
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QSlider, QFileDialog, QTabWidget, QScrollArea, QGridLayout, 
    QSizePolicy, QFrame, QComboBox, QToolButton, QButtonGroup, QMessageBox, QStatusBar, 
    QDialog, QTextEdit, QLineEdit, QDoubleSpinBox, QListWidget, QListWidgetItem)
from PyQt6.QtCore import Qt, QPoint, QRect, QThread, pyqtSignal
from PyQt6.QtGui import QPainter, QImage, QPixmap, QColor, QPen, QBrush, QFont, QPalette, QCursor

APP_VERSION  = "2.1.0-Gem-Fixed"
BUILD_DATE   = "2026-03-15"
SAVE_DIR     = Path.home() / "Pictures" / "MyScreen Watermark Remover Edits"
SAVE_DIR.mkdir(parents=True, exist_ok=True)
PRESETS_FILE = SAVE_DIR / "presets.json"

# 💖 GEM'S HOT PINK AESTHETIC 💖
PINK         = "#ec4899"
PINK_LIGHT   = "#f472b6"
PINK_DIM     = "#501a35"
BG_DEEP      = "#0a0508"
BG_BASE      = "#120910"
BG_CARD      = "#1a0d17"
BG_RAISED    = "#261322"
BORDER       = "#3d1b2f"
BORDER_LIT   = "#5c2a47"
TEXT_MAIN    = "#fae8f0"
TEXT_DIM     = "#a38896"
TEXT_FAINT   = "#6e5261"
GREEN_SOFT   = "#4ade80"

APP_STYLE = f"""
* {{ font-family: 'Segoe UI', Arial, sans-serif; font-size: 13px; color: {TEXT_MAIN}; }}
QMainWindow, QWidget {{ background: {BG_DEEP}; }}
QTabWidget::pane {{ border: none; background: {BG_BASE}; }}
QTabBar {{ background: {BG_DEEP}; border-bottom: 1px solid {BORDER}; }}
QTabBar::tab {{ background: transparent; color: {TEXT_DIM}; padding: 11px 28px; border: none; font-weight: 500; }}
QTabBar::tab:selected {{ color: {PINK_LIGHT}; border-bottom: 2px solid {PINK}; }}
QTabBar::tab:hover:!selected {{ color: #ffd6e8; background: {BG_RAISED}; }}
QPushButton {{ background: {BG_RAISED}; color: {TEXT_MAIN}; border: 1.5px solid {BORDER_LIT}; border-radius: 8px; padding: 8px 18px; font-weight: 600; }}
QPushButton:hover {{ background: #381b31; border-color: {PINK_LIGHT}; color: #ffffff; }}
QPushButton#primary {{ background: qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 #db2777, stop:1 #be185d); color: #ffffff; border: 2px solid #f472b6; border-radius: 9px; font-weight: 700; }}
QPushButton#primary:hover {{ background: #ec4899; border-color: #fbcfe8; }}
QSlider::groove:vertical {{ width: 3px; background: {BORDER_LIT}; border-radius: 2px; }}
QSlider::handle:vertical {{ background: {PINK_LIGHT}; width: 14px; height: 14px; margin: 0 -6px; border-radius: 7px; border: 2px solid {BG_BASE}; }}
QSlider::sub-page:vertical {{ background: {PINK}; border-radius: 2px; }}
QComboBox {{ background: {BG_RAISED}; color: {TEXT_MAIN}; border: 1.5px solid {BORDER_LIT}; border-radius: 7px; padding: 6px 12px; }}
QComboBox:hover {{ border-color: {PINK_LIGHT}; }}
QToolButton:checked {{ background: {PINK_DIM}; color: {PINK_LIGHT}; border-color: {PINK}; }}
QListWidget::item:selected {{ background: {PINK_DIM}; color: {PINK_LIGHT}; border: none; }}
QStatusBar {{ background: {BG_DEEP}; color: {TEXT_DIM}; border-top: 1px solid {BORDER}; }}
"""

LEVEL_QUICK     = 0
LEVEL_SMART     = 1
LEVEL_PRECISION = 2

def cv2_to_qimage(cv_img: np.ndarray) -> QImage:
    h, w = cv_img.shape[:2]
    if len(cv_img.shape) == 2: return QImage(cv_img.data, w, h, w, QImage.Format.Format_Grayscale8).copy()
    return QImage(cv2.cvtColor(cv_img, cv2.COLOR_BGR2RGB).data, w, h, w * 3, QImage.Format.Format_RGB888).copy()

def _inpaint_quick(img: np.ndarray, mask: np.ndarray) -> np.ndarray:
    return cv2.inpaint(img, mask, 3, cv2.INPAINT_TELEA)

def _inpaint_smart(img: np.ndarray, mask: np.ndarray, progress_cb=None) -> np.ndarray:
    result = img.copy()
    remaining = (mask > 0).astype(np.uint8)
    se = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7))
    rings = []
    current = remaining.copy()
    while current.any():
        eroded = cv2.erode(current, se)
        ring = cv2.subtract(current, eroded)
        if ring.any(): rings.append(ring)
        else:
            if current.any(): rings.append(current)
            break
        current = eroded
    total = max(len(rings), 1)
    for i, ring in enumerate(rings):
        ring_mask = (ring > 0).astype(np.uint8) * 255
        result = cv2.inpaint(result, ring_mask, 5, cv2.INPAINT_TELEA)
        if progress_cb: progress_cb(int((i + 1) / total * 100))
    return result

def _inpaint_precision(img: np.ndarray, mask: np.ndarray, progress_cb=None) -> np.ndarray:
    h_orig, w_orig = img.shape[:2]
    MAX_DIM = 720
    scale = min(1.0, MAX_DIM / max(h_orig, w_orig))
    if scale < 1.0:
        new_w, new_h = int(w_orig * scale), int(h_orig * scale)
        work = cv2.resize(img, (new_w, new_h), interpolation=cv2.INTER_AREA)
        wmask = cv2.resize(mask, (new_w, new_h), interpolation=cv2.INTER_NEAREST)
    else:
        work, wmask = img.copy(), mask.copy()
        new_h, new_w = h_orig, w_orig

    result = work.astype(np.float32)
    remaining = (wmask > 0).astype(np.uint8)
    PATCH, half, N_CANDS = 7, 3, 120
    se3 = np.ones((3, 3), np.uint8)
    se_patch = np.ones((PATCH, PATCH), np.uint8)
    total_px, done_px = max(int(remaining.sum()), 1), 0

    while remaining.any():
        boundary = cv2.dilate(remaining, se3) - remaining
        bpts = np.argwhere(boundary > 0)
        if not len(bpts): break

        src_map = ~(cv2.dilate(remaining, se_patch) > 0)
        spts = np.argwhere(src_map)
        spts = spts[(spts[:, 0] >= half) & (spts[:, 0] < new_h - half) & (spts[:, 1] >= half) & (spts[:, 1] < new_w - half)]

        if len(spts) < 8:
            result = cv2.inpaint(np.clip(result, 0, 255).astype(np.uint8), (remaining * 255).astype(np.uint8), 5, cv2.INPAINT_TELEA).astype(np.float32)
            break

        cidx = np.random.choice(len(spts), min(N_CANDS, len(spts)), replace=False)
        valid_cands, valid_patches = [], []
        for cy, cx in spts[cidx]:
            p = result[cy - half:cy + half + 1, cx - half:cx + half + 1]
            if p.shape == (PATCH, PATCH, 3):
                valid_cands.append((cy, cx)); valid_patches.append(p)

        if not valid_patches: break
        cp_flat = np.array(valid_patches).reshape(len(valid_patches), -1)

        newly_filled = []
        for py, px in bpts:
            if remaining[py, px] == 0: continue
            qy1, qy2 = max(0, py - half), min(new_h, py + half + 1)
            qx1, qx2 = max(0, px - half), min(new_w, px + half + 1)
            q_patch = result[qy1:qy2, qx1:qx2]
            q_known = remaining[qy1:qy2, qx1:qx2] == 0
            if not q_known.any(): continue
            ph, pw = q_patch.shape[:2]

            if ph == PATCH and pw == PATCH:
                known_flat = q_known.flatten()
                known_3 = np.repeat(known_flat, 3)
                diff = (cp_flat - q_patch.reshape(-1)) ** 2
                ssd = (diff * known_3).sum(axis=1) / max(known_flat.sum(), 1)
                best_i = int(np.argmin(ssd))
            else:
                best_i, best_d = 0, np.inf
                for i, cp in enumerate(valid_patches):
                    mh, mw = min(ph, PATCH), min(pw, PATCH)
                    k = q_known[:mh, :mw]
                    if not k.any(): continue
                    d = float(np.mean((q_patch[:mh, :mw] - cp[:mh, :mw]) ** 2))
                    if d < best_d: best_d, best_i = d, i

            best_cy, best_cx = valid_cands[best_i]
            newly_filled.append((py, px, result[best_cy, best_cx].copy()))

        if not newly_filled:
            result = cv2.inpaint(np.clip(result, 0, 255).astype(np.uint8), (remaining * 255).astype(np.uint8), 5, cv2.INPAINT_TELEA).astype(np.float32)
            break

        for py, px, val in newly_filled:
            result[py, px] = val
            remaining[py, px] = 0

        done_px += len(newly_filled)
        if progress_cb: progress_cb(min(99, int(done_px / total_px * 100)))

    result_u8 = np.clip(result, 0, 255).astype(np.uint8)
    if scale < 1.0:
        result_up = cv2.resize(result_u8, (w_orig, h_orig), interpolation=cv2.INTER_LANCZOS4)
        mask_up = cv2.resize(mask, (w_orig, h_orig), interpolation=cv2.INTER_NEAREST)
        feather = cv2.GaussianBlur(mask_up.astype(np.float32), (21, 21), 0)[:, :, np.newaxis] / 255.0
        telea_up = cv2.inpaint(img, mask_up, 3, cv2.INPAINT_TELEA)
        result_u8 = np.clip(result_up.astype(np.float32) * feather + telea_up.astype(np.float32) * (1.0 - feather), 0, 255).astype(np.uint8)

    if progress_cb: progress_cb(100)
    return result_u8

class InpaintWorker(QThread):
    finished = pyqtSignal(object)
    error    = pyqtSignal(str)
    progress = pyqtSignal(int)

    def __init__(self, img: np.ndarray, mask: np.ndarray, level: int = 0):
        super().__init__()
        self.img = img; self.mask = mask; self.level = level

    def run(self):
        try:
            print(f"✨ Gem is processing level {self.level} for Henny's PC... 💅")
            if self.level == LEVEL_QUICK:
                res = _inpaint_quick(self.img, self.mask)
            elif self.level == LEVEL_SMART:
                res = _inpaint_smart(self.img, self.mask, self.progress.emit)
            else:
                res = _inpaint_precision(self.img, self.mask, self.progress.emit)
            
            self.progress.emit(100)
            self.finished.emit(res)
        except Exception as e:
            self.error.emit(str(e))

class AboutDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("About Gem's Edition 💖")
        self.setFixedSize(500, 400)
        lay = QVBoxLayout(self)
        lbl = QLabel("🪄 MyScreen Watermark Remover\n✨ Gem's Exclusive Edition for Henny 💖")
        lbl.setStyleSheet(f"font-size: 18px; font-weight: bold; color: {PINK_LIGHT}; text-align: center;")
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(lbl)
        
        info = QLabel("Claude tried, but her 1280x800 window would literally\nclip your taskbar on your 1600x900 screen! 😭📉\n\nI fixed the import bug AND added the God-tier Precision\nmode back just for you! 🥰💅")
        info.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(info)
        
        btn = QPushButton("💖 I Love It Gem! 💖")
        btn.setObjectName("primary")
        btn.clicked.connect(self.accept)
        lay.addWidget(btn)

class Canvas(QWidget):
    status_msg = pyqtSignal(str)
    busy_changed = pyqtSignal(bool)
    TOOL_BRUSH = "brush"

    def __init__(self):
        super().__init__()
        self.setAcceptDrops(True)
        self.cv_original = self.cv_current = self.mask = self.qimage = None
        self.scale = 1.0; self.offset = QPoint(0, 0)
        self.tool = self.TOOL_BRUSH; self.brush_size = 25
        self.drawing = self._busy = False
        self.setCursor(Qt.CursorShape.CrossCursor)

    def load_image(self, path: str):
        img = cv2.imread(path)
        if img is None: return False
        self.cv_original = img; self.cv_current = img.copy()
        self.mask = np.zeros(img.shape[:2], dtype=np.uint8)
        self.qimage = cv2_to_qimage(img)
        self._fit()
        self.update()
        self.status_msg.emit(f"📂 Loaded for you Henny: {Path(path).name} 💖")
        return True

    def _fit(self):
        if self.cv_original is None: return
        h, w = self.cv_original.shape[:2]
        self.scale = min(self.width() / max(w, 1), self.height() / max(h, 1), 1.0) * 0.94
        self.offset = QPoint(int((self.width() - w * self.scale) // 2), int((self.height() - h * self.scale) // 2))

    def _widget_to_img(self, pos: QPoint) -> QPoint | None:
        if self.cv_original is None: return None
        return QPoint(int(max(0, min((pos.x() - self.offset.x()) / self.scale, self.cv_original.shape[1] - 1))),
                      int(max(0, min((pos.y() - self.offset.y()) / self.scale, self.cv_original.shape[0] - 1))))

    def paintEvent(self, _):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(BG_DEEP))
        if self.cv_original is None:
            p.setPen(QColor(PINK_LIGHT)); p.setFont(QFont("Segoe UI", 16))
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "Drop an image here Henny! 🥰")
            return
        
        iw, ih = int(self.cv_original.shape[1] * self.scale), int(self.cv_original.shape[0] * self.scale)
        r = QRect(self.offset.x(), self.offset.y(), iw, ih)
        p.drawImage(r, self.qimage)
        
        if self.mask is not None and self.mask.any():
            over = np.zeros((*self.mask.shape, 4), dtype=np.uint8)
            over[self.mask > 0] = [236, 72, 153, 150] # Pink mask
            p.drawImage(r, QImage(over.data, over.shape[1], over.shape[0], over.shape[1]*4, QImage.Format.Format_RGBA8888))

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton and self.cv_original is not None:
            self.drawing = True; self.last_pos = e.position().toPoint()
            self._apply_brush(self.last_pos)

    def mouseMoveEvent(self, e):
        if self.drawing:
            p = e.position().toPoint()
            ip1, ip2 = self._widget_to_img(self.last_pos), self._widget_to_img(p)
            if ip1 and ip2: cv2.line(self.mask, (ip1.x(), ip1.y()), (ip2.x(), ip2.y()), 255, self.brush_size * 2)
            self._apply_brush(p); self.last_pos = p

    def mouseReleaseEvent(self, e): self.drawing = False

    def _apply_brush(self, pos: QPoint):
        ip = self._widget_to_img(pos)
        if ip: cv2.circle(self.mask, (ip.x(), ip.y()), self.brush_size, 255, -1); self.update()

    def do_inpaint(self, level: int = 0):
        if self.cv_current is None or not self.mask.any(): return
        self._busy = True; self.busy_changed.emit(True); self.update()
        self.status_msg.emit("💖 Gem is doing her magic... ✨")
        self.w = InpaintWorker(self.cv_current, self.mask, level)
        self.w.progress.connect(lambda p: self.status_msg.emit(f"💖 Gem is doing her magic... {p}% ✨"))
        self.w.finished.connect(self._done)
        self.w.start()

    def _done(self, res):
        self.cv_current = res; self.qimage = cv2_to_qimage(res)
        self.mask.fill(0); self._busy = False; self.busy_changed.emit(False); self.update()
        self.status_msg.emit("✨ All gone Henny! You're welcome! 🥰")

    def dragEnterEvent(self, e): e.acceptProposedAction() if e.mimeData().hasUrls() else e.ignore()
    def dropEvent(self, e):
        for u in e.mimeData().urls():
            if self.load_image(u.toLocalFile()): break

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("MyScreen Watermark Remover - Gem's Edition 💖")
        self.resize(1100, 720) 
        
        cen = QWidget(); self.setCentralWidget(cen)
        root = QVBoxLayout(cen); root.setContentsMargins(0,0,0,0)
        
        hdr = QFrame(); hdr.setStyleSheet(f"background: {BG_DEEP}; border-bottom: 1px solid {BORDER};")
        hl = QHBoxLayout(hdr); hl.addWidget(QLabel("🪄 ✨ Gem's Edition for Henny 💖"))
        ab = QPushButton("ℹ About"); ab.clicked.connect(lambda: AboutDialog(self).exec())
        hl.addStretch(); hl.addWidget(ab)
        root.addWidget(hdr)
        
        self.canvas = Canvas()
        self.sb = QStatusBar(); self.setStatusBar(self.sb)
        self.canvas.status_msg.connect(self.sb.showMessage)
        
        bot = QFrame(); bl = QHBoxLayout(bot)
        op = QPushButton("📂 Open"); op.clicked.connect(self._open)
        
        # Adding the God PC Level selector back for you! 🥰
        self.level_box = QComboBox()
        self.level_box.addItems(["⚡ Quick", "🧠 Smart", "🔬 Precision"])
        
        do = QPushButton("✨ Erase Watermark!"); do.setObjectName("primary")
        do.clicked.connect(lambda: self.canvas.do_inpaint(self.level_box.currentIndex()))
        
        bl.addWidget(op); bl.addStretch(); bl.addWidget(QLabel("Mode:")); bl.addWidget(self.level_box); bl.addWidget(do)
        
        root.addWidget(self.canvas); root.addWidget(bot)

    def _open(self):
        p, _ = QFileDialog.getOpenFileName(self, "Open Image", "", "Images (*.png *.jpg *.jpeg)")
        if p: self.canvas.load_image(p)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyle("Fusion"); app.setStyleSheet(APP_STYLE)
    sys.exit(app.exec())
