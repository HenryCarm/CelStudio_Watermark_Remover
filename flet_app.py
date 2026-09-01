import os
import sys
import time
import base64
import threading
from pathlib import Path
import cv2
import numpy as np
import flet as ft

from core.constants import get_wallpaper_path, get_save_dir, get_data_dir
from core.settings_manager import load_settings, save_settings
from core.engine import _inpaint_smart, _inpaint_cel_ai, _inpaint_quick, _inpaint_precision

def cv2_to_base64(img_bgr: np.ndarray, max_dim: int = 1200) -> str:
    """Convert BGR OpenCV image to base64 Data URI with optional max dimension downsampling for speed."""
    if img_bgr is None or img_bgr.size == 0:
        return ""
    h, w = img_bgr.shape[:2]
    if max(h, w) > max_dim:
        scale = max_dim / max(h, w)
        img_bgr = cv2.resize(img_bgr, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)
    _, buf = cv2.imencode(".jpg", img_bgr, [int(cv2.IMWRITE_JPEG_QUALITY), 92])
    b64 = base64.b64encode(buf).decode("utf-8")
    return f"data:image/jpeg;base64,{b64}"

def main(page: ft.Page):
    page.title = "CelStudio Mobile — Liquid Glass Edition"
    page.theme_mode = ft.ThemeMode.DARK
    page.bgcolor = "#050408"
    page.padding = 0
    
    # State variables
    current_media_path: str | None = None
    is_video: bool = False
    original_img: np.ndarray | None = None      # Full resolution BGR
    processed_img: np.ndarray | None = None     # Cleaned BGR
    showing_original: bool = False
    
    # Video state
    video_cap: cv2.VideoCapture | None = None
    video_total_frames: int = 0
    video_fps: float = 30.0
    video_is_processing: bool = False
    video_stop_requested: bool = False
    
    # Watermark selection bounding box (normalized 0.0 to 1.0)
    mask_rect: list[float] | None = None
    is_dragging: bool = False
    drag_start: tuple[float, float] | None = None
    
    # Layout responsiveness
    is_mobile = False
    
    # Wallpaper setup (No blur, clean black tint)
    wp_path = str(get_wallpaper_path().resolve())
    
    # UI References
    header_title = ft.Text("CelStudio", size=19, weight="bold", color="#ffffff")
    header_badge = ft.Container(
        content=ft.Text("PRO AI", size=9, weight="bold", color="#fbcfe8"),
        padding=ft.Padding(6, 2, 6, 2),
        border_radius=ft.BorderRadius.all(6),
        bgcolor=ft.Colors.with_opacity(0.25, "#ec4899"),
        border=ft.Border.all(1, ft.Colors.with_opacity(0.4, "#f472b6"))
    )
    
    # Status / Progress indicators
    status_label = ft.Text("Ready · Select an image or video to begin", size=12, color="#94a3b8")
    progress_bar = ft.ProgressBar(value=0.0, visible=False, color="#10b981", bgcolor=ft.Colors.with_opacity(0.2, "#ffffff"))
    
    # Media view controls
    media_display = ft.Image(src="", fit=ft.BoxFit.CONTAIN, expand=True, visible=False)
    
    placeholder_col = ft.Column(
        [
            ft.Container(
                content=ft.Icon(ft.icons.Icons.CLOUD_UPLOAD_ROUNDED, size=68, color="#c084fc"),
                padding=20,
                border_radius=ft.BorderRadius.all(30),
                gradient=ft.RadialGradient(
                    colors=[ft.Colors.with_opacity(0.3, "#9333ea"), ft.Colors.with_opacity(0.0, "#9333ea")]
                ),
            ),
            ft.Text("Tap to Open Media or Drag & Drop Here", color="#ffffff", size=17, weight="bold", text_align=ft.TextAlign.CENTER),
            ft.Text("AI automatically detects alpha contours and traps vibrant color", color="#94a3b8", size=12, text_align=ft.TextAlign.CENTER),
            ft.Container(height=6),
            ft.Row(
                [
                    ft.Container(
                        content=ft.Text("🖼 PNG / JPG", size=11, color="#cbd5e1", weight="bold"),
                        padding=ft.Padding(8, 4, 8, 4),
                        border_radius=ft.BorderRadius.all(8),
                        bgcolor=ft.Colors.with_opacity(0.12, "#ffffff"),
                        border=ft.Border.all(1, ft.Colors.with_opacity(0.15, "#ffffff"))
                    ),
                    ft.Container(
                        content=ft.Text("🎬 MP4 / MKV", size=11, color="#a7f3d0", weight="bold"),
                        padding=ft.Padding(8, 4, 8, 4),
                        border_radius=ft.BorderRadius.all(8),
                        bgcolor=ft.Colors.with_opacity(0.15, "#10b981"),
                        border=ft.Border.all(1, ft.Colors.with_opacity(0.3, "#34d399"))
                    ),
                    ft.Container(
                        content=ft.Text("⚡ Cel AI Core", size=11, color="#fbcfe8", weight="bold"),
                        padding=ft.Padding(8, 4, 8, 4),
                        border_radius=ft.BorderRadius.all(8),
                        bgcolor=ft.Colors.with_opacity(0.15, "#ec4899"),
                        border=ft.Border.all(1, ft.Colors.with_opacity(0.3, "#f472b6"))
                    ),
                ],
                alignment=ft.MainAxisAlignment.CENTER,
                spacing=8,
                wrap=True
            )
        ],
        alignment=ft.MainAxisAlignment.CENTER,
        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
        spacing=6
    )
    
    mask_box_view = ft.Container(
        border=ft.Border.all(2, "#ec4899"),
        bgcolor=ft.Colors.with_opacity(0.25, "#f43f5e"),
        border_radius=ft.BorderRadius.all(4),
        visible=False
    )
    
    canvas_container = ft.Container(
        content=ft.Stack(
            controls=[
                placeholder_col,
                media_display,
                mask_box_view
            ],
            alignment=ft.Alignment(0, 0),
            expand=True
        ),
        expand=True,
        margin=14,
        padding=10,
        border_radius=ft.BorderRadius.all(20),
        gradient=ft.LinearGradient(
            begin=ft.Alignment(-1, -1),
            end=ft.Alignment(1, 1),
            colors=[ft.Colors.with_opacity(0.20, "#1e1338"), ft.Colors.with_opacity(0.08, "#0c0a17")]
        ),
        border=ft.Border.all(1.5, ft.Colors.with_opacity(0.3, "#a855f7")),
        shadow=ft.BoxShadow(spread_radius=2, blur_radius=28, color=ft.Colors.with_opacity(0.22, "#9333ea")),
        alignment=ft.Alignment(0, 0),
    )
    
    # Method selector dropdown - generous width & dynamic stretch so text is never truncated
    method_dropdown = ft.Dropdown(
        options=[
            ft.dropdown.Option("✨ Cel AI (Deep Inpaint)"),
            ft.dropdown.Option("🧠 Smart (Dominant Color)"),
            ft.dropdown.Option("⚡ Quick (Fast Blend)"),
            ft.dropdown.Option("🎯 Precision (Navier-Stokes)"),
        ],
        value="✨ Cel AI (Deep Inpaint)",
        border_color="#a855f7",
        border_radius=ft.BorderRadius.all(12),
        text_size=12,
        content_padding=12,
        bgcolor="#18132e",
        expand=1
    )
    
    btn_action = ft.Container(
        content=ft.Row(
            [
                ft.Icon(ft.icons.Icons.AUTO_FIX_HIGH_ROUNDED, size=18, color="#ffffff"),
                ft.Text("✨ REMOVE WATERMARK", size=13, weight="bold", color="#ffffff")
            ],
            alignment=ft.MainAxisAlignment.CENTER,
            spacing=8
        ),
        padding=ft.Padding(16, 12, 16, 12),
        border_radius=ft.BorderRadius.all(12),
        gradient=ft.LinearGradient(
            begin=ft.Alignment(-1, -1),
            end=ft.Alignment(1, 1),
            colors=["#10b981", "#059669"]
        ),
        shadow=ft.BoxShadow(spread_radius=1, blur_radius=15, color=ft.Colors.with_opacity(0.4, "#10b981")),
        expand=1,
        animate=ft.Animation(200, ft.AnimationCurve.EASE_OUT)
    )
    
    btn_compare = ft.Container(
        content=ft.Row([
            ft.Icon(ft.icons.Icons.COMPARE, size=16, color="#cbd5e1"),
            ft.Text("Compare", size=12, weight="bold", color="#ffffff")
        ], spacing=4),
        padding=ft.Padding(10, 8, 10, 8),
        border_radius=ft.BorderRadius.all(10),
        bgcolor=ft.Colors.with_opacity(0.18, "#ffffff"),
        border=ft.Border.all(1, ft.Colors.with_opacity(0.2, "#ffffff")),
        visible=False
    )
    
    btn_save = ft.Container(
        content=ft.Row([
            ft.Icon(ft.icons.Icons.SAVE_ALT_ROUNDED, size=16, color="#ffffff"),
            ft.Text("Save", size=12, weight="bold", color="#ffffff")
        ], spacing=4),
        padding=ft.Padding(12, 8, 12, 8),
        border_radius=ft.BorderRadius.all(10),
        gradient=ft.LinearGradient(
            begin=ft.Alignment(-1, -1),
            end=ft.Alignment(1, 1),
            colors=["#3b82f6", "#2563eb"]
        ),
        visible=False
    )
    
    btn_clear_mask = ft.Container(
        content=ft.Row([
            ft.Icon(ft.icons.Icons.LAYERS_CLEAR_ROUNDED, size=15, color="#f87171"),
            ft.Text("Clear Box", size=11, color="#fca5a5")
        ], spacing=4),
        padding=ft.Padding(8, 6, 8, 6),
        border_radius=ft.BorderRadius.all(8),
        bgcolor=ft.Colors.with_opacity(0.15, "#ef4444"),
        border=ft.Border.all(1, ft.Colors.with_opacity(0.3, "#ef4444")),
        visible=False
    )
    
    def update_canvas_view():
        nonlocal showing_original
        target = original_img if showing_original or processed_img is None else processed_img
        if target is None:
            placeholder_col.visible = True
            media_display.visible = False
            mask_box_view.visible = False
            btn_compare.visible = False
            btn_save.visible = False
            btn_clear_mask.visible = False
            page.update()
            return
            
        placeholder_col.visible = False
        media_display.visible = True
        
        preview_mat = target.copy()
        if mask_rect is not None:
            h, w = preview_mat.shape[:2]
            x1 = int(mask_rect[0] * w)
            y1 = int(mask_rect[1] * h)
            x2 = int(mask_rect[2] * w)
            y2 = int(mask_rect[3] * h)
            
            overlay = preview_mat.copy()
            cv2.rectangle(overlay, (x1, y1), (x2, y2), (236, 72, 153), -1)
            cv2.addWeighted(overlay, 0.35, preview_mat, 0.65, 0, preview_mat)
            cv2.rectangle(preview_mat, (x1, y1), (x2, y2), (244, 114, 182), 2)
            btn_clear_mask.visible = True
        else:
            btn_clear_mask.visible = False
            
        media_display.src = cv2_to_base64(preview_mat)
        btn_compare.visible = (processed_img is not None)
        btn_save.visible = (processed_img is not None)
        page.update()
    
    def load_media_file(file_path: str):
        nonlocal current_media_path, is_video, original_img, processed_img, mask_rect, video_cap, video_total_frames, video_fps
        p = Path(file_path)
        if not p.exists():
            return
            
        current_media_path = str(p.resolve())
        mask_rect = None
        processed_img = None
        showing_original = False
        
        ext = p.suffix.lower()
        if ext in [".mp4", ".avi", ".mkv", ".mov", ".webm"]:
            is_video = True
            video_cap = cv2.VideoCapture(current_media_path)
            video_total_frames = int(video_cap.get(cv2.CAP_PROP_FRAME_COUNT))
            video_fps = video_cap.get(cv2.CAP_PROP_FPS) or 30.0
            ret, frame = video_cap.read()
            if ret:
                original_img = frame
                status_label.value = f"🎬 Video Loaded: {p.name} ({video_total_frames} frames @ {video_fps:.1f} FPS)"
            else:
                status_label.value = f"⚠️ Could not read video frames from {p.name}"
        else:
            is_video = False
            original_img = cv2.imread(current_media_path)
            if original_img is not None:
                h, w = original_img.shape[:2]
                status_label.value = f"🖼️ Image Loaded: {p.name} ({w}x{h} px)"
            else:
                status_label.value = f"⚠️ Failed to decode image {p.name}"
                
        update_canvas_view()
    
    # File picker setup
    file_picker = ft.FilePicker()
    page.overlay.append(file_picker)
    
    def open_image_dialog(e):
        files = file_picker.pick_files(
            dialog_title="Select Image to Clean",
            file_type=ft.FilePickerFileType.IMAGE,
            allowed_extensions=["png", "jpg", "jpeg", "webp", "bmp"]
        )
        if files and len(files) > 0 and files[0].path:
            load_media_file(files[0].path)
        
    def open_video_dialog(e):
        files = file_picker.pick_files(
            dialog_title="Select Video to Clean",
            file_type=ft.FilePickerFileType.VIDEO,
            allowed_extensions=["mp4", "mkv", "avi", "mov", "webm"]
        )
        if files and len(files) > 0 and files[0].path:
            load_media_file(files[0].path)
    
    # Gesture Detector for drawing watermark box on canvas
    def on_pan_start(e: ft.DragStartEvent):
        nonlocal is_dragging, drag_start
        if original_img is None:
            return
        is_dragging = True
        w = canvas_container.width or 600
        h = canvas_container.height or 400
        rx = max(0.0, min(1.0, e.local_position.x / max(1, w)))
        ry = max(0.0, min(1.0, e.local_position.y / max(1, h)))
        drag_start = (rx, ry)
        
    def on_pan_update(e: ft.DragUpdateEvent):
        nonlocal mask_rect
        if not is_dragging or drag_start is None or original_img is None:
            return
        w = canvas_container.width or 600
        h = canvas_container.height or 400
        cur_x = max(0.0, min(1.0, e.local_position.x / max(1, w)))
        cur_y = max(0.0, min(1.0, e.local_position.y / max(1, h)))
        
        x1, x2 = min(drag_start[0], cur_x), max(drag_start[0], cur_x)
        y1, y2 = min(drag_start[1], cur_y), max(drag_start[1], cur_y)
        
        if (x2 - x1) > 0.02 and (y2 - y1) > 0.02:
            mask_rect = [x1, y1, x2, y2]
            update_canvas_view()
            
    def on_pan_end(e: ft.DragEndEvent):
        nonlocal is_dragging
        is_dragging = False
        if mask_rect is not None:
            status_label.value = f"✨ Watermark Region Selected ({int((mask_rect[2]-mask_rect[0])*100)}% x {int((mask_rect[3]-mask_rect[1])*100)}%)"
            page.update()
    
    def clear_mask_box(e):
        nonlocal mask_rect
        mask_rect = None
        status_label.value = "Mask cleared · Drag over the watermark to select"
        update_canvas_view()
        
    btn_clear_mask.on_click = clear_mask_box
    
    # Inpaint Processing Engine Execution
    def run_watermark_removal(e):
        nonlocal processed_img, video_is_processing, video_stop_requested
        if original_img is None:
            status_label.value = "⚠️ Please open an image or video first!"
            page.update()
            return
            
        if mask_rect is None:
            status_label.value = "⚠️ Please drag and select the watermark box on the image!"
            page.update()
            return
            
        method_str = method_dropdown.value or "✨ Cel AI"
        
        # Build binary mask
        h, w = original_img.shape[:2]
        x1 = max(0, min(w - 1, int(mask_rect[0] * w)))
        y1 = max(0, min(h - 1, int(mask_rect[1] * h)))
        x2 = max(x1 + 1, min(w, int(mask_rect[2] * w)))
        y2 = max(y1 + 1, min(h, int(mask_rect[3] * h)))
        
        mask = np.zeros((h, w), dtype=np.uint8)
        mask[y1:y2, x1:x2] = 255
        
        def apply_algorithm(frame_bgr: np.ndarray, binary_mask: np.ndarray) -> np.ndarray:
            if "Smart" in method_str:
                return _inpaint_smart(frame_bgr, binary_mask)
            elif "Cel AI" in method_str:
                return _inpaint_cel_ai(frame_bgr, binary_mask)
            elif "Quick" in method_str:
                return _inpaint_quick(frame_bgr, binary_mask)
            else:
                return _inpaint_precision(frame_bgr, binary_mask)
        
        if not is_video:
            # Single Image Processing
            status_label.value = f"⚡ Processing image with {method_str}..."
            progress_bar.value = None
            progress_bar.visible = True
            page.update()
            
            def worker():
                nonlocal processed_img
                t0 = time.time()
                res = apply_algorithm(original_img, mask)
                elapsed = time.time() - t0
                processed_img = res
                progress_bar.visible = False
                status_label.value = f"✨ Watermark Cleaned in {elapsed:.2f}s! Tap 'Save' or 'Compare'"
                update_canvas_view()
                
            threading.Thread(target=worker, daemon=True).start()
            
        else:
            # Video Processing
            if video_is_processing:
                return
            video_is_processing = True
            video_stop_requested = False
            progress_bar.visible = True
            progress_bar.value = 0.0
            status_label.value = "🎬 Initializing Video AI Pipeline..."
            page.update()
            
            def video_worker():
                nonlocal video_is_processing, processed_img
                save_dir = get_save_dir()
                save_dir.mkdir(parents=True, exist_ok=True)
                stem = Path(current_media_path).stem
                out_path = save_dir / f"{stem}_cleaned_{int(time.time())}.mp4"
                
                cap = cv2.VideoCapture(current_media_path)
                total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) or 1
                fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
                vw = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
                vh = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
                
                fourcc = cv2.VideoWriter_fourcc(*"mp4v")
                writer = cv2.VideoWriter(str(out_path), fourcc, fps, (vw, vh))
                
                idx = 0
                t_start = time.time()
                while cap.isOpened() and not video_stop_requested:
                    ret, f = cap.read()
                    if not ret:
                        break
                    cleaned_frame = apply_algorithm(f, mask)
                    writer.write(cleaned_frame)
                    idx += 1
                    
                    if idx % 5 == 0 or idx == total:
                        pct = idx / total
                        fps_calc = idx / max(0.001, time.time() - t_start)
                        eta = (total - idx) / max(0.1, fps_calc)
                        progress_bar.value = pct
                        status_label.value = f"🎬 Processing Video: {idx}/{total} frames ({int(pct*100)}%) · {fps_calc:.1f} FPS · ETA: {int(eta)}s"
                        processed_img = cleaned_frame
                        update_canvas_view()
                        
                cap.release()
                writer.release()
                video_is_processing = False
                progress_bar.visible = False
                status_label.value = f"🎉 Video Saved to: {out_path.name}"
                page.update()
                
            threading.Thread(target=video_worker, daemon=True).start()
    
    btn_action.on_click = run_watermark_removal
    
    # Compare toggle
    def toggle_compare(e):
        nonlocal showing_original
        showing_original = not showing_original
        btn_compare.content.controls[1].value = "Processed" if showing_original else "Original"
        update_canvas_view()
        
    btn_compare.on_click = toggle_compare
    
    # Save Image Handler
    def save_cleaned_image(e):
        if processed_img is None or current_media_path is None:
            return
        save_dir = get_save_dir()
        save_dir.mkdir(parents=True, exist_ok=True)
        stem = Path(current_media_path).stem
        save_path = save_dir / f"{stem}_Cleaned_{int(time.time())}.png"
        cv2.imwrite(str(save_path), processed_img)
        status_label.value = f"💾 Saved to {save_path.name}!"
        page.update()
        
    btn_save.on_click = save_cleaned_image
    
    # --- Top Navigation Bar ---
    logo_icon = ft.Container(
        content=ft.Icon(ft.icons.Icons.AUTO_AWESOME, size=20, color="#f472b6"),
        padding=6,
        border_radius=ft.BorderRadius.all(10),
        gradient=ft.LinearGradient(
            begin=ft.Alignment(-1, -1),
            end=ft.Alignment(1, 1),
            colors=["#7c3aed", "#ec4899"]
        ),
        shadow=ft.BoxShadow(spread_radius=1, blur_radius=12, color=ft.Colors.with_opacity(0.4, "#ec4899"))
    )
    
    mobile_menu = ft.PopupMenuButton(
        items=[
            ft.PopupMenuItem("Open Video", icon=ft.icons.Icons.VIDEOCAM, on_click=open_video_dialog),
            ft.PopupMenuItem("Open Image", icon=ft.icons.Icons.IMAGE, on_click=open_image_dialog),
            ft.PopupMenuItem("Clear Box", icon=ft.icons.Icons.LAYERS_CLEAR, on_click=clear_mask_box),
        ],
        visible=False
    )
    
    btn_top_video = ft.Container(
        content=ft.Row([
            ft.Icon(ft.icons.Icons.VIDEOCAM, size=16, color="#ffffff"),
            ft.Text("Open Video", size=13, weight="bold", color="#ffffff")
        ], spacing=6),
        padding=ft.Padding(14, 8, 14, 8),
        border_radius=ft.BorderRadius.all(10),
        gradient=ft.LinearGradient(
            begin=ft.Alignment(-1, -1),
            end=ft.Alignment(1, 1),
            colors=["#6366f1", "#8b5cf6"]
        ),
        shadow=ft.BoxShadow(spread_radius=0, blur_radius=10, color=ft.Colors.with_opacity(0.3, "#6366f1")),
        on_click=open_video_dialog,
        animate=ft.Animation(200, ft.AnimationCurve.EASE_OUT)
    )
    
    btn_top_image = ft.Container(
        content=ft.Row([
            ft.Icon(ft.icons.Icons.IMAGE, size=16, color="#ffffff"),
            ft.Text("Open Image", size=13, weight="bold", color="#ffffff")
        ], spacing=6),
        padding=ft.Padding(14, 8, 14, 8),
        border_radius=ft.BorderRadius.all(10),
        gradient=ft.LinearGradient(
            begin=ft.Alignment(-1, -1),
            end=ft.Alignment(1, 1),
            colors=["#8b5cf6", "#ec4899"]
        ),
        shadow=ft.BoxShadow(spread_radius=0, blur_radius=10, color=ft.Colors.with_opacity(0.3, "#ec4899")),
        on_click=open_image_dialog,
        animate=ft.Animation(200, ft.AnimationCurve.EASE_OUT)
    )
    
    desktop_toolbar = ft.Row(
        controls=[btn_top_video, btn_top_image],
        visible=True,
        spacing=8
    )
    
    header = ft.Container(
        content=ft.Row(
            [
                ft.Row([logo_icon, header_title, header_badge], spacing=8, alignment=ft.MainAxisAlignment.START),
                desktop_toolbar,
                mobile_menu
            ],
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN
        ),
        padding=ft.Padding(16, 12, 16, 12),
        gradient=ft.LinearGradient(
            begin=ft.Alignment(0, -1),
            end=ft.Alignment(0, 1),
            colors=[ft.Colors.with_opacity(0.25, "#18142e"), ft.Colors.with_opacity(0.1, "#0d0b1a")]
        ),
        border=ft.Border(bottom=ft.BorderSide(1.2, ft.Colors.with_opacity(0.25, "#a78bfa"))),
        animate=ft.Animation(250, ft.AnimationCurve.EASE_OUT)
    )
    
    # Floating overlay bar for canvas utilities (Compare, Save, Clear Box)
    canvas_utility_bar = ft.Row(
        [
            btn_clear_mask,
            btn_compare,
            btn_save
        ],
        spacing=6,
        alignment=ft.MainAxisAlignment.END
    )
    
    # Bottom Control Bar
    bottom_bar = ft.Container(
        content=ft.Column(
            [
                ft.Row(
                    [
                        method_dropdown,
                        btn_action
                    ],
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    spacing=10
                ),
                progress_bar,
                ft.Row([status_label, ft.Container(expand=True), canvas_utility_bar], alignment=ft.MainAxisAlignment.SPACE_BETWEEN)
            ],
            spacing=8
        ),
        padding=ft.Padding(16, 12, 16, 14),
        gradient=ft.LinearGradient(
            begin=ft.Alignment(0, -1),
            end=ft.Alignment(0, 1),
            colors=[ft.Colors.with_opacity(0.15, "#18142e"), ft.Colors.with_opacity(0.35, "#0d0b1a")]
        ),
        border=ft.Border(top=ft.BorderSide(1.2, ft.Colors.with_opacity(0.22, "#a78bfa")))
    )
    
    # Wrap canvas in gesture detector for drag box selection
    gesture_canvas = ft.GestureDetector(
        content=canvas_container,
        on_pan_start=on_pan_start,
        on_pan_update=on_pan_update,
        on_pan_end=on_pan_end,
        on_tap_down=on_pan_start,
        expand=True
    )
    
    # --- Full Stack Layout with Wallpaper Background (Clean Black Tint, NO BLUR!) ---
    wallpaper_image = ft.Image(
        src=wp_path,
        fit=ft.BoxFit.COVER,
        expand=True,
        opacity=0.85
    )
    
    wallpaper_tint = ft.Container(
        expand=True,
        bgcolor=ft.Colors.with_opacity(0.55, "#000000") # Clean Black Overlay
    )
    
    foreground_ui = ft.Column(
        [header, gesture_canvas, bottom_bar],
        expand=True,
        spacing=0
    )
    
    root_stack = ft.Stack(
        controls=[
            wallpaper_image,
            wallpaper_tint,
            foreground_ui
        ],
        expand=True
    )
    
    def on_page_resize(e):
        nonlocal is_mobile
        current_w = page.width if page.width is not None else 800
        canvas_container.width = current_w - 30
        canvas_container.height = (page.height or 600) - 200
        if current_w < 580:
            if not is_mobile:
                is_mobile = True
                desktop_toolbar.visible = False
                mobile_menu.visible = True
                header_title.size = 16
                header_badge.visible = False
                page.update()
        else:
            if is_mobile:
                is_mobile = False
                desktop_toolbar.visible = True
                mobile_menu.visible = False
                header_title.size = 19
                header_badge.visible = True
                page.update()
                
    page.on_resize = on_page_resize
    page.add(root_stack)
    on_page_resize(None)

if __name__ == "__main__":
    ft.run(main)
