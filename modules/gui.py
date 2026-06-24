"""
Modul Settings GUI (Tkinter)
Sistem Inspeksi Dimensi Part Manufaktur
"""

import tkinter as tk
from tkinter import ttk, messagebox
from modules.config import save_config, DEFAULT_CONFIG
from modules.database import PSYCOPG2_AVAILABLE

# Try importing psycopg2 for settings testing if available
if PSYCOPG2_AVAILABLE:
    import psycopg2


class SettingsGUI:
    """
    Settings window pra-inspeksi yang dibangun dengan Tkinter.
    Menampilkan form parameter yang dapat diedit oleh operator sebelum loop inspeksi utama berjalan.
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

    def _build(self):
        self.root = tk.Tk()
        self.root.title("Capstone — Sistem Inspeksi Dimensi v7  |  Settings")
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
        if cfg is None:
            return

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
        self.var_roi_x1.set(str(roi[0]))
        self.var_roi_y1.set(str(roi[1]))
        self.var_roi_x2.set(str(roi[2]))
        self.var_roi_y2.set(str(roi[3]))
        db = d["db"]
        self.var_db_enabled.set(bool(db["enabled"]))
        self.var_db_host.set(db["host"])
        self.var_db_port.set(str(db["port"]))
        self.var_db_name.set(db["dbname"])
        self.var_db_user.set(db["user"])
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
