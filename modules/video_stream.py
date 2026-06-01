"""
Video Stream Module - Stream kamera CV ke dashboard via MJPEG
Menggunakan Flask untuk serve MJPEG stream yang bisa diakses via HTTP

Usage:
  from modules.video_stream import VideoStream
  
  stream = VideoStream(port=5000)
  stream.start()
  
  # Di main loop:
  stream.update_frame(display_frame)
  
  # Saat program selesai:
  stream.stop()
"""

import threading
import cv2
from flask import Flask, Response
import time


class VideoStream:
    """
    Stream video frame dari CV program ke dashboard via MJPEG over HTTP.
    Dashboard bisa akses stream via: http://localhost:5000/video_feed
    """
    
    def __init__(self, port=5000, quality=70):
        self.port = port
        self.quality = quality  # JPEG quality (0-100, lower = faster)
        self.frame = None
        self.lock = threading.Lock()
        self.app = Flask(__name__)
        self.server_thread = None
        self._running = False
        
        # Setup Flask routes
        @self.app.route('/video_feed')
        def video_feed():
            return Response(
                self._generate_frames(),
                mimetype='multipart/x-mixed-replace; boundary=frame'
            )
        
        @self.app.route('/health')
        def health():
            return {'status': 'ok', 'streaming': self.frame is not None}
    
    def start(self):
        """Start Flask server di background thread."""
        if self._running:
            return
        
        self._running = True
        self.server_thread = threading.Thread(
            target=self._run_server,
            daemon=True,
            name="VideoStream-Server"
        )
        self.server_thread.start()
        print(f"[STREAM] Video stream started at http://localhost:{self.port}/video_feed")
    
    def _run_server(self):
        """Run Flask server (internal)."""
        # Disable Flask logging untuk mengurangi noise di terminal
        import logging
        log = logging.getLogger('werkzeug')
        log.setLevel(logging.ERROR)
        
        self.app.run(
            host='0.0.0.0',  # Allow external access
            port=self.port,
            threaded=True,
            debug=False,
            use_reloader=False
        )
    
    def update_frame(self, frame):
        """Update frame yang akan di-stream (dipanggil dari main loop)."""
        with self.lock:
            self.frame = frame.copy()
    
    def _generate_frames(self):
        """Generator untuk MJPEG stream (internal)."""
        while self._running:
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
            
            # Yield frame dalam format MJPEG
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
            
            # No artificial delay - stream as fast as frames are available
            # Latency now depends only on encoding + network (~20-50ms)
    
    def stop(self):
        """Stop streaming server."""
        self._running = False
        print("[STREAM] Video stream stopped")


# ============================================================================
# Standalone Test
# ============================================================================

if __name__ == "__main__":
    import numpy as np
    
    print("Testing VideoStream...")
    stream = VideoStream(port=5000)
    stream.start()
    
    print("Generating test frames...")
    print("Open browser: http://localhost:5000/video_feed")
    
    try:
        frame_count = 0
        while True:
            # Generate test frame (moving circle)
            frame = np.zeros((480, 640, 3), dtype=np.uint8)
            x = int(320 + 200 * np.sin(frame_count * 0.05))
            y = int(240 + 100 * np.cos(frame_count * 0.05))
            cv2.circle(frame, (x, y), 50, (0, 255, 0), -1)
            cv2.putText(frame, f"Frame: {frame_count}", (10, 30),
                       cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
            
            stream.update_frame(frame)
            frame_count += 1
            time.sleep(0.033)  # 30 FPS
            
    except KeyboardInterrupt:
        print("\nStopping...")
        stream.stop()
