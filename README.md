# Sistem Inspeksi Dimensi Part Manufaktur
### Berbasis Computer Vision pada Lingkungan Terkontrol

**Capstone Project A.3 — Automated Dimensional Inspection**  
Fakultas Ilmu Komputer, Universitas Brawijaya — 2026

---

## Deskripsi

Sistem inspeksi otomatis yang mengukur dimensi komponen manufaktur secara real-time menggunakan kamera dan algoritma computer vision berbasis OpenCV. Dikembangkan sebagai solusi pengganti inspeksi manual (jangka sorong/mikrometer) di lini produksi **PT. Indonesia Epson Industry**.

Sistem berjalan sepenuhnya secara lokal (*edge computing*) tanpa ketergantungan pada koneksi internet, dan dapat dikompilasi menjadi file `.exe` untuk kemudahan penggunaan oleh operator di lantai produksi.

---

## Fitur Utama

| Fitur | Keterangan |
|---|---|
| **Deteksi Multi-Bentuk** | Lingkaran, Segitiga, Kotak, Persegi Panjang, Pentagon, Heksagon, Poligon |
| **Pengukuran Dimensi** | Konversi pixel → mm via konstanta kalibrasi yang dapat dikonfigurasi |
| **Multi-Referensi** | Simpan banyak profil referensi dengan nama bebas per jenis part |
| **Status GOOD / NO GOOD** | Perbandingan otomatis dengan toleransi ±mm yang dapat diatur |
| **Warning System** | Overlay merah berkedip saat terdeteksi part NG |
| **Object Tracker** | Stabilisasi deteksi antar frame — menghilangkan efek *flashing* pada permukaan metalik |
| **Settings GUI** | Antarmuka Tkinter untuk konfigurasi sebelum sistem berjalan |
| **Export JSON** | Setiap hasil deteksi disimpan sebagai file JSON + gambar crop |
| **Database PostgreSQL** | Logging terintegrasi (aktifkan di `config.json`) |
| **EXE-Ready** | Kompatibel dengan PyInstaller dan auto-py-to-exe |

---

## Teknologi

- **Python** 3.10+
- **OpenCV** — pemrosesan citra, deteksi kontur, rendering overlay
- **NumPy** — operasi matrix dan array
- **Tkinter** — GUI pengaturan (bawaan Python)
- **psycopg2** — koneksi PostgreSQL (opsional)

---

## Struktur Repository

```
├── main-programV7.py       # Program utama
├── config.json             # Parameter konfigurasi (di-generate otomatis)
├── referensi.json          # Profil referensi benda (di-generate otomatis)
├── requirements.txt        # Daftar dependensi Python
├── README.md               # Dokumentasi ini
├── .gitignore              # Mengecualikan file build dan output runtime
├── screenshots/            # Hasil screenshot operator (di-create otomatis)
└── deteksi_part/           # Hasil deteksi JSON + gambar crop (di-create otomatis)
```

---

## Instalasi & Menjalankan dari Source

### 1. Prasyarat

- Python 3.10 atau lebih baru
- Webcam USB, DroidCam (USB/WiFi), atau kamera IP

### 2. Clone repository

```bash
git clone https://github.com/ApricotSch/CapstoneA3-3-MainProgram.git
cd CapstoneA3-3-MainProgram
```

### 3. Buat virtual environment (disarankan)

```bash
python -m venv venv

# Windows
venv\Scripts\activate

# Linux / macOS
source venv/bin/activate
```

### 4. Install dependensi

```bash
pip install -r requirements.txt
```

Jika logging database PostgreSQL akan digunakan, install juga:

```bash
pip install psycopg2-binary
```

### 5. Jalankan program

```bash
python main-programV7.py
```

Window pengaturan (*Settings GUI*) akan muncul terlebih dahulu. Sesuaikan konfigurasi lalu klik **Save & Start**.

---

## Konfigurasi

Semua parameter sistem tersimpan di `config.json` dan dapat diubah melalui Settings GUI. Parameter utama:

| Parameter | Default | Keterangan |
|---|---|---|
| `camera_source` | `1` | Index kamera USB (`0`/`1`/`2`) atau URL stream (`http://IP:8080/video`) |
| `pixel_per_mm` | `9.28` | Konstanta kalibrasi skala — **wajib dikalibrasi ulang** jika jarak kamera berubah |
| `tolerance_mm` | `1.0` | Toleransi maksimum selisih dimensi untuk status GOOD (mm) |
| `contour_thresh` | `200` | Threshold binarisasi awal; dapat diubah real-time dengan `+` / `-` |
| `droidcam_fix` | `true` | Aktifkan jika menggunakan DroidCam USB dan layar menjadi hijau |

### Kalibrasi Skala

