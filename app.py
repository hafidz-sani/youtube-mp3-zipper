import io
import os
import re
import zipfile
import tempfile
import shutil
from datetime import datetime
from typing import List, Optional, Dict, Any, Tuple

import streamlit as st
from yt_dlp import YoutubeDL
from yt_dlp.utils import DownloadError
from mutagen.id3 import ID3, ID3NoHeaderError, TPE1, TIT2


# =========================
# Utilities
# =========================
def parse_urls(text: str) -> List[str]:
    lines = [ln.strip() for ln in (text or "").splitlines()]
    urls = [ln for ln in lines if ln and not ln.startswith("#")]
    seen, out = set(), []
    for u in urls:
        if u not in seen:
            out.append(u); seen.add(u)
    return out


def slugify(name: str, maxlen: int = 80) -> str:
    name = re.sub(r"[^\w\s-]", "", name, flags=re.UNICODE).strip()
    name = re.sub(r"[\s_-]+", "_", name)
    return (name[:maxlen]).strip("_") or "untitled"


def human_filename(text: str, maxlen: int = 120) -> str:
    r"""Sanitasi nama file agar tetap 'ramah manusia' (spasi & tanda minus dipertahankan).
    Menghapus karakter terlarang Windows: <>:"/\|?* dan merapikan spasi.
    """
    if not text:
        return "untitled"
    text = re.sub(r'[<>:"/\\|?*]', '', text)
    text = re.sub(r"\s+", " ", text).strip(" .-_")
    return (text or "untitled")[:maxlen]


def compute_artist_title(info: Dict[str, Any]) -> Tuple[str, str]:
    """Dapatkan (artist, title) dari metadata dengan fallback yang masuk akal."""
    artist = info.get("artist") or info.get("uploader") or info.get("channel") or "Unknown Artist"
    title = info.get("track") or info.get("alt_title") or info.get("title") or "Unknown Title"
    return human_filename(artist, 80), human_filename(title, 120)


def set_id3_basic(file_path: str, artist: str, title: str) -> None:
    """Set metadata ID3 dasar (artist & title) tanpa mengganggu tag lain (thumbnail dsb)."""
    try:
        try:
            tags = ID3(file_path)
        except ID3NoHeaderError:
            tags = ID3()
        # Ganti nilai agar tidak duplikat
        tags.setall('TPE1', [TPE1(encoding=3, text=artist)])
        tags.setall('TIT2', [TIT2(encoding=3, text=title)])
        tags.save(file_path)
    except Exception:
        # Jangan gagalkan proses hanya karena penulisan tag gagal
        pass


def ensure_writable_output_dir(path: str) -> Tuple[str, Optional[str]]:
    """Pastikan folder output bisa ditulis. Jika gagal, fallback ke /tmp/out_mp3.
    Mengembalikan (final_path, note_message_or_None).
    """
    try:
        os.makedirs(path, exist_ok=True)
        testfile = os.path.join(path, ".write_test")
        with open(testfile, "w", encoding="utf-8") as f:
            f.write("ok")
        os.remove(testfile)
        return path, None
    except Exception as e:
        fallback = os.path.join(tempfile.gettempdir(), "out_mp3")
        try:
            os.makedirs(fallback, exist_ok=True)
        except Exception:
            pass
        return fallback, f"Folder '{path}' tidak bisa ditulis (\"{e}\"). Menggunakan '{fallback}'."


def make_ydl_opts(output_dir: str,
                  bitrate_kbps: int,
                  embed_thumb: bool,
                  ffmpeg_location: Optional[str]) -> Dict[str, Any]:
    outtmpl = os.path.join(output_dir, "%(title).180B - %(id)s.%(ext)s")
    pp = [
        {"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": str(bitrate_kbps)},
        {"key": "FFmpegMetadata"},
    ]
    if embed_thumb:
        pp.insert(1, {"key": "EmbedThumbnail"})
    opts = {
        "format": "bestaudio/best",
        "outtmpl": outtmpl,
        "noplaylist": True,          # kita expand playlist manual; jadi tetap True
        "ignoreerrors": False,       # biar error nyata terangkat (lebih mudah debug)
        "postprocessors": pp,
        "writethumbnail": embed_thumb,
        "quiet": True,
        "no_warnings": True,
        "prefer_ffmpeg": True,
        "geo_bypass": True,
    }
    if ffmpeg_location:
        opts["ffmpeg_location"] = ffmpeg_location
    return opts


