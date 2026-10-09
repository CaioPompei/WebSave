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
HISTORY_LIMIT = 300
HAS_FFMPEG = shutil.which("ffmpeg") is not None
CFG = {
    "app": False,                                     # True when running inside the APK
    "data_dir": os.path.dirname(os.path.abspath(__file__)),
    "tmp_dir": tempfile.gettempdir(),
    "merge": None,                                    # native (Android) video + audio merger
    "save": None,                                     # native (Android) save-to-gallery function
    "qjs": None,                                      # QuickJS binary bundled with the APK
}

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
        "cachedir": os.path.join(CFG["data_dir"], "cache"),
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


def choose(info, kind, quality):
    """Prefer H.264 + AAC in MP4, which the gallery, WhatsApp and CapCut all accept."""
    fmts = info.get("formats") or []
    limit = int(quality) if str(quality).isdigit() else None

    def fits(f):
        return not limit or resolution(f) <= limit

    def bitrate(f):
        return f.get("abr") or f.get("tbr") or 0

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
ACTIVE = ("analyzing", "downloading", "merging", "saving")


def api_config():
    try:
        version = yt().version.__version__
    except Exception:
        version = "?"
    has_js = bool(CFG["qjs"]) or any(shutil.which(x) for x in ("deno", "node", "bun", "qjs"))
    return {"app": CFG["app"], "cookies": bool(cookies_path()), "ffmpeg": HAS_FFMPEG,
            "engine": version, "js": has_js}, 200


def api_info(body):
    url = (body.get("url") or "").strip()
    if not url:
        return {"error": "Paste a link first."}, 400
    try:
        with yt().YoutubeDL(base_opts()) as ydl:
            video = _first_video(ydl.extract_info(url, download=False))
        options = quality_options(video)
        notice = None
        if video.get("extractor_key") == "Youtube" and (not options or options[0]["res"] <= 360):
            notice = ("YouTube only offered low quality for this video. Update the engine in Settings "
                      "or import your cookies to try to unlock the others.")
        elif len(options) <= 1:
            notice = "This site offers a single quality for this video."
        return {
            "url": url,
            "title": video.get("title"),
            "thumbnail": video.get("thumbnail"),
            "duration": video.get("duration"),
            "channel": video.get("uploader") or video.get("channel"),
            "site": SITES.get(video.get("extractor_key"), video.get("extractor_key")),
            "qualities": options,
            "audio_size": estimated_size(video, "audio", "best"),
            "notice": notice,
        }, 200
    except Exception as e:
        text, code = explain_error(e)
        return {"error": text, "code": code}, 400


def _run_download(job_id, url, kind, quality):
    job = JOBS[job_id]
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
        with yt().YoutubeDL(base_opts()) as ydl:
            info = _first_video(ydl.extract_info(url, download=False))
        name = yt().utils.sanitize_filename(info.get("title") or "video")[:120].strip() or "video"
        mode, selection = choose(info, kind, quality)

        job["status"] = "downloading"
        if mode == "merge":
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

        filename = os.path.basename(final)
        mime = mimetypes.guess_type(filename)[0] or ("audio/mp4" if filename.endswith(".m4a") else "video/mp4")
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
        })
    except Exception as e:
        if job.get("cancel"):
            job.update(status="cancelled")
        else:
            text, code = explain_error(e)
            job.update(status="error", error=text, code=code)
        if not job.get("path"):
            shutil.rmtree(folder, ignore_errors=True)


def api_download(body):
    job_id = uuid.uuid4().hex
    meta = {k: body.get(k) for k in ("url", "title", "thumbnail", "duration", "channel", "site")}
    JOBS[job_id] = {"status": "analyzing", "progress": 0, "meta": meta, "kind": body.get("kind", "video"),
                    "label": body.get("label") or "", "started": int(time.time())}
    threading.Thread(target=_run_download, daemon=True,
                     args=(job_id, body.get("url", ""), body.get("kind", "video"), body.get("quality", "best"))).start()
    return {"id": job_id}, 200


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
    active = [{"id": jid, "active": True, "progress": j.get("progress", 0), "kind": j["kind"],
               "label": j["label"], "saved_at": j["started"], **j["meta"]}
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
            self._json(api_update_engine())
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
               save=lambda path, name: native.save(path, name))
    threading.Thread(target=serve, args=(port,), daemon=True).start()
    threading.Thread(target=yt, daemon=True).start()  # warm up the engine


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
