# 🎥 CV Program Quick Start Guide

## 📦 Installation

### 1. Install Python Dependencies

```bash
cd epsight-metric-mainprogram
pip install -r Requirements.txt
```

### 2. Configure Connection

Edit `config.json`:

```json
{
  "api": {
    "enabled": true,
    "api_url": "https://epsight-metric-backend-production.up.railway.app",
    "part_id": 1,
    "timeout": 10
  }
}
```

---

## 🚀 Running the Program

### Start CV Program

```bash
python Main-ProgramV7.py
```

### Expected Output

```
[CFG] Konfigurasi dimuat dari 'config.json'
[API] Client aktif -> https://epsight-metric-backend-production.up.railway.app
[API] Sesi disinkronkan: SES-1234567890-1 | Operator: John Doe
[API] Command listener connected
[CAM] Membuka: 0
[CAM] 1920 × 1080
```

✅ **CV Online** — Jika semua log di atas muncul, CV sudah terhubung ke dashboard

---

## 🎮 Operating Modes

### Mode 1: Online (Dashboard Trigger)

**Use Case:** Operator di dashboard mengontrol kapan inspect

**Flow:**
1. Operator login di dashboard → start session
2. Operator klik tombol **INSPECT** di dashboard
3. CV program otomatis capture & detect
4. Hasil langsung muncul di dashboard

**CV Program Log:**
```
[API] Trigger inspection dari dashboard
[MAIN] Inspection triggered by dashboard
[API] Inspeksi terkirim: OK | Circle | session=SES-...
```

---

### Mode 2: Offline (Keyboard Trigger)

**Use Case:** CV program standalone tanpa dashboard

**Flow:**
1. Jalankan CV program
2. Letakkan part di depan kamera
3. Tekan **D** di keyboard
4. Hasil disimpan lokal (JSON + SQLite)

**CV Program Log:**
```
[DETEKSI] deteksi_part/deteksi_20240120_143022.json
[API][STUB] OK | Circle | ref=Gear Kecil A
```

---

## ⌨️ Keyboard Controls

| Key | Action |
|-----|--------|
| **D** | Deteksi part (offline mode) |
| **V** | Simpan referensi baru |
| **S** | Screenshot |
| **C** | Toggle contour detection |
| **R** | Toggle ROI box |
| **P** | Toggle debug view |
| **+/-** | Adjust threshold |
| **Q** | Quit program |

---

## 🔍 Status Indicators

### Terminal Logs

✅ **Good Connection:**
```
[API] Sesi disinkronkan: SES-... | Operator: John Doe
[API] Command listener connected
```

❌ **Connection Failed:**
```
[API] Koneksi gagal - BE tidak bisa dijangkau
[API] Command listener error: ...
```

### Dashboard Badge

- 🟢 **CV Online** — CV terhubung, terima update dalam 60 detik terakhir
- 🔴 **CV Offline** — CV tidak terhubung atau tidak ada update > 60 detik

---

## 🐛 Troubleshooting

### Problem: "requests tidak terinstall"

```bash
pip install requests
```

### Problem: "Kamera tidak bisa dibuka"

1. Cek kamera terhubung
2. Ubah `camera_source` di `config.json`:
   ```json
   "camera_source": 1  // atau 2, 3, dst
   ```

### Problem: "Koneksi gagal - BE tidak bisa dijangkau"

1. Cek koneksi internet
2. Test manual:
   ```bash
   curl https://epsight-metric-backend-production.up.railway.app/health
   ```
3. Cek `api.api_url` di `config.json` (harus HTTPS)

### Problem: Dashboard tidak terima hasil CV

1. Pastikan log `[API] Command listener connected` muncul
2. Pastikan operator sudah start session di dashboard
3. Cek badge "CV Online" di dashboard (harus hijau)

---

## 📊 Performance Tips

### Optimize Frame Rate

Edit `config.json`:

```json
{
  "capture_width": 1280,   // turunkan dari 1920
  "capture_height": 720,   // turunkan dari 1080
  "contour_min_area": 2000 // naikkan untuk skip objek kecil
}
```

### Reduce Network Latency

```json
{
  "api": {
    "timeout": 5  // turunkan jika koneksi stabil
  }
}
```

---

## 🔄 Restart Procedure

### Normal Restart

1. Tekan **Q** untuk quit
2. Jalankan ulang: `python Main-ProgramV7.py`

### Force Restart (Hang)

1. **Windows:** `Ctrl+C` di terminal
2. **Linux/Mac:** `Ctrl+C` atau `killall python`

---

## 📝 Daily Checklist

### Before Starting Work

- [ ] Cek koneksi internet
- [ ] Cek kamera terhubung
- [ ] Jalankan CV program
- [ ] Pastikan log `[API] Command listener connected` muncul
- [ ] Buka dashboard → start session
- [ ] Pastikan badge "CV Online" hijau

### During Work

- [ ] Monitor terminal untuk error logs
- [ ] Jika "CV Offline" → restart CV program
- [ ] Jika hasil tidak akurat → adjust threshold (+/-)

### After Work

- [ ] Stop session di dashboard
- [ ] Tekan **Q** untuk quit CV program
- [ ] Backup file `deteksi_part/*.json` (optional)

---

## 🎯 Best Practices

1. **Lighting:** Pastikan pencahayaan konsisten
2. **Background:** Gunakan background kontras (putih/hitam)
3. **Distance:** Jaga jarak kamera ke part konsisten
4. **Calibration:** Kalibrasi `pixel_per_mm` setiap ganti kamera/jarak
5. **Network:** Gunakan koneksi internet stabil (WiFi/LAN)

---

## 📞 Support

Jika ada masalah:
1. Screenshot error di terminal
2. Cek log di `deteksi_part/` folder
3. Contact: [your-email@example.com]

---

**Last Updated:** 2024-01-XX
**Version:** 1.0.0
