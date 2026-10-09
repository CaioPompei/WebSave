"""
WebSave: save videos from the web using yt-dlp.

Desktop or Termux:  pip install -U "yt-dlp[default]"  then  python websave.py
(opens http://127.0.0.1:5000)
Android APK: the app calls start() and shows the UI in a WebView.
"""
import glob
import json
import mimetypes
import os
import shutil
import ssl
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import quote, urlparse

JOBS = {}
HISTORY_LOCK = threading.Lock()
SETTINGS_LOCK = threading.Lock()
HISTORY_LIMIT = 300
MAX_PARALLEL = 2                       # downloads running at the same time; the rest wait in line
SLOTS = threading.Semaphore(MAX_PARALLEL)
DEFAULT_SETTINGS = {"wifi_only": False, "auto_update": True, "last_update_check": 0, "engine_note": ""}
HAS_FFMPEG = shutil.which("ffmpeg") is not None
CFG = {
    "app": False,                                     # True when running inside the APK
    "data_dir": os.path.dirname(os.path.abspath(__file__)),
    "tmp_dir": tempfile.gettempdir(),
    "merge": None,                                    # native (Android) video + audio merger
    "save": None,                                     # native (Android) save-to-gallery function
    "qjs": None,                                      # QuickJS binary bundled with the APK
    "frames": None,                                   # native (Android) frame extractor for GIFs
    "trim": None,                                     # native (Android) cutter for a time range
    "on_wifi": None,                                  # native (Android) check for an unmetered network
}


# ---------------------------------------------------------------- settings

def _settings_file():
    return os.path.join(CFG["data_dir"], "settings.json")


def settings():
    try:
        with open(_settings_file(), encoding="utf-8") as f:
            return {**DEFAULT_SETTINGS, **json.load(f)}
    except (OSError, ValueError):
        return dict(DEFAULT_SETTINGS)


def save_settings(**changes):
    with SETTINGS_LOCK:
        current = settings()
        current.update({k: v for k, v in changes.items() if k in DEFAULT_SETTINGS})
        os.makedirs(CFG["data_dir"], exist_ok=True)
        with open(_settings_file() + ".tmp", "w", encoding="utf-8") as f:
            json.dump(current, f)
        os.replace(_settings_file() + ".tmp", _settings_file())
        return current

# ---------------------------------------------------------------- engine (yt-dlp)

_yt = None


def _engine_dir():
    return os.path.join(CFG["data_dir"], "engine")


def yt():
    """Import yt-dlp, preferring a newer version downloaded with 'Update engine'."""
    global _yt
    if _yt is None:
        for package in ("yt_dlp_ejs", "yt_dlp"):
            wheels = sorted(glob.glob(os.path.join(_engine_dir(), package + "-*.whl")))
            if wheels:
                sys.path.insert(0, wheels[-1])
        import yt_dlp
        _yt = yt_dlp
    return _yt


def _ssl_context():
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        return ssl.create_default_context()


def cookies_path():
    for p in (
        os.path.join(CFG["data_dir"], "cookies.txt"),
        os.path.expanduser("~/cookies.txt"),
        os.path.expanduser("~/storage/downloads/cookies.txt"),
    ):
        if os.path.isfile(p):
            return p
    return None


def base_opts():
    opts = {
        "quiet": True, "no_warnings": True, "noprogress": True, "no_color": True, "noplaylist": True,
        # keep the download time as the file date, so it shows up on top of the gallery
        "updatetime": False,
        "cachedir": os.path.join(CFG["data_dir"], "cache"),
        # faster: several pieces in parallel, and big chunks so YouTube doesn't throttle
        "concurrent_fragment_downloads": 4,
        "http_chunk_size": 10 * 1024 * 1024,
        # resilient: retry when the connection drops instead of failing
        "retries": 10, "fragment_retries": 10, "extractor_retries": 3, "socket_timeout": 30,
        # YouTube needs a JavaScript runtime to unlock every quality; these are its solver scripts
        "remote_components": ["ejs:github"],
    }
    if CFG["qjs"]:
        opts["js_runtimes"] = {"quickjs": {"path": CFG["qjs"]}}
    else:
        opts["js_runtimes"] = {"deno": {}, "node": {}, "bun": {}, "quickjs": {}}
    cookies = cookies_path()
    if cookies:
        opts["cookiefile"] = cookies
    return opts