def mp3_path_from_prepared(prepared_filename: str) -> str:
    base, _ = os.path.splitext(prepared_filename)
    return base + ".mp3"


def download_one(url: str, output_dir: str, ydl_opts: Dict[str, Any]) -> Dict[str, Any]:
    os.makedirs(output_dir, exist_ok=True)
    rec = {"url": url, "title": None, "id": None, "status": "pending", "path": None, "error": None, "filesize_mb": None}
    try:
        with YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            if not info:
                # Coba fallback extractor args (mis. client Android) + header UA
                fallback_opts = dict(ydl_opts)
                # copy list agar tidak termodifikasi silang
                if 'postprocessors' in fallback_opts and isinstance(fallback_opts['postprocessors'], list):
                    fallback_opts['postprocessors'] = list(fallback_opts['postprocessors'])
                fallback_opts['extractor_args'] = {
                    'youtube': {
                        'player_client': ['android', 'android_music', 'web']
                    }
                }
                fallback_opts['http_headers'] = {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36'
                }
                try:
                    with YoutubeDL(fallback_opts) as y2:
                        info = y2.extract_info(url, download=True)
                except Exception as e2:
                    rec["status"] = "failed"; rec["error"] = f"Fallback extractor gagal: {e2}"; return rec
                if not info:
                    rec["status"] = "failed"; rec["error"] = "Tidak dapat mengambil metadata (fallback juga gagal)."; return rec
            if "entries" in info and info["entries"]:
                info = info["entries"][0]

            rec["title"] = info.get("title"); rec["id"] = info.get("id")
            prepared = ydl.prepare_filename(info)
            mp3_path = mp3_path_from_prepared(prepared)

            if not os.path.exists(mp3_path):
                vid = info.get("id", "")
                for name in os.listdir(output_dir):
                    if name.endswith(".mp3") and name.endswith(f"{vid}.mp3"):
                        mp3_path = os.path.join(output_dir, name); break

            if os.path.exists(mp3_path):
                # Setelah file jadi, ubah nama menjadi "Artist - Title.mp3" dan set metadata dasar
                artist_name, title_name = compute_artist_title(info)
                target_base = human_filename(f"{artist_name} - {title_name}", 180)
                target_path = os.path.join(output_dir, f"{target_base}.mp3")
                final_path = mp3_path
                try:
                    if os.path.abspath(mp3_path) != os.path.abspath(target_path):
                        # Hindari tabrakan nama: tambah suffix (1), (2), ... bila perlu
                        if os.path.exists(target_path):
                            n = 1
                            while True:
                                candidate = os.path.join(output_dir, f"{target_base} ({n}).mp3")
                                if not os.path.exists(candidate):
                                    target_path = candidate
                                    break
                                n += 1
                        os.replace(mp3_path, target_path)
                        final_path = target_path
                except Exception:
                    # Jika rename gagal, tetap gunakan mp3_path
                    final_path = mp3_path

                # Tulis metadata dasar (artist & title) untuk memudahkan pengelompokan
                set_id3_basic(final_path, artist_name, title_name)

                rec["status"] = "ok"; rec["path"] = final_path
                try: rec["filesize_mb"] = round(os.path.getsize(final_path)/(1024*1024), 2)
                except Exception: pass
            else:
                rec["status"] = "failed"; rec["error"] = "File MP3 tidak ditemukan setelah konversi."
    except DownloadError as e:
        rec["status"] = "failed"; rec["error"] = f"DownloadError: {e}"
    except Exception as e:
        rec["status"] = "failed"; rec["error"] = f"Error: {e}"
    return rec


