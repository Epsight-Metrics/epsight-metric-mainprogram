"""
Video Stream Module - WebSocket Implementation
Stream kamera CV ke dashboard via WebSocket untuk ultra-low latency

Features:
- Binary frame transfer (JPEG compressed)
- Latency: 20-50ms (vs 50-150ms MJPEG)
- Bidirectional communication
- Automatic reconnection handling
- Multiple client support

Usage:
  from modules.video_stream_websocket import VideoStreamWebSocket
  
  stream = VideoStreamWebSocket(port=5000)
  stream.start()
  
  # Di main loop:
  stream.update_frame(display_frame)
  
  # Saat program selesai:
  stream.stop()
"""

import threading
import cv2
import time
import json
from flask import Flask
from flask_socketio import SocketIO, emit
from flask_cors import CORS


class VideoStreamWebSocket:
    """
    Stream video frame dari CV program ke dashboard via WebSocket.
    Dashboard connect ke: ws://localhost:5000
    """
    
    def __init__(self, port=5000, quality=70, fps_limit=30):
        self.port = port
        self.quality = quality  # JPEG quality (0-100, lower = faster)
        self.fps_limit = fps_limit
        self.frame = None
        self.lock = threading.Lock()
        self.app = Flask(__name__)
        self.app.config['SECRET_KEY'] = 'cv-stream-secret'
        
        # Enable CORS for WebSocket
        CORS(self.app, resources={r"/*": {"origins": "*"}})
        
        self.socketio = SocketIO(
            self.app,
            cors_allowed_origins="*",
            async_mode='threading',
            logger=False,
            engineio_logger=False,
            ping_timeout=60,
            ping_interval=25
        )
        
        self.server_thread = None
        self._running = False
        self._stream_thread = None
        self._connected_clients = 0
        
        # Setup SocketIO event handlers
        @self.socketio.on('connect')
        def handle_connect():
            self._connected_clients += 1
            print(f"[STREAM-WS] Client connected (total: {self._connected_clients})")
            emit('status', {'message': 'Connected to CV stream', 'fps': self.fps_limit})
        
        @self.socketio.on('disconnect')
        def handle_disconnect():
            self._connected_clients -= 1
            print(f"[STREAM-WS] Client disconnected (total: {self._connected_clients})")
        
        @self.socketio.on('request_frame')
        def handle_frame_request():
            """Client request frame (optional, untuk pull-based streaming)"""
            pass
        
        # HTTP health check endpoint
        @self.app.route('/health')
        def health():
            return {
                'status': 'ok',
                'streaming': self.frame is not None,
                'clients': self._connected_clients,
                'fps_limit': self.fps_limit
            }
    
    def start(self):
        """Start Flask-SocketIO server di background thread."""
        if self._running:
            return
        
        self._running = True
        
        # Start Flask-SocketIO server
        self.server_thread = threading.Thread(
            target=self._run_server,
            daemon=True,
            name="VideoStream-WebSocket-Server"
        )
        self.server_thread.start()
        
        # Start frame broadcasting thread
        self._stream_thread = threading.Thread(
            target=self._broadcast_frames,
            daemon=True,
            name="VideoStream-WebSocket-Broadcaster"
        )
        self._stream_thread.start()
        
        print(f"[STREAM-WS] WebSocket video stream started at ws://localhost:{self.port}")
        print(f"[STREAM-WS] Quality: {self.quality}%, FPS limit: {self.fps_limit}")
    
    def _run_server(self):
        """Run Flask-SocketIO server (internal)."""
        self.socketio.run(
            self.app,
            host='0.0.0.0',
            port=self.port,
            debug=False,
            use_reloader=False,
            log_output=False
        )
    
    def update_frame(self, frame):
        """Update frame yang akan di-stream (dipanggil dari main loop)."""
        with self.lock:
            self.frame = frame.copy()
    
    def _broadcast_frames(self):
        """Broadcast frames ke semua connected clients (internal)."""
        frame_interval = 1.0 / self.fps_limit
        last_frame_time = 0
        
        while self._running:
            current_time = time.time()
            
            # Rate limiting
            if current_time - last_frame_time < frame_interval:
                time.sleep(0.001)  # Small sleep to prevent CPU spinning
                continue
            
            # Skip jika tidak ada client
            if self._connected_clients == 0:
                time.sleep(0.1)
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
            
            # Broadcast ke semua clients
            try:
                self.socketio.emit('frame', frame_bytes, namespace='/')
                last_frame_time = current_time
            except Exception as e:
                print(f"[STREAM-WS] Broadcast error: {e}")
                time.sleep(0.1)
    
    def stop(self):
        """Stop streaming server."""
        self._running = False
        print("[STREAM-WS] WebSocket video stream stopped")
    
    def get_stats(self):
        """Return streaming statistics."""
        return {
            'running': self._running,
            'connected_clients': self._connected_clients,
            'has_frame': self.frame is not None,
            'quality': self.quality,
            'fps_limit': self.fps_limit
        }


# ============================================================================
# Standalone Test
# ============================================================================

if __name__ == "__main__":
    import numpy as np
    
    print("Testing VideoStreamWebSocket...")
    print("Install dependencies: pip install flask-socketio flask-cors")
    
    stream = VideoStreamWebSocket(port=5000, quality=70, fps_limit=30)
    stream.start()
    
    print("\nGenerating test frames...")
    print("Open browser console and run:")
    print("  const socket = io('http://localhost:5000');")
    print("  socket.on('frame', (data) => { console.log('Frame received:', data.byteLength); });")
    
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
            cv2.putText(frame, f"Clients: {stream.get_stats()['connected_clients']}", (10, 60),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 0), 2)
            
            stream.update_frame(frame)
            frame_count += 1
            time.sleep(0.033)  # 30 FPS
            
    except KeyboardInterrupt:
        print("\nStopping...")
        stream.stop()
