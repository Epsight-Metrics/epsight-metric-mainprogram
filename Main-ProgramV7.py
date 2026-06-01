"""
Sistem Inspeksi Dimensi Part Manufaktur Berbasis Computer Vision
Capstone Project A.3 â€” Automated Dimensional Inspection
Universitas Brawijaya, Fakultas Ilmu Komputer â€” 2026

Tim Pengembang : Jagoan Mamah Papah
Mitra Industri : PT. Indonesia Epson Industry

Program Utama (Modular Entry Point)
"""

import cv2
import time
import os

# Import modular components
from modules.config import load_config, base_path
from modules.database import DatabaseManager
from modules.reference import ReferenceManager
from modules.tracker import ObjectTracker
from modules.overlays import Notification, WarningOverlay
from modules.gui import SettingsGUI
from modules.detection import preprocess, get_binary, find_objects
from modules.rendering import (
    C,
    label,
    draw_roi_box,
    render_object,
    _draw_tracker_status,
    draw_info_panel,
    draw_result_panel,
    draw_controls,
)
from modules.api_client import ApiClient
from modules.video_stream import VideoStream
from modules.video_stream_websocket import VideoStreamWebSocket
from modules.actions import (
    action_deteksi_part,
    action_save_reference,
    process_pending_reference,
)