def make_zip_bytes(file_paths: List[str]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for p in file_paths:
            if p and os.path.exists(p):
                zf.write(p, arcname=os.path.basename(p))
    buf.seek(0)
    return buf.read()


def cleanup_folder(folder: str) -> None:
    """Hapus semua isi folder (file & subfolder) tanpa menghapus foldernya."""
    try:
        if not os.path.isdir(folder):
            return
        for name in os.listdir(folder):
            path = os.path.join(folder, name)
            try:
                if os.path.isfile(path) or os.path.islink(path):
                    os.remove(path)
                elif os.path.isdir(path):
                    shutil.rmtree(path, ignore_errors=True)
            except Exception:
                # Abaikan error per-file agar cleanup tetap lanjut
                pass
    except Exception:
        pass


# ---------- Playlist helpers ----------
def expand_single_playlist(url: str, limit: Optional[int] = None) -> Tuple[str, List[str]]:
    """
    Mengambil judul playlist & daftar URL video. Tidak mengunduh media.
    """
    opts = {
        "quiet": True,
        "no_warnings": True,
        "extract_flat": True,      # ambil data daftar saja
        "skip_download": True,
        "noplaylist": False,       # izinkan yt-dlp menganggap ini playlist
    }
    title = "Playlist"
    urls: List[str] = []
    with YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=False)
        if not info:
            return title, urls
        title = info.get("title") or title
        entries = info.get("entries") or []
        for e in entries[:limit] if limit else entries:
            # coba dapatkan URL penuh; jika tidak ada, bentuk dari id (YouTube)
            if isinstance(e, dict):
                if e.get("url") and e["url"].startswith("http"):
                    urls.append(e["url"])
                elif e.get("webpage_url"):
                    urls.append(e["webpage_url"])
                elif e.get("id"):
                    urls.append(f"https://www.youtube.com/watch?v={e['id']}")
    return title, urls


def expand_playlists(pl_urls: List[str], per_playlist_limit: Optional[int] = None):
    """
    Kembalikan:
      - mapping video_url -> nama_playlist
      - ringkasan [(judul_playlist, jumlah_video, url_playlist)]
    """
    url_to_group: Dict[str, str] = {}
    summary = []
    for purl in pl_urls:
        try:
            ptitle, vurls = expand_single_playlist(purl, per_playlist_limit)
            cnt = 0
            for vu in vurls:
                if vu not in url_to_group:
                    url_to_group[vu] = ptitle
                    cnt += 1
            summary.append((ptitle, cnt, purl))
        except Exception as e:
            summary.append((f"Gagal baca playlist ({purl})", 0, purl))
    return url_to_group, summary


# =========================
# Streamlit UI
# =========================
st.set_page_config(page_title="YouTube → MP3 Zipper", page_icon="🎵", layout="wide")
st.title("🎵 YouTube → MP3 Zipper (MP3 320 kbps)")
st.caption("Masukkan URL video dan/atau playlist YouTube → unduh MP3 → buat ZIP.")

with st.sidebar:
    st.header("⚙️ Pengaturan")
    bitrate = st.slider("Bitrate MP3 (kbps)", 96, 320, 320, 32)
    embed_thumb = st.checkbox("Sertakan thumbnail sebagai album art", value=True)
    ffmpeg_loc = st.text_input("Lokasi FFmpeg (opsional)", value="", placeholder="/usr/bin/ffmpeg atau C:\\ffmpeg\\bin")
    output_dir = st.text_input("Folder sementara output MP3", value="out_mp3")

    zip_mode = st.radio("Mode ZIP", ["Gabungkan semua (1 ZIP)", "Satu ZIP per playlist"], index=0)
    per_playlist_limit = st.number_input("Batas video per playlist (0 = tanpa batas)", min_value=0, max_value=5000, value=0, step=10)
    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    default_zip = f"mp3_bundle_{ts}.zip"
    zip_name_input = st.text_input("Nama file ZIP (untuk mode gabungan)", value=default_zip)

st.subheader("1) Masukkan daftar URL Video")
c1, c2 = st.columns(2)
with c1:
    text_input = st.text_area(
        "Tempel URL video (satu per baris). Baris diawali `#` diabaikan.",
        height=150,
        placeholder="https://www.youtube.com/watch?v=AAAAAAAAAAA\nhttps://www.youtube.com/watch?v=BBBBBBBBBBB",
    )
with c2:
    file_up = st.file_uploader("Atau unggah file `urls.txt` (URL video, 1 per baris)", type=["txt"])

urls_from_text = parse_urls(text_input)
urls_from_file = []
if file_up is not None:
    try:
        content = file_up.read().decode("utf-8", errors="ignore")
        urls_from_file = parse_urls(content)
    except Exception as e:
        st.error(f"Gagal baca file upload: {e}")