def explain_error(e):
    """Turn a yt-dlp error into (message for the user, code for the UI)."""
    msg = str(e).replace("ERROR: ", "").strip()
    low = msg.lower()
    if "not a bot" in low or "sign in to confirm" in low:
        if cookies_path():
            return ("YouTube asked for verification and rejected the imported cookies. "
                    "Export a fresh cookies.txt and import it again in Settings.", "cookies")
        return ("YouTube asked for account verification. Import your cookies in Settings and try again.", "cookies")
    if "unsupported url" in low:
        return ("This link isn't supported. Check that it opens a video in your browser.", None)
    if "private" in low:
        return ("This video is private. Only videos that open without signing in can be saved.", None)
    if "urlopen error" in low or "getaddrinfo" in low or "timed out" in low:
        return ("Couldn't reach the site. Check your connection and try again.", None)
    if "http error 404" in low or "unable to download webpage" in low:
        return ("This address didn't open. Check that the link is complete and the video still exists.", None)
    if "requested format is not available" in low:
        return ("This quality isn't available for this video. Pick another one.", None)
    return (msg or "Something went wrong while reading the link.", None)


def is_transient(e):
    """Network hiccups worth retrying, as opposed to errors that will fail again."""
    low = str(e).lower()
    return any(k in low for k in ("timed out", "timeout", "connection reset", "connection aborted", "temporarily",
                                  "http error 5", "incompleteread", "urlopen error", "network is unreachable",
                                  "remote end closed"))


def thumbnail_of(entry):
    return entry.get("thumbnail") or ((entry.get("thumbnails") or [{}])[-1] or {}).get("url")


def _first_video(info):
    if info.get("_type") == "playlist":
        entries = [e for e in (info.get("entries") or []) if e]
        if not entries:
            raise RuntimeError("No video found at this link.")
        return entries[0]
    return info


# ---------------------------------------------------------------- format selection

def _can_merge():
    return HAS_FFMPEG or CFG["merge"] is not None


def resolution(f):
    """Resolution in the usual sense (1080p, 720p...): the shorter side, so vertical videos work too."""
    w, h = f.get("width"), f.get("height")
    if w and h:
        return min(w, h)
    return h or 0


def _has_video(f):
    return f.get("vcodec") != "none"


def _has_audio(f):
    return f.get("acodec") != "none"


def _audio_only(f):
    return f.get("vcodec") == "none" and f.get("acodec") not in (None, "none")


def _mergeable_video(f):
    return (f.get("acodec") == "none" and f.get("ext") == "mp4"
            and (f.get("vcodec") or "").startswith("avc1"))


def _size(f):
    return f.get("filesize") or f.get("filesize_approx")


def has_audio(info):
    fmts = info.get("formats") or []
    return any(f.get("acodec") not in (None, "none") for f in fmts) or (
        not looks_like_gif(info) and any(f.get("acodec") is None for f in fmts))


def looks_like_gif(info):
    """Sites like X, Reddit, Imgur, Giphy and Tenor serve GIFs as silent MP4 clips."""
    fmts = info.get("formats") or []
    urls = [f.get("url") or "" for f in fmts] + [info.get("url") or "", info.get("webpage_url") or ""]
    if any(f.get("ext") == "gif" for f in fmts) or any(u.split("?")[0].lower().endswith((".gif", ".gifv")) for u in urls):
        return True
    if any("/tweet_video/" in u for u in urls):            # X animated GIFs
        return True
    if info.get("extractor_key") in ("Giphy", "Tenor"):
        return True
    known = [f.get("acodec") for f in fmts if f.get("acodec") is not None]
    silent = bool(known) and all(a == "none" for a in known) and not any(_audio_only(f) for f in fmts)
    return silent and (info.get("duration") or 0) <= 120


def choose(info, kind, quality):
    """Prefer H.264 + AAC in MP4, which the gallery, WhatsApp and CapCut all accept."""
    fmts = info.get("formats") or []
    limit = int(quality) if str(quality).isdigit() else None

    def fits(f):
        return not limit or resolution(f) <= limit

    def bitrate(f):
        return f.get("abr") or f.get("tbr") or 0

    if kind == "gif":
        gifs = [f for f in fmts if f.get("ext") == "gif"]
        if gifs:
            return ("single", max(gifs, key=resolution)["format_id"])
        # the source clip only needs to be a little sharper than the GIF itself
        clips = [f for f in fmts if _has_video(f) and resolution(f) <= 720]  # 0 = size unknown
        if clips:
            # a plain file decodes more reliably on phones than a stream (m3u8 / MPEG-TS)
            best = max(clips, key=lambda f: (not str(f.get("protocol") or "").startswith("m3u8"),
                                             f.get("ext") == "mp4", (f.get("vcodec") or "").startswith(("avc1", "h264")),
                                             resolution(f), f.get("tbr") or 0))
            return ("single", best["format_id"])
        return ("single", "bv*[height<=720]/b[height<=720]/b")

    if kind == "audio":
        audios = [f for f in fmts if _audio_only(f)]
        pool = [f for f in audios if f.get("ext") == "m4a"] or audios
        return ("single", max(pool, key=bitrate)["format_id"] if pool else "ba/b")

    combined = [f for f in fmts if _has_video(f) and _has_audio(f) and fits(f)]
    best_combined = max(
        combined, key=lambda f: (resolution(f), f.get("ext") == "mp4", f.get("tbr") or 0)) if combined else None

    if _can_merge():
        videos = [f for f in fmts if _mergeable_video(f) and fits(f)]
        audios = [f for f in fmts if _audio_only(f) and f.get("ext") == "m4a"]
        if videos and audios:
            video = max(videos, key=lambda f: (resolution(f), f.get("tbr") or 0))
            # only merge when it beats the best version that already has audio
            if not best_combined or resolution(video) > resolution(best_combined):
                return ("merge", (video["format_id"], max(audios, key=bitrate)["format_id"]))

    if best_combined:
        return ("single", best_combined["format_id"])
    h = f"[height<={limit}]" if limit else ""
    return ("single", f"b{h}[ext=mp4]/b{h}/b")


