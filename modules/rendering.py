"""
Modul Rendering Visualisasi OpenCV
Sistem Inspeksi Dimensi Part Manufaktur
"""

import cv2
import math
from modules.utils import midpt, dist
from modules.detection import DetectedObject, SHAPE_LABEL

# OpenCV rendering constants (BGR) and font
C = {
    "green"  : (50,  220,  50),
    "red"    : (40,   40, 220),
    "yellow" : (0,   210, 255),
    "cyan"   : (255, 200,   0),
    "white"  : (255, 255, 255),
    "orange" : (0,   140, 255),
    "purple" : (200,  50, 200),
    "gray"   : (160, 160, 160),
    "black"  : (0,     0,   0),
    "teal"   : (180, 220, 120),
    "good"   : (50,  220,  50),
    "ng"     : (40,   40, 220),
    "warn"   : (0,   165, 255),
}

FONT = cv2.FONT_HERSHEY_SIMPLEX

def _status_color(st: str) -> tuple:
    return C["good"] if st == "GOOD" else (C["ng"] if st == "NO GOOD" else C["warn"])

def label(img, text: str, pos: tuple, scale: float = 0.50, color: tuple = C["white"],
          bg: tuple = None, thick: int = 1, pad: int = 5):
    """Menggambar label teks dengan background opsional pada citra OpenCV."""
    (tw, th), _ = cv2.getTextSize(text, FONT, scale, thick)
    x, y = int(pos[0]), int(pos[1])
    if bg is not None:
        cv2.rectangle(img, (x-pad, y-th-pad), (x+tw+pad, y+pad), bg, -1)
    cv2.putText(img, text, (x, y), FONT, scale, color, thick, cv2.LINE_AA)

def arrow_line(img, p1: tuple, p2: tuple, color: tuple, thick: int = 1):
    """Menggambar garis panah penunjuk dimensi di OpenCV."""
    p1 = (int(p1[0]), int(p1[1]))
    p2 = (int(p2[0]), int(p2[1]))
    cv2.line(img, p1, p2, color, thick, cv2.LINE_AA)
    dx = p2[0] - p1[0]
    dy = p2[1] - p1[1]
    length = math.hypot(dx, dy)
    if length == 0:
        return
    nx, ny = -dy / length * 6, dx / length * 6
    for p in [p1, p2]:
        cv2.line(img, (int(p[0]-nx), int(p[1]-ny)),
                 (int(p[0]+nx), int(p[1]+ny)), color, thick+1, cv2.LINE_AA)

def draw_dim_line(img, p1: tuple, p2: tuple, value_mm: float, color: tuple, offset_px: int = 22):
    """Menggambar anotasi garis dimensi beserta nilai desimal (mm) di atas objek."""
    p1 = (int(p1[0]), int(p1[1]))
    p2 = (int(p2[0]), int(p2[1]))
    dx = p2[0] - p1[0]
    dy = p2[1] - p1[1]
    length = math.hypot(dx, dy)
    if length < 2:
        return
    nx = int(-dy / length * offset_px)
    ny = int(dx / length * offset_px)
    op1 = (p1[0] + nx, p1[1] + ny)
    op2 = (p2[0] + nx, p2[1] + ny)
    cv2.line(img, p1, op1, color, 1, cv2.LINE_AA)
    cv2.line(img, p2, op2, color, 1, cv2.LINE_AA)
    arrow_line(img, op1, op2, color, 1)
    mid = midpt(op1, op2)
    label(img, f"{value_mm:.1f}mm", (mid[0]-18, mid[1]-5), 0.44, color, (18,18,18))

def draw_roi_box(img, roi_px: tuple, active: bool):
    """Menggambar kotak pembatas Region of Interest (ROI) dengan tepian bergaya HUD industri."""
    if not active:
        return
    x1, y1, x2, y2 = roi_px
    overlay = img.copy()
    cv2.rectangle(overlay, (0,0), (img.shape[1],img.shape[0]), C["black"], -1)
    cv2.rectangle(overlay, (x1,y1), (x2,y2), C["black"], -1)
    cv2.addWeighted(overlay, 0.20, img, 0.80, 0, img)
    cv2.rectangle(img, (x1,y1), (x2,y2), C["cyan"], 2)
    cl = 22
    for (cx,cy),(ddx,ddy) in [((x1,y1),(1,1)), ((x2,y1),(-1,1)),
                              ((x1,y2),(1,-1)), ((x2,y2),(-1,-1))]:
        cv2.line(img, (cx,cy), (cx+ddx*cl,cy), C["cyan"], 3)
        cv2.line(img, (cx,cy), (cx,cy+ddy*cl), C["cyan"], 3)
    label(img, "[ AREA INSPEKSI ]", (x1+8, y1-8), 0.44, C["cyan"])

