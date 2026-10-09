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
import urllib.request
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import quote, urlparse

JOBS = {}
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


def available_resolutions(info):
    """Resolutions WebSave can actually deliver for this video."""
    fmts = info.get("formats") or []
    has_m4a = any(_audio_only(f) and f.get("ext") == "m4a" for f in fmts)
    found = set()
    for f in fmts:
        r = resolution(f)
        if not r or not _has_video(f):
            continue
        if _has_audio(f) or (_can_merge() and has_m4a and _mergeable_video(f)):
            found.add(r)
    return sorted(found, reverse=True)


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


# ---------------------------------------------------------------- API

SITES = {"Youtube": "YouTube", "Twitter": "X", "TikTok": "TikTok", "Instagram": "Instagram",
         "Facebook": "Facebook", "Vimeo": "Vimeo", "Reddit": "Reddit", "Generic": None}


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
        resolutions = available_resolutions(video)
        notice = None
        if video.get("extractor_key") == "Youtube" and (not resolutions or resolutions[0] <= 360):
            notice = ("YouTube only offered low quality for this video. Update the engine in Settings "
                      "or import your cookies to try to unlock the others.")
        elif len(resolutions) <= 1:
            notice = "This site offers a single quality for this video."
        return {
            "title": video.get("title"),
            "thumbnail": video.get("thumbnail"),
            "duration": video.get("duration"),
            "channel": video.get("uploader") or video.get("channel"),
            "site": SITES.get(video.get("extractor_key"), video.get("extractor_key")),
            "resolutions": resolutions,
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
        if p.get("status") == "downloading":
            total = p.get("total_bytes") or p.get("total_bytes_estimate")
            if total:
                job["progress"] = round(span["start"] + p.get("downloaded_bytes", 0) / total * span["weight"], 1)

    def fetch(info, fmt, prefix):
        opts = {**base_opts(), "format": fmt, "progress_hooks": [hook],
                "outtmpl": os.path.join(folder, prefix + ".%(ext)s")}
        with yt().YoutubeDL(opts) as ydl:
            ydl.process_ie_result(ydl.sanitize_info(info, remove_private_keys=False), download=True)
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
        job.update(filename=filename, mime=mime)
        if CFG["save"]:
            job["status"] = "saving"
            uri, location = str(CFG["save"](final, filename)).split("|", 1)
            job.update(uri=uri, location=location)
            shutil.rmtree(folder, ignore_errors=True)
        else:
            job["path"] = final
        job.update(status="done", progress=100)
    except Exception as e:
        text, code = explain_error(e)
        job.update(status="error", error=text, code=code)
        if not job.get("path"):
            shutil.rmtree(folder, ignore_errors=True)


def api_download(body):
    job_id = uuid.uuid4().hex
    JOBS[job_id] = {"status": "analyzing", "progress": 0}
    threading.Thread(target=_run_download, daemon=True,
                     args=(job_id, body.get("url", ""), body.get("kind", "video"), body.get("quality", "best"))).start()
    return {"id": job_id}, 200


def api_status(job_id):
    job = JOBS.get(job_id)
    if not job:
        return {"error": "This download no longer exists. Start again."}, 404
    return {k: v for k, v in job.items() if k != "path"}, 200


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
        if path == "/":
            self._send(HTML.encode(), "text/html; charset=utf-8")
        elif path == "/api/ping":
            self._json(({"ok": True}, 200))
        elif path == "/api/config":
            self._json(api_config())
        elif path.startswith("/api/status/"):
            self._json(api_status(path.rsplit("/", 1)[-1]))
        elif path.startswith("/api/file/"):
            job = JOBS.get(path.rsplit("/", 1)[-1])
            if not job or not job.get("path") or not os.path.isfile(job["path"]):
                return self._json(({"error": "File not available."}, 404))
            self.send_response(200)
            self.send_header("Content-Type", job.get("mime") or "application/octet-stream")
            self.send_header("Content-Length", str(os.path.getsize(job["path"])))
            self.send_header("Content-Disposition", "attachment; filename*=UTF-8''" + quote(job["filename"]))
            self.end_headers()
            with open(job["path"], "rb") as f:
                shutil.copyfileobj(f, self.wfile)
        else:
            self._json(({"error": "Not found."}, 404))

    def do_POST(self):
        path = urlparse(self.path).path
        if path == "/api/info":
            self._json(api_info(self._json_body()))
        elif path == "/api/download":
            self._json(api_download(self._json_body()))
        elif path == "/api/cookies":
            self._json(api_import_cookies(self._body()))
        elif path == "/api/update":
            self._body()
            self._json(api_update_engine())
        else:
            self._json(({"error": "Not found."}, 404))

    def do_DELETE(self):
        if urlparse(self.path).path == "/api/cookies":
            self._json(api_remove_cookies())
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

HTML = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="theme-color" content="#EDEFF2" media="(prefers-color-scheme: light)">
<meta name="theme-color" content="#15181C" media="(prefers-color-scheme: dark)">
<title>WebSave</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Schibsted+Grotesk:wght@400;500;600;700;800&display=swap" rel="stylesheet">
<style>
:root{
  --paper:#EDEFF2; --sheet:#FFFFFF; --groove:#E1E5EA; --ink:#171A1F; --muted:#5D6571; --rule:#D3D8DE;
  --cobalt:#2443D6; --track:#D5DCF7; --ok:#157F55; --danger:#B42318; --danger-bg:#FBEAE8;
  --font:"Schibsted Grotesk",system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;
  color-scheme:light;
}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){
  --paper:#15181C; --sheet:#1E2227; --groove:#252A30; --ink:#E9ECF0; --muted:#9AA3AE; --rule:#30363D;
  --cobalt:#5B7CFF; --track:#232C4D; --ok:#3DBB84; --danger:#FF8A80; --danger-bg:#3A2121;
  color-scheme:dark;
}}
:root[data-theme="dark"]{
  --paper:#15181C; --sheet:#1E2227; --groove:#252A30; --ink:#E9ECF0; --muted:#9AA3AE; --rule:#30363D;
  --cobalt:#5B7CFF; --track:#232C4D; --ok:#3DBB84; --danger:#FF8A80; --danger-bg:#3A2121;
  color-scheme:dark;
}
*{box-sizing:border-box}
html{-webkit-text-size-adjust:100%;-webkit-tap-highlight-color:transparent}
body{margin:0;background:var(--paper);color:var(--ink);font:400 16px/1.5 var(--font);
  padding:env(safe-area-inset-top) 0 env(safe-area-inset-bottom)}