def estimated_size(info, kind, quality):
    """Approximate file size in bytes for a choice, or None when the site doesn't say."""
    by_id = {f.get("format_id"): f for f in info.get("formats") or []}
    mode, selection = choose(info, kind, quality)
    ids = selection if mode == "merge" else (selection,)
    sizes = [_size(by_id[i]) if i in by_id else None for i in ids]
    return sum(sizes) if all(sizes) else None


def quality_options(info):
    """Resolutions WebSave can actually deliver for this video, highest first, with sizes."""
    fmts = info.get("formats") or []
    has_m4a = any(_audio_only(f) and f.get("ext") == "m4a" for f in fmts)
    found = set()
    for f in fmts:
        r = resolution(f)
        if not r or not _has_video(f):
            continue
        if _has_audio(f) or (_can_merge() and has_m4a and _mergeable_video(f)):
            found.add(r)
    return [{"value": str(r), "res": r, "size": estimated_size(info, "video", r)}
            for r in sorted(found, reverse=True)]


# ---------------------------------------------------------------- GIF

GIF_FPS = 12
GIF_MAX_FRAMES = 200


def make_gif(source, target, width, start=None, end=None):
    """Turn a silent clip (or a range of it) into a real animated GIF that plays in any gallery."""
    if source.lower().endswith(".gif") and start is None:
        os.replace(source, target)
        return
    if HAS_FFMPEG:
        graph = (f"fps={GIF_FPS},scale='min({width},iw)':-2:flags=lanczos,split[a][b];"
                 "[a]palettegen=stats_mode=diff[p];[b][p]paletteuse=dither=bayer:bayer_scale=4")
        cut = (["-ss", f"{start:.3f}"] if start else []) + (["-t", f"{end - (start or 0):.3f}"] if end else [])
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", *cut, "-i", source, "-vf", graph, "-loop", "0", target],
                       check=True)
        return
    if CFG["frames"]:
        raw = source + ".rgba"
        start_ms = int((start or 0) * 1000)
        end_ms = int(end * 1000) if end else -1
        w, h, count, delay = (int(x) for x in str(
            CFG["frames"](source, raw, width, GIF_FPS, GIF_MAX_FRAMES, start_ms, end_ms)).split("|"))
        try:
            encode_gif(raw, w, h, count, delay, target)
        finally:
            if os.path.exists(raw):
                os.remove(raw)
        return
    raise RuntimeError("Creating GIFs needs ffmpeg. Install it with: pkg install ffmpeg")


def encode_gif(raw, width, height, count, delay_ms, target):
    """Encode raw RGBA frames into a GIF with one shared, optimized palette."""
    from PIL import Image
    frame_size = width * height * 4

    def frames():
        with open(raw, "rb") as f:
            for _ in range(count):
                data = f.read(frame_size)
                if len(data) < frame_size:
                    return
                yield Image.frombytes("RGBA", (width, height), data).convert("RGB")

    # build the palette from a dozen frames spread across the clip, so colors stay stable
    step = max(1, count // 12)
    samples = [fr for i, fr in enumerate(frames()) if i % step == 0][:12]
    if not samples:
        raise RuntimeError("Couldn't read any frame from this clip.")
    sheet = Image.new("RGB", (width, height * len(samples)))
    for i, fr in enumerate(samples):
        sheet.paste(fr, (0, height * i))
    palette = sheet.quantize(colors=256, method=Image.Quantize.MEDIANCUT)

    out = [fr.quantize(palette=palette, dither=Image.Dither.FLOYDSTEINBERG) for fr in frames()]
    out[0].save(target, save_all=True, append_images=out[1:], duration=max(20, delay_ms), loop=0, disposal=1)


# ---------------------------------------------------------------- trim and tags

def trim_media(source, target, start, end):
    """Keep only [start, end] seconds. Cuts land on the nearest keyframe, without re-encoding."""
    if CFG["trim"]:
        CFG["trim"](source, target, int(start * 1000), int(end * 1000))
    elif HAS_FFMPEG:
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{start:.3f}", "-i", source,
                        "-t", f"{end - start:.3f}", "-c", "copy", "-avoid_negative_ts", "make_zero",
                        "-movflags", "+faststart", target], check=True)
    else:
        raise RuntimeError("Trimming needs ffmpeg. Install it with: pkg install ffmpeg")


