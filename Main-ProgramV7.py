"""
Sistem Inspeksi Dimensi Part Manufaktur Berbasis Computer Vision
Capstone Project A.3 — Automated Dimensional Inspection
Universitas Brawijaya, Fakultas Ilmu Komputer — 2026

Tim Pengembang : Jagoan Mamah Papah
Mitra Industri : PT. Indonesia Epson Industry

Deskripsi
---------
Sistem inspeksi otomatis yang mengukur dimensi komponen manufaktur
secara real-time menggunakan kamera dan algoritma computer vision
berbasis OpenCV. Sistem berjalan sepenuhnya secara lokal (edge computing)
tanpa ketergantungan pada koneksi internet.

Pipeline Pemrosesan
-------------------
1. Akuisisi citra dari kamera (Webcam USB / DroidCam / IP Webcam)
2. Crop ke Region of Interest (ROI) yang telah dikonfigurasi
3. Preprocessing: Grayscale → Gaussian Blur → CLAHE
4. Binarisasi: Adaptive Threshold + Canny → Morphological Close
5. Deteksi kontur (RETR_EXTERNAL) → klasifikasi bentuk (approxPolyDP)
6. Pengukuran dimensi: pixel → milimeter via konstanta kalibrasi
7. Perbandingan dengan profil referensi → status GOOD / NO GOOD / NO REF
8. Rendering overlay, warning system, dan pencatatan hasil

Struktur File
-------------
  capstone_inspection_v7.py  — program utama
  config.json                — parameter konfigurasi (di-generate otomatis)
  referensi.json             — profil referensi benda (di-generate otomatis)
  screenshots/               — hasil screenshot operator
  deteksi_part/              — hasil deteksi JSON + gambar crop

Kontrol Keyboard (saat window inspeksi aktif)
---------------------------------------------
  Q / ESC  — keluar dari program
  D        — jalankan deteksi: simpan JSON, gambar crop, dan log database
  V        — simpan benda saat ini sebagai profil referensi baru
  S        — screenshot tampilan layar penuh
  R        — tampilkan / sembunyikan kotak ROI
  C        — aktifkan / nonaktifkan deteksi kontur
  P        — tampilkan debug preprocessing (Gray / CLAHE / Binary)
  + / =    — naikkan threshold binarisasi (+5, maksimum 250)
  -        — turunkan threshold binarisasi (−5, minimum 10)
"""

# =============================================================================
# DEPENDENCIES
# =============================================================================
import cv2
import numpy as np
import math
import time
import os
import sys
import json
import datetime
import threading
import tkinter as tk
from tkinter import ttk, messagebox
import collections
from collections import deque

# psycopg2 is optional. The application runs normally without it;
# database logging falls back to console-only (stub) mode.
try:
    import psycopg2
    import psycopg2.extras
    PSYCOPG2_AVAILABLE = True
except ImportError:
    PSYCOPG2_AVAILABLE = False


# =============================================================================
# PATH RESOLUTION
# Resolves the correct base directory whether the program is run as a
# plain Python script or as a frozen PyInstaller executable (.EXE).
# =============================================================================
def get_base_dir() -> str:
    """
    Return the application's base directory.

    When frozen by PyInstaller, ``sys.executable`` points to the compiled
    binary, so output files (config.json, referensi.json, etc.) are placed
    next to the executable rather than in the temporary extraction directory
    (``_MEIPASS``).

    Returns
    -------
    str
        Absolute path to the directory containing the executable or script.
    """
    if getattr(sys, "frozen", False):
        # Running as a PyInstaller frozen executable.
        return os.path.dirname(sys.executable)
    # Running as a standard Python script.
    return os.path.dirname(os.path.abspath(__file__))

BASE_DIR = get_base_dir()

def base_path(filename: str) -> str:
    """Return an absolute path by joining *filename* with the application base directory."""
    return os.path.join(BASE_DIR, filename)


# =============================================================================
# CONFIGURATION MANAGER
# Loads and persists runtime parameters via an external config.json file.
# Missing keys are back-filled from DEFAULT_CONFIG to support version upgrades.
# =============================================================================
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
    Load the application configuration from *config.json*.

    If the file does not exist it is created with DEFAULT_CONFIG values.
    Any keys absent from the stored file (e.g. after a version upgrade) are
    back-filled from DEFAULT_CONFIG so the application never crashes on a
    missing key.

    Returns
    -------
    dict
        Merged configuration dictionary ready for use by the application.
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
        # Deep-merge the nested "db" sub-dictionary separately.
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