button,input{font:inherit;color:inherit}
button{cursor:pointer}
:focus-visible{outline:2px solid var(--cobalt);outline-offset:2px}
[hidden]{display:none!important}

.page{max-width:560px;margin:0 auto;padding:0 20px 48px}

.topbar{display:flex;align-items:center;justify-content:space-between;height:64px}
.brand{display:flex;align-items:center;gap:9px;font-weight:800;font-size:19px;letter-spacing:-.02em}
.brand svg{width:26px;height:26px;color:var(--cobalt)}
.icon-btn{width:44px;height:44px;margin-right:-10px;border:0;background:none;border-radius:50%;display:grid;place-items:center;color:var(--muted)}
.icon-btn:active{background:var(--groove)}
.icon-btn svg{width:22px;height:22px}

.prompt{display:block;font-size:30px;line-height:1.12;font-weight:700;letter-spacing:-.025em;margin:28px 0 18px}
.field{display:flex;align-items:center;background:var(--sheet);border:1.5px solid var(--rule);border-radius:12px;transition:border-color .15s}
.field:focus-within{border-color:var(--cobalt)}
.field input{flex:1;min-width:0;border:0;background:none;outline:none;padding:15px 0 15px 16px;font-size:17px}
.field input::placeholder{color:var(--muted);opacity:.7}
.paste{border:0;background:none;color:var(--cobalt);font-weight:600;padding:15px 16px;border-radius:0 12px 12px 0}
.clear{border:0;background:none;color:var(--muted);width:40px;height:48px;display:grid;place-items:center}
.clear svg{width:18px;height:18px}

.primary{width:100%;margin-top:12px;border:0;border-radius:12px;padding:15px;font-weight:700;font-size:17px;
  background:var(--ink);color:var(--paper)}
.primary:disabled{opacity:.55;cursor:default}
.hint{color:var(--muted);font-size:14px;margin:12px 0 0}

.error{display:flex;gap:12px;align-items:flex-start;justify-content:space-between;margin-top:20px;padding:13px 14px;
  border-radius:10px;background:var(--danger-bg);color:var(--danger);font-size:15px;line-height:1.4}
.error button{flex:none;border:0;background:none;color:inherit;font-weight:700;text-decoration:underline;padding:0}