st.subheader("1b) Masukkan URL Playlist (opsional)")
playlist_text = st.text_area(
    "Tempel URL playlist (satu per baris).",
    height=120,
    placeholder="https://www.youtube.com/playlist?list=XXXXXXXXXXXX\nhttps://www.youtube.com/playlist?list=YYYYYYYYYYYY",
)
playlist_urls = parse_urls(playlist_text)

# Ekspansi playlist → daftar video
limit = None if per_playlist_limit == 0 else int(per_playlist_limit)
url_to_group, playlist_summary = ({}, [])
if playlist_urls:
    with st.status("Mengekstrak daftar video dari playlist…", expanded=False) as status:
        url_to_group, playlist_summary = expand_playlists(playlist_urls, limit)
        status.update(label="Playlist diekstrak.", state="complete")

# Gabungkan semua sumber URL video
all_video_urls = []
seen = set()
for u in urls_from_text + urls_from_file + list(url_to_group.keys()):
    if u not in seen:
        all_video_urls.append(u); seen.add(u)

# Info ringkas
st.write(f"🎯 Ditemukan **{len(all_video_urls)}** video untuk diproses.")
if playlist_summary:
    st.markdown("**Ringkasan Playlist:**")
    for title, count, purl in playlist_summary:
        st.write(f"- {title} → {count} video")

st.subheader("2) Proses unduh & konversi")
start = st.button("Mulai Download & Buat ZIP", type="primary", disabled=(len(all_video_urls) == 0))

if start:
    st.info("Memulai proses. Jangan tutup tab sampai selesai.")
    progress = st.progress(0)
    table_area = st.empty()
    results = []

    # Pastikan folder output bisa ditulis; fallback ke /tmp bila perlu
    out_dir_effective, out_note = ensure_writable_output_dir(output_dir)
    if out_note:
        st.warning(out_note)

    # Deteksi otomatis ffmpeg jika kolom kosong
    ffmpeg_auto = ffmpeg_loc.strip() or shutil.which("ffmpeg") or None

    ydl_opts = make_ydl_opts(
        output_dir=out_dir_effective,
        bitrate_kbps=int(bitrate),
        embed_thumb=bool(embed_thumb),
        ffmpeg_location=ffmpeg_auto,
    )

    # Grup untuk mode 'Satu ZIP per playlist'
    grouped_paths: Dict[str, List[str]] = {}
    ungrouped_paths: List[str] = []

    ok_paths: List[str] = []
    total = len(all_video_urls)

    for idx, url in enumerate(all_video_urls, start=1):
        rec = download_one(url, out_dir_effective, ydl_opts)
        results.append(rec)

        if rec.get("status") == "ok" and rec.get("path"):
            ok_paths.append(rec["path"])
            group = url_to_group.get(url)  # None jika bukan dari playlist
            if group:
                grouped_paths.setdefault(group, []).append(rec["path"])
            else:
                ungrouped_paths.append(rec["path"])

        # tampilkan tabel ringkas
        rows = [{
            "No": i + 1,
            "Judul": r.get("title") or "-",
            "Status": r.get("status"),
            "Ukuran (MB)": r.get("filesize_mb"),
            "File": os.path.basename(r.get("path")) if r.get("path") else "-",
            "Error": (r.get("error") or "").splitlines()[0][:120] if r.get("status") != "ok" else "",
        } for i, r in enumerate(results)]
        table_area.dataframe(rows, hide_index=True, use_container_width=True)
        progress.progress(int(idx * 100 / max(total, 1)))

    if not ok_paths:
        st.error("Tidak ada MP3 yang berhasil dibuat. Cek URL/FFmpeg/Koneksi.")
        # Reset state hasil
        st.session_state.pop("zip_state", None)
        # Tampilkan rincian error agar mudah diagnosa
        failed = [r for r in results if r.get("status") != "ok"]
        if failed:
            with st.expander("Detail error (diagnostik)", expanded=False):
                for i, r in enumerate(failed, 1):
                    st.write(f"{i}. URL: {r.get('url')}")
                    st.code(r.get("error") or "(tidak ada pesan)")
    else:
        st.success(f"Berhasil membuat {len(ok_paths)} file MP3.")

        # Siapkan state untuk tombol unduh & pembersihan setelah unduh
        ts_now = datetime.now().strftime('%Y%m%d_%H%M%S')
        zip_state = {
            "mode": "gabungan" if zip_mode.startswith("Gabungkan") else "per_playlist",
            "output_dir": out_dir_effective,
            "cleaned": False,
        }

        if zip_state["mode"] == "gabungan":
            try:
                st.write("Mengemas semua file menjadi satu ZIP…")
                zip_bytes = make_zip_bytes(ok_paths)
                zip_name = zip_name_input if zip_name_input.endswith(".zip") else (zip_name_input + ".zip")
                zip_state.update({
                    "combined_bytes": zip_bytes,
                    "combined_name": zip_name,
                })
                st.info(f"File MP3 sementara tersimpan di folder: `{os.path.abspath(out_dir_effective)}`")
            except Exception as e:
                st.error(f"Gagal membuat ZIP: {e}")
                st.session_state.pop("zip_state", None)
                zip_state = None
        else:
            st.write("Mengemas ZIP per playlist…")
            group_zips = {}
            # Buat ZIP untuk setiap playlist
            for group_title, paths in grouped_paths.items():
                if not paths:
                    continue
                try:
                    zbytes = make_zip_bytes(paths)
                    fname = f"playlist_{slugify(group_title)}_{ts_now}.zip"
                    group_zips[group_title] = {"bytes": zbytes, "name": fname}
                except Exception as e:
                    st.error(f"Gagal ZIP untuk playlist '{group_title}': {e}")
            # Buat ZIP untuk 'Lainnya' (video yang bukan dari playlist)
            if ungrouped_paths:
                try:
                    zbytes = make_zip_bytes(ungrouped_paths)
                    fname = f"Lainnya_{ts_now}.zip"
                    group_zips["Lainnya"] = {"bytes": zbytes, "name": fname}
                except Exception as e:
                    st.error(f"Gagal ZIP untuk 'Lainnya': {e}")

            if not group_zips:
                st.warning("Tidak ada file untuk dikemas.")
            else:
                zip_state["group_zips"] = group_zips

        if zip_state:
            st.session_state["zip_state"] = zip_state

