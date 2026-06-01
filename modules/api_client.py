"""
Modul API Client - CV ke Backend HTTP
Mengirim hasil inspeksi ke BE via HTTP POST (non-blocking, thread terpisah).
Mengambil konfigurasi kalibrasi dari BE saat startup.
Mensinkronisasi sessionId & operatorId dari sesi FE yang aktif.
"""

import threading
import time
import json

try:
    import requests
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False
    print("[API] requests tidak terinstall - jalankan: pip install requests")


class ApiClient:
    """
    Mengirim hasil deteksi CV ke Backend via HTTP POST.
    Mensinkronisasi session & operator dari FE secara periodik.
    Beroperasi dalam thread terpisah agar tidak menghambat loop kamera.
    """

    SYNC_INTERVAL = 30  # detik antara sinkronisasi session

    def __init__(self, cfg: dict):
        self.base_url    = cfg.get("api_url", "http://localhost:3000").rstrip("/")
        self.enabled     = cfg.get("enabled", False) and REQUESTS_AVAILABLE
        self.api_key     = cfg.get("api_key", "")  # CV_API_KEY untuk auth ke BE
        self.part_id     = cfg.get("part_id", 1)
        self.operator_id = cfg.get("operator_id", None)
        self.session_id  = cfg.get("session_id", None)
        self.batch_id    = cfg.get("batch_id", None)
        self.timeout     = cfg.get("timeout", 5)
        self._operator_name = None
        self._lock       = threading.Lock()
        self._stop_sync  = threading.Event()
        self._trigger_callback = None
        self._session    = None

        if self.enabled:
            print(f"[API] Client aktif -> {self.base_url}")
            self._session = requests.Session()  # reuse TCP connection
            # Sinkronisasi session pertama kali
            self._sync_session()
            # Mulai thread sync periodik
            self._start_sync_thread()
            # Mulai command listener untuk trigger dari dashboard
            self._start_command_listener()
        else:
            reason = "requests tidak terinstall" if not REQUESTS_AVAILABLE else "api.enabled=False"
            print(f"[API] Mode STUB ({reason})")

    # ------------------------------------------------------------------
    def set_trigger_callback(self, callback):
        """Set callback yang dipanggil saat backend trigger inspection."""
        self._trigger_callback = callback

    def _start_sync_thread(self):
        """Jalankan thread yang mensinkronisasi session setiap SYNC_INTERVAL detik."""
        def loop():
            while not self._stop_sync.wait(self.SYNC_INTERVAL):
                self._sync_session()
        t = threading.Thread(target=loop, daemon=True, name="ApiClient-SyncSession")
        t.start()

    def _start_command_listener(self):
        """Listen SSE dari backend untuk command (cv-trigger)."""
        def loop():
            while not self._stop_sync.is_set():
                try:
                    url = f"{self.base_url}/api/notifications/stream"
                    # SSE endpoint butuh auth, tapi untuk CV kita skip dulu (public endpoint)
                    # Jika implement auth nanti, tambahkan header Authorization
                    resp = self._session.get(url, stream=True, timeout=None)
                    
                    print("[API] Command listener connected")
                    for line in resp.iter_lines():
                        if self._stop_sync.is_set():
                            break
                        if line:
                            line_str = line.decode('utf-8')
                            if line_str.startswith('event: '):
                                event_type = line_str[7:].strip()
                            elif line_str.startswith('data: '):
                                try:
                                    data = json.loads(line_str[6:])  # FIXED: Use json.loads instead of eval()
                                    if isinstance(data, dict) and event_type == 'cv-trigger':
                                        print("[API] Trigger inspection dari dashboard")
                                        if self._trigger_callback:
                                            self._trigger_callback()
                                except (ValueError, KeyError) as parse_err:
                                    print(f"[API] Gagal parse SSE data: {parse_err}")
                except Exception as e:
                    if not self._stop_sync.is_set():
                        print(f"[API] Command listener error: {e}")
                        time.sleep(5)  # retry setelah 5 detik
        
        t = threading.Thread(target=loop, daemon=True, name="ApiClient-CommandListener")
        t.start()

    def _sync_session(self):
        """Ambil session & operator aktif dari FE/BE, update state CV."""
        url = f"{self.base_url}/api/operator/active-session/public"
        try:
            session = self._session if self._session else requests
            resp = session.get(url, timeout=self.timeout)
            if resp.status_code == 200:
                data = resp.json()
                with self._lock:
                    if data.get("active"):
                        new_session  = data.get("sessionId")
                        new_operator = data.get("operatorId")
                        new_name     = data.get("operatorName", "-")
                        if new_session != self.session_id or new_operator != self.operator_id:
                            self.session_id   = new_session
                            self.operator_id  = new_operator
                            self._operator_name = new_name
                            print(f"[API] Sesi disinkronkan: {new_session} | Operator: {new_name}")
                    else:
                        if self.session_id is not None:
                            print("[API] Tidak ada sesi aktif - sessionId & operatorId dikosongkan")
                        self.session_id   = None
                        self.operator_id  = None
                        self._operator_name = None
        except Exception as e:
            print(f"[API] Gagal sinkronisasi sesi: {e}")

    # ------------------------------------------------------------------
    def get_session_info(self) -> dict:
        """Return info sesi aktif saat ini (untuk display di CV overlay jika perlu)."""
        with self._lock:
            return {
                "session_id":    self.session_id,
                "operator_id":   self.operator_id,
                "operator_name": self._operator_name,
            }

    def stop(self):
        """Hentikan thread sinkronisasi (panggil saat program tutup)."""
        self._stop_sync.set()

    # ------------------------------------------------------------------
    def fetch_calibration(self) -> dict | None:
        """
        Ambil konfigurasi kalibrasi dari BE saat startup.
        Return dict dalam format config.json CV, atau None jika gagal.
        """
        if not self.enabled:
            return None
        url = f"{self.base_url}/api/engineer/calibration/public"
        try:
            session = self._session if self._session else requests
            resp = session.get(url, timeout=self.timeout)
            if resp.status_code == 200:
                data = resp.json()
                print(f"[API] Kalibrasi dari BE: ppm={data.get('pixel_per_mm')} tol={data.get('tolerance_mm')}")
                return data
            else:
                print(f"[API] Gagal ambil kalibrasi ({resp.status_code}) - pakai config lokal")
                return None
        except Exception as e:
            print(f"[API] fetch_calibration gagal: {e} - pakai config lokal")
            return None

    # ------------------------------------------------------------------
    def send_inspection(self, id_part: str, shape: str, nilai_dimensi: dict,
                        status: str, matched_ref=None, image_path=None):
        """
        Kirim hasil inspeksi ke BE secara async (non-blocking).
        sessionId & operatorId diambil dari state sinkronisasi terkini.
        status harus salah satu dari: 'OK', 'NG', 'NO GOOD', 'GOOD'
        """
        # Normalise status ke format yang diterima BE
        status_map = {"GOOD": "OK", "NO GOOD": "NG"}
        be_status = status_map.get(status, status)

        if not self.enabled:
            print(f"[API][STUB] {be_status} | {shape} | ref={matched_ref}")
            return

        with self._lock:
            current_session  = self.session_id
            current_operator = self.operator_id
            current_batch    = self.batch_id

        payload = {
            "partId":       self.part_id,
            "status":       be_status,
            "idPart":       id_part,
            "shape":        shape,
            "nilaiDimensi": nilai_dimensi,
            "matchedRef":   matched_ref,
            "imagePath":    image_path,
        }
        if current_operator is not None:
            payload["operatorId"] = current_operator
        if current_session is not None:
            payload["sessionId"] = current_session
        if current_batch is not None:
            payload["batchId"] = current_batch

        t = threading.Thread(target=self._post, args=(payload,), daemon=True)
        t.start()

    # ------------------------------------------------------------------
    def _post(self, payload: dict):
        """Internal: HTTP POST ke BE (dijalankan di thread terpisah)."""
        url = f"{self.base_url}/api/operator/inspect/cv"
        try:
            session = self._session if self._session else requests
            # Sertakan x-api-key header agar BE bisa autentikasi request dari CV
            headers = {"x-api-key": self.api_key} if self.api_key else {}
            resp = session.post(url, json=payload, headers=headers, timeout=self.timeout)
            if resp.status_code == 201:
                print(f"[API] Inspeksi terkirim: {payload.get('status')} | "
                      f"{payload.get('shape')} | session={payload.get('sessionId', '-')}")
            elif resp.status_code == 401:
                print(f"[API] AUTH GAGAL (401): Periksa api_key di config.json")
            else:
                print(f"[API] Gagal ({resp.status_code}): {resp.text[:120]}")
        except requests.exceptions.ConnectionError:
            print("[API] Koneksi gagal - BE tidak bisa dijangkau")
        except requests.exceptions.Timeout:
            print("[API] Timeout saat kirim ke BE")
        except Exception as e:
            print(f"[API] Error: {e}")