def _cover_image(info):
    """A JPEG or PNG thumbnail (what music players accept as cover art), as (bytes, is_png)."""
    candidates = [t for t in (info.get("thumbnails") or []) if t.get("url")]
    candidates.sort(key=lambda t: (t.get("preference") or 0, t.get("width") or 0))
    urls = [t["url"] for t in reversed(candidates)] + [info.get("thumbnail") or ""]
    for url in urls:
        path = url.split("?")[0].lower()
        if not path.endswith((".jpg", ".jpeg", ".png")):
            continue
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=15, context=_ssl_context()) as r:
                return r.read(), path.endswith(".png")
        except Exception:
            continue
    return None, False


def tag_audio(path, info):
    """Write title, artist and cover art so music players show more than a file name."""
    if not path.lower().endswith((".m4a", ".mp4")):
        return
    try:
        from mutagen.mp4 import MP4, MP4Cover
        audio = MP4(path)
        if info.get("title"):
            audio["\xa9nam"] = [info["title"]]
        artist = info.get("artist") or info.get("uploader") or info.get("channel")
        if artist:
            audio["\xa9ART"] = [artist]
        if info.get("album"):
            audio["\xa9alb"] = [info["album"]]
        data, is_png = _cover_image(info)
        if data:
            audio["covr"] = [MP4Cover(data, MP4Cover.FORMAT_PNG if is_png else MP4Cover.FORMAT_JPEG)]
        audio.save()
    except Exception:
        pass  # tags are a nice extra; never fail the download over them


# ---------------------------------------------------------------- history

def _history_file():
    return os.path.join(CFG["data_dir"], "history.json")


def load_history():
    try:
        with open(_history_file(), encoding="utf-8") as f:
            items = json.load(f)
        return items if isinstance(items, list) else []
    except (OSError, ValueError):
        return []


def _write_history(items):
    os.makedirs(CFG["data_dir"], exist_ok=True)
    tmp = _history_file() + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(items[:HISTORY_LIMIT], f, ensure_ascii=False)
    os.replace(tmp, _history_file())


def add_history(entry):
    with HISTORY_LOCK:
        items = [i for i in load_history() if i.get("id") != entry["id"]]
        _write_history([entry] + items)


def remove_history(item_id):
    with HISTORY_LOCK:
        _write_history([i for i in load_history() if i.get("id") != item_id])


# ---------------------------------------------------------------- API

SITES = {"Youtube": "YouTube", "Twitter": "X", "TikTok": "TikTok", "Instagram": "Instagram",
         "Facebook": "Facebook", "Vimeo": "Vimeo", "Reddit": "Reddit", "Generic": None}
ACTIVE = ("waiting_wifi", "queued", "retrying", "analyzing", "downloading", "merging", "converting", "trimming", "saving")


def api_config():
    try:
        version = yt().version.__version__
    except Exception:
        version = "?"
    has_js = bool(CFG["qjs"]) or any(shutil.which(x) for x in ("deno", "node", "bun", "qjs"))
    return {"app": CFG["app"], "cookies": bool(cookies_path()), "ffmpeg": HAS_FFMPEG,
            "engine": version, "js": has_js, "settings": settings()}, 200