# =============================================================================
# SETTINGS GUI  (Tkinter)
# Pre-flight configuration window presented to the operator before the
# OpenCV inspection loop starts. Saves changes to config.json on confirm.
# =============================================================================
class SettingsGUI:
    """
    Pre-flight settings window built with Tkinter.

    Displays all configurable parameters in a scrollable form. The operator
    reviews or adjusts the settings and clicks "Save & Start" to persist the
    configuration and launch the OpenCV inspection loop.

    Attributes
    ----------
    cfg : dict
        The configuration dictionary loaded at startup.
    result_cfg : dict or None
        Set to the validated configuration when the operator confirms.
        Remains ``None`` if the window is closed without saving.
    """

    # UI colour palette — dark blue theme.
    BG          = "#1E2A3A"
    BG_FRAME    = "#253447"
    BG_ENTRY    = "#2E4057"
    FG          = "#E8EEF4"
    FG_LABEL    = "#A8BDD0"
    ACCENT      = "#2E75B6"
    ACCENT_DARK = "#1A5490"
    GREEN       = "#2ECC71"
    RED         = "#E74C3C"
    YELLOW      = "#F39C12"

    def __init__(self, cfg: dict):
        self.cfg        = cfg
        self.result_cfg = None   # Populated only after the operator confirms.
        self._build()

    # -------------------------------------------------------------------------
    def _build(self):
        self.root = tk.Tk()
        self.root.title("Capstone — Sistem Inspeksi Dimensi v6  |  Settings")
        self.root.configure(bg=self.BG)
        self.root.resizable(False, False)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        # Centre the window on the primary display.
        W_WIN, H_WIN = 1000, 720
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        self.root.geometry(f"{W_WIN}x{H_WIN}+{(sw-W_WIN)//2}+{(sh-H_WIN)//2}")

        # Application header banner.
        hdr = tk.Frame(self.root, bg=self.ACCENT, pady=14)
        hdr.pack(fill="x")
        tk.Label(hdr, text="SISTEM INSPEKSI DIMENSI PART MANUFAKTUR",
                 bg=self.ACCENT, fg=self.FG,
                 font=("Arial", 13, "bold")).pack()
        tk.Label(hdr, text="Capstone Project A.3  |  Tim Jagoan Mamah Papah  |  UB 2026",
                 bg=self.ACCENT, fg="#C8D8E8",
                 font=("Arial", 9)).pack()

        # Scrollable content area containing all parameter input fields.
        canvas  = tk.Canvas(self.root, bg=self.BG, highlightthickness=0)
        scrollb = ttk.Scrollbar(self.root, orient="vertical",
                                command=canvas.yview)
        self.scroll_frame = tk.Frame(canvas, bg=self.BG)
        self.scroll_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=self.scroll_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollb.set)
        canvas.pack(side="left", fill="both", expand=True)
        scrollb.pack(side="right", fill="y")
        canvas.bind_all("<MouseWheel>",
                        lambda e: canvas.yview_scroll(-1*(e.delta//120), "units"))

        pad = {"padx": 20, "pady": 4}

        # --- Camera settings section ---
        self._section("PENGATURAN KAMERA")

        self._row("Source Kamera",
                  "Nomor index (0/1/2) atau URL stream\n"
                  "Contoh URL: http://192.168.1.5:8080/video")
        self.var_camera = tk.StringVar(value=str(self.cfg["camera_source"]))
        self._entry(self.var_camera)

        self._row("Resolusi Capture Lebar (px)")
        self.var_cap_w = tk.StringVar(value=str(self.cfg["capture_width"]))
        self._entry(self.var_cap_w)

        self._row("Resolusi Capture Tinggi (px)")
        self.var_cap_h = tk.StringVar(value=str(self.cfg["capture_height"]))
        self._entry(self.var_cap_h)

        self._row("DroidCam Fix (layar hijau)",
                  "Aktifkan jika menggunakan DroidCam USB dan layar menjadi hijau")
        self.var_droidcam = tk.BooleanVar(value=bool(self.cfg["droidcam_fix"]))
        self._checkbox(self.var_droidcam, "Aktifkan DroidCam Green Fix")

        # --- Calibration and detection settings section ---
        self._section("KALIBRASI & DETEKSI")

        self._row("Pixel per mm (kalibrasi skala)",
                  "Rumus: ukur benda referensi (mm) → hitung pixel-nya\n"
                  "pixel_per_mm = pixel_benda / mm_benda\n"
                  "Contoh: koin Rp500 (27mm) terukur 250px → 250/27 = 9.26")
        self.var_ppm = tk.StringVar(value=str(self.cfg["pixel_per_mm"]))
        self._entry(self.var_ppm)

        self._row("Toleransi Good/NG (mm)",
                  "Selisih dimensi maksimum yang masih dianggap GOOD\n"
                  "Default: 1.0 mm")
        self.var_tol = tk.StringVar(value=str(self.cfg["tolerance_mm"]))
        self._entry(self.var_tol)

        self._row("Threshold Kontur Awal",
                  "Nilai awal binarisasi (10–250)\n"
                  "Dapat diubah real-time saat inspeksi dengan tombol +/-")
        self.var_thresh = tk.StringVar(value=str(self.cfg["contour_thresh"]))
        self._entry(self.var_thresh)

        self._row("Area Kontur Minimum (pixel²)",
                  "Kontur lebih kecil dari nilai ini diabaikan\n"
                  "Naikkan jika terlalu banyak noise deteksi (default: 1500)")
        self.var_min_area = tk.StringVar(value=str(self.cfg["contour_min_area"]))
        self._entry(self.var_min_area)

        self._row("Dimensi Minimum (mm)",
                  "Objek dengan dimensi < nilai ini diabaikan (default: 5.0)")
        self.var_min_mm = tk.StringVar(value=str(self.cfg["min_feature_mm"]))
        self._entry(self.var_min_mm)

        self._row("Durasi Warning NG (detik)",
                  "Berapa lama overlay merah berkedip saat ada part NG (default: 5)")
        self.var_warn_dur = tk.StringVar(value=str(self.cfg["warning_duration"]))
        self._entry(self.var_warn_dur)

        # --- Region of Interest (ROI) settings section ---
        self._section("AREA INSPEKSI (ROI)")

        roi = self.cfg["roi_percent"]
        self._row("ROI — X Mulai (0.0 – 1.0)",
                  "Batas kiri area inspeksi sebagai persentase lebar frame")
        self.var_roi_x1 = tk.StringVar(value=str(roi[0]))
        self._entry(self.var_roi_x1)

        self._row("ROI — Y Mulai (0.0 – 1.0)",
                  "Batas atas area inspeksi sebagai persentase tinggi frame")
        self.var_roi_y1 = tk.StringVar(value=str(roi[1]))
        self._entry(self.var_roi_y1)

        self._row("ROI — X Selesai (0.0 – 1.0)",
                  "Batas kanan area inspeksi")
        self.var_roi_x2 = tk.StringVar(value=str(roi[2]))
        self._entry(self.var_roi_x2)

        self._row("ROI — Y Selesai (0.0 – 1.0)",
                  "Batas bawah area inspeksi")
        self.var_roi_y2 = tk.StringVar(value=str(roi[3]))
        self._entry(self.var_roi_y2)

        # --- PostgreSQL database settings section ---
        self._section("DATABASE POSTGRESQL")

        db = self.cfg["db"]

        self._row("Aktifkan Database",
                  "Jika diaktifkan, setiap deteksi akan dicatat ke PostgreSQL\n"
                  "Pastikan psycopg2 terinstall: pip install psycopg2-binary")
        self.var_db_enabled = tk.BooleanVar(value=bool(db.get("enabled", False)))
        self._checkbox(self.var_db_enabled, "Aktifkan logging ke PostgreSQL")

        self._row("Host")
        self.var_db_host = tk.StringVar(value=str(db.get("host", "localhost")))
        self._entry(self.var_db_host)

        self._row("Port")
        self.var_db_port = tk.StringVar(value=str(db.get("port", 5432)))
        self._entry(self.var_db_port)

        self._row("Nama Database")
        self.var_db_name = tk.StringVar(value=str(db.get("dbname", "capstone_db")))
        self._entry(self.var_db_name)

        self._row("Username")
        self.var_db_user = tk.StringVar(value=str(db.get("user", "postgres")))
        self._entry(self.var_db_user)

        self._row("Password")
        self.var_db_pass = tk.StringVar(value=str(db.get("password", "")))
        self._entry(self.var_db_pass, show="●")

        # Status bar at the bottom of the window.
        self.status_var = tk.StringVar(value="Siap — ubah pengaturan lalu klik Save & Start")
        status_bar = tk.Label(self.root, textvariable=self.status_var,
                              bg=self.BG_FRAME, fg=self.FG_LABEL,
                              font=("Arial", 9), anchor="w", padx=12, pady=6)
        status_bar.pack(fill="x", side="bottom")

        # Action buttons at the bottom of the window.
        btn_frame = tk.Frame(self.root, bg=self.BG, pady=12)
        btn_frame.pack(fill="x", side="bottom")

        tk.Button(
            btn_frame, text="Reset ke Default",
            bg=self.BG_FRAME, fg=self.FG_LABEL,
            font=("Arial", 10), relief="flat",
            padx=14, pady=8, cursor="hand2",
            command=self._reset_defaults
        ).pack(side="left", padx=20)

        tk.Button(
            btn_frame, text="Test Koneksi DB",
            bg=self.BG_FRAME, fg=self.YELLOW,
            font=("Arial", 10), relief="flat",
            padx=14, pady=8, cursor="hand2",
            command=self._test_db
        ).pack(side="left", padx=10)

        tk.Button(
            btn_frame, text="✓  Save & Start",
            bg=self.GREEN, fg="white",
            font=("Arial", 11, "bold"), relief="flat",
            padx=24, pady=8, cursor="hand2",
            command=self._save_and_start
        ).pack(side="right", padx=20)

    # -------------------------------------------------------------------------
    # Widget factory helpers
    def _section(self, title: str):
        f = tk.Frame(self.scroll_frame, bg=self.ACCENT, pady=6)
        f.pack(fill="x", padx=16, pady=(14, 2))
        tk.Label(f, text=f"  {title}",
                 bg=self.ACCENT, fg="white",
                 font=("Arial", 10, "bold")).pack(anchor="w")

    def _row(self, label: str, hint: str = ""):
        f = tk.Frame(self.scroll_frame, bg=self.BG)
        f.pack(fill="x", padx=20, pady=(8, 0))
        tk.Label(f, text=label, bg=self.BG, fg=self.FG,
                 font=("Arial", 10, "bold"), anchor="w").pack(anchor="w")
        if hint:
            tk.Label(f, text=hint, bg=self.BG, fg=self.FG_LABEL,
                     font=("Arial", 8), anchor="w", justify="left").pack(anchor="w")

    def _entry(self, var: tk.StringVar, show: str = ""):
        e = tk.Entry(self.scroll_frame, textvariable=var,
                     bg=self.BG_ENTRY, fg=self.FG,
                     insertbackground=self.FG,
                     font=("Courier New", 11),
                     relief="flat", bd=0,
                     show=show)
        e.pack(fill="x", padx=20, pady=(2, 0), ipady=6)
        # 1-pixel accent-coloured underline acts as the input field border.
        sep = tk.Frame(self.scroll_frame, bg=self.ACCENT, height=1)
        sep.pack(fill="x", padx=20)
        return e

    def _checkbox(self, var: tk.BooleanVar, text: str):
        cb = tk.Checkbutton(
            self.scroll_frame, text=text, variable=var,
            bg=self.BG, fg=self.FG, selectcolor=self.ACCENT,
            activebackground=self.BG, activeforeground=self.FG,
            font=("Arial", 10), anchor="w", cursor="hand2")
        cb.pack(anchor="w", padx=20, pady=(2, 0))

    # -------------------------------------------------------------------------
    # Form actions
    def _collect(self) -> dict | None:
        """Collect and validate all widget values, returning a config dict or None on error."""
        errors = []

        def get_float(var, name, mn=None, mx=None):
            try:
                v = float(var.get())
                if mn is not None and v < mn:
                    errors.append(f"{name}: nilai minimum {mn}")
                if mx is not None and v > mx:
                    errors.append(f"{name}: nilai maksimum {mx}")
                return v
            except ValueError:
                errors.append(f"{name}: harus berupa angka desimal")
                return None

        def get_int(var, name, mn=None, mx=None):
            try:
                v = int(var.get())
                if mn is not None and v < mn:
                    errors.append(f"{name}: nilai minimum {mn}")
                if mx is not None and v > mx:
                    errors.append(f"{name}: nilai maksimum {mx}")
                return v
            except ValueError:
                errors.append(f"{name}: harus berupa bilangan bulat")
                return None

        # camera_source accepts an integer device index or a URL string.
        cam_raw = self.var_camera.get().strip()
        try:
            camera_source = int(cam_raw)
        except ValueError:
            camera_source = cam_raw   # URL string

        cap_w    = get_int(self.var_cap_w,    "Lebar capture",    320, 7680)
        cap_h    = get_int(self.var_cap_h,    "Tinggi capture",   240, 4320)
        ppm      = get_float(self.var_ppm,    "Pixel per mm",     0.1, 1000)
        tol      = get_float(self.var_tol,    "Toleransi",        0.0, 100)
        thresh   = get_int(self.var_thresh,   "Threshold",        10,  250)
        min_area = get_int(self.var_min_area, "Area minimum",     100)
        min_mm   = get_float(self.var_min_mm, "Dimensi minimum",  0.1)
        warn_dur = get_float(self.var_warn_dur,"Durasi warning",  1.0, 60)
        roi_x1   = get_float(self.var_roi_x1, "ROI X1",          0.0, 0.9)
        roi_y1   = get_float(self.var_roi_y1, "ROI Y1",          0.0, 0.9)
        roi_x2   = get_float(self.var_roi_x2, "ROI X2",          0.1, 1.0)
        roi_y2   = get_float(self.var_roi_y2, "ROI Y2",          0.1, 1.0)
        db_port  = get_int(self.var_db_port,  "Port DB",          1,   65535)

        if errors:
            messagebox.showerror(
                "Input Tidak Valid",
                "Terdapat kesalahan input:\n\n" + "\n".join(f"• {e}" for e in errors))
            return None

        return {
            "camera_source"   : camera_source,
            "droidcam_fix"    : self.var_droidcam.get(),
            "capture_width"   : cap_w,
            "capture_height"  : cap_h,
            "pixel_per_mm"    : ppm,
            "roi_percent"     : [roi_x1, roi_y1, roi_x2, roi_y2],
            "contour_min_area": min_area,
            "contour_thresh"  : thresh,
            "min_feature_mm"  : min_mm,
            "tolerance_mm"    : tol,
            "warning_duration": warn_dur,
            "dir_screenshot"  : self.cfg.get("dir_screenshot", "screenshots"),
            "dir_deteksi"     : self.cfg.get("dir_deteksi",    "deteksi_part"),
            "file_reference"  : self.cfg.get("file_reference", "referensi.json"),
            "db": {
                "enabled" : self.var_db_enabled.get(),
                "host"    : self.var_db_host.get().strip(),
                "port"    : db_port,
                "dbname"  : self.var_db_name.get().strip(),
                "user"    : self.var_db_user.get().strip(),
                "password": self.var_db_pass.get(),
            }
        }

    def _save_and_start(self):
        """Validate form input, optionally verify the database connection, persist config.json, then close the window."""
        cfg = self._collect()
        if cfg is None: return          # ada error validasi dari input

        # If the operator has enabled database logging, verify connectivity
        # before closing the settings window to avoid a silent failure at runtime.
        if cfg["db"]["enabled"]:
            if not PSYCOPG2_AVAILABLE:
                messagebox.showerror("Error Database", 
                    "Library psycopg2 belum terinstall!\nSilakan matikan centang database atau install via terminal: pip install psycopg2-binary")
                return
            
            self.status_var.set("Mengecek koneksi database...")
            self.root.update()

            try:
                conn = psycopg2.connect(
                    host    = cfg["db"]["host"],
                    port    = cfg["db"]["port"],
                    dbname  = cfg["db"]["dbname"],
                    user    = cfg["db"]["user"],
                    password= cfg["db"]["password"],
                    connect_timeout=3
                )
                conn.close()
            except Exception as e:
                messagebox.showerror("Koneksi DB Gagal", 
                                     f"Gagal terhubung ke database!\n\n{e}\n\n"
                                     "Periksa pengaturan DB atau MATIKAN centang 'Aktifkan Database' jika belum butuh.")
                self.status_var.set("✗ Koneksi DB gagal. Perbaiki atau matikan fitur DB.")
                return 

        # All validations passed — persist configuration and launch the system.
        save_config(cfg)
        self.result_cfg = cfg
        self.status_var.set("Konfigurasi disimpan. Membuka sistem inspeksi...")
        self.root.after(300, self.root.destroy)

    def _reset_defaults(self):
        if not messagebox.askyesno(
                "Reset Konfigurasi",
                "Semua pengaturan akan dikembalikan ke nilai default.\nLanjutkan?"):
            return
        d = DEFAULT_CONFIG
        self.var_camera.set(str(d["camera_source"]))
        self.var_cap_w.set(str(d["capture_width"]))
        self.var_cap_h.set(str(d["capture_height"]))
        self.var_droidcam.set(bool(d["droidcam_fix"]))
        self.var_ppm.set(str(d["pixel_per_mm"]))
        self.var_tol.set(str(d["tolerance_mm"]))
        self.var_thresh.set(str(d["contour_thresh"]))
        self.var_min_area.set(str(d["contour_min_area"]))
        self.var_min_mm.set(str(d["min_feature_mm"]))
        self.var_warn_dur.set(str(d["warning_duration"]))
        roi = d["roi_percent"]
        self.var_roi_x1.set(str(roi[0])); self.var_roi_y1.set(str(roi[1]))
        self.var_roi_x2.set(str(roi[2])); self.var_roi_y2.set(str(roi[3]))
        db = d["db"]
        self.var_db_enabled.set(bool(db["enabled"]))
        self.var_db_host.set(db["host"]); self.var_db_port.set(str(db["port"]))
        self.var_db_name.set(db["dbname"]); self.var_db_user.set(db["user"])
        self.var_db_pass.set(db["password"])
        self.status_var.set("Konfigurasi direset ke nilai default.")

    def _test_db(self):
        """Attempt a live connection to PostgreSQL using the current form values and report the result."""
        if not PSYCOPG2_AVAILABLE:
            messagebox.showwarning(
                "psycopg2 Tidak Ada",
                "Library psycopg2 belum terinstall.\n\n"
                "Jalankan: pip install psycopg2-binary")
            return

        self.status_var.set("Mencoba koneksi ke database...")
        self.root.update()

        try:
            conn = psycopg2.connect(
                host    = self.var_db_host.get().strip(),
                port    = int(self.var_db_port.get()),
                dbname  = self.var_db_name.get().strip(),
                user    = self.var_db_user.get().strip(),
                password= self.var_db_pass.get(),
                connect_timeout=5
            )
            conn.close()
            messagebox.showinfo("Koneksi Berhasil",
                                "Koneksi ke PostgreSQL berhasil!\n"
                                "Database siap digunakan.")
            self.status_var.set("✓ Koneksi DB berhasil.")
        except Exception as e:
            messagebox.showerror("Koneksi Gagal",
                                 f"Gagal terhubung ke database:\n\n{e}\n\n"
                                 "Periksa kembali host, port, nama DB, user, dan password.")
            self.status_var.set("✗ Koneksi DB gagal.")

    def _on_close(self):
        if messagebox.askyesno("Keluar", "Tutup program tanpa memulai sistem inspeksi?"):
            self.root.destroy()

    def run(self) -> dict | None:
        """Enter the Tkinter event loop and return the saved config dict, or None if the window was closed without saving."""
        self.root.mainloop()
        return self.result_cfg


# =============================================================================
# OPENCV RENDERING CONSTANTS
# Colour palette (BGR) and font used for all OpenCV overlay drawing.
# =============================================================================
C = {
    "green"  : (50,  220,  50),
    "red"    : (40,   40, 220),
    "yellow" : (0,   210, 255),
    "cyan"   : (255, 200,   0),
    "white"  : (255, 255, 255),
    "orange" : (0,   140, 255),
    "purple" : (200,  50, 200),
    "gray"   : (160, 160, 160),
    "black"  : (0,     0,   0),
    "teal"   : (180, 220, 120),
    "good"   : (50,  220,  50),
    "ng"     : (40,   40, 220),
    "warn"   : (0,   165, 255),
}
FONT = cv2.FONT_HERSHEY_SIMPLEX


# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================
def px2mm(pixels, ppm):
    return pixels / ppm if ppm > 0 else 0.0

def dist(p1, p2):
    return math.hypot(p1[0] - p2[0], p1[1] - p2[1])

def midpt(p1, p2):
    return ((p1[0] + p2[0]) // 2, (p1[1] + p2[1]) // 2)

def now_str():
    return datetime.datetime.now().strftime("%Y%m%d_%H%M%S")

def now_iso():
    return datetime.datetime.now().isoformat()

def label(img, text, pos, scale=0.50, color=C["white"],
          bg=None, thick=1, pad=5):
    (tw, th), _ = cv2.getTextSize(text, FONT, scale, thick)
    x, y = int(pos[0]), int(pos[1])
    if bg is not None:
        cv2.rectangle(img, (x-pad, y-th-pad), (x+tw+pad, y+pad), bg, -1)
    cv2.putText(img, text, (x, y), FONT, scale, color, thick, cv2.LINE_AA)

def arrow_line(img, p1, p2, color, thick=1):
    p1 = (int(p1[0]), int(p1[1])); p2 = (int(p2[0]), int(p2[1]))
    cv2.line(img, p1, p2, color, thick, cv2.LINE_AA)
    dx = p2[0]-p1[0]; dy = p2[1]-p1[1]
    length = math.hypot(dx, dy)
    if length == 0: return
    nx, ny = -dy/length*6, dx/length*6
    for p in [p1, p2]:
        cv2.line(img, (int(p[0]-nx), int(p[1]-ny)),
                 (int(p[0]+nx), int(p[1]+ny)), color, thick+1, cv2.LINE_AA)

def draw_dim_line(img, p1, p2, value_mm, color, offset_px=22):
    p1 = (int(p1[0]), int(p1[1])); p2 = (int(p2[0]), int(p2[1]))
    dx = p2[0]-p1[0]; dy = p2[1]-p1[1]
    length = math.hypot(dx, dy)
    if length < 2: return
    nx = int(-dy/length * offset_px); ny = int(dx/length * offset_px)
    op1 = (p1[0]+nx, p1[1]+ny); op2 = (p2[0]+nx, p2[1]+ny)
    cv2.line(img, p1, op1, color, 1, cv2.LINE_AA)
    cv2.line(img, p2, op2, color, 1, cv2.LINE_AA)
    arrow_line(img, op1, op2, color, 1)
    mid = midpt(op1, op2)
    label(img, f"{value_mm:.1f}mm", (mid[0]-18, mid[1]-5), 0.44, color, (18,18,18))

def draw_roi_box(img, roi_px, active):
    if not active: return
    x1, y1, x2, y2 = roi_px
    overlay = img.copy()
    cv2.rectangle(overlay, (0,0), (img.shape[1],img.shape[0]), C["black"], -1)
    cv2.rectangle(overlay, (x1,y1), (x2,y2), C["black"], -1)
    cv2.addWeighted(overlay, 0.20, img, 0.80, 0, img)
    cv2.rectangle(img, (x1,y1), (x2,y2), C["cyan"], 2)
    cl = 22
    for (cx,cy),(ddx,ddy) in [((x1,y1),(1,1)),((x2,y1),(-1,1)),
                                ((x1,y2),(1,-1)),((x2,y2),(-1,-1))]:
        cv2.line(img,(cx,cy),(cx+ddx*cl,cy),C["cyan"],3)
        cv2.line(img,(cx,cy),(cx,cy+ddy*cl),C["cyan"],3)
    label(img, "[ AREA INSPEKSI ]", (x1+8, y1-8), 0.44, C["cyan"])


# =============================================================================
# SHAPE CLASSIFIER
# Classifies a contour into a geometric category using the Douglas-Peucker
# polygon approximation (approxPolyDP) combined with circularity and aspect
# ratio heuristics.
# =============================================================================
def classify_shape(contour):
    perimeter    = cv2.arcLength(contour, True)
    area         = cv2.contourArea(contour)
    epsilon      = 0.03 * perimeter
    approx       = cv2.approxPolyDP(contour, epsilon, True)
    n            = len(approx)
    circularity  = 4 * math.pi * area / (perimeter**2 + 1e-6)
    x, y, w, h   = cv2.boundingRect(contour)
    aspect_ratio = min(w,h) / max(w,h) if max(w,h) > 0 else 0

    if circularity > 0.75:                    return "circle",    n, circularity
    if aspect_ratio > 0.88 and n > 6:        return "circle",    n, circularity
    if n == 3:                                return "triangle",  n, circularity
    if n == 4:
        ar = w/float(h) if h>0 else 1
        return ("square" if 0.90<=ar<=1.10 else "rectangle"), n, circularity
    if n == 5:                                return "pentagon",  n, circularity
    if n == 6:                                return "hexagon",   n, circularity
    return "polygon", n, circularity

SHAPE_LABEL = {
    "circle"   : "LINGKARAN", "triangle" : "SEGITIGA",
    "square"   : "KOTAK",     "rectangle": "PERSEGI PANJANG",
    "pentagon" : "PENTAGON",  "hexagon"  : "HEKSAGON",
    "polygon"  : "POLIGON",
}


# =============================================================================
# DETECTED OBJECT
# Data class representing a single detected contour with all computed
# geometric properties (bounding rect, enclosing circle, shape class, etc.).
# =============================================================================
class DetectedObject:
    def __init__(self, contour, ppm: float):
        self.contour  = contour
        self.area_px  = cv2.contourArea(contour)
        x, y, w, h    = cv2.boundingRect(contour)
        self.bbox     = (x, y, x+w, y+h)
        rr             = cv2.minAreaRect(contour)
        self.rot_rect  = rr
        self.rot_box   = cv2.boxPoints(rr).astype(int)
        rw, rh         = rr[1]
        self.width_px  = max(rw, rh);  self.height_px = min(rw, rh)
        self.width_mm  = px2mm(self.width_px,  ppm)
        self.height_mm = px2mm(self.height_px, ppm)
        (cx,cy), self.radius_px = cv2.minEnclosingCircle(contour)
        self.center       = (int(cx), int(cy))
        self.diameter_px  = self.radius_px * 2
        self.diameter_mm  = px2mm(self.diameter_px, ppm)
        self.shape, self.vertices, self.circularity = classify_shape(contour)
        self._ppm = ppm

    @property
    def label_size(self):
        return (f"Ø{self.diameter_mm:.1f}mm" if self.shape == "circle"
                else f"{self.width_mm:.1f}×{self.height_mm:.1f}mm")

    def to_dict(self):
        return {
            "shape": self.shape, "vertices": self.vertices,
            "circularity": round(self.circularity, 3),
            "timestamp": now_str(), "pixel_per_mm": self._ppm,
            "diameter_mm": round(self.diameter_mm, 2),
            "width_mm": round(self.width_mm, 2),
            "height_mm": round(self.height_mm, 2),
            "area_px": round(self.area_px, 1),
            "bbox": list(self.bbox),
        }


# =============================================================================
# IMAGE PREPROCESSING PIPELINE
# Grayscale → Gaussian Blur → CLAHE → (Adaptive Threshold OR Canny) → Close
# =============================================================================
def preprocess(frame):
    gray     = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    blurred  = cv2.GaussianBlur(gray, (5,5), 0)
    clahe    = cv2.createCLAHE(clipLimit=2.5, tileGridSize=(8,8))
    enhanced = clahe.apply(blurred)
    return gray, blurred, enhanced

def get_binary(enhanced, thresh_val):
    adaptive = cv2.adaptiveThreshold(enhanced, 255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV,
        21, thresh_val // 4)
    canny    = cv2.Canny(enhanced, thresh_val*0.5, thresh_val*1.5)
    combined = cv2.bitwise_or(adaptive, canny)
    kernel   = cv2.getStructuringElement(cv2.MORPH_RECT, (3,3))
    return cv2.morphologyEx(combined, cv2.MORPH_CLOSE, kernel, iterations=2)

def find_objects(binary, min_area, ppm, min_feature_mm):
    contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    objects = []
    for cnt in contours:
        if cv2.contourArea(cnt) < min_area: continue
        obj = DetectedObject(cnt, ppm)
        if obj.width_mm < min_feature_mm and obj.height_mm < min_feature_mm: continue
        objects.append(obj)
    objects.sort(key=lambda o: o.bbox[0])
    return objects


# =============================================================================
# DATABASE MANAGER
# Manages the PostgreSQL connection and inspection log writes.
# Operates in stub mode (console-only logging) when the database is
# disabled or psycopg2 is unavailable.
# =============================================================================
class DatabaseManager:
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
            self.conn = None; self.enabled = False
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


# =============================================================================
# REFERENCE MANAGER
# Stores and compares dimensional reference profiles persisted in
# referensi.json. Supports multiple named profiles per shape type.
# =============================================================================
class ReferenceManager:
    def __init__(self, filepath: str):
        self.filepath = filepath
        self.refs: dict = {}
        self._load()

    def _load(self):
        if os.path.exists(self.filepath):
            try:
                with open(self.filepath, "r") as f:
                    self.refs = json.load(f)
                print(f"[REF] {len(self.refs)} referensi dimuat dari '{self.filepath}'")
                for name, d in self.refs.items():
                    key = d.get("diameter_mm", d.get("width_mm","?"))
                    print(f"  · '{name}' — {d['shape']} ({key} mm)")
            except Exception as e:
                print(f"[REF] Gagal baca: {e}"); self.refs = {}
        else:
            print("[REF] File referensi belum ada — akan dibuat saat pertama save.")

    def _save(self):
        with open(self.filepath, "w") as f:
            json.dump(self.refs, f, indent=2)
        print(f"[REF] Disimpan ({len(self.refs)} profil)")

    def save_reference(self, obj: DetectedObject, name: str, tol: float) -> dict:
        data = {"name":name,"shape":obj.shape,"vertices":obj.vertices,
                "diameter_mm":round(obj.diameter_mm,2),
                "width_mm":round(obj.width_mm,2),
                "height_mm":round(obj.height_mm,2),
                "tolerance_mm":tol,"timestamp":now_str()}
        self.refs[name] = data
        self._save()
        return data

    def compare(self, obj: DetectedObject, tol: float):
        same = {n:d for n,d in self.refs.items() if d["shape"]==obj.shape}
        if not same:
            return "NO REF", None, f"Belum ada referensi untuk {obj.shape}"
        best_name = None; best_delta = float("inf")
        for name, ref in same.items():
            t = ref.get("tolerance_mm", tol)
            if obj.shape == "circle":
                delta = abs(obj.diameter_mm - ref["diameter_mm"])
                ok    = delta <= t
            else:
                dw = abs(obj.width_mm  - ref["width_mm"])
                dh = abs(obj.height_mm - ref["height_mm"])
                delta = max(dw,dh); ok = dw<=t and dh<=t
            if ok and delta < best_delta:
                best_delta = delta; best_name = name
        if best_name:
            ref = same[best_name]
            if obj.shape == "circle":
                d = abs(obj.diameter_mm - ref["diameter_mm"])
                detail = f"Ø ref={ref['diameter_mm']:.1f} got={obj.diameter_mm:.1f} Δ={d:.1f}mm ✓"
            else:
                detail = (f"P ref={ref['width_mm']:.1f} got={obj.width_mm:.1f} "
                          f"| L ref={ref['height_mm']:.1f} got={obj.height_mm:.1f} ✓")
            return "GOOD", best_name, detail
        closest = min(same, key=lambda n: _outer_delta(obj, same[n]))
        ref = same[closest]
        if obj.shape == "circle":
            d = abs(obj.diameter_mm - ref["diameter_mm"])
            detail = f"Ø ref={ref['diameter_mm']:.1f} got={obj.diameter_mm:.1f} Δ={d:.1f}mm ✗"
        else:
            detail = (f"P ref={ref['width_mm']:.1f} got={obj.width_mm:.1f} "
                      f"| L ref={ref['height_mm']:.1f} got={obj.height_mm:.1f} ✗")
        return "NO GOOD", closest, detail

    def list_names(self): return list(self.refs.keys())
    def clear_all(self): self.refs={}; self._save()


def _outer_delta(obj, ref):
    if obj.shape=="circle": return abs(obj.diameter_mm - ref.get("diameter_mm",0))
    return abs(obj.width_mm-ref.get("width_mm",0))+abs(obj.height_mm-ref.get("height_mm",0))


# =============================================================================
# NOTIFICATION SYSTEM
# Renders auto-expiring status messages in the centre of the OpenCV window.
# =============================================================================
class Notification:
    def __init__(self): self.messages = []

    def add(self, text, color=C["white"], duration=3.0):
        self.messages.append((text, color, time.time()+duration))
        print(f"[NOTIF] {text}")

    def draw(self, img):
        now = time.time()
        self.messages = [(t,c,e) for t,c,e in self.messages if e>now]
        H,W = img.shape[:2]; y = H//2 - len(self.messages)*30
        for text, color, _ in self.messages:
            (tw,th),_ = cv2.getTextSize(text,FONT,0.65,2)
            x = (W-tw)//2
            ov = img.copy()
            cv2.rectangle(ov,(x-14,y-th-12),(x+tw+14,y+12),C["black"],-1)
            cv2.addWeighted(ov,0.65,img,0.35,0,img)
            cv2.putText(img,text,(x,y),FONT,0.65,color,2,cv2.LINE_AA)
            y += 48


# =============================================================================
# WARNING OVERLAY
# Renders a prominent, blinking red alert when one or more inspected parts
# are classified as NO GOOD. Remains visible for a configurable duration.
# =============================================================================
class WarningOverlay:
    BLINK_HZ = 2.0
    def __init__(self): self.active=False; self.expire=0.0; self.ng_count=0

    def trigger(self, ng_count: int):
        self.active=True; self.ng_count=ng_count
        print(f"[WARNING] {ng_count} part NO GOOD!")

    def set_duration(self, dur: float):
        self.expire = time.time() + dur

    def clear(self): self.active=False

    def draw(self, img, dur: float):
        if not self.active: return
        if self.expire == 0.0: self.expire = time.time() + dur
        now = time.time()
        if now > self.expire: self.active=False; self.expire=0.0; return
        if (now % (1.0/self.BLINK_HZ)) / (1.0/self.BLINK_HZ) > 0.5: return
        H,W = img.shape[:2]
        ov = img.copy()
        cv2.rectangle(ov,(0,0),(W,H),(0,0,180),-1)
        cv2.addWeighted(ov,0.25,img,0.75,0,img)
        cv2.rectangle(img,(4,4),(W-4,H-4),(0,0,220),8)
        lines = [
            ("⚠  PART TIDAK LOLOS SELEKSI  ⚠", 1.10, (0,0,255)),
            (f"{self.ng_count} PART BERSTATUS NO GOOD",  0.80, (0,140,255)),
            ("PINDAHKAN KE WADAH NG !",                  0.90, (0,0,255)),
        ]
        y = H//2 - 70
        for text, scale, col in lines:
            (tw,th),_ = cv2.getTextSize(text,FONT,scale,3)
            x = (W-tw)//2
            cv2.putText(img,text,(x+3,y+3),FONT,scale,C["black"],4,cv2.LINE_AA)
            cv2.putText(img,text,(x,y),FONT,scale,col,3,cv2.LINE_AA)
            y += th+22
        remaining = max(0.0, self.expire-now)
        cd = f"Peringatan hilang dalam {remaining:.0f} detik"
        (tw,_),_ = cv2.getTextSize(cd,FONT,0.46,1)
        label(img, cd, ((W-tw)//2, H-28), 0.46, (0,180,255), C["black"])

class ObjectTracker:
    """
    Temporal stabiliser for per-frame contour detections.

    Eliminates the "flashing" artefact caused by single-frame detection
    failures on reflective metallic parts, and ensures that the inspect
    action (key D) always reads a valid detection even if the most recent
    frame contained no contours.
 
    Each tracked position is maintained in a *slot* dictionary.

    Slot lifecycle
    --------------
    MATCHING
        Each new raw detection is greedily matched to the nearest existing
        slot within MAX_DIST_PX pixels. Unmatched detections create a new slot.
    CONFIRM
        A slot is promoted to *visible* only after it has been matched for
        CONFIRM_FRAMES consecutive frames, suppressing transient false positives.
    GHOST
        When a slot receives no match it enters *ghost* mode. The last valid
        detection is retained for up to GHOST_FRAMES frames before the slot
        is discarded, keeping the display stable across brief detection gaps.
    SMOOTHING
        Dimensional values shown to the operator are the moving average of the
        most recent SMOOTH_FRAMES readings, reducing measurement jitter.
    """
 
    # Tuning parameters — adjust these to balance responsiveness vs. stability.
    CONFIRM_FRAMES = 4   # Consecutive hits required before a slot becomes visible.
    GHOST_FRAMES   = 12  # Miss frames tolerated before a slot is discarded.
    SMOOTH_FRAMES  = 6   # Window size for the dimensional moving average.
    MAX_DIST_PX    = 80  # Maximum centroid displacement (px) for slot matching.
 
    def __init__(self):
        self._slots: list[dict] = []
        self._next_id = 0
 
    def update(self, raw_objects: list) -> list:
        """
        Ingest raw detections for the current frame and return stable objects.

        Parameters
        ----------
        raw_objects : list[DetectedObject]
            Unfiltered detections produced by ``find_objects()`` for this frame.

        Returns
        -------
        list[DetectedObject]
            Confirmed, smoothed detections — only slots that have passed the
            confirmation threshold and have not yet expired.
        """
        self._match_and_update(raw_objects)
        self._expire_slots()
        return self._get_stable_objects()
 
    @property
    def stable_objects(self) -> list:
        """
        Return the current stable objects without advancing the tracker state.

        Used by the inspect action (key D) to guarantee a valid read even
        when the most recent frame contained no contours.
        """
        return self._get_stable_objects()
 
    def reset(self):
        self._slots.clear()
 
    def _center(self, obj) -> tuple:
        return obj.center if obj.shape == "circle" else (
            (obj.bbox[0] + obj.bbox[2]) // 2,
            (obj.bbox[1] + obj.bbox[3]) // 2)
 
    def _match_and_update(self, raw_objects: list):
        """
        Match raw detections to existing slots using a greedy nearest-neighbour strategy.

        Each raw detection is assigned to the closest unmatched slot within
        MAX_DIST_PX. Detections with no suitable slot create a new one.
        Slots that received no match have their miss counter incremented.
        """
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
                # Refresh the matched slot with the new detection.
                used_slot_ids.add(best_slot["id"])
                best_slot["hit_count"]  = min(
                    best_slot["hit_count"] + 1, self.CONFIRM_FRAMES + 2)
                best_slot["miss_count"] = 0
                best_slot["last_center"] = (cx, cy)
                best_slot["last_obj"]    = obj
 
                # Append the new measurement to the smoothing buffer.
                self._push_dims(best_slot, obj)
 
            else:
                # No existing slot is close enough — initialise a new one.
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
 
        # Increment miss counters for unmatched slots.
        # hit_count is intentionally NOT decremented: a confirmed slot remains
        # visible throughout the ghost window, preventing flicker on frames
        # where the contour is momentarily absent due to reflection or motion.
        for slot in self._slots:
            if slot["id"] not in used_slot_ids:
                slot["miss_count"] += 1
 
    def _push_dims(self, slot: dict, obj):
        """Append the dimensional measurements from *obj* to the slot's smoothing buffer."""
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
        """Remove slots whose miss counter has exceeded the ghost frame threshold."""
        self._slots = [
            s for s in self._slots
            if s["miss_count"] <= self.GHOST_FRAMES
        ]
 
    def _get_stable_objects(self) -> list:
        """
        Return smoothed detections from all confirmed, non-expired slots.

        Dimensions are averaged over the slot's buffer before the object is
        returned, reducing per-frame measurement jitter.
        """
        stable = []
        for slot in self._slots:
            if slot["hit_count"] < self.CONFIRM_FRAMES:
                continue  # Not yet confirmed.
            if slot["miss_count"] > self.GHOST_FRAMES:
                continue  # Expired (belt-and-suspenders guard).
 
            obj = slot["last_obj"]
            # Apply moving average before returning the object.
            self._apply_smooth(obj, slot["dim_buffer"])
            stable.append(obj)
 
        # Preserve left-to-right ordering consistent with find_objects.
        stable.sort(key=lambda o: o.bbox[0])
        return stable
 
    @staticmethod
    def _apply_smooth(obj, buf: deque):
        """
        Apply the buffered moving average to *obj* in-place.

        The object is a per-frame snapshot, not the canonical instance stored
        in find_objects, so mutation here is safe and does not affect the
        detection pipeline.
        """
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

def _draw_tracker_status(roi_img, n_raw: int, n_stable: int):
    """
    Render a compact diagnostic indicator in the bottom-left corner of the ROI.

    Displays the raw detection count alongside the tracker-stabilised count.
    Green indicates a steady state (raw == stable); orange indicates that some
    detections are still in the confirmation window.
    """
    # Inline colour values avoid a dependency on the module-level C palette dict.
    color = (50, 220, 50) if n_raw == n_stable else (0, 165, 255)
    H = roi_img.shape[0]
    cv2.putText(roi_img, f"RAW={n_raw}  STABLE={n_stable}",
                (6, H-8), cv2.FONT_HERSHEY_SIMPLEX, 0.38, (0,0,0), 2, cv2.LINE_AA)
    cv2.putText(roi_img, f"RAW={n_raw}  STABLE={n_stable}",
                (6, H-8), cv2.FONT_HERSHEY_SIMPLEX, 0.38, color, 1, cv2.LINE_AA)

# =============================================================================
# RENDERING
# Functions that draw measurement annotations and status overlays onto
# the OpenCV display frame.
# =============================================================================
def _status_color(st):
    return C["good"] if st=="GOOD" else (C["ng"] if st=="NO GOOD" else C["warn"])

def render_object(img, obj: DetectedObject, idx: int, status: str, matched_name):
    col    = _status_color(status)
    sh_lbl = SHAPE_LABEL.get(obj.shape, obj.shape.upper())
    cv2.drawContours(img, [obj.contour], -1, C["teal"], 1)
    if obj.shape == "circle":
        cv2.circle(img, obj.center, int(obj.radius_px), col, 2, cv2.LINE_AA)
        cx,cy = obj.center; r = int(obj.radius_px)
        draw_dim_line(img, (cx-r,cy), (cx+r,cy), obj.diameter_mm, C["yellow"], 28)
        top_y = cy-r-14
    else:
        cv2.drawContours(img, [obj.rot_box], -1, col, 2)
        box = obj.rot_box
        sa = dist(box[0],box[1]); sb = dist(box[1],box[2])
        if sa>=sb: lp1,lp2=tuple(box[0]),tuple(box[1]); sp1,sp2=tuple(box[1]),tuple(box[2])
        else:      lp1,lp2=tuple(box[1]),tuple(box[2]); sp1,sp2=tuple(box[0]),tuple(box[1])
        draw_dim_line(img, lp1, lp2, obj.width_mm,  C["yellow"], 28)
        draw_dim_line(img, sp1, sp2, obj.height_mm, C["purple"], 28)
        top_y = obj.bbox[1]-14
    label(img, f"#{idx+1} {sh_lbl}  {obj.label_size}", (obj.bbox[0],top_y), 0.48, col, (20,20,20))
    st_txt = f"{status}  [{matched_name}]" if matched_name else status
    label(img, st_txt, (obj.bbox[0],top_y-20), 0.52, col, (20,20,20), 2)


# =============================================================================
# HUD PANELS
# Composites the information panel, measurement results table, and keyboard
# shortcut guide onto the display frame each tick.
# =============================================================================
def draw_info_panel(img, fps, obj_count, show_contour, show_roi,
                    thresh, ref_mgr: ReferenceManager, db_mgr: DatabaseManager,
                    ppm: float, tol: float):
    ov = img.copy()
    cv2.rectangle(ov,(8,8),(340,192),(10,10,10),-1)
    cv2.addWeighted(ov,0.75,img,0.25,0,img)
    cv2.rectangle(img,(8,8),(340,192),C["cyan"],1)
    db_st = "AKTIF" if db_mgr.enabled else "STUB"
    rows = [
        (f"FPS        : {fps:5.1f}",         C["green"] if fps>15 else C["yellow"]),
        (f"Objek      : {obj_count} terdeteksi", C["green"] if obj_count>0 else C["gray"]),
        (f"Skala      : {ppm:.2f} px/mm",     C["white"]),
        (f"Toleransi  : ±{tol} mm",           C["white"]),
        (f"Referensi  : {len(ref_mgr.refs)} profil",
         C["good"] if ref_mgr.refs else C["warn"]),
        (f"Database   : {db_st}",             C["good"] if db_mgr.enabled else C["warn"]),
        (f"Kontur     : {'ON' if show_contour else 'OFF'}",
         C["teal"] if show_contour else C["gray"]),
        (f"Thresh     : {thresh}   (+/- ubah)", C["gray"]),
    ]
    for i,(t,col) in enumerate(rows):
        cv2.putText(img,t,(16,32+i*20),FONT,0.43,col,1,cv2.LINE_AA)


def draw_result_panel(img, objects, results):
    if not objects: return
    H,W = img.shape[:2]; n=len(objects)
    ph=40+n*26+10; px=W-420; py=H-ph-14
    ov=img.copy()
    cv2.rectangle(ov,(px-10,py-10),(W-10,H-10),(10,10,10),-1)
    cv2.addWeighted(ov,0.70,img,0.30,0,img)
    cv2.rectangle(img,(px-10,py-10),(W-10,H-10),C["yellow"],1)
    label(img,f"HASIL PENGUKURAN ({n} objek)",(px,py+8),0.50,C["yellow"])
    for i,(obj,(st,mname,_)) in enumerate(zip(objects,results)):
        sh = SHAPE_LABEL.get(obj.shape,obj.shape)
        dim = f"Ø{obj.diameter_mm:.2f}mm" if obj.shape=="circle" else f"{obj.width_mm:.2f}×{obj.height_mm:.2f}mm"
        ref_txt = f" ← {mname}" if mname else ""
        sc = _status_color(st)
        label(img,f"#{i+1} {sh} {dim}",(px,py+34+i*26),0.42,C["cyan"])
        label(img,f"[{st}]{ref_txt}",(px+225,py+34+i*26),0.42,sc,(20,20,20))


def draw_controls(img):
    H,W = img.shape[:2]
    keys = ["[Q/ESC] Keluar","[D]     Deteksi Part","[V]     Save Referensi",
            "[S]     Screenshot","[R]     ROI on/off","[C]     Kontur on/off",
            "[P]     Debug view","[+/-]   Threshold"]
    for i,t in enumerate(keys):
        label(img,t,(W-210,H-14-i*18),0.37,C["gray"])


# =============================================================================
# ACTION: INSPECT PART  [keyboard: D]
# Triggered by the operator to evaluate the current stable detections,
# raise a visual warning for any NG parts, and persist results to disk
# and the database.
# =============================================================================
def action_deteksi_part(objects, results, roi_frame,
                        notif, warning, db_mgr, cfg):
    if not objects:
        notif.add("Tidak ada objek terdeteksi!", C["warn"]); return

    ng_list    = [(o,r) for o,r in zip(objects,results) if r[0]=="NO GOOD"]
    noref_list = [(o,r) for o,r in zip(objects,results) if r[0]=="NO REF"]
    good_list  = [(o,r) for o,r in zip(objects,results) if r[0]=="GOOD"]

    if ng_list:
        warning.trigger(len(ng_list))
        warning.set_duration(cfg["warning_duration"])
    elif noref_list:
        notif.add(f"{len(noref_list)} objek tanpa referensi — simpan dulu [V]", C["warn"], 4.0)

    dir_deteksi = base_path(cfg["dir_deteksi"])
    os.makedirs(dir_deteksi, exist_ok=True)
    ts = now_str()
    json_data = {
        "timestamp": ts, "pixel_per_mm": cfg["pixel_per_mm"],
        "tolerance_mm": cfg["tolerance_mm"],
        "summary": {"total":len(objects),"good":len(good_list),
                    "no_good":len(ng_list),"no_ref":len(noref_list)},
        "objects": []
    }
    for i,(obj,(st,mname,detail)) in enumerate(zip(objects,results)):
        e = obj.to_dict(); e.update({"id":i+1,"status":st,"matched_ref":mname,"match_detail":detail})
        json_data["objects"].append(e)

    json_path = os.path.join(dir_deteksi, f"deteksi_{ts}.json")
    img_path  = os.path.join(dir_deteksi, f"deteksi_{ts}.png")
    with open(json_path,"w") as f: json.dump(json_data,f,indent=2)
    cv2.imwrite(img_path, roi_frame)

    for i,(obj,(st,mname,detail)) in enumerate(zip(objects,results)):
        db_mgr.save_log(
            timestamp=now_iso(), id_part=f"{ts}_obj{i+1}",
            nilai_dimensi={"shape":obj.shape,"diameter_mm":obj.diameter_mm,
                           "width_mm":obj.width_mm,"height_mm":obj.height_mm,"area_px":obj.area_px},
            status=st, matched_ref=mname, image_path=img_path, shape=obj.shape)

    summary = f"✓ {len(good_list)} GOOD"
    if ng_list:    summary += f"  ✗ {len(ng_list)} NG"
    if noref_list: summary += f"  ? {len(noref_list)} NO REF"
    notif.add(f"Deteksi selesai — {summary}",
              C["good"] if not ng_list else C["warn"], 4.0)
    print(f"[DETEKSI] {json_path}")


# =============================================================================
# ACTION: SAVE REFERENCE PROFILE  [keyboard: V]
# Opens a Tkinter input dialog for the operator to name and persist the
# currently detected object as a dimensional reference profile.
# =============================================================================
from tkinter import simpledialog

def action_save_reference(objects, ref_mgr, notif, tol):
    """
    Display a Tkinter input dialog and save the detected object as a reference profile.

    The dialog is synchronous, which briefly pauses the OpenCV loop. This is
    intentional: the part must remain stationary while the operator enters a name,
    so no frames are missed during a meaningful inspection cycle.

    Parameters
    ----------
    objects : list[DetectedObject]
        The current list of stable detected objects. Exactly one must be present.
    ref_mgr : ReferenceManager
        The active reference manager instance.
    notif : Notification
        Notification system used to display feedback in the OpenCV window.
    tol : float
        Dimensional tolerance (mm) to associate with the new reference profile.
    """
    if not objects:
        notif.add("ERROR: Tidak ada objek terdeteksi!", C["ng"], 4.0); return
    if len(objects) > 1:
        notif.add(f"ERROR: {len(objects)} objek! Sisakan 1 saja.", C["ng"], 5.0); return

    # Create a hidden root window so the dialog appears without a blank Tk window.
    # The topmost flag ensures the dialog is not obscured by the OpenCV window.
    temp_root = tk.Tk()
    temp_root.withdraw()
    temp_root.attributes("-topmost", True)
    name = simpledialog.askstring(
        "Simpan Referensi",
        "Masukkan nama referensi (contoh: Gear Kecil A):",
        parent=temp_root)
    temp_root.destroy()

    if name and name.strip():
        ref_mgr.save_reference(objects[0], name.strip(), tol)
        notif.add(f"'{name.strip()}' disimpan: {objects[0].label_size}", C["good"], 5.0)
    else:
        notif.add("Batal menyimpan referensi.", C["warn"], 2.0)


def process_pending_reference(objects, ref_mgr, notif, tol):
    """
    No-op compatibility stub.

    The reference-saving workflow now uses a synchronous Tkinter dialog in
    ``action_save_reference``, so this function is no longer required.
    It is retained to avoid a NameError at the call site in ``main()``.
    """
    pass

# =============================================================================
# MAIN INSPECTION LOOP
# =============================================================================
def main(cfg: dict):
    """
    Run the OpenCV inspection loop.

    Captures frames from the configured camera, runs the preprocessing and
    contour detection pipeline, stabilises detections via ObjectTracker,
    compares measurements against stored reference profiles, and renders
    the annotated result to a named window each tick.

    Parameters
    ----------
    cfg : dict
        Validated runtime configuration produced by SettingsGUI.
    """
    WINDOW_NAME = "Capstone — Sistem Inspeksi Dimensi v7"
 
    ppm          = cfg["pixel_per_mm"]
    tol          = cfg["tolerance_mm"]
    roi          = cfg["roi_percent"]
    warn_dur     = cfg["warning_duration"]
    cam_src      = cfg["camera_source"]
    droidcam_fix = cfg["droidcam_fix"]
    dir_ss       = base_path(cfg["dir_screenshot"])
    ref_path     = base_path(cfg["file_reference"])
 
    print("=" * 62)
    print("  CAPSTONE — Sistem Inspeksi Dimensi Part Manufaktur v6")
    print("  Tim: Jagoan Mamah Papah | Universitas Brawijaya 2026")
    print("=" * 62)
    print(f"  Kamera    : {cam_src}")
    print(f"  Skala     : {ppm} px/mm")
    print(f"  Toleransi : ±{tol} mm")
    print(f"  Tracker   : CONFIRM={ObjectTracker.CONFIRM_FRAMES}fr "
          f"GHOST={ObjectTracker.GHOST_FRAMES}fr "
          f"SMOOTH={ObjectTracker.SMOOTH_FRAMES}fr")
    print()
 
    ref_mgr = ReferenceManager(ref_path)
    db_mgr  = DatabaseManager(cfg["db"])
    notif   = Notification()
    warning = WarningOverlay()
    tracker = ObjectTracker()
 
    print(f"  [CAM] Membuka: {cam_src}")
    cap = cv2.VideoCapture(cam_src)
    if isinstance(cam_src, int):
        cap.set(cv2.CAP_PROP_FRAME_WIDTH,  cfg["capture_width"])
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, cfg["capture_height"])
        cap.set(cv2.CAP_PROP_AUTOFOCUS, 0)
 
    if not cap.isOpened():
        print("\n  [ERROR] Kamera tidak bisa dibuka!")
        db_mgr.close(); return
 
    print(f"  [CAM] {int(cap.get(3))} × {int(cap.get(4))}")
    print("\n  D=Deteksi | V=Referensi | S=Screenshot | C=Kontur")
    print("  R=ROI | P=Debug | +/-=Threshold | Q=Keluar\n")
 
    os.makedirs(dir_ss, exist_ok=True)
    os.makedirs(base_path(cfg["dir_deteksi"]), exist_ok=True)
 
    show_roi     = True
    show_contour = True
    show_debug   = False
    thresh       = cfg["contour_thresh"]
    fps          = 0.0
    t_prev       = time.time()
    shot_n       = 0
 
    # raw_objects    — detections from the current frame (unfiltered)
    # stable_objects — tracker-confirmed detections used for display and action D
    # results        — comparison output for each stable object
    raw_objects    = []
    stable_objects = []
    results        = []
 
    while True:
        ret, raw = cap.read()
        if not ret:
            time.sleep(0.3)
            continue
 
        # DroidCam USB sometimes delivers frames in YUV format, causing a
        # solid-green image when interpreted as BGR. Detect and correct this.
        if droidcam_fix and raw is not None and raw.shape[2] == 3:
            bm = raw[:,:,0].mean()
            gm = raw[:,:,1].mean()
            rm = raw[:,:,2].mean()
            if gm > 150 and bm < 50 and rm < 50:
                try:
                    raw = cv2.cvtColor(raw, cv2.COLOR_YUV2BGR_YUYV)
                except Exception:
                    pass
 
        frame = raw.copy()
        H, W  = frame.shape[:2]
 
        rx1 = int(roi[0]*W); ry1 = int(roi[1]*H)
        rx2 = int(roi[2]*W); ry2 = int(roi[3]*H)
        roi_frame = frame[ry1:ry2, rx1:rx2].copy()
 
        # Preprocessing pipeline followed by contour detection.
        gray, blurred, enhanced = preprocess(roi_frame)
        binary = get_binary(enhanced, thresh)
 
        if show_contour:
            raw_objects    = find_objects(binary, cfg["contour_min_area"],
                                          ppm, cfg["min_feature_mm"])
            # Feed raw detections into the tracker; retrieve stabilised output.
            stable_objects = tracker.update(raw_objects)
        else:
            raw_objects    = []
            stable_objects = []
            tracker.reset()
 
        # Compare each stable detection against stored reference profiles.
        results = [ref_mgr.compare(obj, tol) for obj in stable_objects]
 
        process_pending_reference(stable_objects, ref_mgr, notif, tol)
 
        # Compose the annotated display frame.
        display     = frame.copy()
        roi_display = display[ry1:ry2, rx1:rx2]
 
        if show_contour:
            for i, (obj, (st, mname, _)) in enumerate(zip(stable_objects, results)):
                render_object(roi_display, obj, i, st, mname)
 
            # Diagnostic indicator: shows raw vs. stable detection counts.
            _draw_tracker_status(roi_display, len(raw_objects), len(stable_objects))
 
        draw_roi_box(display, (rx1, ry1, rx2, ry2), show_roi)
        draw_result_panel(display, stable_objects, results)
        draw_info_panel(display, fps, len(stable_objects),
                        show_contour, show_roi, thresh,
                        ref_mgr, db_mgr, ppm, tol)
        draw_controls(display)
        label(display,
              "CAPSTONE v6  |  Inspeksi Dimensi Part Manufaktur  |  Jagoan Mamah Papah",
              (W//2-285, H-10), 0.37, C["gray"])
 
        if show_debug:
            dh = H//4; dw = W//4
            for ig, ti, px_off in [
                (gray,     "Gray",   W-dw*3-15),
                (enhanced, "CLAHE",  W-dw*2-10),
                (binary,   "Binary", W-dw-5),
            ]:
                t_  = cv2.resize(ig, (dw, dh))
                tb  = cv2.cvtColor(t_, cv2.COLOR_GRAY2BGR)
                label(tb, ti, (4, 18), 0.45, C["yellow"])
                display[8:8+dh, px_off:px_off+dw] = tb
                cv2.rectangle(display, (px_off,8), (px_off+dw,8+dh), C["cyan"], 1)
 
        warning.draw(display, warn_dur)
        notif.draw(display)
 
        now    = time.time()
        fps    = 0.85*fps + 0.15*(1.0/max(now-t_prev, 1e-5))
        t_prev = now
 
        cv2.imshow(WINDOW_NAME, display)
        key = cv2.waitKey(1) & 0xFF
 
        if key in (ord('q'), 27):
            break
 
        elif key == ord('d'):
            # stable_objects is guaranteed non-empty during ghost frames, so
            # pressing D during a brief detection gap still works correctly.
            action_deteksi_part(stable_objects, results, roi_frame,
                                notif, warning, db_mgr, cfg)
 
        elif key == ord('v'):
            action_save_reference(stable_objects, ref_mgr, notif, tol)
 
        elif key == ord('s'):
            shot_n += 1
            fname = os.path.join(dir_ss, f"ss_{shot_n:04d}.png")
            cv2.imwrite(fname, display)
            notif.add(f"Screenshot: ss_{shot_n:04d}.png", C["cyan"], 2.0)
 
        elif key == ord('r'):
            show_roi = not show_roi
 
        elif key == ord('c'):
            show_contour = not show_contour
            tracker.reset()  # Clear all slots so stale data does not persist.
            notif.add(f"Kontur {'ON' if show_contour else 'OFF'}", C["white"], 1.5)
 
        elif key == ord('p'):
            show_debug = not show_debug
 
        elif key in (ord('+'), ord('=')):
            thresh = min(thresh+5, 250)
            tracker.reset()  # Clear all slots so stale data does not persist.
            notif.add(f"Threshold: {thresh}", C["white"], 1.0)

        elif key == ord('-'):
            thresh = max(thresh-5, 10)
            tracker.reset()  # Clear all slots so stale data does not persist.
            notif.add(f"Threshold: {thresh}", C["white"], 1.0)
 
    cap.release()
    cv2.destroyAllWindows()
    db_mgr.close()
    print("\n[INFO] Program selesai.")


# =============================================================================
# ENTRY POINT
# =============================================================================
if __name__ == "__main__":
    # 1. Load (or generate) config.json.
    cfg = load_config()

    # 2. Present the pre-flight settings window.
    gui = SettingsGUI(cfg)
    result = gui.run()

    # 3. If the operator confirmed, launch the OpenCV inspection loop.
    if result is not None:
        main(result)
    else:
        print("[INFO] Settings window closed — application terminated.")
