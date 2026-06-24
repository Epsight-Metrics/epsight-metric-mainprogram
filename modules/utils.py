"""
Modul Utilitas Dasar
Sistem Inspeksi Dimensi Part Manufaktur
"""

import math
import datetime

def px2mm(pixels: float, ppm: float) -> float:
    """Konversi satuan piksel ke milimeter berdasarkan konstanta kalibrasi pixel-per-mm (ppm)."""
    return pixels / ppm if ppm > 0 else 0.0

def dist(p1: tuple, p2: tuple) -> float:
    """Hitung jarak Euclidean antara dua titik p1=(x1, y1) dan p2=(x2, y2)."""
    return math.hypot(p1[0] - p2[0], p1[1] - p2[1])

def midpt(p1: tuple, p2: tuple) -> tuple:
    """Hitung titik tengah antara dua titik p1=(x1, y1) dan p2=(x2, y2)."""
    return ((p1[0] + p2[0]) // 2, (p1[1] + p2[1]) // 2)

def now_str() -> str:
    """Mengembalikan string waktu saat ini dengan format YYYYMMDD_HHMMSS."""
    return datetime.datetime.now().strftime("%Y%m%d_%H%M%S")

def now_iso() -> str:
    """Mengembalikan string waktu saat ini dalam format ISO 8601."""
    return datetime.datetime.now().isoformat()
