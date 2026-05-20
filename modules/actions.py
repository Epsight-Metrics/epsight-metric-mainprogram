"""
Modul Aksi Keyboard Operator
Sistem Inspeksi Dimensi Part Manufaktur
"""

import os
import json
import cv2
import tkinter as tk
from tkinter import simpledialog
from modules.utils import now_str, now_iso
from modules.config import base_path
from modules.rendering import C


def action_deteksi_part(objects: list, results: list, roi_frame,
                        notif, warning, db_mgr, cfg: dict):
    """
    Menyimpan hasil pengukuran semua objek terdeteksi ke file JSON,
    menyimpan citra crop ROI ke PNG, mengirimkan log data ke PostgreSQL,
    dan memicu warning overlay jika ada part NO GOOD.
    """
    if not objects:
        notif.add("Tidak ada objek terdeteksi!", C["warn"])
        return

    ng_list    = [(o, r) for o, r in zip(objects, results) if r[0] == "NO GOOD"]
    noref_list = [(o, r) for o, r in zip(objects, results) if r[0] == "NO REF"]
    good_list  = [(o, r) for o, r in zip(objects, results) if r[0] == "GOOD"]

    if ng_list:
        warning.trigger(len(ng_list))
        warning.set_duration(cfg["warning_duration"])
    elif noref_list:
        notif.add(f"{len(noref_list)} objek tanpa referensi — simpan dulu [V]", C["warn"], 4.0)

    dir_deteksi = base_path(cfg["dir_deteksi"])
    os.makedirs(dir_deteksi, exist_ok=True)
    ts = now_str()
    json_data = {
        "timestamp": ts,
        "pixel_per_mm": cfg["pixel_per_mm"],
        "tolerance_mm": cfg["tolerance_mm"],
        "summary": {
            "total": len(objects),
            "good": len(good_list),
            "no_good": len(ng_list),
            "no_ref": len(noref_list)
        },
        "objects": []
    }
    for i, (obj, (st, mname, detail)) in enumerate(zip(objects, results)):
        e = obj.to_dict()
        e.update({"id": i+1, "status": st, "matched_ref": mname, "match_detail": detail})
        json_data["objects"].append(e)

    json_path = os.path.join(dir_deteksi, f"deteksi_{ts}.json")
    img_path  = os.path.join(dir_deteksi, f"deteksi_{ts}.png")
    
    try:
        with open(json_path, "w") as f:
            json.dump(json_data, f, indent=2)
        cv2.imwrite(img_path, roi_frame)
    except Exception as e:
        print(f"[ACTION] Gagal menyimpan file deteksi ke disk: {e}")
        notif.add("Gagal simpan file deteksi ke disk!", C["ng"])

    for i, (obj, (st, mname, detail)) in enumerate(zip(objects, results)):
        db_mgr.save_log(
            timestamp=now_iso(),
            id_part=f"{ts}_obj{i+1}",
            nilai_dimensi={
                "shape": obj.shape,
                "diameter_mm": obj.diameter_mm,
                "width_mm": obj.width_mm,
                "height_mm": obj.height_mm,
                "area_px": obj.area_px
            },
            status=st,
            matched_ref=mname,
            image_path=img_path,
            shape=obj.shape
        )

    summary = f"✓ {len(good_list)} GOOD"
    if ng_list:
        summary += f"  ✗ {len(ng_list)} NG"
    if noref_list:
        summary += f"  ? {len(noref_list)} NO REF"
    notif.add(f"Deteksi selesai — {summary}", C["good"] if not ng_list else C["warn"], 4.0)
    print(f"[DETEKSI] {json_path}")


def action_save_reference(objects: list, ref_mgr, notif, tol: float):
    """
    Menampilkan dialog input Tkinter sinkron untuk memberikan nama referensi
    dan menyimpannya ke referensi.json.
    """
    if not objects:
        notif.add("ERROR: Tidak ada objek terdeteksi!", C["ng"], 4.0)
        return
    if len(objects) > 1:
        notif.add(f"ERROR: {len(objects)} objek! Sisakan 1 saja.", C["ng"], 5.0)
        return

    # Create a hidden root window so the dialog appears without a blank Tk window.
    temp_root = tk.Tk()
    temp_root.withdraw()
    temp_root.attributes("-topmost", True)
    name = simpledialog.askstring(
        "Simpan Referensi",
        "Masukkan nama referensi (contoh: Gear Kecil A):",
        parent=temp_root)
    temp_root.destroy()

    if name and name.strip():
        ref_mgr.save_reference(objects[0], name.strip(), tol)
        notif.add(f"'{name.strip()}' disimpan: {objects[0].label_size}", C["good"], 5.0)
    else:
        notif.add("Batal menyimpan referensi.", C["warn"], 2.0)


def process_pending_reference(objects, ref_mgr, notif, tol):
    """
    No-op compatibility stub.
    """
    pass