.video{margin-top:32px;padding-top:28px;border-top:1px solid var(--rule)}
.cover{display:block;width:100%;aspect-ratio:16/9;object-fit:cover;border-radius:10px;background:var(--groove)}
.title{font-size:20px;line-height:1.3;font-weight:600;letter-spacing:-.01em;margin:16px 0 6px;
  display:-webkit-box;-webkit-line-clamp:3;-webkit-box-orient:vertical;overflow:hidden}
.meta{display:flex;flex-wrap:wrap;column-gap:14px;color:var(--muted);font-size:14px;margin:0}
.meta .duration{font-variant-numeric:tabular-nums}
.notice{margin:12px 0 0;padding:10px 12px;border-left:3px solid var(--cobalt);background:var(--sheet);
  border-radius:0 8px 8px 0;font-size:14px;line-height:1.45;color:var(--muted)}

.option{border:0;margin:22px 0 0;padding:0}
.option legend{font-size:14px;font-weight:600;color:var(--muted);margin-bottom:8px;padding:0}
.segmented{display:flex;background:var(--groove);border-radius:10px;padding:3px}
.segmented label{flex:1;position:relative}
.segmented input{position:absolute;opacity:0;inset:0;margin:0}
.segmented span{display:block;text-align:center;padding:9px 4px;border-radius:8px;font-weight:500;font-size:15px;color:var(--muted);
  font-variant-numeric:tabular-nums}
.segmented input:checked+span{background:var(--sheet);color:var(--ink);font-weight:600;box-shadow:0 0 0 1px var(--rule)}
.segmented input:focus-visible+span{outline:2px solid var(--cobalt);outline-offset:1px}

/* the save button doubles as the progress bar */
.save{position:relative;display:block;width:100%;height:56px;margin-top:26px;border:0;padding:0;border-radius:12px;overflow:hidden;
  font-weight:700;font-size:17px;font-variant-numeric:tabular-nums;--p:100%}
