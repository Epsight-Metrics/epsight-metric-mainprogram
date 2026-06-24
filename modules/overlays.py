"""
Modul Overlay Dinamis (Notification & WarningOverlay)
Sistem Inspeksi Dimensi Part Manufaktur
"""

import cv2
import time
from modules.rendering import C, FONT, label


class Notification:
    """
    Sistem notifikasi yang merender pesan status yang otomatis hilang
    di bagian tengah layar OpenCV.
    """
    def __init__(self):
        self.messages = []

    def add(self, text: str, color: tuple = C["white"], duration: float = 3.0):
        self.messages.append((text, color, time.time() + duration))
        print(f"[NOTIF] {text}")

    def draw(self, img):
        now = time.time()
        self.messages = [(t, c, e) for t, c, e in self.messages if e > now]
        H, W = img.shape[:2]
        y = H // 2 - len(self.messages) * 30
        for text, color, _ in self.messages:
            (tw, th), _ = cv2.getTextSize(text, FONT, 0.65, 2)
            x = (W - tw) // 2
            ov = img.copy()
            cv2.rectangle(ov, (x-14, y-th-12), (x+tw+14, y+12), C["black"], -1)
            cv2.addWeighted(ov, 0.65, img, 0.35, 0, img)
            cv2.putText(img, text, (x, y), FONT, 0.65, color, 2, cv2.LINE_AA)
            y += 48


class WarningOverlay:
    """
    Merender overlay merah berkedip sebagai peringatan keras ketika ada satu atau lebih
    part yang diklasifikasikan sebagai NO GOOD. Peringatan akan bertahan sesuai durasi konfigurasi.
    """
    BLINK_HZ = 2.0

    def __init__(self):
        self.active = False
        self.expire = 0.0
        self.ng_count = 0

    def trigger(self, ng_count: int):
        self.active = True
        self.ng_count = ng_count
        print(f"[WARNING] {ng_count} part NO GOOD!")

    def set_duration(self, dur: float):
        self.expire = time.time() + dur

    def clear(self):
        self.active = False

    def draw(self, img, dur: float):
        if not self.active:
            return
        if self.expire == 0.0:
            self.expire = time.time() + dur
        now = time.time()
        if now > self.expire:
            self.active = False
            self.expire = 0.0
            return
        if (now % (1.0 / self.BLINK_HZ)) / (1.0 / self.BLINK_HZ) > 0.5:
            return

        H, W = img.shape[:2]
        ov = img.copy()
        cv2.rectangle(ov, (0,0), (W,H), (0,0,180), -1)
        cv2.addWeighted(ov, 0.25, img, 0.75, 0, img)
        cv2.rectangle(img, (4,4), (W-4,H-4), (0,0,220), 8)
        lines = [
            ("⚠  PART TIDAK LOLOS SELEKSI  ⚠", 1.10, (0,0,255)),
            (f"{self.ng_count} PART BERSTATUS NO GOOD",  0.80, (0,140,255)),
            ("PINDAHKAN KE WADAH NG !",                  0.90, (0,0,255)),
        ]
        y = H // 2 - 70
        for text, scale, col in lines:
            (tw, th), _ = cv2.getTextSize(text, FONT, scale, 3)
            x = (W - tw) // 2
            cv2.putText(img, text, (x+3, y+3), FONT, scale, C["black"], 4, cv2.LINE_AA)
            cv2.putText(img, text, (x, y), FONT, scale, col, 3, cv2.LINE_AA)
            y += th + 22

        remaining = max(0.0, self.expire - now)
        cd = f"Peringatan hilang dalam {remaining:.0f} detik"
        (tw, _), _ = cv2.getTextSize(cd, FONT, 0.46, 1)
        label(img, cd, ((W-tw)//2, H-28), 0.46, (0,180,255), C["black"])
