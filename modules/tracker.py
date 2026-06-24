"""
Modul Temporal Object Tracker
Sistem Inspeksi Dimensi Part Manufaktur
"""

import math
from collections import deque
from modules.detection import DetectedObject


class ObjectTracker:
    """
    Temporal stabiliser untuk kontur deteksi per-frame.

    Mengeliminasi kedipan (flickering) akibat refleksi logam dan menjaga
    kesinambungan deteksi saat melakukan aksi inspeksi (key D).

    Lifecycle Slot:
    - MATCHING: Deteksi baru dipetakan ke slot terdekat (maksimal MAX_DIST_PX).
    - CONFIRM: Slot dipromosikan ke 'visible' jika terdeteksi CONFIRM_FRAMES berturut-turut.
    - GHOST: Saat tidak cocok, slot masuk mode ghost selama GHOST_FRAMES sebelum dibuang.
    - SMOOTHING: Nilai dimensi yang dikembalikan dirata-rata sebanyak SMOOTH_FRAMES.
    """

    CONFIRM_FRAMES = 4   # Frame berturut-turut agar slot dianggap stabil.
    GHOST_FRAMES   = 12  # Toleransi frame hilang sebelum slot dihapus.
    SMOOTH_FRAMES  = 6   # Ukuran window moving average.
    MAX_DIST_PX    = 80  # Jarak displacement maksimal (px) untuk matching.

    def __init__(self):
        self._slots: list[dict] = []
        self._next_id = 0

    def update(self, raw_objects: list) -> list:
        """
        Menerima deteksi mentah per frame dan mengembalikan deteksi stabil yang dihaluskan.
        """
        self._match_and_update(raw_objects)
        self._expire_slots()
        return self._get_stable_objects()

    @property
    def stable_objects(self) -> list:
        """
        Mengembalikan objek stabil saat ini tanpa memajukan state tracker.
        """
        return self._get_stable_objects()

    def reset(self):
        """Reset slot pelacakan."""
        self._slots.clear()

    def _center(self, obj: DetectedObject) -> tuple:
        if obj.shape == "circle":
            return obj.center
        return (
            (obj.bbox[0] + obj.bbox[2]) // 2,
            (obj.bbox[1] + obj.bbox[3]) // 2
        )

    def _match_and_update(self, raw_objects: list):
        """Pencocokan deteksi mentah ke slot dengan strategi greedy nearest-neighbour."""
        used_slot_ids = set()

        for obj in raw_objects:
            cx, cy = self._center(obj)
            best_slot = None
            best_dist = self.MAX_DIST_PX

            for slot in self._slots:
                if slot["id"] in used_slot_ids:
                    continue
                scx, scy = slot["last_center"]
                d = math.hypot(cx - scx, cy - scy)
                if d < best_dist:
                    best_dist = d
                    best_slot = slot

            if best_slot is not None:
                # Refresh slot yang cocok
                used_slot_ids.add(best_slot["id"])
                best_slot["hit_count"]  = min(
                    best_slot["hit_count"] + 1, self.CONFIRM_FRAMES + 2)
                best_slot["miss_count"] = 0
                best_slot["last_center"] = (cx, cy)
                best_slot["last_obj"]    = obj
                self._push_dims(best_slot, obj)
            else:
                # Slot baru
                slot = {
                    "id"          : self._next_id,
                    "hit_count"   : 1,
                    "miss_count"  : 0,
                    "last_center" : (cx, cy),
                    "last_obj"    : obj,
                    "dim_buffer"  : deque(maxlen=self.SMOOTH_FRAMES),
                }
                self._next_id += 1
                self._push_dims(slot, obj)
                self._slots.append(slot)
                used_slot_ids.add(slot["id"])

        # Tambahkan miss count pada slot yang tidak terpakai
        for slot in self._slots:
            if slot["id"] not in used_slot_ids:
                slot["miss_count"] += 1

    def _push_dims(self, slot: dict, obj: DetectedObject):
        """Masukkan nilai pengukuran dimensi ke buffer smoothing slot."""
        slot["dim_buffer"].append({
            "diameter_mm" : obj.diameter_mm,
            "width_mm"    : obj.width_mm,
            "height_mm"   : obj.height_mm,
            "diameter_px" : obj.diameter_px,
            "width_px"    : obj.width_px,
            "height_px"   : obj.height_px,
            "radius_px"   : obj.radius_px,
        })

    def _expire_slots(self):
        """Hapus slot yang miss-nya melebihi ambang batas ghost frame."""
        self._slots = [
            s for s in self._slots
            if s["miss_count"] <= self.GHOST_FRAMES
        ]

    def _get_stable_objects(self) -> list:
        """Mengambil deteksi stabil dari slot yang sudah terkonfirmasi dan belum kadaluarsa."""
        stable = []
        for slot in self._slots:
            if slot["hit_count"] < self.CONFIRM_FRAMES:
                continue
            if slot["miss_count"] > self.GHOST_FRAMES:
                continue

            obj = slot["last_obj"]
            self._apply_smooth(obj, slot["dim_buffer"])
            stable.append(obj)

        stable.sort(key=lambda o: o.bbox[0])
        return stable

    @staticmethod
    def _apply_smooth(obj: DetectedObject, buf: deque):
        """Terapkan moving average ke objek terdeteksi secara in-place."""
        if not buf:
            return
        n = len(buf)
        avg = {k: sum(b[k] for b in buf) / n for k in buf[0]}

        obj.diameter_mm = avg["diameter_mm"]
        obj.width_mm    = avg["width_mm"]
        obj.height_mm   = avg["height_mm"]
        obj.diameter_px = avg["diameter_px"]
        obj.width_px    = avg["width_px"]
        obj.height_px   = avg["height_px"]
        obj.radius_px   = avg["radius_px"]
