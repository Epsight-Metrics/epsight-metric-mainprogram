"""
Modul Database Manager
Sistem Inspeksi Dimensi Part Manufaktur
"""

import json
from modules.utils import now_iso

# psycopg2 is optional. The application runs normally without it;
# database logging falls back to console-only (stub) mode.
try:
    import psycopg2
    import psycopg2.extras
    PSYCOPG2_AVAILABLE = True
except ImportError:
    PSYCOPG2_AVAILABLE = False


class DatabaseManager:
    """
    Manages the PostgreSQL connection and inspection log writes.
    Operates in stub mode (console-only logging) when the database is
    disabled or psycopg2 is unavailable.
    """
    def __init__(self, db_cfg: dict):
        self.conn    = None
        self.enabled = db_cfg.get("enabled", False) and PSYCOPG2_AVAILABLE
        self._cfg    = db_cfg
        if self.enabled:
            self._connect()
        else:
            reason = "enabled=False" if not db_cfg.get("enabled") else "psycopg2 tidak terinstall"
            print(f"[DB] Mode STUB ({reason})")

    def _connect(self):
        try:
            self.conn = psycopg2.connect(
                host=self._cfg["host"], port=self._cfg["port"],
                dbname=self._cfg["dbname"], user=self._cfg["user"],
                password=self._cfg["password"])
            self.conn.autocommit = True
            print(f"[DB] Terhubung: {self._cfg['host']}:{self._cfg['port']}/{self._cfg['dbname']}")
        except Exception as e:
            self.conn = None
            self.enabled = False
            print(f"[DB] Gagal konek: {e} — fallback ke STUB")

    def save_log(self, timestamp, id_part, nilai_dimensi, status,
                 matched_ref=None, image_path=None, shape=None):
        print(f"[DB] LOG | {timestamp[:19]} | {id_part} | "
              f"{shape or '?':12s} | {status:8s} | ref={matched_ref or '-'}")
        if not self.enabled:
            payload = {"timestamp":timestamp,"id_part":id_part,"shape":shape,
                       "nilai_dimensi":nilai_dimensi,"status":status,
                       "matched_ref":matched_ref,"image_path":image_path}
            print(f"[DB][STUB] {json.dumps(payload)}")
            return True
        if not self.conn: return False
        try:
            with self.conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO inspeksi_log
                        (timestamp,id_part,shape,nilai_dimensi,status,matched_ref,image_path)
                    VALUES (%s,%s,%s,%s,%s,%s,%s)""",
                    (timestamp, id_part, shape,
                     psycopg2.extras.Json(nilai_dimensi),
                     status, matched_ref, image_path))
            return True
        except Exception as e:
            print(f"[DB] INSERT gagal: {e}")
            try: self.conn.rollback()
            except: pass
            return False

    def close(self):
        if self.conn:
            try: self.conn.close()
            except: pass
