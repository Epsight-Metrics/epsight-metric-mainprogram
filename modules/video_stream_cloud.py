"""
Video Stream Cloud Uploader
Upload frame ke BE Railway agar bisa diakses dari mana saja

Usage:
  from modules.video_stream_cloud import VideoStreamCloud
  
  stream = VideoStreamCloud(
      backend_url="https://your-railway-app.up.railway.app",
      api_key="your-cv-api-key"
  )
  stream.start()
  
  # Di main loop:
  stream.update_frame(display_frame)
"""

import threading
import cv2
import time
import requests
from typing import Optional


class VideoStreamCloud:
    """Upload frame ke BE Railway untuk streaming online."""
    
    def __init__(self, backend_url: str, api_key: str, quality: int = 70, fps: int = 10):
        self.backend_url = backend_url.rstrip('/')
        self.api_key = api_key
        self.quality = quality
        self.fps = fps
        self.frame = None
        self.lock = threading.Lock()
        self._running = False
        self._upload_thread = None
        self._stats = {
            'uploaded': 0,
            'failed': 0,
            'last_latency': 0
        }
    
    def start(self):
        """Start upload thread."""
        if self._running:
            return
        
        self._running = True
        self._upload_thread = threading.Thread(
            target=self._upload_loop,
            daemon=True,
            name="VideoStream-Cloud-Uploader"
        )
        self._upload_thread.start()
        print(f"[STREAM-CLOUD] Started uploading to {self.backend_url}")
        print(f"[STREAM-CLOUD] Quality: {self.quality}%, FPS: {self.fps}")
    
    def update_frame(self, frame):
        """Update frame yang akan di-upload."""
        with self.lock:
            self.frame = frame.copy()
    
    def _upload_loop(self):
        """Upload frames ke BE (internal)."""
        frame_interval = 1.0 / self.fps
        last_upload_time = 0
        
        while self._running:
            current_time = time.time()
            
            # Rate limiting
            if current_time - last_upload_time < frame_interval:
                time.sleep(0.01)
                continue
            
            with self.lock:
                if self.frame is None:
                    time.sleep(0.1)
                    continue
                
                # Encode frame ke JPEG
                ret, buffer = cv2.imencode(
                    '.jpg',
                    self.frame,
                    [cv2.IMWRITE_JPEG_QUALITY, self.quality]
                )
                
                if not ret:
                    continue
                
                frame_bytes = buffer.tobytes()
            
            # Upload ke BE
            try:
                upload_start = time.time()
                
                response = requests.post(
                    f"{self.backend_url}/api/stream/upload",
                    files={'frame': ('frame.jpg', frame_bytes, 'image/jpeg')},
                    headers={'x-api-key': self.api_key},
                    timeout=2
                )
                
                if response.status_code == 200:
                    self._stats['uploaded'] += 1
                    self._stats['last_latency'] = int((time.time() - upload_start) * 1000)
                    
                    if self._stats['uploaded'] % 100 == 0:
                        print(f"[STREAM-CLOUD] Uploaded {self._stats['uploaded']} frames "
                              f"(latency: {self._stats['last_latency']}ms)")
                else:
                    self._stats['failed'] += 1
                    print(f"[STREAM-CLOUD] Upload failed: {response.status_code}")
                
                last_upload_time = current_time
                
            except Exception as e:
                self._stats['failed'] += 1
                if self._stats['failed'] % 10 == 0:
                    print(f"[STREAM-CLOUD] Upload error: {e}")
                time.sleep(1)
    
    def stop(self):
        """Stop upload thread."""
        self._running = False
        print(f"[STREAM-CLOUD] Stopped. Stats: {self._stats}")
    
    def get_stats(self):
        """Return upload statistics."""
        return self._stats.copy()