.save .layer{position:absolute;inset:0;display:flex;align-items:center;justify-content:center;gap:8px}
.save .base{background:var(--track);color:var(--ink)}
.save .fill{background:var(--cobalt);color:#fff;clip-path:inset(0 calc(100% - var(--p)) 0 0);transition:clip-path .35s ease-out,background-color .3s}
.save.done .fill{background:var(--ok)}
.save:disabled{cursor:default}
.save svg{width:20px;height:20px}
.status{min-height:21px;margin:10px 0 0;color:var(--muted);font-size:14px;line-height:1.5}
.actions{display:flex;gap:10px;margin-top:14px}
.actions button{flex:1;padding:13px;border-radius:12px;border:1.5px solid var(--rule);background:var(--sheet);font-weight:600}
.another{display:block;margin:18px auto 0;border:0;background:none;color:var(--cobalt);font-weight:600;padding:8px}

/* settings sheet */
dialog{border:0;padding:0;margin:auto auto 0;width:100%;max-width:560px;border-radius:18px 18px 0 0;background:var(--sheet);color:var(--ink)}
dialog::backdrop{background:rgba(10,14,20,.45)}
.sheet{padding:8px 20px calc(24px + env(safe-area-inset-bottom))}
.grabber{width:36px;height:4px;border-radius:2px;background:var(--rule);margin:4px auto 14px}
.sheet h2{font-size:22px;letter-spacing:-.02em;margin:0 0 4px}
.group{padding:18px 0;border-bottom:1px solid var(--rule)}
.group:last-of-type{border-bottom:0}
.group h3{font-size:16px;margin:0 0 4px}
.group p{margin:0 0 12px;color:var(--muted);font-size:14px;line-height:1.5}
.group .state{color:var(--ink);font-weight:500}
.button-row{display:flex;gap:10px;flex-wrap:wrap}
.secondary{padding:11px 16px;border-radius:10px;border:1.5px solid var(--rule);background:none;font-weight:600}
.secondary.strong{background:var(--ink);color:var(--sheet);border-color:var(--ink)}
.close{width:100%;margin-top:8px}

@media (prefers-reduced-motion:reduce){*{transition:none!important;animation:none!important}}
@keyframes spin{to{transform:rotate(360deg)}}
.spin{animation:spin .8s linear infinite}
</style>
</head>
<body>
<div class="page">
  <header class="topbar">
    <div class="brand">
      <svg viewBox="0 0 26 26" fill="none" aria-hidden="true"><rect x="1" y="1" width="24" height="24" rx="7" fill="currentColor"/>
        <path d="M13 6.5v9m0 0-3.6-3.6M13 15.5l3.6-3.6M7.5 19h11" stroke="#fff" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/></svg>
      WebSave
    </div>
    <button class="icon-btn" id="openSettings" aria-label="Settings">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" aria-hidden="true">
        <path d="M4 7h10M18 7h2M4 17h4M12 17h8"/><circle cx="16" cy="7" r="2"/><circle cx="10" cy="17" r="2"/></svg>
    </button>
  </header>

  <form id="form" autocomplete="off">
    <label class="prompt" for="url">Paste the video link</label>
    <div class="field">
      <input id="url" type="url" inputmode="url" enterkeyhint="search" placeholder="https://" spellcheck="false">
      <button type="button" class="clear" id="clear" aria-label="Clear link" hidden>
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M6 6l12 12M18 6 6 18"/></svg>
      </button>
      <button type="button" class="paste" id="paste">Paste</button>
    </div>
    <button class="primary" id="find">Find video</button>
    <p class="hint" id="hint">Works with YouTube, Instagram, TikTok, X, Facebook, Vimeo and hundreds of other sites.</p>
  </form>

  <div class="error" id="error" role="alert" hidden><span id="errorText"></span><button type="button" id="errorAction" hidden>Open settings</button></div>

  <section class="video" id="video" hidden aria-live="polite">
    <img class="cover" id="cover" alt="" referrerpolicy="no-referrer">
    <h1 class="title" id="title"></h1>
    <p class="meta" id="meta"></p>
    <p class="notice" id="notice" hidden></p>

    <fieldset class="option">
      <legend>Format</legend>
      <div class="segmented" id="kinds">
        <label><input type="radio" name="kind" value="video" checked><span>Video</span></label>
        <label><input type="radio" name="kind" value="audio"><span>Audio only</span></label>
      </div>
    </fieldset>
    <fieldset class="option" id="qualityGroup">
      <legend>Quality</legend>
      <div class="segmented" id="qualities"></div>
    </fieldset>

    <button class="save" id="save" type="button">
      <span class="layer base"><span class="label"></span></span>
      <span class="layer fill" aria-hidden="true"><span class="label"></span></span>
    </button>
    <p class="status" id="status"></p>
    <div class="actions" id="actions" hidden>
      <button type="button" id="openFile">Open</button>
      <button type="button" id="shareFile">Send to…</button>
    </div>
    <button type="button" class="another" id="another" hidden>Save another video</button>
  </section>
</div>

<dialog id="settings" aria-labelledby="settingsTitle">
  <div class="sheet">
    <div class="grabber"></div>
    <h2 id="settingsTitle">Settings</h2>
    <div class="group">
      <h3>YouTube cookies</h3>
      <p>Use these when YouTube asks for account verification. Export a cookies.txt file with YouTube open and import it here. <span class="state" id="cookieState"></span></p>
      <div class="button-row">
        <label class="secondary strong" for="cookieFile" tabindex="0" role="button">Import cookies.txt</label>
        <input type="file" id="cookieFile" accept=".txt,text/plain" hidden>
        <button type="button" class="secondary" id="cookieRemove" hidden>Remove</button>
      </div>
    </div>
    <div class="group">
      <h3>Download engine</h3>
      <p>Sites change often. If a link stops working, update. <span class="state" id="engineState"></span></p>
      <div class="button-row"><button type="button" class="secondary" id="update">Update engine</button></div>
    </div>
    <button type="button" class="primary close" id="closeSettings">Close</button>
  </div>
</dialog>

<script>
const $ = s => document.querySelector(s);
const native = window.WebSaveAndroid || null;
const ICON_OK = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><path d="m5 12.5 4.5 4.5L19 7.5"/></svg>';
const ICON_SPIN = '<svg class="spin" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round"><path d="M12 3a9 9 0 1 0 9 9"/></svg>';
const state = {url:"", job:null, timer:null, busy:false};

async function api(path, opts={}){
  const r = await fetch(path, opts);
  const d = await r.json().catch(()=>({}));
  if(!r.ok){ const e = new Error(d.error || "The local server didn't respond. Reopen the app."); e.code = d.code; throw e; }
  return d;
}
const postJSON = (path, body) => api(path, {method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify(body)});

function formatDuration(s){
  if(!s) return "";
  s = Math.round(s); const h = Math.floor(s/3600), m = Math.floor(s%3600/60), x = String(s%60).padStart(2,"0");
  return h ? `${h}:${String(m).padStart(2,"0")}:${x}` : `${m}:${x}`;
}
function looksLikeLink(t){ return /^(https?:\/\/)?[\w-]+(\.[\w-]+)+\S*$/i.test((t||"").trim()); }
function extractLink(t){ const m = (t||"").match(/https?:\/\/\S+/); return m ? m[0] : (t||"").trim(); }

function showError(msg, code){
  $("#errorText").textContent = msg;
  $("#errorAction").hidden = code !== "cookies";
  $("#error").hidden = false;
}
function clearError(){ $("#error").hidden = true; }

/* ---------- save button = progress bar ---------- */
function setButton(text, p, {icon="", done=false, enabled=true}={}){
  const b = $("#save");
  b.style.setProperty("--p", p + "%");
  b.classList.toggle("done", done);
  b.disabled = !enabled;
  b.querySelectorAll(".label").forEach(l => l.innerHTML = icon + `<span>${text}</span>`);
  b.setAttribute("aria-label", text);
}
const kind = () => document.querySelector('input[name="kind"]:checked').value;
const quality = () => (document.querySelector('input[name="quality"]:checked')||{}).value || "best";
function saveLabel(){ return kind() === "audio" ? "Save audio" : "Save video"; }
function resetSave(){
  clearInterval(state.timer); state.busy = false; state.job = null;
  setButton(saveLabel(), 100); $("#status").textContent = ""; $("#actions").hidden = true; $("#another").hidden = true;
}

function resolutionLabel(r){ return r >= 2160 ? "4K" : r >= 1440 ? "1440p" : `${r}p`; }
function buildQualities(resolutions){
  // the 4 highest resolutions this video really has
  const list = [...new Set(resolutions)].sort((a,b) => b-a).slice(0,4);
  const options = list.length ? list.map(r => [String(r), resolutionLabel(r)]) : [["best","Original"]];
  $("#qualities").innerHTML = options.map(([v,n],i) =>
    `<label><input type="radio" name="quality" value="${v}" ${i===0?"checked":""}><span>${n}</span></label>`).join("");
}

/* ---------- find ---------- */
async function find(){
  const url = extractLink($("#url").value);
  if(!url){ showError("Paste a link first."); $("#url").focus(); return; }
  $("#url").value = url; updateField();
  clearError(); resetSave();
  const b = $("#find"); b.disabled = true; b.textContent = "Finding…";
  try{
    const d = await postJSON("/api/info", {url});
    state.url = url;
    const cover = $("#cover"); cover.hidden = !d.thumbnail; cover.src = d.thumbnail || "";
    $("#title").textContent = d.title || "Untitled video";
    $("#meta").innerHTML = "";
    [d.channel, d.site, formatDuration(d.duration)].forEach((t,i) => {
      if(!t) return; const s = document.createElement("span"); s.textContent = t; if(i===2) s.className = "duration"; $("#meta").appendChild(s);
    });
    $("#notice").hidden = !d.notice; $("#notice").textContent = d.notice || "";
    buildQualities(d.resolutions || []);
    document.querySelector('input[name="kind"][value="video"]').checked = true;
    $("#qualityGroup").hidden = false;
    resetSave();
    $("#video").hidden = false; $("#hint").hidden = true;
    $("#video").scrollIntoView({behavior: matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth", block:"start"});
  }catch(e){ $("#video").hidden = true; showError(e.message, e.code); }
  b.disabled = false; b.textContent = "Find video";
}

/* ---------- save ---------- */
async function save(){
  if(state.busy) return;
  state.busy = true; clearError();
  $("#actions").hidden = true; $("#another").hidden = true;
  setButton("Preparing…", 0, {icon:ICON_SPIN, enabled:false});
  $("#status").textContent = "Reading the video details.";
  try{
    const {id} = await postJSON("/api/download", {url:state.url, kind:kind(), quality:quality()});
    state.job = id;
    state.timer = setInterval(() => track(id), 600);
  }catch(e){ resetSave(); showError(e.message, e.code); }
}

async function track(id){
  let s; try{ s = await api("/api/status/" + id); }catch(e){ return; }
  if(state.job !== id) return;
  const p = Math.max(2, Math.min(100, s.progress || 0));
  if(s.status === "analyzing"){ setButton("Preparing…", 0, {icon:ICON_SPIN, enabled:false}); }
  else if(s.status === "downloading"){ setButton(`Downloading ${Math.floor(p)}%`, p, {enabled:false}); $("#status").textContent = "You can leave the app; the download keeps going."; }
  else if(s.status === "merging"){ setButton("Merging audio and video", 99, {icon:ICON_SPIN, enabled:false}); $("#status").textContent = "Almost there."; }
  else if(s.status === "saving"){ setButton("Saving", 100, {icon:ICON_SPIN, enabled:false}); }
  else if(s.status === "error"){ resetSave(); showError(s.error, s.code); }
  else if(s.status === "done"){
    clearInterval(state.timer); state.busy = false;
    setButton("Saved", 100, {icon:ICON_OK, done:true, enabled:false});
    $("#another").hidden = false;
    if(native && s.uri){
      $("#status").textContent = `It's in ${s.location}. It already shows up in your gallery and in CapCut.`;
      $("#actions").hidden = false;
      $("#openFile").onclick = () => native.open(s.uri, s.mime);
      $("#shareFile").onclick = () => native.share(s.uri, s.mime);
    }else{
      $("#status").textContent = `${s.filename} was sent to your browser's downloads.`;
      location.href = "/api/file/" + id;
    }
  }
}

/* ---------- link field ---------- */
function updateField(){ const empty = !$("#url").value; $("#clear").hidden = empty; $("#paste").hidden = !empty; }
async function paste(){
  let t = "";
  try{ t = native ? native.paste() : await navigator.clipboard.readText(); }catch(e){}
  if(!t){ showError("The clipboard is empty. Copy the link in the video's app and try again."); return; }
  $("#url").value = extractLink(t); updateField();
  if(looksLikeLink($("#url").value)) find();
}
function receiveLink(t){ $("#url").value = extractLink(t); updateField(); find(); }
window.receiveLink = receiveLink;

$("#form").addEventListener("submit", e => { e.preventDefault(); find(); });
$("#url").addEventListener("input", updateField);
$("#paste").addEventListener("click", paste);
$("#clear").addEventListener("click", () => { $("#url").value = ""; updateField(); $("#url").focus(); });
$("#save").addEventListener("click", save);
$("#another").addEventListener("click", () => {
  resetSave(); $("#video").hidden = true; $("#hint").hidden = false; $("#url").value = ""; updateField();
  window.scrollTo(0,0); $("#url").focus();
});
document.addEventListener("change", e => { if(e.target.name === "kind" || e.target.name === "quality"){
  $("#qualityGroup").hidden = kind() === "audio";
  if(!state.busy) resetSave();
}});

/* ---------- settings ---------- */
async function loadSettings(){
  try{
    const c = await api("/api/config");
    $("#cookieState").textContent = c.cookies ? "Cookies imported." : "No cookies imported.";
    $("#cookieRemove").hidden = !c.cookies;
    $("#engineState").textContent = `Installed version: ${c.engine}.`;
  }catch(e){}
}
function openSettings(){ loadSettings(); $("#settings").showModal(); }
$("#openSettings").addEventListener("click", openSettings);
$("#errorAction").addEventListener("click", openSettings);
$("#closeSettings").addEventListener("click", () => $("#settings").close());
$("#settings").addEventListener("click", e => { if(e.target === $("#settings")) $("#settings").close(); });
document.querySelector('label[for="cookieFile"]').addEventListener("keydown", e => {
  if(e.key === "Enter" || e.key === " "){ e.preventDefault(); $("#cookieFile").click(); }
});
$("#cookieFile").addEventListener("change", async e => {
  const f = e.target.files[0]; if(!f) return;
  try{
    await api("/api/cookies", {method:"POST", body:await f.arrayBuffer()});
    $("#cookieState").textContent = "Cookies imported. Try the link again."; $("#cookieRemove").hidden = false;
  }catch(err){ $("#cookieState").textContent = err.message; }
  e.target.value = "";
});
$("#cookieRemove").addEventListener("click", async () => { await api("/api/cookies", {method:"DELETE"}); loadSettings(); });
$("#update").addEventListener("click", async () => {
  const b = $("#update"); b.disabled = true; b.textContent = "Updating…";
  try{
    const r = await api("/api/update", {method:"POST"});
    $("#engineState").textContent = r.updated
      ? `Version ${r.version} downloaded. Close and reopen WebSave to use it.`
      : `You already have the latest version (${r.version}).`;
  }catch(e){ $("#engineState").textContent = e.message; }
  b.disabled = false; b.textContent = "Update engine";
});

/* ---------- start ---------- */
resetSave(); updateField();
const initial = new URLSearchParams(location.search).get("url");
if(initial){ history.replaceState(null, "", "/"); receiveLink(initial); }
</script>
</body>
</html>"""


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
