"""
Modul Manajemen Referensi Benda
Sistem Inspeksi Dimensi Part Manufaktur
"""

import os
import json
from modules.utils import now_str
from modules.detection import DetectedObject

def _outer_delta(obj: DetectedObject, ref: dict) -> float:
    """Hitung selisih dimensi terluar antara objek terdeteksi dan profil referensi."""
    if obj.shape == "circle":
        return abs(obj.diameter_mm - ref.get("diameter_mm", 0))
    return abs(obj.width_mm - ref.get("width_mm", 0)) + abs(obj.height_mm - ref.get("height_mm", 0))


class ReferenceManager:
    """
    Menyimpan dan membandingkan profil dimensi referensi dari referensi.json.
    Mendukung banyak profil bernama untuk setiap tipe bentuk.
    """
    def __init__(self, filepath: str):
        self.filepath = filepath
        self.refs: dict = {}
        self._load()

    def _load(self):
        if os.path.exists(self.filepath):
            try:
                with open(self.filepath, "r") as f:
                    self.refs = json.load(f)
                print(f"[REF] {len(self.refs)} referensi dimuat dari '{self.filepath}'")
                for name, d in self.refs.items():
                    key = d.get("diameter_mm", d.get("width_mm","?"))
                    print(f"  · '{name}' — {d['shape']} ({key} mm)")
            except Exception as e:
                print(f"[REF] Gagal baca: {e}")
                self.refs = {}
        else:
            print("[REF] File referensi belum ada — akan dibuat saat pertama save.")

    def _save(self):
        try:
            with open(self.filepath, "w") as f:
                json.dump(self.refs, f, indent=2)
            print(f"[REF] Disimpan ({len(self.refs)} profil)")
        except Exception as e:
            print(f"[REF] Gagal simpan referensi: {e}")

    def save_reference(self, obj: DetectedObject, name: str, tol: float) -> dict:
        """Simpan objek saat ini sebagai profil referensi baru."""
        data = {
            "name": name,
            "shape": obj.shape,
            "vertices": obj.vertices,
            "diameter_mm": round(obj.diameter_mm, 2),
            "width_mm": round(obj.width_mm, 2),
            "height_mm": round(obj.height_mm, 2),
            "tolerance_mm": tol,
            "timestamp": now_str()
        }
        self.refs[name] = data
        self._save()
        return data

    def compare(self, obj: DetectedObject, tol: float) -> tuple:
        """
        Bandingkan dimensi objek terdeteksi dengan profil referensi yang cocok.
        Mengembalikan tuple: (status [GOOD/NO GOOD/NO REF], nama_referensi_terdekat, string_detail)
        """
        same = {n:d for n,d in self.refs.items() if d["shape"]==obj.shape}
        if not same:
            return "NO REF", None, f"Belum ada referensi untuk {obj.shape}"

        best_name = None
        best_delta = float("inf")
        for name, ref in same.items():
            t = ref.get("tolerance_mm", tol)
            if obj.shape == "circle":
                delta = abs(obj.diameter_mm - ref["diameter_mm"])
                ok    = delta <= t
            else:
                dw = abs(obj.width_mm  - ref["width_mm"])
                dh = abs(obj.height_mm - ref["height_mm"])
                delta = max(dw, dh)
                ok = dw<=t and dh<=t

            if ok and delta < best_delta:
                best_delta = delta
                best_name = name

        if best_name:
            ref = same[best_name]
            if obj.shape == "circle":
                d = abs(obj.diameter_mm - ref["diameter_mm"])
                detail = f"Ø ref={ref['diameter_mm']:.1f} got={obj.diameter_mm:.1f} Δ={d:.1f}mm ✓"
            else:
                detail = (f"P ref={ref['width_mm']:.1f} got={obj.width_mm:.1f} "
                          f"| L ref={ref['height_mm']:.1f} got={obj.height_mm:.1f} ✓")
            return "GOOD", best_name, detail

        closest = min(same, key=lambda n: _outer_delta(obj, same[n]))
        ref = same[closest]
        if obj.shape == "circle":
            d = abs(obj.diameter_mm - ref["diameter_mm"])
            detail = f"Ø ref={ref['diameter_mm']:.1f} got={obj.diameter_mm:.1f} Δ={d:.1f}mm ✗"
        else:
            detail = (f"P ref={ref['width_mm']:.1f} got={obj.width_mm:.1f} "
                      f"| L ref={ref['height_mm']:.1f} got={obj.height_mm:.1f} ✗")
        return "NO GOOD", closest, detail

    def list_names(self) -> list:
        """Mengembalikan daftar nama profil referensi."""
        return list(self.refs.keys())

    def clear_all(self):
        """Hapus semua profil referensi."""
        self.refs = {}
        self._save()
