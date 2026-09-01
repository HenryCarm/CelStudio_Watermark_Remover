import flet as ft
import cv2
import numpy as np
import base64
import math

# ─── COLOR PALETTE ────────────────────────────────────────────────────────
BG_DEEP = "#09090f"
BG_BASE = "#0e0e1a"
BG_CARD = "#131320"
PURPLE = "#7c3aed"
PURPLE_LIGHT = "#a78bfa"
TEXT_MAIN = "#e4e4f0"

def main(page: ft.Page):
    page.title = "MyScreen WR Mobile 🪄"
    page.theme_mode = ft.ThemeMode.DARK
    page.bgcolor = BG_DEEP
    page.padding = 0
    page.window_width = 400
    page.window_height = 800

    # ─── APP STATE ────────────────────────────────────────────────────────
    state = {
        "img_orig": None,
        "img_cur": None,
        "mask": None,
        "h": 0, "w": 0,
        "scale": 1.0,
        "offset_x": 0.0,
        "offset_y": 0.0,
        "tool": "brush",  # "brush" or "pan"
        "brush_size": 25,
        "last_x": None,
        "last_y": None,
        "is_processing": False
    }

    # ─── UI COMPONENTS ────────────────────────────────────────────────────
    img_display = ft.Image(src=None, fit=ft.BoxFit.CONTAIN, visible=False)
    mask_display = ft.Image(src=None, fit=ft.BoxFit.CONTAIN, visible=False)
    
    status_text = ft.Text("Ready! 🪄", color=PURPLE_LIGHT, size=12, weight="bold")
    loading_ring = ft.ProgressRing(width=16, height=16, stroke_width=2, color=PURPLE_LIGHT, visible=False)

    # ─── HELPER FUNCTIONS ─────────────────────────────────────────────────
    def cv2_to_b64(img, is_rgba=False):
        """Converts OpenCV image to base64 for Flet to display"""
        if img is None: return None
        if is_rgba:
            _, buffer = cv2.imencode('.png', img)
        else:
            _, buffer = cv2.imencode('.jpg', img, [int(cv2.IMWRITE_JPEG_QUALITY), 95])
        return base64.b64encode(buffer).decode('utf-8')

    def update_mask_display():
        """Creates a red semi-transparent overlay from the numpy mask"""
        if state["mask"] is None or not state["mask"].any():
            mask_display.src_base64 = None
            mask_display.visible = False
            return
        
        # BGRA format for OpenCV -> Flet PNG
        overlay = np.zeros((state["h"], state["w"], 4), dtype=np.uint8)
        overlay[state["mask"] > 0] = [250, 139, 167, 140] # Purple-ish Red mask!
        
        mask_display.src_base64 = cv2_to_b64(overlay, is_rgba=True)
        mask_display.visible = True
        page.update()

    # ─── GESTURE HANDLING (DRAWING & PANNING) ─────────────────────────────
    def map_to_img_coords(x, y, container_w, container_h):
        """Maps Flet screen coordinates to actual image pixel coordinates"""
        if state["w"] == 0 or state["h"] == 0: return 0, 0
        
        # Flet's ImageFit.CONTAIN logic
        img_aspect = state["w"] / state["h"]
        box_aspect = container_w / container_h
        
        if img_aspect > box_aspect:
            # Image hits width bounds
            draw_w = container_w
            draw_h = container_w / img_aspect
            pad_x = 0
            pad_y = (container_h - draw_h) / 2
        else:
            # Image hits height bounds
            draw_h = container_h
            draw_w = container_h * img_aspect
            pad_x = (container_w - draw_w) / 2
            pad_y = 0
            
        # Adjust for Pan & Zoom scale
        adj_x = (x - pad_x - state["offset_x"]) / state["scale"]
        adj_y = (y - pad_y - state["offset_y"]) / state["scale"]
        
        img_x = int((adj_x / draw_w) * state["w"])
        img_y = int((adj_y / draw_h) * state["h"])
        return img_x, img_y

    def on_pan_start(e: ft.DragStartEvent):
        if state["img_cur"] is None: return
        state["last_x"] = e.local_x
        state["last_y"] = e.local_y

    def on_pan_update(e: ft.DragUpdateEvent):
        if state["img_cur"] is None: return
        
        if state["tool"] == "pan":
            # Move the image
            state["offset_x"] += e.delta_x
            state["offset_y"] += e.delta_y
            stack_transform.left = state["offset_x"]
            stack_transform.top = state["offset_y"]
            page.update()
            
        elif state["tool"] == "brush":
            # Draw on the mask
            cw, ch = gesture_container.width, gesture_container.height
            if not cw or not ch: return # Prevent math errors
            
            ix1, iy1 = map_to_img_coords(state["last_x"], state["last_y"], cw, ch)
            ix2, iy2 = map_to_img_coords(e.local_x, e.local_y, cw, ch)
            
            # Draw line on numpy mask
            cv2.line(state["mask"], (ix1, iy1), (ix2, iy2), 255, state["brush_size"] * 2)
            
            state["last_x"] = e.local_x
            state["last_y"] = e.local_y
            update_mask_display()

    # ─── CORE ACTIONS ─────────────────────────────────────────────────────
    def on_file_picked(e: ft.FilePickerResultEvent):
        if e.files and len(e.files) > 0:
            path = e.files[0].path
            img = cv2.imread(path)
            if img is not None:
                state["img_orig"] = img.copy()
                state["img_cur"] = img.copy()
                state["h"], state["w"] = img.shape[:2]
                state["mask"] = np.zeros((state["h"], state["w"]), dtype=np.uint8)
                
                # Reset transform
                state["scale"] = 1.0
                state["offset_x"] = 0.0
                state["offset_y"] = 0.0
                stack_transform.left = 0
                stack_transform.top = 0
                stack_transform.scale = 1.0
                
                img_display.src_base64 = cv2_to_b64(img)
                img_display.visible = True
                update_mask_display()
                
                status_text.value = f"Loaded! {state['w']}x{state['h']}"
                page.update()

    def do_inpaint(e):
        if state["img_cur"] is None or state["mask"] is None or not state["mask"].any():
            status_text.value = "⚠️ Draw a mask first!"
            page.update()
            return
            
        # UI Loading State
        status_text.value = "✨ Removing watermark..."
        loading_ring.visible = True
        btn_inpaint.disabled = True
        page.update()
        
        # Perform Quick Inpaint (Telea)
        result = cv2.inpaint(state["img_cur"], state["mask"], 3, cv2.INPAINT_TELEA)
        state["img_cur"] = result
        state["mask"].fill(0) # Clear mask
        
        # Update UI
        img_display.src_base64 = cv2_to_b64(result)
        update_mask_display()
        
        status_text.value = "✅ All clean!"
        loading_ring.visible = False
        btn_inpaint.disabled = False
        page.update()

    def toggle_tool(e):
        if state["tool"] == "brush":
            state["tool"] = "pan"
            btn_tool.icon = ft.icons.PAN_TOOL
            btn_tool.tooltip = "Switch to Brush"
            status_text.value = "🖐 Pan Mode"
        else:
            state["tool"] = "brush"
            btn_tool.icon = ft.icons.BRUSH
            btn_tool.tooltip = "Switch to Pan"
            status_text.value = "🖌 Brush Mode"
        page.update()

    def clear_mask(e):
        if state["mask"] is not None:
            state["mask"].fill(0)
            update_mask_display()
            status_text.value = "🧹 Mask cleared!"
            page.update()

    # ─── UI LAYOUT ────────────────────────────────────────────────────────
    file_picker = ft.FilePicker(on_result=on_file_picked)
    page.overlay.append(file_picker)

    # The canvas stack that holds the image and mask
    stack_transform = ft.Container(
        content=ft.Stack([img_display, mask_display], expand=True),
        expand=True,
        left=0, top=0, scale=1.0,
        animate_scale=ft.animation.Animation(200, ft.AnimationCurve.EASE_OUT)
    )

    gesture_container = ft.GestureDetector(
        content=stack_transform,
        expand=True,
        drag_interval=10, # smooth updates
        on_pan_start=on_pan_start,
        on_pan_update=on_pan_update,
    )

    # ─── BUTTONS ──────────────────────────────────────────────────────────
    btn_open = ft.IconButton(
        icon=ft.icons.IMAGE_SEARCH, 
        icon_color=TEXT_MAIN,
        on_click=lambda _: file_picker.pick_files(allow_multiple=False)
    )
    
    btn_tool = ft.IconButton(
        icon=ft.icons.BRUSH, 
        icon_color=PURPLE_LIGHT,
        on_click=toggle_tool,
        tooltip="Switch to Pan"
    )
    
    btn_clear = ft.IconButton(
        icon=ft.icons.CLEANING_SERVICES,
        icon_color=TEXT_MAIN,
        on_click=clear_mask
    )
    
    btn_inpaint = ft.ElevatedButton(
        "✨ Remove",
        color=ft.colors.WHITE,
        bgcolor=PURPLE,
        on_click=do_inpaint
    )

    # ─── PAGE ASSEMBLY ────────────────────────────────────────────────────
    page.add(
        ft.Column(
            expand=True,
            controls=[
                # Header
                ft.Container(
                    content=ft.Row([
                        ft.Text("🪄 MyScreen WR", size=18, weight="bold", color=PURPLE_LIGHT),
                        ft.Row([loading_ring, status_text])
                    ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                    padding=15,
                    bgcolor=BG_BASE
                ),
                
                # Editor Area
                ft.Container(
                    content=gesture_container,
                    expand=True,
                    bgcolor=BG_CARD,
                    border_radius=10,
                    margin=10,
                    clip_behavior=ft.ClipBehavior.HARD_EDGE # Keeps image inside bounds!
                ),
                
                # Bottom Toolbar
                ft.Container(
                    content=ft.Row([
                        btn_open,
                        btn_tool,
                        btn_clear,
                        ft.Container(expand=True), # Spacer
                        btn_inpaint
                    ]),
                    padding=10,
                    bgcolor=BG_BASE,
                    border_radius=ft.border_radius.only(topLeft=15, topRight=15)
                )
            ]
        )
    )

if __name__ == "__main__":
    ft.run(main)