def api_info(body):
    url = (body.get("url") or "").strip()
    if not url:
        return {"error": "Paste a link first."}, 400
    try:
        with yt().YoutubeDL({**base_opts(), "extract_flat": "in_playlist"}) as ydl:
            info = ydl.extract_info(url, download=False)
        entries = [e for e in (info.get("entries") or []) if e] if info.get("_type") == "playlist" else []
        if len(entries) > 1:
            return {
                "playlist": True,
                "url": url,
                "title": info.get("title") or "Playlist",
                "channel": info.get("uploader") or info.get("channel"),
                "site": SITES.get(info.get("extractor_key"), info.get("extractor_key")),
                "count": len(entries),
                "entries": [{"index": i + 1, "title": e.get("title") or f"Item {i + 1}",
                             "thumbnail": thumbnail_of(e), "duration": e.get("duration")}
                            for i, e in enumerate(entries[:100])],
            }, 200
        video = _first_video(info)
        if video.get("_type") == "url" and video.get("url"):
            with yt().YoutubeDL(base_opts()) as ydl:
                video = _first_video(ydl.extract_info(video["url"], download=False))
        options = quality_options(video)
        gif_like = looks_like_gif(video)
        notice = None
        if gif_like:
            notice = "This is a silent clip, so WebSave saves it as a GIF that plays right in your gallery."
        elif video.get("extractor_key") == "Youtube" and (not options or options[0]["res"] <= 360):
            notice = ("YouTube only offered low quality for this video. Update the engine in Settings "
                      "or import your cookies to try to unlock the others.")
        elif len(options) <= 1:
            notice = "This site offers a single quality for this video."
        return {
            "url": url,
            "title": video.get("title"),
            "thumbnail": thumbnail_of(video),
            "duration": video.get("duration"),
            "channel": video.get("uploader") or video.get("channel"),
            "site": SITES.get(video.get("extractor_key"), video.get("extractor_key")),
            "qualities": options,
            "audio_size": estimated_size(video, "audio", "best"),
            "gif_like": gif_like,
            "has_audio": has_audio(video),
            "notice": notice,
        }, 200
    except Exception as e:
        text, code = explain_error(e)
        return {"error": text, "code": code}, 400


def _run_download(job_id, body):
    """Wait for Wi-Fi (if asked) and a free slot, then download, retrying network hiccups."""
    job = JOBS[job_id]

    def check_cancel():
        if job.get("cancel"):
            raise yt().utils.DownloadCancelled("Cancelled")

    try:
        while settings()["wifi_only"] and CFG["on_wifi"] and not CFG["on_wifi"]():
            check_cancel()
            job["status"] = "waiting_wifi"
            time.sleep(3)
        job["status"] = "queued"
        while not SLOTS.acquire(timeout=1):
            check_cancel()
        try:
            for attempt in range(3):
                try:
                    _download(job_id, body)
                    break
                except Exception as e:
                    if job.get("cancel") or not is_transient(e) or attempt == 2:
                        raise
                    job.update(status="retrying", progress=0)
                    time.sleep(3 * (attempt + 1))
        finally:
            SLOTS.release()
    except Exception as e:
        if job.get("cancel"):
            job.update(status="cancelled")
        else:
            text, code = explain_error(e)
            job.update(status="error", error=text, code=code)