def main(cfg: dict):
    """
    Menjalankan loop inspeksi OpenCV utama.
    Menangkap frame dari kamera, menerapkan pipeline prapemrosesan, deteksi kontur,
    stabilisasi pelacakan temporal, pembandingan referensi, dan merender HUD/Overlay.
    """
    WINDOW_NAME = "Capstone â€” Sistem Inspeksi Dimensi v7"

    ppm          = cfg["pixel_per_mm"]
    tol          = cfg["tolerance_mm"]
    roi          = cfg["roi_percent"]
    warn_dur     = cfg["warning_duration"]
    cam_src      = cfg["camera_source"]
    droidcam_fix = cfg["droidcam_fix"]
    dir_ss       = base_path(cfg["dir_screenshot"])
    ref_path     = base_path(cfg["file_reference"])

    print("=" * 62)
    print("  CAPSTONE â€” Sistem Inspeksi Dimensi Part Manufaktur v7 (Modular)")
    print("  Tim: Jagoan Mamah Papah | Universitas Brawijaya 2026")
    print("=" * 62)
    print(f"  Kamera    : {cam_src}")
    print(f"  Skala     : {ppm} px/mm")
    print(f"  Toleransi : Â±{tol} mm")
    print(f"  Tracker   : CONFIRM={ObjectTracker.CONFIRM_FRAMES}fr "
          f"GHOST={ObjectTracker.GHOST_FRAMES}fr "
          f"SMOOTH={ObjectTracker.SMOOTH_FRAMES}fr")
    print()

    # Inisialisasi komponen sistem
    ref_mgr = ReferenceManager(ref_path)
    db_mgr  = DatabaseManager(cfg["db"])
    api_client = ApiClient(cfg.get("api", {}))
    
    # Choose video streaming method: WebSocket (low latency) or MJPEG (simple)
    use_websocket = cfg.get("video_stream", {}).get("use_websocket", True)
    
    if use_websocket:
        video_stream = VideoStreamWebSocket(port=5000, quality=70, fps_limit=30)
        print("  [STREAM] Using WebSocket (low latency: 20-50ms)")
    else:
        video_stream = VideoStream(port=5000, quality=70)
        print("  [STREAM] Using MJPEG (latency: 50-150ms)")
    
    notif   = Notification()
    warning = WarningOverlay()
    tracker = ObjectTracker()

    # Setup trigger callback untuk inspection dari dashboard
    trigger_inspection = [False]  # Use list for mutable closure
    def on_dashboard_trigger():
        trigger_inspection[0] = True
    api_client.set_trigger_callback(on_dashboard_trigger)

    # Start video streaming server
    video_stream.start()

    print(f"  [CAM] Membuka: {cam_src}")
    cap = cv2.VideoCapture(cam_src)
    if isinstance(cam_src, int):
        cap.set(cv2.CAP_PROP_FRAME_WIDTH,  cfg["capture_width"])
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, cfg["capture_height"])
        cap.set(cv2.CAP_PROP_AUTOFOCUS, 0)

    if not cap.isOpened():
        print("\n  [ERROR] Kamera tidak bisa dibuka!")
        db_mgr.close()
        return

    print(f"  [CAM] {int(cap.get(3))} Ã— {int(cap.get(4))}")
    print("\n  D=Deteksi | V=Referensi | S=Screenshot | C=Kontur")
    print("  R=ROI | P=Debug | +/-=Threshold | Q=Keluar\n")

    os.makedirs(dir_ss, exist_ok=True)
    os.makedirs(base_path(cfg["dir_deteksi"]), exist_ok=True)

    show_roi     = True
    show_contour = True
    show_debug   = False
    thresh       = cfg["contour_thresh"]
    fps          = 0.0
    t_prev       = time.time()
    shot_n       = 0

    raw_objects    = []
    stable_objects = []
    results        = []

    while True:
        ret, raw = cap.read()
        if not ret:
            time.sleep(0.3)
            continue

        # Green overlay correction for DroidCam USB in YUV formats
        if droidcam_fix and raw is not None and raw.shape[2] == 3:
            bm = raw[:,:,0].mean()
            gm = raw[:,:,1].mean()
            rm = raw[:,:,2].mean()
            if gm > 150 and bm < 50 and rm < 50:
                try:
                    raw = cv2.cvtColor(raw, cv2.COLOR_YUV2BGR_YUYV)
                except Exception:
                    pass

        frame = raw.copy()
        H, W  = frame.shape[:2]

        rx1 = int(roi[0]*W)
        ry1 = int(roi[1]*H)
        rx2 = int(roi[2]*W)
        ry2 = int(roi[3]*H)
        roi_frame = frame[ry1:ry2, rx1:rx2].copy()

        # Image preprocessing and thresholding
        gray, blurred, enhanced = preprocess(roi_frame)
        binary = get_binary(enhanced, thresh)

        # Object contour finding & temporal tracking
        if show_contour:
            raw_objects    = find_objects(binary, cfg["contour_min_area"],
                                          ppm, cfg["min_feature_mm"])
            stable_objects = tracker.update(raw_objects)
        else:
            raw_objects    = []
            stable_objects = []
            tracker.reset()

        # Compare measurements against profile references
        results = [ref_mgr.compare(obj, tol) for obj in stable_objects]
        process_pending_reference(stable_objects, ref_mgr, notif, tol)

        # Rendering overlay visual annotations
        display     = frame.copy()
        roi_display = display[ry1:ry2, rx1:rx2]

        if show_contour:
            for i, (obj, (st, mname, _)) in enumerate(zip(stable_objects, results)):
                render_object(roi_display, obj, i, st, mname)

            _draw_tracker_status(roi_display, len(raw_objects), len(stable_objects))

        # HUD panels and UI overlay drawing
        draw_roi_box(display, (rx1, ry1, rx2, ry2), show_roi)
        draw_result_panel(display, stable_objects, results)
        draw_info_panel(display, fps, len(stable_objects),
                        show_contour, show_roi, thresh,
                        ref_mgr, db_mgr, ppm, tol)
        draw_controls(display)
        label(display,
              "CAPSTONE v7  |  Inspeksi Dimensi Part Manufaktur  |  Jagoan Mamah Papah",
              (W//2-285, H-10), 0.37, C["gray"])

        # Debug pre-processing visuals
        if show_debug:
            dh = H // 4
            dw = W // 4
            for ig, ti, px_off in [
                (gray,     "Gray",   W-dw*3-15),
                (enhanced, "CLAHE",  W-dw*2-10),
                (binary,   "Binary", W-dw-5),
            ]:
                t_  = cv2.resize(ig, (dw, dh))
                tb  = cv2.cvtColor(t_, cv2.COLOR_GRAY2BGR)
                label(tb, ti, (4, 18), 0.45, C["yellow"])
                display[8:8+dh, px_off:px_off+dw] = tb
                cv2.rectangle(display, (px_off, 8), (px_off+dw, 8+dh), C["cyan"], 1)

        warning.draw(display, warn_dur)
        notif.draw(display)

        # Update video stream frame
        video_stream.update_frame(display)

        # FPS calculation
        now    = time.time()
        fps    = 0.85*fps + 0.15*(1.0/max(now-t_prev, 1e-5))
        t_prev = now

        cv2.imshow(WINDOW_NAME, display)
        key = cv2.waitKey(1) & 0xFF

        # Trigger dari dashboard (online mode)
        if trigger_inspection[0]:
            trigger_inspection[0] = False
            action_deteksi_part(stable_objects, results, roi_frame,
                                notif, warning, db_mgr, cfg, api_client)
            print("[MAIN] Inspection triggered by dashboard")

        if key in (ord('q'), 27):
            break

        elif key == ord('d'):
            # Trigger dari keyboard (offline mode)
            action_deteksi_part(stable_objects, results, roi_frame,
                                notif, warning, db_mgr, cfg, api_client)

        elif key == ord('v'):
            action_save_reference(stable_objects, ref_mgr, notif, tol)

        elif key == ord('s'):
            shot_n += 1
            fname = os.path.join(dir_ss, f"ss_{shot_n:04d}.png")
            try:
                cv2.imwrite(fname, display)
                notif.add(f"Screenshot: ss_{shot_n:04d}.png", C["cyan"], 2.0)
            except Exception as e:
                print(f"[ERROR] Gagal screenshot: {e}")
                notif.add("Gagal screenshot!", C["ng"], 2.0)

        elif key == ord('r'):
            show_roi = not show_roi

        elif key == ord('c'):
            show_contour = not show_contour
            tracker.reset()
            notif.add(f"Kontur {'ON' if show_contour else 'OFF'}", C["white"], 1.5)

        elif key == ord('p'):
            show_debug = not show_debug

        elif key in (ord('+'), ord('=')):
            thresh = min(thresh+5, 250)
            tracker.reset()
            notif.add(f"Threshold: {thresh}", C["white"], 1.0)

        elif key == ord('-'):
            thresh = max(thresh-5, 10)
            tracker.reset()
            notif.add(f"Threshold: {thresh}", C["white"], 1.0)

    cap.release()
    cv2.destroyAllWindows()
    db_mgr.close()
    api_client.stop()
    video_stream.stop()
    print("\n[INFO] Program selesai.")


if __name__ == "__main__":
    # 1. Load (or generate) config.json parameters
    cfg = load_config()

    # 2. Open pre-flight settings window (Tkinter GUI)
    gui = SettingsGUI(cfg)
    result = gui.run()

    # 3. Open main OpenCV camera inspection loop if Settings window is successfully saved
    if result is not None:
        main(result)
    else:
        print("[INFO] Settings window closed â€” application terminated.")