Letakkan benda referensi dengan dimensi yang diketahui (contoh: koin Rp 500 = diameter 27 mm) di tengah photobox, ambil screenshot, ukur jumlah pixel benda tersebut, lalu hitung:

```
pixel_per_mm = lebar_benda_dalam_pixel / lebar_nyata_mm
```

Masukkan nilai hasil kalkulasi ke field **Pixel per mm** di Settings GUI.

---

## Penggunaan oleh Operator

### Setup Awal (satu kali per jenis part)

1. Letakkan **satu** part master di tengah photobox
2. Atur threshold hingga deteksi stabil (gunakan `+` / `-`)
3. Tekan **`V`** — masukkan nama referensi di dialog yang muncul (contoh: `Gear Kecil A`)
4. Konfirmasi — profil tersimpan di `referensi.json`

### Sesi Inspeksi

1. Letakkan part yang akan diinspeksi di area inspeksi (ROI)
2. Tunggu bounding box dan status (`GOOD` / `NO GOOD` / `NO REF`) muncul
3. Tekan **`D`** untuk menyimpan hasil dan mengirim ke database
4. Perhatikan status — jika muncul overlay merah, pindahkan part ke wadah NG
5. Ganti dengan part berikutnya, ulangi dari langkah 1

### Referensi Cepat Keyboard

| Tombol | Fungsi |
|---|---|
| `D` | Deteksi & simpan hasil (JSON + gambar + database) |
| `V` | Simpan part saat ini sebagai profil referensi baru |
| `S` | Screenshot tampilan layar penuh |
| `R` | Tampilkan / sembunyikan kotak area inspeksi (ROI) |
| `C` | Aktifkan / nonaktifkan deteksi kontur |
| `P` | Debug view — tampilkan hasil preprocessing |
| `+` / `=` | Naikkan threshold binarisasi (+5) |
| `-` | Turunkan threshold binarisasi (−5) |
| `Q` / `ESC` | Keluar dari program |

---

## Interpretasi Status

| Status | Warna | Arti | Tindakan |
|---|---|---|---|
| `GOOD` | Hijau | Dimensi sesuai referensi (Δ ≤ toleransi) | Lanjutkan produksi |
| `NO GOOD` | Merah + overlay berkedip | Dimensi tidak sesuai referensi | Pindahkan ke wadah NG |
| `NO REF` | Oranye | Belum ada referensi untuk jenis part ini | Simpan referensi terlebih dahulu (`V`) |

---

## Integrasi Database PostgreSQL

Secara default database dinonaktifkan. Untuk mengaktifkan:

1. Pastikan PostgreSQL berjalan dan buat database:

```sql
CREATE DATABASE capstone_db;

\c capstone_db

CREATE TABLE IF NOT EXISTS inspeksi_log (
    id            SERIAL PRIMARY KEY,
    timestamp     TIMESTAMPTZ NOT NULL,
    id_part       VARCHAR(64),
    shape         VARCHAR(32),
    nilai_dimensi JSONB,
    status        VARCHAR(16),
    matched_ref   VARCHAR(128),
    image_path    VARCHAR(256)
);
```

2. Install psycopg2:

```bash
pip install psycopg2-binary
```

3. Isi kredensial dan centang **Aktifkan Database** di Settings GUI, lalu klik **Test Koneksi DB** untuk memverifikasi sebelum memulai.

---

## Kompilasi ke EXE

Program siap dikompilasi menggunakan **auto-py-to-exe**:

```bash
pip install auto-py-to-exe
auto-py-to-exe
```

Pengaturan yang disarankan:
- **Script**: pilih `main-programV7.py`
- **Onefile / One Directory**: pilih **One Directory** (startup lebih cepat)
- **Console Window**: biarkan muncul (membantu debugging)
- **Additional Files**: tambahkan `config.json` dan `referensi.json` agar terbundle

Distribusikan seluruh folder output (termasuk `_internal/`) sebagai satu zip. Upload zip tersebut ke **GitHub Releases**, bukan ke dalam commit.

---

## Anggota Tim

| Nama | NIM | Program Studi | Peran |
|---|---|---|---|
| Abdul Fikri Zaki | 235150400111007 | Sistem Informasi | Project Manager, System Analyst, QA |
| Dhio Rahmansyah | 235150301111013 | Teknik Komputer | Computer Vision Developer |
| Muhammad Farkhan Fadillah | 235150300111016 | Teknik Komputer | Hardware & Edge System Integrator |
| A. Issadurrofiq Jaya Utama | 235150700111023 | Teknologi Informasi | Backend & Database Engineer |
| Adi Baskara Husodo | 235150300111050 | Teknik Komputer | Station & Optics Designer |
| A. Wildan Hula Aufa | 235150700111013 | Teknologi Informasi | Frontend Developer & System Ops |

---

## Lisensi

Proyek ini dikembangkan untuk keperluan akademik Capstone Project Universitas Brawijaya 2026.
