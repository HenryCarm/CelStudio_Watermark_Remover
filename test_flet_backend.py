import os
import sys
import time
from pathlib import Path
import cv2
import numpy as np

from core.engine import _inpaint_smart, _inpaint_cel_ai, _inpaint_quick, _inpaint_precision
from core.constants import get_wallpaper_path, get_save_dir

def run_tests():
    print("=== STARTING CELSTUDIO FLET BACKEND TEST SUITE ===")
    
    # 1. Check wallpaper exists and readable
    wp = get_wallpaper_path()
    assert wp.exists(), f"Wallpaper not found at {wp}"
    print(f"✅ Wallpaper verified at {wp}")
    
    # 2. Test Image AI Inpainting
    h, w = 300, 400
    test_img = np.zeros((h, w, 3), dtype=np.uint8)
    test_img[:, :] = (120, 40, 80) # Maroon background
    # Add white text watermark
    cv2.putText(test_img, "SAMPLE WATERMARK", (50, 150), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)
    
    mask = np.zeros((h, w), dtype=np.uint8)
    mask[120:180, 40:360] = 255
    
    methods = [
        ("Smart Dominant Color", _inpaint_smart),
        ("Cel AI Color Trapping", _inpaint_cel_ai),
        ("Quick Telea", _inpaint_quick),
        ("Precision Navier-Stokes", _inpaint_precision),
    ]
    
    for name, fn in methods:
        t0 = time.time()
        res = fn(test_img.copy(), mask.copy())
        elapsed = time.time() - t0
        assert res.shape == test_img.shape, f"{name} output shape mismatch!"
        assert res.dtype == np.uint8, f"{name} output dtype mismatch!"
        print(f"✅ {name} passed in {elapsed*1000:.1f}ms")
        
    # 3. Test Video Frame Pipeline
    test_video_path = Path("/tmp/cel_test_video.mp4")
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(str(test_video_path), fourcc, 30.0, (w, h))
    for i in range(15):
        frame = test_img.copy()
        cv2.putText(frame, f"Frame {i}", (10, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1)
        writer.write(frame)
    writer.release()
    print("✅ Synthetic test video created")
    
    # Process the synthetic video
    cap = cv2.VideoCapture(str(test_video_path))
    out_video_path = Path("/tmp/cel_test_video_out.mp4")
    out_writer = cv2.VideoWriter(str(out_video_path), fourcc, 30.0, (w, h))
    
    frames_processed = 0
    while cap.isOpened():
        ret, frame = cap.read()
        if not ret:
            break
        cleaned = _inpaint_cel_ai(frame, mask)
        out_writer.write(cleaned)
        frames_processed += 1
        
    cap.release()
    out_writer.release()
    
    assert frames_processed == 15, f"Expected 15 frames, got {frames_processed}"
    assert out_video_path.exists() and out_video_path.stat().st_size > 0
    print(f"✅ Video processing engine passed ({frames_processed} frames cleaned and written)")
    
    print("=== ALL TESTS PASSED WITH 100% SUCCESS ===")

if __name__ == "__main__":
    run_tests()
