"""
Frame Uploader Module - Upload video frame ke backend untuk streaming
Menggantikan local Flask server dengan upload ke Railway backend
"""

import threading
import time
import cv2
import base64


class FrameUploader:
    """
    Upload frame ke backend setiap X ms untuk di-stream ke dashboard.
    Backend akan serve frame sebagai MJPEG stream.
    """
    
    def __init__(self, api_url: str, upload_interval: float = 0.1, quality: int = 80):
        """
        Args:
            api_url: Base URL backend (e.g., https://backend.railway.app)
            upload_interval: Interval upload dalam detik (default 0.1 = 10 FPS)
            quality: JPEG quality 0-100 (default 80)
        """
        self.api_url = api_url.rstrip("/")
        self.upload_interval = upload_interval
        self.quality = quality
        self.frame = None
        self.lock = threading.Lock()
        self._stop_event = threading.Event()
        self._upload_thread = None
        self._session = None
        
        try:
            import requests
            self._session = requests.Session()
        except ImportError:
            print("[UPLOAD] requests tidak terinstall - frame upload disabled")
    
    def start(self):
        """Start background thread untuk upload frame."""
        if not self._session:
            return
        
        self._stop_event.clear()
        self._upload_thread = threading.Thread(
            target=self._upload_loop,
            daemon=True,
            name="FrameUploader"
        )
        self._upload_thread.start()
        print(f"[UPLOAD] Frame uploader started (interval: {self.upload_interval}s)")
    
    def update_frame(self, frame):
        """Update frame yang akan di-upload (dipanggil dari main loop)."""
        with self.lock:
            self.frame = frame.copy()
    
    def _upload_loop(self):
        """Background loop untuk upload frame ke backend."""
        url = f"{self.api_url}/api/stream/upload"
        
        while not self._stop_event.is_set():
            try:
                with self.lock:
                    if self.frame is None:
                        time.sleep(self.upload_interval)
                        continue
                    
                    # Encode frame ke JPEG
                    ret, buffer = cv2.imencode(
                        '.jpg',
                        self.frame,
                        [cv2.IMWRITE_JPEG_QUALITY, self.quality]
                    )
                    
                    if not ret:
                        time.sleep(self.upload_interval)
                        continue
                    
                    # Convert ke base64
                    frame_base64 = base64.b64encode(buffer).decode('utf-8')
                
                # Upload ke backend
                response = self._session.post(
                    url,
                    json={'frame': frame_base64},
                    timeout=2
                )
                
                if response.status_code != 200:
                    print(f"[UPLOAD] Failed: {response.status_code}")
                
            except Exception as e:
                # Silent fail - jangan spam console
                pass
            
            time.sleep(self.upload_interval)
    
    def stop(self):
        """Stop upload thread."""
        self._stop_event.set()
        if self._upload_thread:
            self._upload_thread.join(timeout=2)
        print("[UPLOAD] Frame uploader stopped")