def _download(job_id, body):
    job = JOBS[job_id]
    url, kind, quality = body.get("url", ""), body.get("kind", "video"), body.get("quality", "best")
    item = body.get("item")
    trim = body.get("trim") or None
    start = float(trim["start"]) if trim else None
    end = float(trim["end"]) if trim else None
    folder = tempfile.mkdtemp(prefix="websave_", dir=CFG["tmp_dir"])
    span = {"start": 0.0, "weight": 100.0}

    def hook(p):
        if job.get("cancel"):
            raise yt().utils.DownloadCancelled("Cancelled")
        if p.get("status") == "downloading":
            total = p.get("total_bytes") or p.get("total_bytes_estimate")
            if total:
                job["progress"] = round(span["start"] + p.get("downloaded_bytes", 0) / total * span["weight"], 1)

    def fetch(info, fmt, prefix):
        opts = {**base_opts(), "format": fmt, "progress_hooks": [hook],
                "outtmpl": os.path.join(folder, prefix + ".%(ext)s")}
        with yt().YoutubeDL(opts) as ydl:
            ydl.process_ie_result(ydl.sanitize_info(info, remove_private_keys=False), download=True)
        if job.get("cancel"):
            raise yt().utils.DownloadCancelled("Cancelled")
        done = [os.path.join(folder, f) for f in os.listdir(folder)
                if f.startswith(prefix + ".") and not f.endswith((".part", ".ytdl"))]
        if not done:
            raise RuntimeError("The download finished without producing a file.")
        return max(done, key=os.path.getsize)

    def fetch_single(info, fmt):
        tmp = fetch(info, fmt, "s")
        final = os.path.join(folder, name + os.path.splitext(tmp)[1])
        os.replace(tmp, final)
        return final

    try:
        job["status"] = "analyzing"
        opts = base_opts()
        if item:
            opts.update(noplaylist=False, playlist_items=str(item))
        with yt().YoutubeDL(opts) as ydl:
            info = _first_video(ydl.extract_info(url, download=False))
        name = yt().utils.sanitize_filename(info.get("title") or "video")[:120].strip() or "video"
        if trim:
            name = f"{name} ({_clock(start)}-{_clock(end)})"
        mode, selection = choose(info, kind, quality)

        job["status"] = "downloading"
        if kind == "gif":
            span.update(start=0, weight=80)
            clip = fetch(info, selection, "c")
            job.update(status="converting", progress=85)
            final = os.path.join(folder, name + ".gif")
            try:
                make_gif(clip, final, int(quality) if str(quality).isdigit() else 480, start, end)
                os.remove(clip)
            except Exception:
                # never lose the download: keep the clip as a video and say so
                final = os.path.join(folder, name + os.path.splitext(clip)[1])
                os.replace(clip, final)
                job["warning"] = "This clip couldn't be turned into a GIF, so it was saved as a video."
            trim = None  # already applied while making the GIF
        elif mode == "merge":
            span.update(start=0, weight=85)
            video = fetch(info, selection[0], "v")
            span.update(start=85, weight=13)
            audio = fetch(info, selection[1], "a")
            job.update(status="merging", progress=99)
            final = os.path.join(folder, name + ".mp4")
            try:
                if CFG["merge"]:
                    CFG["merge"](video, audio, final)
                else:
                    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", video, "-i", audio,
                                    "-map", "0:v:0", "-map", "1:a:0", "-c", "copy",
                                    "-movflags", "+faststart", final], check=True)
            except Exception:
                # if merging fails, fall back to the best version that already has audio
                job.update(status="downloading", progress=0)
                span.update(start=0, weight=100)
                final = fetch_single(info, "b[ext=mp4]/b")
            for f in (video, audio):
                if os.path.exists(f):
                    os.remove(f)
        else:
            final = fetch_single(info, selection)

        if trim:
            job.update(status="trimming", progress=99)
            cut = os.path.join(folder, "trimmed" + os.path.splitext(final)[1])
            trim_media(final, cut, start, end)
            os.replace(cut, final)
        if kind == "audio":
            tag_audio(final, info)

        filename = os.path.basename(final)
        mime = mimetypes.guess_type(filename)[0] or ("audio/mp4" if filename.endswith(".m4a") else "video/mp4")
        if filename.endswith(".gif"):
            mime = "image/gif"
        size = os.path.getsize(final)
        job.update(filename=filename, mime=mime, size=size)
        if CFG["save"]:
            job["status"] = "saving"
            uri, location = str(CFG["save"](final, filename)).split("|", 1)
            job.update(uri=uri, location=location)
            shutil.rmtree(folder, ignore_errors=True)
        else:
            job["path"] = final
        job.update(status="done", progress=100)
        add_history({
            "id": job_id, "saved_at": int(time.time()), **job["meta"],
            "kind": kind, "label": job["label"], "size": size, "filename": filename, "mime": mime,
            "uri": job.get("uri"), "location": job.get("location"), "path": job.get("path"),
            "item": item, "warning": job.get("warning"),
        })
    except Exception:
        if not job.get("path"):
            shutil.rmtree(folder, ignore_errors=True)
        raise


def _clock(seconds):
    """Time for a file name, without ':' (not allowed on every storage): 5s, 1m05s, 1h02m05s."""
    seconds = int(seconds or 0)
    h, m, s = seconds // 3600, seconds % 3600 // 60, seconds % 60
    if h:
        return f"{h}h{m:02d}m{s:02d}s"
    return f"{m}m{s:02d}s" if m else f"{s}s"


def api_download(body):
    job_id = uuid.uuid4().hex
    meta = {k: body.get(k) for k in ("url", "title", "thumbnail", "duration", "channel", "site")}
    JOBS[job_id] = {"status": "queued", "progress": 0, "meta": meta, "kind": body.get("kind", "video"),
                    "label": body.get("label") or "", "started": time.time()}
    threading.Thread(target=_run_download, args=(job_id, body), daemon=True).start()
    return {"id": job_id}, 200


def api_jobs():
    """Every download of this session with its state (the notification service polls this)."""
    keys = ("status", "progress", "error", "warning", "uri", "mime", "location", "filename", "kind")
    jobs = [{"id": jid, "title": j["meta"].get("title"), **{k: j.get(k) for k in keys}}
            for jid, j in sorted(JOBS.items(), key=lambda kv: kv[1]["started"])]
    return {"jobs": jobs}, 200


