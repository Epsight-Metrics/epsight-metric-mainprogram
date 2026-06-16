"""
Modul Deteksi & Klasifikasi Objek
Sistem Inspeksi Dimensi Part Manufaktur
"""

import cv2
import numpy as np
import math
from modules.utils import px2mm, now_str

SHAPE_LABEL = {
    "circle"   : "LINGKARAN",
    "triangle" : "SEGITIGA",
    "square"   : "KOTAK",
    "rectangle": "PERSEGI PANJANG",
    "pentagon" : "PENTAGON",
    "hexagon"  : "HEKSAGON",
    "polygon"  : "POLIGON",
}

def classify_shape(contour) -> tuple:
    """
    Klasifikasi bentuk kontur menggunakan Douglas-Peucker approximation
    serta rasio sirkularitas dan aspek rasio.
    """
    perimeter    = cv2.arcLength(contour, True)
    area         = cv2.contourArea(contour)
    epsilon      = 0.03 * perimeter
    approx       = cv2.approxPolyDP(contour, epsilon, True)
    n            = len(approx)
    circularity  = 4 * math.pi * area / (perimeter**2 + 1e-6)
    x, y, w, h   = cv2.boundingRect(contour)
    aspect_ratio = min(w,h) / max(w,h) if max(w,h) > 0 else 0

    # 1. Cek bentuk segitiga dan segi empat terlebih dahulu agar tidak salah terklasifikasi sebagai lingkaran
    if n == 3:
        return "triangle", n, circularity
    if n == 4:
        ar = w/float(h) if h>0 else 1
        return ("square" if 0.90<=ar<=1.10 else "rectangle"), n, circularity

    # 2. Cek bentuk lingkaran dengan threshold sirkularitas lebih tinggi (>= 0.85)
    #    agar persegi dengan sudut menumpul/bayangan tidak terdeteksi sebagai lingkaran
    if circularity > 0.85:
        return "circle", n, circularity
    if aspect_ratio > 0.88 and n > 6:
        return "circle", n, circularity

    if n == 5:
        return "pentagon", n, circularity
    if n == 6:
        return "hexagon", n, circularity
    return "polygon", n, circularity


class DetectedObject:
    """
    Data class yang mewakili satu kontur yang terdeteksi dengan
    properti geometris yang dihitung (bounding box, rotated box, area, diameter, dll).
    """
    def __init__(self, contour, ppm: float):
        self.contour  = contour
        self.area_px  = cv2.contourArea(contour)
        x, y, w, h    = cv2.boundingRect(contour)
        self.bbox     = (x, y, x+w, y+h)
        rr             = cv2.minAreaRect(contour)
        self.rot_rect  = rr
        self.rot_box   = cv2.boxPoints(rr).astype(int)
        rw, rh         = rr[1]
        self.width_px  = max(rw, rh)
        self.height_px = min(rw, rh)
        self.width_mm  = px2mm(self.width_px,  ppm)
        self.height_mm = px2mm(self.height_px, ppm)
        (cx,cy), self.radius_px = cv2.minEnclosingCircle(contour)
        self.center       = (int(cx), int(cy))
        self.diameter_px  = self.radius_px * 2
        self.diameter_mm  = px2mm(self.diameter_px, ppm)
        self.shape, self.vertices, self.circularity = classify_shape(contour)
        self._ppm = ppm

    @property
    def label_size(self) -> str:
        return (f"Ø{self.diameter_mm:.1f}mm" if self.shape == "circle"
                else f"{self.width_mm:.1f}×{self.height_mm:.1f}mm")

    def to_dict(self) -> dict:
        return {
            "shape": self.shape,
            "vertices": self.vertices,
            "circularity": round(self.circularity, 3),
            "timestamp": now_str(),
            "pixel_per_mm": self._ppm,
            "diameter_mm": round(self.diameter_mm, 2),
            "width_mm": round(self.width_mm, 2),
            "height_mm": round(self.height_mm, 2),
            "area_px": round(self.area_px, 1),
            "bbox": list(self.bbox),
        }


def preprocess(frame) -> tuple:
    """Pipeline pemrosesan awal citra: Gray -> Gaussian Blur -> CLAHE."""
    gray     = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    blurred  = cv2.GaussianBlur(gray, (5,5), 0)
    clahe    = cv2.createCLAHE(clipLimit=2.5, tileGridSize=(8,8))
    enhanced = clahe.apply(blurred)
    return gray, blurred, enhanced

def get_binary(enhanced, thresh_val) -> np.ndarray:
    """Konversi citra preprocessed ke binarisasi (Adaptive + Canny + Morphological Close)."""
    adaptive = cv2.adaptiveThreshold(enhanced, 255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV,
        21, thresh_val // 4)
    canny    = cv2.Canny(enhanced, thresh_val*0.5, thresh_val*1.5)
    combined = cv2.bitwise_or(adaptive, canny)
    kernel   = cv2.getStructuringElement(cv2.MORPH_RECT, (3,3))
    return cv2.morphologyEx(combined, cv2.MORPH_CLOSE, kernel, iterations=2)

def find_objects(binary, min_area: float, ppm: float, min_feature_mm: float) -> list:
    """Temukan kontur luar pada citra biner dan filter objek berdasarkan kriteria minimum."""
    contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    objects = []
    for cnt in contours:
        if cv2.contourArea(cnt) < min_area: continue
        obj = DetectedObject(cnt, ppm)
        if obj.width_mm < min_feature_mm and obj.height_mm < min_feature_mm: continue
        objects.append(obj)
    objects.sort(key=lambda o: o.bbox[0])
    return objects