def render_object(img, obj: DetectedObject, idx: int, status: str, matched_name: str):
    """Render kontur terdeteksi, bounding box rotasi, dan garis dimensi terukur pada frame."""
    col    = _status_color(status)
    sh_lbl = SHAPE_LABEL.get(obj.shape, obj.shape.upper())
    cv2.drawContours(img, [obj.contour], -1, C["teal"], 1)

    if obj.shape == "circle":
        cv2.circle(img, obj.center, int(obj.radius_px), col, 2, cv2.LINE_AA)
        cx, cy = obj.center
        r = int(obj.radius_px)
        draw_dim_line(img, (cx-r,cy), (cx+r,cy), obj.diameter_mm, C["yellow"], 28)
        top_y = cy - r - 14
    else:
        cv2.drawContours(img, [obj.rot_box], -1, col, 2)
        box = obj.rot_box
        sa = dist(box[0], box[1])
        sb = dist(box[1], box[2])
        if sa >= sb:
            lp1, lp2 = tuple(box[0]), tuple(box[1])
            sp1, sp2 = tuple(box[1]), tuple(box[2])
        else:
            lp1, lp2 = tuple(box[1]), tuple(box[2])
            sp1, sp2 = tuple(box[0]), tuple(box[1])
        draw_dim_line(img, lp1, lp2, obj.width_mm,  C["yellow"], 28)
        draw_dim_line(img, sp1, sp2, obj.height_mm, C["purple"], 28)
        top_y = obj.bbox[1] - 14

    label(img, f"#{idx+1} {sh_lbl}  {obj.label_size}", (obj.bbox[0], top_y), 0.48, col, (20,20,20))
    st_txt = f"{status}  [{matched_name}]" if matched_name else status
    label(img, st_txt, (obj.bbox[0], top_y-20), 0.52, col, (20,20,20), 2)

def _draw_tracker_status(roi_img, n_raw: int, n_stable: int):
    """Render indikator kecil di pojok kiri bawah ROI yang menampilkan RAW vs STABLE deteksi."""
    color = (50, 220, 50) if n_raw == n_stable else (0, 165, 255)
    H = roi_img.shape[0]
    cv2.putText(roi_img, f"RAW={n_raw}  STABLE={n_stable}",
                (6, H-8), cv2.FONT_HERSHEY_SIMPLEX, 0.38, (0,0,0), 2, cv2.LINE_AA)
    cv2.putText(roi_img, f"RAW={n_raw}  STABLE={n_stable}",
                (6, H-8), cv2.FONT_HERSHEY_SIMPLEX, 0.38, color, 1, cv2.LINE_AA)

def draw_info_panel(img, fps: float, obj_count: int, show_contour: bool, show_roi: bool,
                    thresh: int, ref_mgr, db_mgr, ppm: float, tol: float):
    """Render panel informasi HUD di sisi kiri atas layar OpenCV."""
    ov = img.copy()
    cv2.rectangle(ov, (8,8), (340,192), (10,10,10), -1)
    cv2.addWeighted(ov, 0.75, img, 0.25, 0, img)
    cv2.rectangle(img, (8,8), (340,192), C["cyan"], 1)

    db_st = "AKTIF" if db_mgr.enabled else "STUB"
    rows = [
        (f"FPS        : {fps:5.1f}",         C["green"] if fps>15 else C["yellow"]),
        (f"Objek      : {obj_count} terdeteksi", C["green"] if obj_count>0 else C["gray"]),
        (f"Skala      : {ppm:.2f} px/mm",     C["white"]),
        (f"Toleransi  : ±{tol} mm",           C["white"]),
        (f"Referensi  : {len(ref_mgr.refs)} profil", C["good"] if ref_mgr.refs else C["warn"]),
        (f"Database   : {db_st}",             C["good"] if db_mgr.enabled else C["warn"]),
        (f"Kontur     : {'ON' if show_contour else 'OFF'}", C["teal"] if show_contour else C["gray"]),
        (f"Thresh     : {thresh}   (+/- ubah)", C["gray"]),
    ]
    for i, (t, col) in enumerate(rows):
        cv2.putText(img, t, (16,32+i*20), FONT, 0.43, col, 1, cv2.LINE_AA)

def draw_result_panel(img, objects: list, results: list):
    """Render panel tabel hasil dimensi di pojok kanan bawah."""
    if not objects:
        return
    H, W = img.shape[:2]
    n = len(objects)
    ph = 40 + n * 26 + 10
    px = W - 420
    py = H - ph - 14
    ov = img.copy()
    cv2.rectangle(ov, (px-10, py-10), (W-10, H-10), (10,10,10), -1)
    cv2.addWeighted(ov, 0.70, img, 0.30, 0, img)
    cv2.rectangle(img, (px-10, py-10), (W-10, H-10), C["yellow"], 1)

    label(img, f"HASIL PENGUKURAN ({n} objek)", (px, py+8), 0.50, C["yellow"])
    for i, (obj, (st, mname, _)) in enumerate(zip(objects, results)):
        sh = SHAPE_LABEL.get(obj.shape, obj.shape)
        dim = f"Ø{obj.diameter_mm:.2f}mm" if obj.shape=="circle" else f"{obj.width_mm:.2f}×{obj.height_mm:.2f}mm"
        ref_txt = f" ← {mname}" if mname else ""
        sc = _status_color(st)
        label(img, f"#{i+1} {sh} {dim}", (px, py+34+i*26), 0.42, C["cyan"])
        label(img, f"[{st}]{ref_txt}", (px+225, py+34+i*26), 0.42, sc, (20,20,20))

def draw_controls(img):
    """Render panduan tombol shortcut di sisi kanan bawah layar."""
    H, W = img.shape[:2]
    keys = [
        "[Q/ESC] Keluar", "[D]     Deteksi Part", "[V]     Save Referensi",
        "[S]     Screenshot", "[R]     ROI on/off", "[C]     Kontur on/off",
        "[P]     Debug view", "[+/-]   Threshold"
    ]
    for i, t in enumerate(keys):
        label(img, t, (W-210, H-14-i*18), 0.37, C["gray"])