def api_thumbnail(body):
    """Save a video's cover image to the gallery (or hand it to the browser on desktop)."""
    url = body.get("url") or ""
    if not url:
        return {"error": "This video has no cover image."}, 400
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=20, context=_ssl_context()) as r:
            data, ctype = r.read(), r.headers.get("Content-Type", "")
        ext = {"image/png": ".png", "image/webp": ".webp", "image/gif": ".gif"}.get(ctype.split(";")[0], ".jpg")
        name = yt().utils.sanitize_filename(body.get("title") or "cover")[:110].strip() or "cover"
        folder = tempfile.mkdtemp(prefix="websave_", dir=CFG["tmp_dir"])
        path = os.path.join(folder, f"{name} (cover){ext}")
        with open(path, "wb") as f:
            f.write(data)
        if CFG["save"]:
            uri, location = str(CFG["save"](path, os.path.basename(path))).split("|", 1)
            shutil.rmtree(folder, ignore_errors=True)
            return {"uri": uri, "location": location}, 200
        job_id = uuid.uuid4().hex
        JOBS[job_id] = {"status": "done", "path": path, "filename": os.path.basename(path), "mime": ctype or "image/jpeg",
                        "meta": {}, "kind": "image", "label": "", "started": time.time()}
        return {"id": job_id}, 200
    except Exception as e:
        return {"error": f"Couldn't save the cover: {e}"}, 500


def api_set_settings(body):
    allowed = {k: bool(v) for k, v in body.items() if k in ("wifi_only", "auto_update")}
    return {"settings": save_settings(**allowed)}, 200


def auto_update():
    """Once a week, quietly fetch a newer engine. It's used from the next launch."""
    time.sleep(20)
    s = settings()
    if not s["auto_update"] or time.time() - s["last_update_check"] < 7 * 86400:
        return
    result, status = api_update_engine()
    note = f"Version {result['version']} downloaded automatically; it's used from the next launch." \
        if status == 200 and result.get("updated") else ""
    save_settings(last_update_check=int(time.time()), engine_note=note)


def api_status(job_id):
    job = JOBS.get(job_id)
    if not job:
        return {"error": "This download no longer exists. Start again."}, 404
    return {k: v for k, v in job.items() if k not in ("path", "cancel")}, 200


def api_cancel(job_id):
    job = JOBS.get(job_id)
    if job and job.get("status") in ACTIVE:
        job["cancel"] = True
    return {"ok": True}, 200


def api_history():
    active = [{"id": jid, "active": True, "status": j["status"], "progress": j.get("progress", 0), "kind": j["kind"],
               "label": j["label"], "saved_at": int(j["started"]), **j["meta"]}
              for jid, j in JOBS.items() if j.get("status") in ACTIVE]
    active.sort(key=lambda i: i["saved_at"], reverse=True)
    items = [{k: v for k, v in i.items() if k != "path"} for i in load_history()]
    return {"items": active + items}, 200


def api_history_remove(item_id):
    remove_history(item_id)
    return {"ok": True}, 200


def _file_for(item_id):
    job = JOBS.get(item_id)
    if job and job.get("path"):
        return job["path"], job["filename"], job.get("mime")
    for i in load_history():
        if i.get("id") == item_id and i.get("path"):
            return i["path"], i["filename"], i.get("mime")
    return None, None, None


def api_import_cookies(data):
    if not data:
        return {"error": "The file is empty."}, 400
    text = data.decode("utf-8", "ignore").lower()
    if "youtube" not in text and "google" not in text:
        return {"error": "This file has no YouTube cookies. Export it with YouTube open."}, 400
    os.makedirs(CFG["data_dir"], exist_ok=True)
    with open(os.path.join(CFG["data_dir"], "cookies.txt"), "wb") as out:
        out.write(data)
    return {"ok": True}, 200


def api_remove_cookies():
    p = os.path.join(CFG["data_dir"], "cookies.txt")
    if os.path.isfile(p):
        os.remove(p)
    return {"ok": True}, 200


