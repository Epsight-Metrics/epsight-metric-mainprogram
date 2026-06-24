"""
Modul Manajemen Konfigurasi
Sistem Inspeksi Dimensi Part Manufaktur
"""

import os
import sys
import json

def get_base_dir() -> str:
    """
    Return the application's base directory.

    When frozen by PyInstaller, sys.executable points to the compiled
    binary. Otherwise, returns the parent directory of this module
    to point to the project's root folder.
    """
    if getattr(sys, "frozen", False):
        # Running as a PyInstaller frozen executable.
        return os.path.dirname(sys.executable)
    # Running as standard script, modules/config.py is inside modules/
    # We want base dir to be the parent directory (project root).
    current_dir = os.path.dirname(os.path.abspath(__file__))
    if os.path.basename(current_dir) == "modules":
        return os.path.dirname(current_dir)
    return current_dir

BASE_DIR = get_base_dir()

def base_path(filename: str) -> str:
    """Return an absolute path by joining *filename* with the application base directory."""
    return os.path.join(BASE_DIR, filename)

CONFIG_PATH = base_path("config.json")

DEFAULT_CONFIG = {
    "camera_source"   : 1,
    "droidcam_fix"    : True,
    "capture_width"   : 1920,
    "capture_height"  : 1080,
    "pixel_per_mm"    : 9.28,
    "roi_percent"     : [0.20, 0.10, 0.80, 0.90],
    "contour_min_area": 1500,
    "contour_thresh"  : 200,
    "min_feature_mm"  : 5.0,
    "tolerance_mm"    : 1.0,
    "warning_duration": 5.0,
    "dir_screenshot"  : "screenshots",
    "dir_deteksi"     : "deteksi_part",
    "file_reference"  : "referensi.json",
    "api": {
        "enabled"    : False,
        "api_url"    : "http://localhost:3000",
        "part_id"    : 1,
        "operator_id": None,
        "session_id" : None,
        "batch_id"   : None,
        "timeout"    : 5,
        "api_key"    : "" 
    },
    "db": {
        "enabled" : False,
        "host"    : "localhost",
        "port"    : 5432,
        "dbname"  : "capstone_db",
        "user"    : "postgres",
        "password": ""
    }
}

def load_config() -> dict:
    """
    Load the application configuration from config.json.

    If the file does not exist it is created with DEFAULT_CONFIG values.
    Any keys absent from the stored file are back-filled from DEFAULT_CONFIG.
    """
    if not os.path.exists(CONFIG_PATH):
        save_config(DEFAULT_CONFIG)
        print(f"[CFG] config.json tidak ditemukan — dibuat dengan nilai default.")
        return dict(DEFAULT_CONFIG)

    try:
        with open(CONFIG_PATH, "r") as f:
            data = json.load(f)
        # Shallow-merge top-level keys, ensuring all defaults are present.
        merged = dict(DEFAULT_CONFIG)
        merged.update(data)
        # Deep-merge the nested "api" and "db" sub-dictionaries separately.
        merged["api"] = dict(DEFAULT_CONFIG["api"])
        merged["api"].update(data.get("api", {}))
        merged["db"] = dict(DEFAULT_CONFIG["db"])
        merged["db"].update(data.get("db", {}))
        print(f"[CFG] Konfigurasi dimuat dari '{CONFIG_PATH}'")
        return merged
    except Exception as e:
        print(f"[CFG] Gagal baca config.json: {e} — menggunakan default.")
        return dict(DEFAULT_CONFIG)

def save_config(cfg: dict) -> None:
    """Serialise *cfg* and write it to config.json."""
    try:
        with open(CONFIG_PATH, "w") as f:
            json.dump(cfg, f, indent=2)
        print(f"[CFG] Konfigurasi disimpan ke '{CONFIG_PATH}'")
    except Exception as e:
        print(f"[CFG] Gagal simpan config.json: {e}")

