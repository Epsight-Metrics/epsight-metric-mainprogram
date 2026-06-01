"""
Modul Frame Uploader - Kirim Frame & Deteksi ke CV API
Mengirim frame dan hasil deteksi ke CV API untuk akses realtime dari dashboard
"""

import threading
import time
import cv2
import numpy as np

try:
    import requests
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False
    print("[FRAME_UPLOADER] requests tidak terinstall")


class FrameUploader:
    """
    Mengirim frame dan deteksi ke CV API secara async untuk dashboard realtime
    """
    
    def __init__(self, cfg: dict):
        self.cv_api_url = cfg.get("cv_api_url", "http://localhost:8000").rstrip("/")
        self.enabled = cfg.get("enabled", False) and REQUESTS_AVAILABLE
        self.upload_interval = cfg.get("upload_interval", 0.5)  # seconds
        self._stop_event = threading.Event()
        self._frame_queue = []
        self._detection_queue = []
        self._lock = threading.Lock()
        
        if self.enabled:
            print(f"[FRAME_UPLOADER] Aktif -> {self.cv_api_url}")
            self._start_upload_thread()
        else:
            reason = "requests tidak terinstall" if not REQUESTS_AVAILABLE else "cv_api.enabled=False"
            print(f"[FRAME_UPLOADER] Mode STUB ({reason})")
    
    def _start_upload_thread(self):
        """Start background thread untuk upload frame & deteksi"""
        def loop():
            while not self._stop_event.wait(self.upload_interval):
                self._process_uploads()
        
        t = threading.Thread(target=loop, daemon=True, name="FrameUploader")
        t.start()
    
    def _process_uploads(self):
        """Process queued uploads"""
        with self._lock:
            if not self._frame_queue and not self._detection_queue:
                return
            
            frame = self._frame_queue[-1] if self._frame_queue else None
            detections = self._detection_queue[-1] if self._detection_queue else None
            
            # Clear queues
            self._frame_queue.clear()
            self._detection_queue.clear()
        
        # Upload frame
        if frame is not None:
            try:
                _, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
                files = {'file': ('frame.jpg', buffer.tobytes(), 'image/jpeg')}
                requests.post(
                    f"{self.cv_api_url}/update-frame",
                    files=files,
                    timeout=2
                )
            except Exception as e:
                pass  # Silent fail untuk tidak mengganggu main loop
        
        # Upload detections
        if detections is not None:
            try:
                requests.post(
                    f"{self.cv_api_url}/update-detections",
                    json=detections,
                    timeout=2
                )
            except Exception as e:
                pass  # Silent fail
    
    def upload_frame(self, frame):
        """Queue frame untuk upload"""
        if not self.enabled:
            return
        
        with self._lock:
            self._frame_queue.append(frame.copy())
            # Keep only latest frame
            if len(self._frame_queue) > 2:
                self._frame_queue.pop(0)
    
    def upload_detections(self, objects: list, results: list):
        """Queue detections untuk upload"""
        if not self.enabled:
            return
        
        # Convert objects to serializable format
        objects_data = []
        for obj in objects:
            # Convert contour to list format
            contour_list = obj.contour.tolist() if hasattr(obj.contour, 'tolist') else []
            
            obj_dict = {
                "shape": obj.shape,
                "bbox": obj.bbox,
                "center": obj.center,
                "width_mm": round(obj.width_mm, 2),
                "height_mm": round(obj.height_mm, 2),
                "diameter_mm": round(obj.diameter_mm, 2),
                "vertices": obj.vertices,
                "radius_px": obj.radius_px,
                "rot_box": obj.rot_box.tolist() if hasattr(obj.rot_box, 'tolist') else obj.rot_box,
                "contour": contour_list[:100] if len(contour_list) > 100 else contour_list  # Limit contour points
            }
            objects_data.append(obj_dict)
        
        # Convert results to serializable format
        results_data = []
        for status, matched_ref, detail in results:
            results_data.append({
                "status": status,
                "matched_ref": matched_ref,
                "detail": detail
            })
        
        with self._lock:
            self._detection_queue.append({
                "objects": objects_data,
                "results": results_data
            })
            # Keep only latest detection
            if len(self._detection_queue) > 2:
                self._detection_queue.pop(0)
    
    def stop(self):
        """Stop upload thread"""
        self._stop_event.set()