def api_update_engine():
    """Download the latest yt-dlp (and its solver scripts) from PyPI. Applies after reopening the app."""
    try:
        ctx = _ssl_context()

        def pypi(package):
            with urllib.request.urlopen(f"https://pypi.org/pypi/{package}/json", timeout=20, context=ctx) as r:
                return json.load(r)

        latest = pypi("yt-dlp")
        version = latest["info"]["version"]
        if version == yt().version.__version__:
            return {"version": version, "updated": False}, 200
        os.makedirs(_engine_dir(), exist_ok=True)
        for prefix, meta in (("yt_dlp", latest), ("yt_dlp_ejs", pypi("yt-dlp-ejs"))):
            wheel = next(u for u in meta["urls"] if u["filename"].endswith("py3-none-any.whl"))
            target = os.path.join(_engine_dir(), wheel["filename"])
            with urllib.request.urlopen(wheel["url"], timeout=120, context=ctx) as r, open(target + ".tmp", "wb") as out:
                shutil.copyfileobj(r, out)
            for old in glob.glob(os.path.join(_engine_dir(), prefix + "-*.whl")):
                os.remove(old)
            os.replace(target + ".tmp", target)
        return {"version": version, "updated": True}, 200
    except Exception as e:
        return {"error": f"Couldn't update: {e}"}, 500


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *args):
        pass

    def _send(self, body, content_type, status=200):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, result):
        obj, status = result
        self._send(json.dumps(obj).encode(), "application/json; charset=utf-8", status)

    def _body(self):
        n = int(self.headers.get("Content-Length") or 0)
        return self.rfile.read(n) if n else b""

    def _json_body(self):
        try:
            return json.loads(self._body() or b"{}")
        except ValueError:
            return {}

    def do_GET(self):
        path = urlparse(self.path).path
        last = path.rsplit("/", 1)[-1]
        if path == "/":
            self._send(HTML.encode(), "text/html; charset=utf-8")
        elif path == "/api/ping":
            self._json(({"ok": True}, 200))
        elif path == "/api/config":
            self._json(api_config())
        elif path == "/api/history":
            self._json(api_history())
        elif path == "/api/jobs":
            self._json(api_jobs())
        elif path.startswith("/api/status/"):
            self._json(api_status(last))
        elif path.startswith("/api/file/"):
            file_path, filename, mime = _file_for(last)
            if not file_path or not os.path.isfile(file_path):
                return self._json(({"error": "File not available."}, 404))
            self.send_response(200)
            self.send_header("Content-Type", mime or "application/octet-stream")
            self.send_header("Content-Length", str(os.path.getsize(file_path)))
            self.send_header("Content-Disposition", "attachment; filename*=UTF-8''" + quote(filename))
            self.end_headers()
            with open(file_path, "rb") as f:
                shutil.copyfileobj(f, self.wfile)
        else:
            self._json(({"error": "Not found."}, 404))

    def do_POST(self):
        path = urlparse(self.path).path
        if path == "/api/info":
            self._json(api_info(self._json_body()))
        elif path == "/api/download":
            self._json(api_download(self._json_body()))
        elif path.startswith("/api/cancel/"):
            self._body()
            self._json(api_cancel(path.rsplit("/", 1)[-1]))
        elif path == "/api/cookies":
            self._json(api_import_cookies(self._body()))
        elif path == "/api/update":
            self._body()
            result = api_update_engine()
            save_settings(last_update_check=int(time.time()), engine_note="")
            self._json(result)
        elif path == "/api/thumbnail":
            self._json(api_thumbnail(self._json_body()))
        elif path == "/api/settings":
            self._json(api_set_settings(self._json_body()))
        else:
            self._json(({"error": "Not found."}, 404))

    def do_DELETE(self):
        path = urlparse(self.path).path
        if path == "/api/cookies":
            self._json(api_remove_cookies())
        elif path.startswith("/api/history/"):
            self._json(api_history_remove(path.rsplit("/", 1)[-1]))
        else:
            self._json(({"error": "Not found."}, 404))


def serve(port):
    server = ThreadingHTTPServer(("127.0.0.1", int(port)), Handler)
    server.daemon_threads = True
    server.serve_forever()


# ---------------------------------------------------------------- Android

def start(port, data_dir, cache_dir, native_lib_dir=None):
    """Called by the Android app (Chaquopy)."""
    from java import jclass
    native = jclass("app.websave.Native")
    try:
        import certifi
        os.environ.setdefault("SSL_CERT_FILE", certifi.where())
    except Exception:
        pass
    qjs = os.path.join(native_lib_dir, "libqjs.so") if native_lib_dir else None
    CFG.update(app=True, data_dir=data_dir, tmp_dir=cache_dir,
               qjs=qjs if qjs and os.access(qjs, os.X_OK) else None,
               merge=lambda v, a, out: native.merge(v, a, out),
               save=lambda path, name: native.save(path, name),
               frames=lambda src, out, width, fps, limit, start, end: native.gifFrames(src, out, width, fps, limit, start, end),
               trim=lambda src, out, start, end: native.trim(src, out, start, end),
               on_wifi=lambda: bool(native.isOnWifi()))
    threading.Thread(target=serve, args=(port,), daemon=True).start()
    threading.Thread(target=yt, daemon=True).start()  # warm up the engine
    threading.Thread(target=auto_update, daemon=True).start()


# ---------------------------------------------------------------- UI

from websave_ui import HTML  # noqa: E402  (kept in its own module so the page is easy to edit)


if __name__ == "__main__":
    import webbrowser
    print("WebSave running at http://127.0.0.1:5000  (CTRL+C to stop)")
    if cookies_path():
        print("Using cookies:", cookies_path())
    if not HAS_FFMPEG:
        print("Warning: ffmpeg not found, quality will be limited (install with: pkg install ffmpeg).")
    threading.Timer(1.2, lambda: webbrowser.open("http://127.0.0.1:5000")).start()
    try:
        serve(5000)
    except KeyboardInterrupt:
        pass
