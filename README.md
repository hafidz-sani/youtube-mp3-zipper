# YouTube → MP3 Zipper

Aplikasi Streamlit untuk mengunduh audio YouTube menjadi MP3 (hingga 320 kbps) dari URL video dan/atau playlist, menyematkan thumbnail sebagai album art, lalu mengemas hasilnya ke dalam file ZIP — gabungan tunggal atau per playlist. Mendukung input teks/berkas, pengaturan folder output, serta opsi lokasi FFmpeg.

## Fitur
- Unduh video YouTube ke MP3: 96–320 kbps (default 320).
- Embed thumbnail sebagai album art + metadata dasar.
- Mode ZIP: satu ZIP gabungan atau ZIP terpisah per playlist.
- Input URL via teks atau unggah `urls.txt` (1 URL per baris).
- Batas jumlah video per playlist (0 = tanpa batas).
- Pengaturan folder output sementara (default `out_mp3/`).
- Opsi lokasi `ffmpeg` kustom jika tidak ada di PATH.
- Tabel progres dan ukuran file per video.
 - Penamaan file: "Artis - Judul.mp3" dengan tag ID3 `artist` dan `title` diisi.

## Prasyarat
- Python 3.9+ (disarankan 3.10/3.11).
- FFmpeg terinstal di sistem (diperlukan oleh `yt-dlp` untuk konversi ke MP3).

Instal FFmpeg (pilih salah satu sesuai OS):
- macOS: `brew install ffmpeg`
- Ubuntu/Debian: `sudo apt-get update && sudo apt-get install -y ffmpeg`
- Fedora: `sudo dnf install -y ffmpeg`
- Windows (Chocolatey): `choco install ffmpeg`
- Windows (manual): unduh dari https://www.gyan.dev/ffmpeg/builds/ lalu tambahkan folder `bin` ke PATH atau isi kolom "Lokasi FFmpeg" di aplikasi.

## Instalasi
1) Klon repo dan masuk ke foldernya
```
git clone <url-repo-anda>
cd yt-mp3-zipper
```

2) (Opsional) Buat dan aktifkan virtual environment
```
python -m venv .venv
# macOS/Linux
source .venv/bin/activate
# Windows (PowerShell)
.venv\Scripts\Activate.ps1
```

3) Instal dependensi Python
```
pip install -r requirements.txt
```

4) Jalankan aplikasi
```
streamlit run app.py
```

Streamlit akan menampilkan URL lokal (mis. http://localhost:8501). Buka di browser.

## Cara Pakai
1) Di panel kiri (Sidebar), atur:
   - Bitrate MP3 (kbps)
   - Opsi "Sertakan thumbnail sebagai album art"
   - Lokasi FFmpeg (kosongkan jika FFmpeg sudah ada di PATH)
   - Folder sementara output MP3 (default: `out_mp3`)
   - Mode ZIP: "Gabungkan semua (1 ZIP)" atau "Satu ZIP per playlist"
   - Batas video per playlist (0 = tanpa batas)
   - Nama file ZIP (untuk mode gabungan)

2) Masukkan URL video pada bagian "1) Masukkan daftar URL Video". Anda bisa:
   - Menempel langsung ke textarea (1 URL per baris; baris diawali `#` akan diabaikan), atau
   - Mengunggah berkas `urls.txt` (isi: 1 URL per baris).

3) (Opsional) Masukkan URL playlist pada bagian "1b) Masukkan URL Playlist". Aplikasi akan mengekstrak video di dalamnya (terbatas jika Anda set limit).

4) Klik tombol "Mulai Download & Buat ZIP". Proses akan:
   - Mengunduh audio, mengonversi ke MP3, menempelkan thumbnail (jika dipilih).
   - Menamai file sebagai "Artis - Judul.mp3" (menghindari bentrok nama otomatis dengan suffix (n)).
   - Menampilkan tabel status, judul, ukuran, dan nama file.
   - Mengemas hasil menjadi ZIP sesuai mode yang dipilih.

5) Unduh hasil ZIP pada bagian "3) Unduh ZIP". Setelah unduhan, aplikasi otomatis membersihkan isi folder sementara `out_mp3/` (foldernya tetap ada).

## Tips & Pemecahan Masalah
- FFmpeg tidak ditemukan: isi kolom "Lokasi FFmpeg" (contoh Windows: `C:\\ffmpeg\\bin`) atau tambahkan ke PATH.
- Gagal unduh/konversi: pastikan koneksi internet stabil dan URL valid. Coba ulang.
- Playlist besar: gunakan "Batas video per playlist" untuk mempercepat pengujian.
- Penamaan file: aplikasi menambahkan ID video agar unik, dan menormalisasi judul.

## Catatan
- Folder output sementara default adalah `out_mp3/` (sudah di-`.gitignore`).
- Aplikasi hanya menyimpan file sementara untuk dikemas, lalu dibersihkan otomatis setelah unduhan ZIP.

## Disclaimer
Aplikasi ini ditujukan untuk penggunaan pribadi/pendidikan. Patuhilah syarat layanan (ToS) dan hukum hak cipta yang berlaku di wilayah Anda. Anda bertanggung jawab atas penggunaan Anda sendiri.
