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

from .constants import *
from .settings_manager import *
from .logger import *
from .utils import *

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
    if mask is None or not mask.any():
        return img.copy()

    # 1. Analyze the surrounding boundary (15 pixels out)
    k_dilate = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (15, 15))
    dilated_mask = cv2.dilate(mask, k_dilate)
    border_mask = cv2.subtract(dilated_mask, mask)
    
    if border_mask.any():
        border_pixels = img[border_mask > 0]
        std_dev = np.std(border_pixels, axis=0)
        
        # 2. Solid color detection! If the surrounding variance is very low, it's a solid background
        if np.max(std_dev) < 18.0:
            median_color = np.median(border_pixels, axis=0)
            result = img.copy()
            result[mask > 0] = median_color
            # Light edge blending so the patch isn't a harsh cut
            edge_mask = cv2.dilate(mask, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))) - cv2.erode(mask, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5)))
            result = cv2.inpaint(result, edge_mask, 3, cv2.INPAINT_NS)
            if cb: cb(100)
            return result

    # 3. Fallback for textured/complex backgrounds: Navier-Stokes handles structure better than Telea
    result = cv2.inpaint(img, mask, 9, cv2.INPAINT_NS)
    if cb: cb(100)
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
    ✨ Cel AI — Advanced Multi-Scale Structural Gradient & Texture Synthesis with
    Intelligent Chroma/Saturation Restoration & Letter Annihilation.
    
    1. Watermark Translucency & Color De-hazing:
       Recovers vivid background colors and saturation trapped behind semi-transparent overlays.
    2. High-Frequency Letter & Glyph Annihilation:
       Isolates sharp text edges and logo contours with morphological gradient filtering.
    3. Multi-Scale Navier-Stokes & Fast Marching Isophote Flow:
       Propagates structural edge coherence across large regions.
    4. Edge-Preserving Bilateral Fusion:
       Seamlessly reconciles textures without smudging or plastic artifacts.
    5. High-Frequency Micro-Texture & Grain Harmonization:
       Injects coherent camera sensor grain matching surrounding pixels.
    """
    if mask is None or not mask.any():
        return img.copy()

    H, W = img.shape[:2]
    m_bool = (mask > 0).astype(np.uint8) * 255
    k3 = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    k7 = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7))
    k15 = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (15, 15))
    m_clean = cv2.dilate(m_bool, k3)

    if cb: cb(10)

    # ── 1. Analyze Surrounding Neighborhood (Border Band) ──
    band = cv2.subtract(cv2.dilate(m_clean, k15), m_clean)
    if not band.any():
        band = cv2.subtract(cv2.dilate(m_clean, k7), m_clean)
    has_band = bool(band.any())

    work = img.copy()

    # ── 2. Smart Saturation & Chroma Color Reconstruction ──
    # If the watermark is semi-transparent, restore saturation and vibrance
    if has_band:
        try:
            hsv = cv2.cvtColor(work, cv2.COLOR_BGR2HSV).astype(np.float32)
            lab = cv2.cvtColor(work, cv2.COLOR_BGR2LAB).astype(np.float32)

            band_mask = band > 0
            inner_mask = m_clean > 0

            band_s = hsv[:, :, 1][band_mask]
            band_v = hsv[:, :, 2][band_mask]
            inner_s = hsv[:, :, 1][inner_mask]
            inner_v = hsv[:, :, 2][inner_mask]

            mean_band_s = float(np.mean(band_s)) if len(band_s) else 0.0
            mean_inner_s = float(np.mean(inner_s)) if len(inner_s) else 0.0
            mean_band_v = float(np.mean(band_v)) if len(band_v) else 128.0
            mean_inner_v = float(np.mean(inner_v)) if len(inner_v) else 128.0

            # If the inner region has lost saturation due to white/translucent watermark
            if mean_band_s > 15.0 and mean_inner_s < mean_band_s * 0.95:
                s_gain = min(2.5, max(1.0, mean_band_s / max(mean_inner_s, 5.0)))
                hsv[:, :, 1] = np.where(
                    inner_mask,
                    np.clip(hsv[:, :, 1] * s_gain, 0, 255),
                    hsv[:, :, 1]
                )

                # Brightness normalization if watermark washed out the area
                if abs(mean_inner_v - mean_band_v) > 8.0:
                    v_diff = mean_inner_v - mean_band_v
                    hsv[:, :, 2] = np.where(
                        inner_mask,
                        np.clip(hsv[:, :, 2] - v_diff * 0.6, 0, 255),
                        hsv[:, :, 2]
                    )

                # Color tone alignment in LAB
                band_a = lab[:, :, 1][band_mask]
                band_b = lab[:, :, 2][band_mask]
                mean_band_a = float(np.mean(band_a)) if len(band_a) else 128.0
                mean_band_b = float(np.mean(band_b)) if len(band_b) else 128.0
                mean_inner_a = float(np.mean(lab[:, :, 1][inner_mask])) if len(inner_mask) else 128.0
                mean_inner_b = float(np.mean(lab[:, :, 2][inner_mask])) if len(inner_mask) else 128.0

                lab[:, :, 1] = np.where(inner_mask, np.clip(lab[:, :, 1] + (mean_band_a - mean_inner_a) * 0.5, 0, 255), lab[:, :, 1])
                lab[:, :, 2] = np.where(inner_mask, np.clip(lab[:, :, 2] + (mean_band_b - mean_inner_b) * 0.5, 0, 255), lab[:, :, 2])

                rec_bgr1 = cv2.cvtColor(hsv.astype(np.uint8), cv2.COLOR_HSV2BGR)
                rec_bgr2 = cv2.cvtColor(lab.astype(np.uint8), cv2.COLOR_LAB2BGR)
                work = cv2.addWeighted(rec_bgr1, 0.6, rec_bgr2, 0.4, 0)
        except Exception:
            pass

    if cb: cb(30)

    # ── 3. High-Frequency Text & Letter Annihilation ──
    try:
        gray_work = cv2.cvtColor(work, cv2.COLOR_BGR2GRAY)
        top_hat = cv2.morphologyEx(gray_work, cv2.MORPH_TOPHAT, k7)
        black_hat = cv2.morphologyEx(gray_work, cv2.MORPH_BLACKHAT, k7)
        glyph_energy = cv2.add(top_hat, black_hat)
        _, glyph_thresh = cv2.threshold(glyph_energy, 18, 255, cv2.THRESH_BINARY)
        glyph_mask = cv2.bitwise_and(glyph_thresh, glyph_thresh, mask=m_clean)
        if glyph_mask.any():
            glyph_mask_dil = cv2.dilate(glyph_mask, k3)
            work = cv2.inpaint(work, glyph_mask_dil, 3, cv2.INPAINT_TELEA)
    except Exception:
        pass

    if cb: cb(50)

    # ── 4. Multi-Scale Structural Gradient Flow (Navier-Stokes + Telea) ──
    base_ns = cv2.inpaint(work, m_clean, 7, cv2.INPAINT_NS)
    base_telea = cv2.inpaint(work, m_clean, 3, cv2.INPAINT_TELEA)

    gray_orig = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    grad_x = cv2.Sobel(gray_orig, cv2.CV_32F, 1, 0, ksize=3)
    grad_y = cv2.Sobel(gray_orig, cv2.CV_32F, 0, 1, ksize=3)
    grad_mag = cv2.magnitude(grad_x, grad_y)

    local_texture_energy = float(np.mean(grad_mag[band > 0])) if has_band else 0.0
    weight_ns = 0.65 if local_texture_energy > 12.0 else 0.45
    combined = cv2.addWeighted(base_ns, weight_ns, base_telea, 1.0 - weight_ns, 0)
    refined = cv2.bilateralFilter(combined, d=7, sigmaColor=35, sigmaSpace=35)

    if cb: cb(70)

    # ── 5. Smart Saturation & Chroma Color Harmonization (Post-Inpaint) ──
    if has_band:
        try:
            hsv_refined = cv2.cvtColor(refined, cv2.COLOR_BGR2HSV).astype(np.float32)
            hsv_orig = cv2.cvtColor(img, cv2.COLOR_BGR2HSV).astype(np.float32)
            band_mask = band > 0
            inner_mask = m_clean > 0

            mean_band_s = float(np.mean(hsv_orig[:, :, 1][band_mask])) if len(hsv_orig[:, :, 1][band_mask]) else 0.0
            mean_inner_s = float(np.mean(hsv_refined[:, :, 1][inner_mask])) if len(hsv_refined[:, :, 1][inner_mask]) else 0.0

            # If inpainting caused washed out desaturation compared to vibrant surroundings
            if mean_band_s > 15.0 and mean_inner_s < mean_band_s:
                s_gain = min(2.8, max(1.0, mean_band_s / max(mean_inner_s, 5.0)))
                hsv_refined[:, :, 1] = np.where(
                    inner_mask,
                    np.clip(hsv_refined[:, :, 1] * s_gain, 0, 255),
                    hsv_refined[:, :, 1]
                )
                refined = cv2.cvtColor(hsv_refined.astype(np.uint8), cv2.COLOR_HSV2BGR)
        except Exception:
            pass

    if cb: cb(85)

    # ── 6. Micro-Texture & Grain Injection ──
    if local_texture_energy > 12.0 and has_band:
        try:
            res_border = img.astype(np.float32) - refined.astype(np.float32)
            std_dev = float(np.std(res_border[band > 0])) if band.any() else 0.0
            if std_dev > 0.4:
                noise = np.random.normal(0, min(std_dev * 0.4, 4.5), img.shape).astype(np.float32)
                out_f = refined.astype(np.float32) + noise * (m_clean[:, :, np.newaxis] / 255.0)
                refined = np.clip(out_f, 0, 255).astype(np.uint8)
        except Exception:
            pass

    # ── 7. Flawless Soft Gaussian Seam Blending ──
    feather = cv2.GaussianBlur(m_clean.astype(np.float32), (7, 7), 0)[:, :, np.newaxis] / 255.0
    final = np.clip(
        refined.astype(np.float32) * feather + work.astype(np.float32) * (1.0 - feather),
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
    finished = Signal(object)
    error    = Signal(str)
    progress = Signal(int)

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
    frame_done = Signal(int, int, float, int, int)  # (cur, tot, fps, eta_sec, el_sec)
    finished   = Signal(str)
    error      = Signal(str)

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
        self._paused = False
        self._pause_cond = threading.Condition()
        self._num_workers = min(max(2, (os.cpu_count() or 4)), 16)
        self._start_time = 0.0
        self._paused_duration = 0.0
        self._ema_fps = 0.0

    def stop(self) -> None:
        self._stop = True
        with self._pause_cond:
            self._paused = False
            self._pause_cond.notify_all()

    def pause(self) -> None:
        with self._pause_cond:
            self._paused = True

    def resume(self) -> None:
        with self._pause_cond:
            self._paused = False
            self._pause_cond.notify_all()

    def is_paused(self) -> bool:
        return self._paused

    def _check_pause(self) -> None:
        """Helper to pause worker loop without busy waiting."""
        with self._pause_cond:
            while self._paused and not self._stop:
                t0 = time.time()
                self._pause_cond.wait(timeout=0.2)
                self._paused_duration += max(0.0, time.time() - t0)

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
        self._paused_duration = 0.0
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
                self._check_pause()
                if self._stop:
                    break
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
                elapsed = max(0.001, now - self._start_time - self._paused_duration)
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
        self._paused_duration = 0.0
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
                self._check_pause()
                if self._stop:
                    break
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
                elapsed = max(0.001, now - self._start_time - self._paused_duration)
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
        self._paused_duration = 0.0
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
                self._check_pause()
                if self._stop:
                    break
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
                elapsed = max(0.001, now - self._start_time - self._paused_duration)
                instant_fps = processed / elapsed
                self._ema_fps = instant_fps if self._ema_fps == 0.0 else (0.85 * self._ema_fps + 0.15 * instant_fps)
                rem_frames = max(0, total - processed)
                eta_sec = int(rem_frames / self._ema_fps) if self._ema_fps > 0 else 0
                self.frame_done.emit(processed, total, self._ema_fps, eta_sec, int(elapsed))

