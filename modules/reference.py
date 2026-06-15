"""
Modul Manajemen Referensi Benda
Sistem Inspeksi Dimensi Part Manufaktur
"""

import os
import json
from modules.utils import now_str
from modules.detection import DetectedObject


def _score(obj: DetectedObject, ref: dict) -> float:
    """
    Hitung skor kemiripan antara objek dan referensi menggunakan
    selisih relatif (persentase) terhadap ukuran referensi.
    Skor lebih kecil = lebih mirip (0% = cocok sempurna).
    Menggunakan max dari selisih relatif width & height (atau diameter).
    """
    if obj.shape == "circle":
        ref_d = ref.get("diameter_mm", 1)
        if ref_d <= 0:
            return float("inf")
        return abs(obj.diameter_mm - ref_d) / ref_d * 100
    else:
        ref_w = ref.get("width_mm", 1)
        ref_h = ref.get("height_mm", 1)
        if ref_w <= 0 or ref_h <= 0:
            return float("inf")
        pct_w = abs(obj.width_mm - ref_w) / ref_w * 100
        pct_h = abs(obj.height_mm - ref_h) / ref_h * 100
        return max(pct_w, pct_h)


def _within_tolerance(obj: DetectedObject, ref: dict, tol: float) -> bool:
    """
    Cek apakah objek masuk dalam toleransi absolut.
    SELALU menggunakan `tol` dari parameter (kalibrasi terbaru dari backend),
    BUKAN toleransi lama yang tersimpan di dalam data referensi.
    """
    if obj.shape == "circle":
        return abs(obj.diameter_mm - ref.get("diameter_mm", 0)) <= tol
    dw = abs(obj.width_mm - ref.get("width_mm", 0))
    dh = abs(obj.height_mm - ref.get("height_mm", 0))
    return dw <= tol and dh <= tol


class ReferenceManager:
    """
    Menyimpan dan membandingkan profil dimensi referensi dari referensi.json.
    Mendukung banyak profil bernama untuk setiap tipe bentuk.

    Algoritma matching:
    1. Filter referensi dengan shape yang sama
    2. Hitung score relatif (%) untuk semua referensi
    3. Pilih yang paling mirip (score terkecil) di antara yang dalam toleransi → GOOD
    4. Jika tidak ada yang dalam toleransi → pilih paling dekat → NO GOOD
    5. Toleransi SELALU dari parameter (kalibrasi terbaru), bukan yang tersimpan di ref
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
                    key = d.get("diameter_mm", d.get("width_mm", "?"))
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
        Bandingkan dimensi objek terdeteksi dengan profil referensi.
        Auto-match dengan scoring relatif — pilih referensi yang paling mirip.

        Toleransi selalu menggunakan `tol` dari parameter (kalibrasi terbaru dari backend).
        Toleransi yang tersimpan di data referensi DIABAIKAN untuk matching,
        agar perubahan toleransi di engineer page langsung berlaku.

        Returns:
            tuple: (status, nama_referensi, detail_string)
            status: 'GOOD' | 'NO GOOD' | 'NO REF'
        """
        # Filter referensi dengan shape yang sama
        same = {n: d for n, d in self.refs.items() if d["shape"] == obj.shape}
        if not same:
            return "NO REF", None, f"Belum ada referensi untuk shape '{obj.shape}'"

        # Hitung score untuk semua referensi, pisahkan yang dalam/luar toleransi
        candidates_in  = []  # yang dalam toleransi
        candidates_out = []  # yang di luar toleransi

        for name, ref in same.items():
            score = _score(obj, ref)
            if _within_tolerance(obj, ref, tol):
                candidates_in.append((name, ref, score))
            else:
                candidates_out.append((name, ref, score))

        # Ada yang dalam toleransi → pilih yang score terkecil → GOOD
        if candidates_in:
            candidates_in.sort(key=lambda x: x[2])
            best_name, best_ref, best_score = candidates_in[0]

            if obj.shape == "circle":
                d = abs(obj.diameter_mm - best_ref["diameter_mm"])
                detail = (f"Ø ref={best_ref['diameter_mm']:.2f} got={obj.diameter_mm:.2f} "
                          f"Δ={d:.2f}mm tol=±{tol:.2f}mm ✓")
            else:
                dw = abs(obj.width_mm  - best_ref["width_mm"])
                dh = abs(obj.height_mm - best_ref["height_mm"])
                detail = (f"W ref={best_ref['width_mm']:.2f} got={obj.width_mm:.2f} Δ={dw:.2f} "
                          f"| H ref={best_ref['height_mm']:.2f} got={obj.height_mm:.2f} Δ={dh:.2f} "
                          f"tol=±{tol:.2f}mm ✓")
            return "GOOD", best_name, detail

        # Tidak ada yang dalam toleransi → pilih yang paling dekat → NO GOOD
        candidates_out.sort(key=lambda x: x[2])
        closest_name, closest_ref, closest_score = candidates_out[0]

        if obj.shape == "circle":
            d = abs(obj.diameter_mm - closest_ref["diameter_mm"])
            detail = (f"Ø ref={closest_ref['diameter_mm']:.2f} got={obj.diameter_mm:.2f} "
                      f"Δ={d:.2f}mm tol=±{tol:.2f}mm ✗")
        else:
            dw = abs(obj.width_mm  - closest_ref["width_mm"])
            dh = abs(obj.height_mm - closest_ref["height_mm"])
            detail = (f"W ref={closest_ref['width_mm']:.2f} got={obj.width_mm:.2f} Δ={dw:.2f} "
                      f"| H ref={closest_ref['height_mm']:.2f} got={obj.height_mm:.2f} Δ={dh:.2f} "
                      f"tol=±{tol:.2f}mm ✗")
        return "NO GOOD", closest_name, detail

    def compare_with(self, obj: DetectedObject, ref_name: str, tol: float) -> tuple:
        """
        Bandingkan dimensi objek dengan referensi SPESIFIK.
        Jika referensi tidak ditemukan, fallback ke auto-match.

        Toleransi selalu menggunakan `tol` dari parameter (kalibrasi terbaru dari backend).
        """
        if ref_name not in self.refs:
            print(f"[REF] Referensi '{ref_name}' tidak ditemukan, fallback ke auto-match")
            return self.compare(obj, tol)

        ref = self.refs[ref_name]

        if obj.shape == "circle":
            d = abs(obj.diameter_mm - ref["diameter_mm"])
            ok = d <= tol
            detail = (f"Ø ref={ref['diameter_mm']:.2f} got={obj.diameter_mm:.2f} "
                      f"Δ={d:.2f}mm tol=±{tol:.2f}mm {'✓' if ok else '✗'}")
        else:
            dw = abs(obj.width_mm  - ref["width_mm"])
            dh = abs(obj.height_mm - ref["height_mm"])
            ok = dw <= tol and dh <= tol
            detail = (f"W ref={ref['width_mm']:.2f} got={obj.width_mm:.2f} Δ={dw:.2f} "
                      f"| H ref={ref['height_mm']:.2f} got={obj.height_mm:.2f} Δ={dh:.2f} "
                      f"tol=±{tol:.2f}mm {'✓' if ok else '✗'}")

        status = "GOOD" if ok else "NO GOOD"
        return status, ref_name, detail

    def list_names(self) -> list:
        """Mengembalikan daftar nama profil referensi."""
        return list(self.refs.keys())

    def clear_all(self):
        """Hapus semua profil referensi."""
        self.refs = {}
        self._save()