# Bagian Unduh ZIP (persist melalui session_state)
zip_state = st.session_state.get("zip_state")
if zip_state and not zip_state.get("cleaned", False):
    st.subheader("3) Unduh ZIP")
    if zip_state.get("mode") == "gabungan" and zip_state.get("combined_bytes"):
        clicked = st.download_button(
            "⬇️ Download ZIP (gabungan)",
            data=zip_state["combined_bytes"],
            file_name=zip_state.get("combined_name") or f"mp3_bundle_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip",
            mime="application/zip",
            key="dl_combined",
        )
        if clicked and not zip_state.get("cleaned"):
            cleanup_folder(zip_state.get("output_dir") or "out_mp3")
            zip_state["cleaned"] = True
            st.session_state["zip_state"] = zip_state
            st.success(f"Folder output '{zip_state.get('output_dir')}' telah dibersihkan.")
    elif zip_state.get("mode") == "per_playlist" and zip_state.get("group_zips"):
        any_clicked = False
        for group_title, item in zip_state["group_zips"].items():
            clicked = st.download_button(
                f"⬇️ Download ZIP • {group_title}",
                data=item["bytes"],
                file_name=item["name"],
                mime="application/zip",
                key=f"dl_{slugify(group_title)}",
            )
            any_clicked = any_clicked or clicked
        if any_clicked and not zip_state.get("cleaned"):
            cleanup_folder(zip_state.get("output_dir") or "out_mp3")
            zip_state["cleaned"] = True
            st.session_state["zip_state"] = zip_state
            st.success(f"Folder output '{zip_state.get('output_dir')}' telah dibersihkan.")

# Info lingkungan (diagnostik)
with st.expander("ℹ️ Info lingkungan", expanded=False):
    import sys
    try:
        from yt_dlp.version import __version__ as ytdlp_version
    except Exception:
        ytdlp_version = "unknown"
    st.write({
        "python": sys.version.split(" (", 1)[0],
        "streamlit": st.__version__,
        "yt_dlp": ytdlp_version,
        "ffmpeg_path": shutil.which("ffmpeg"),
        "output_dir": os.path.abspath(st.session_state.get("zip_state", {}).get("output_dir") or (locals().get("out_dir_effective") or "out_mp3")),
    })
