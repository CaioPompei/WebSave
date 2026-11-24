"""
Local file tools for WebSave: photos, PDFs and videos are processed on the device.
Nothing is uploaded: files are copied into the app's cache, worked on, and saved to the gallery.

websave.py sets `core` (itself) and routes /api/tools/* here.
"""
import io
import json
import logging
import mimetypes
import os
import re
import shutil
import subprocess
import threading
import time
import uuid
from urllib.parse import parse_qs, quote, urlparse

core = None          # the websave module (CFG, make_gif, trim_media, ...)
STAGED = {}          # id -> picked file
JOBS = {}            # id -> running or finished tool job
LOCK = threading.Lock()

IMAGE_EXTS = {"jpg", "jpeg", "png", "webp", "heic", "heif", "avif", "gif", "bmp", "tif", "tiff"}
VIDEO_EXTS = {"mp4", "m4v", "mov", "3gp", "mkv", "webm", "avi"}
SIZES = {"original": 0, "large": 2048, "medium": 1280, "small": 800}
VIDEO_PRESETS = {               # short side, video bitrate
    "whatsapp": (720, 2_200_000),
    "small": (480, 900_000),
    "hq": (1080, 5_000_000),
}
AUDIO_BITRATE = 128_000


logging.getLogger("pypdf").setLevel(logging.ERROR)


class ToolError(Exception):
    """A problem worth showing as is: the file is protected, empty, not supported..."""


class Cancelled(Exception):
    pass


# ---------------------------------------------------------------- staging

def stage_root():
    return os.path.join(core.CFG["tmp_dir"], "websave-stage")


def cleanup_stage(max_age=24 * 3600):
    """Forget picked files from earlier days (they are copies; the originals stay where they were)."""
    root = stage_root()
    if not os.path.isdir(root):
        return
    now = time.time()
    for name in os.listdir(root):
        p = os.path.join(root, name)
        try:
            if now - os.path.getmtime(p) > max_age:
                shutil.rmtree(p, ignore_errors=True) if os.path.isdir(p) else os.remove(p)
        except OSError:
            pass


def safe_name(name):
    name = os.path.basename(name or "").strip() or "file"
    name = re.sub(r'[\\/:*?"<>|\x00-\x1f]', "_", name)
    return name[:120]


def kind_of(name, mime=""):
    ext = os.path.splitext(name)[1].lower().lstrip(".")
    mime = (mime or "").lower()
    if ext == "pdf" or mime == "application/pdf":
        return "pdf"
    if ext in IMAGE_EXTS or mime.startswith("image/"):
        return "image"
    if ext in VIDEO_EXTS or mime.startswith("video/"):
        return "video"
    return "other"


def public(item):
    return {k: item[k] for k in ("id", "name", "size", "kind", "meta")}


def register(path, name=None, mime=None):
    name = safe_name(name or os.path.basename(path))
    item = {
        "id": uuid.uuid4().hex[:12], "path": path, "name": name, "mime": mime or mimetypes.guess_type(name)[0] or "",
        "size": os.path.getsize(path), "kind": kind_of(name, mime), "meta": {},
    }
    try:
        item["meta"] = probe(item)
    except Exception:
        item["meta"] = {}
    with LOCK:
        STAGED[item["id"]] = item
    return item


def api_upload(name, data):
    """Desktop: the browser sends the picked file's bytes."""
    if not data:
        return {"error": "The file is empty."}, 400
    folder = os.path.join(stage_root(), uuid.uuid4().hex[:12])
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, safe_name(name))
    with open(path, "wb") as f:
        f.write(data)
    return {"item": public(register(path, name))}, 200


def api_stage(body):
    """Android: the app already copied the picked files into the stage folder."""
    root = os.path.realpath(stage_root())
    items = []
    for f in body.get("files") or []:
        path = os.path.realpath(str(f.get("path") or ""))
        if not path.startswith(root + os.sep) or not os.path.isfile(path):
            continue
        items.append(public(register(path, f.get("name"), f.get("mime"))))
    if not items:
        return {"error": "Couldn't open the selected files."}, 400
    return {"items": items}, 200


def api_items(ids):
    with LOCK:
        return {"items": [public(STAGED[i]) for i in ids if i in STAGED]}, 200


def get_items(ids, kind=None):
    with LOCK:
        items = [STAGED[i] for i in ids if i in STAGED]
    if not items:
        raise ToolError("Pick the files again: they're no longer available.")
    if kind and any(i["kind"] != kind for i in items):
        raise ToolError({"image": "Only photos work here.", "pdf": "Only PDF files work here.",
                         "video": "Only videos work here."}[kind])
    return items


# ---------------------------------------------------------------- reading files

def _native(name):
    return core.CFG.get(name)


def open_image(item):
    """A Pillow image; HEIC/AVIF photos go through Android's decoder first."""
    from PIL import Image
    try:
        img = Image.open(item.get("decoded") or item["path"])
        img.size  # noqa: B018  (forces the header to be read)
        return img
    except Exception:
        decode = _native("decode")
        if decode and not item.get("decoded"):
            out = item["path"] + ".decoded.jpg"
            if decode(item["path"], out):
                item["decoded"] = out
                return Image.open(out)
        raise ToolError(f"“{item['name']}” isn't a photo this phone can open.")


def _rational(v):
    try:
        return float(v)
    except Exception:
        try:
            return v[0] / v[1]
        except Exception:
            return 0.0


def photo_info(img):
    """What a photo carries besides its pixels: location, date, camera."""
    info = {}
    try:
        exif = img.getexif()
    except Exception:
        return info
    try:
        gps = exif.get_ifd(0x8825)
        if gps and 2 in gps and 4 in gps:
            lat = sum(_rational(x) / 60 ** i for i, x in enumerate(gps[2]))
            lon = sum(_rational(x) / 60 ** i for i, x in enumerate(gps[4]))
            if str(gps.get(1, "N")).upper().startswith("S"):
                lat = -lat
            if str(gps.get(3, "E")).upper().startswith("W"):
                lon = -lon
            if lat or lon:
                info["location"] = [round(lat, 5), round(lon, 5)]
    except Exception:
        pass
    try:
        taken = exif.get_ifd(0x8769).get(0x9003) or exif.get(0x0132)
        if taken:
            info["taken"] = str(taken).strip("\x00 ")
    except Exception:
        pass
    camera = " ".join(str(exif.get(t, "")).strip("\x00 ") for t in (0x010F, 0x0110)).strip()
    if camera:
        info["camera"] = camera
    software = str(exif.get(0x0131, "")).strip("\x00 ")
    if software:
        info["software"] = software
    info["extra"] = len(exif) > 0 or bool(img.info.get("xmp") or img.info.get("XML:com.adobe.xmp"))
    return info


def video_info(path):
    """Duration (s), upright width/height, bitrate and whether it has sound."""
    probe_fn = _native("probe")
    if probe_fn:
        d, w, h, br, audio = str(probe_fn(path)).split("|")
        return {"duration": int(d) / 1000, "width": int(w), "height": int(h), "bitrate": int(br), "audio": audio == "1"}
    if shutil.which("ffprobe"):
        out = subprocess.run(["ffprobe", "-v", "error", "-show_entries",
                              "format=duration,bit_rate:stream=codec_type,width,height:stream_side_data=rotation:stream_tags=rotate",
                              "-of", "json", path], capture_output=True, text=True)
        data = json.loads(out.stdout or "{}")
        streams = data.get("streams", [])
        v = next((s for s in streams if s.get("codec_type") == "video"), {})
        w, h = v.get("width", 0), v.get("height", 0)
        rot = abs(int(float((v.get("tags") or {}).get("rotate", 0) or
                            next((sd.get("rotation", 0) for sd in v.get("side_data_list", [])), 0) or 0)))
        if rot in (90, 270):
            w, h = h, w
        fmt = data.get("format", {})
        return {"duration": float(fmt.get("duration") or 0), "width": w, "height": h,
                "bitrate": int(fmt.get("bit_rate") or 0), "audio": any(s.get("codec_type") == "audio" for s in streams)}
    return {}


def pdf_reader(item):
    from pypdf import PdfReader
    try:
        reader = PdfReader(item["path"])
    except Exception:
        raise ToolError(f"“{item['name']}” couldn't be read as a PDF.") from None
    if reader.is_encrypted:
        try:
            ok = reader.decrypt("")
        except Exception:
            ok = 0
        if not ok:
            raise ToolError(f"“{item['name']}” is protected with a password.")
    return reader


def probe(item):
    if item["kind"] == "image":
        img = open_image(item)
        w, h = img.size
        info = photo_info(img)
        try:
            if img.getexif().get(0x0112) in (5, 6, 7, 8):
                w, h = h, w
        except Exception:
            pass
        return {"width": w, "height": h, "format": (img.format or "").lower(), **info}
    if item["kind"] == "pdf":
        try:
            return {"pages": len(pdf_reader(item).pages)}
        except ToolError as e:
            return {"pages": 0, "error": str(e)}
    if item["kind"] == "video":
        return video_info(item["path"])
    return {}


# ---------------------------------------------------------------- thumbnails

def thumbnail(item, page=0, width=320):
    """A small JPEG preview (photo, video frame or PDF page), cached next to the file. None if unavailable."""
    out = f"{item['path']}.t{page}.{width}.jpg"
    if os.path.isfile(out):
        return out
    try:
        if item["kind"] == "image":
            from PIL import Image, ImageOps
            img = open_image(item)
            if img.format == "JPEG":
                img.draft("RGB", (width * 2, width * 2))
            img = ImageOps.exif_transpose(img)
            img.thumbnail((width * 2, width * 2))
            _flatten(img).save(out, "JPEG", quality=80)
            return out
        if item["kind"] == "video":
            fn = _native("video_thumb")
            if fn:
                return out if fn(item["path"], out, width * 2) else None
            if core.HAS_FFMPEG:
                subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", "1", "-i", item["path"], "-frames:v", "1",
                                "-vf", f"scale={width * 2}:-2", out], check=True)
                return out if os.path.isfile(out) else None
        if item["kind"] == "pdf":
            fn = _native("pdf_render")
            if fn:
                return out if fn(item["path"], int(page), width * 2, out) else None
    except Exception:
        return None
    return None


def _flatten(img, background=(255, 255, 255)):
    """RGB copy of any image (transparent areas become white), for JPEG."""
    from PIL import Image
    if img.mode in ("RGBA", "LA", "P"):
        img = img.convert("RGBA")
        base = Image.new("RGB", img.size, background)
        base.paste(img, mask=img.split()[-1])
        return base
    return img.convert("RGB") if img.mode != "RGB" else img


# ---------------------------------------------------------------- photos

def webp_ok():
    try:
        from PIL import features
        return bool(features.check("webp"))
    except Exception:
        return False


def encode_photo(item, size="original", fmt="jpg", quality=82, strip=True):
    """Resize / convert one photo. Returns (bytes, extension)."""
    from PIL import Image, ImageOps
    img = open_image(item)
    limit = SIZES.get(size, 0)
    if limit and img.format == "JPEG":
        img.draft("RGB", (limit, limit))  # decode at a smaller scale: much faster on phones
    img = ImageOps.exif_transpose(img)
    if limit and max(img.size) > limit:
        img.thumbnail((limit, limit), Image.LANCZOS)
    fmt = fmt if fmt in ("jpg", "png", "webp") else "jpg"
    if fmt == "webp" and not webp_ok():
        fmt = "jpg"
    kwargs = {}
    icc = img.info.get("icc_profile")
    if icc:
        kwargs["icc_profile"] = icc
    if not strip:
        try:
            exif = img.getexif()
            exif.pop(0x0112, None)  # pixels are already upright
            kwargs["exif"] = exif.tobytes()
        except Exception:
            pass
    buf = io.BytesIO()
    if fmt == "jpg":
        _flatten(img).save(buf, "JPEG", quality=int(quality), optimize=True, progressive=True, **kwargs)
    elif fmt == "webp":
        if img.mode not in ("RGB", "RGBA"):
            img = img.convert("RGBA" if "A" in img.mode or img.mode == "P" else "RGB")
        img.save(buf, "WEBP", quality=int(quality), method=4, **kwargs)
    else:
        if img.mode not in ("RGB", "RGBA", "L", "LA", "P"):
            img = img.convert("RGBA")
        img.save(buf, "PNG", optimize=True, **kwargs)
    return buf.getvalue(), fmt


def _jpeg_segments(data):
    """Split a JPEG into (marker, payload) segments before the image data, plus the rest."""
    if data[:2] != b"\xff\xd8":
        return None, None
    segs, i = [], 2
    while i + 4 <= len(data):
        if data[i] != 0xFF:
            return None, None
        marker = data[i + 1]
        if marker == 0xD9 or marker == 0xDA:  # end of image / start of scan: the rest is image data
            return segs, data[i:]
        if 0xD0 <= marker <= 0xD7 or marker == 0x01:
            segs.append((marker, b""))
            i += 2
            continue
        length = int.from_bytes(data[i + 2:i + 4], "big")
        segs.append((marker, data[i + 4:i + 2 + length]))
        i += 2 + length
    return None, None


def _exif_without_location(payload):
    from PIL import Image
    exif = Image.Exif()
    exif.load(payload)
    if 0x8825 not in exif:
        return payload
    del exif[0x8825]
    return exif.tobytes()


def clean_jpeg(data, everything):
    """Remove the location (or all hidden info) from a JPEG without re-encoding it: no quality loss."""
    segs, rest = _jpeg_segments(data)
    if segs is None:
        return None
    out = [b"\xff\xd8"]
    for marker, payload in segs:
        if marker == 0xE1:  # APP1: EXIF or XMP
            if payload.startswith(b"Exif\x00\x00"):
                if everything:
                    continue
                try:
                    payload = _exif_without_location(payload)
                except Exception:
                    continue  # unreadable EXIF: drop it rather than risk keeping the location
            else:
                continue  # XMP can repeat the location
        elif marker in (0xED, 0xFE) and everything:  # Photoshop/IPTC, comments
            continue
        elif 0xE3 <= marker <= 0xEF and marker != 0xEE and everything:  # other app data (not ICC/Adobe)
            continue
        if marker in range(0xD0, 0xD8) or marker == 0x01:
            out.append(bytes([0xFF, marker]))
        else:
            out.append(bytes([0xFF, marker]) + (len(payload) + 2).to_bytes(2, "big") + payload)
    out.append(rest)
    return b"".join(out)


def clean_photo(item, everything):
    """Returns (bytes, extension) of a copy without location (or without any hidden info)."""
    with open(item["path"], "rb") as f:
        data = f.read()
    if data[:2] == b"\xff\xd8":
        cleaned = clean_jpeg(data, everything)
        if cleaned:
            return cleaned, "jpg"
    from PIL import ImageOps
    img = ImageOps.exif_transpose(open_image(item))
    fmt = (img.format or "").lower()
    kwargs = {}
    if not everything:
        try:
            exif = img.getexif()
            exif.pop(0x8825, None)
            exif.pop(0x0112, None)
            kwargs["exif"] = exif.tobytes()
        except Exception:
            pass
    if img.info.get("icc_profile"):
        kwargs["icc_profile"] = img.info["icc_profile"]
    buf = io.BytesIO()
    if fmt == "png" or (img.mode in ("RGBA", "LA", "P") and fmt != "webp"):
        img.save(buf, "PNG", optimize=True, **kwargs)
        return buf.getvalue(), "png"
    if fmt == "webp" and webp_ok():
        img.save(buf, "WEBP", quality=95, **kwargs)
        return buf.getvalue(), "webp"
    _flatten(img).save(buf, "JPEG", quality=95, **kwargs)
    return buf.getvalue(), "jpg"


A4 = (1240, 1754)  # 150 dpi


def photos_to_pdf(items, target, page="fit"):
    from PIL import Image, ImageOps
    pages = []
    for item in items:
        img = open_image(item)
        if img.format == "JPEG":
            img.draft("RGB", (2400, 2400))
        img = _flatten(ImageOps.exif_transpose(img))
        if page == "a4":
            w, h = A4 if img.height >= img.width else A4[::-1]
            margin = 60
            img.thumbnail((w - 2 * margin, h - 2 * margin), Image.LANCZOS)
            sheet = Image.new("RGB", (w, h), (255, 255, 255))
            sheet.paste(img, ((w - img.width) // 2, (h - img.height) // 2))
            pages.append(sheet)
        else:
            # every page 11.7 inches on its long side, whatever the photo's pixel size
            scale = 2000 / max(img.size)
            if scale < 1:
                img = img.resize((round(img.width * scale), round(img.height * scale)), Image.LANCZOS)
            elif scale > 1:
                img = img.resize((round(img.width * scale), round(img.height * scale)), Image.BICUBIC)
            pages.append(img)
    resolution = 150.0 if page == "a4" else 2000 / 11.69
    pages[0].save(target, "PDF", save_all=True, append_images=pages[1:], resolution=resolution, quality=85)


# ---------------------------------------------------------------- PDF

def _writer():
    from pypdf import PdfWriter
    return PdfWriter()


def _write(writer, target):
    try:
        for page in writer.pages:
            page.compress_content_streams()
    except Exception:
        pass
    with open(target, "wb") as f:
        writer.write(f)


def pages_label(pages):
    """[0,1,2,5] -> '1-3, 6'"""
    out, start = [], None
    nums = [p + 1 for p in pages]
    for i, n in enumerate(nums):
        if start is None:
            start = n
        if i == len(nums) - 1 or nums[i + 1] != n + 1:
            out.append(str(start) if start == n else f"{start}-{n}")
            start = None
    return ", ".join(out)


def compress_pdf(item, target, level):
    from PIL import Image
    from pypdf import PdfWriter
    reader = pdf_reader(item)
    limit, quality = (1100, 50) if level == "smallest" else (1600, 72)
    writer = PdfWriter(clone_from=reader)
    for page in writer.pages:
        try:
            images = list(page.images)
        except Exception:
            images = []
        for image in images:
            try:
                pil = image.image
                if max(pil.size) < 200:
                    continue  # icons and logos: not worth it
                if max(pil.size) > limit:
                    pil.thumbnail((limit, limit), Image.LANCZOS)
                pil = pil.convert("L") if pil.mode in ("1", "L", "LA") else _flatten(pil)
                image.replace(pil, quality=quality)
            except Exception:
                continue
        try:
            page.compress_content_streams()
        except Exception:
            pass
    try:
        writer.compress_identical_objects(remove_identicals=True, remove_orphans=True)
    except Exception:
        pass
    with open(target, "wb") as f:
        writer.write(f)


# ---------------------------------------------------------------- video

def _even(n):
    return max(2, int(round(n / 2)) * 2)


def video_plan(meta, preset, limit_mb=16, mute=False, start=None, end=None):
    """Output size and bitrate for a compression preset: (width, height, video_bitrate, estimated_bytes)."""
    w, h = meta.get("width") or 1280, meta.get("height") or 720
    duration = (end - start) if (start is not None and end) else (meta.get("duration") or 0)
    audio = 0 if mute or not meta.get("audio", True) else AUDIO_BITRATE
    if preset == "limit":
        vbr = int(max(250_000, (limit_mb * 1_000_000 * 8 * 0.92 / max(duration, 1)) - audio))
        short = 1080 if vbr >= 4_000_000 else 720 if vbr >= 1_500_000 else 480 if vbr >= 700_000 else 360
    else:
        short, vbr = VIDEO_PRESETS.get(preset, VIDEO_PRESETS["whatsapp"])
    src_short = min(w, h)
    scale = min(1.0, short / src_short) if src_short else 1.0
    src_br = meta.get("bitrate") or 0
    if src_br:
        vbr = min(vbr, max(250_000, int(src_br * 0.85)))
    out_w, out_h = _even(w * scale), _even(h * scale)
    return out_w, out_h, vbr, int((vbr + audio) * duration / 8)


def compress_video(job, item, target, preset, limit_mb, mute, start, end):
    meta = item["meta"] or video_info(item["path"])
    out_w, out_h, vbr, _ = video_plan(meta, preset, limit_mb, mute, start, end)
    fn = _native("transcode")
    if fn:
        job["native_cancel"] = _native("transcode_cancel")
        done = threading.Event()

        def poll():
            while not done.wait(0.5):
                try:
                    job["progress"] = max(job["progress"], float(_native("transcode_progress")()))
                except Exception:
                    pass
        threading.Thread(target=poll, daemon=True).start()
        try:
            fn(item["path"], target, out_h, vbr, bool(mute), int((start or 0) * 1000), int(end * 1000) if end else -1)
        except Exception as e:
            if job.get("cancel"):
                raise Cancelled() from None
            raise ToolError(f"Couldn't compress this video: {e}") from None
        finally:
            done.set()
            job.pop("native_cancel", None)
        return
    if not core.HAS_FFMPEG:
        raise ToolError("Compressing videos needs ffmpeg. Install it with: pkg install ffmpeg")
    cut = (["-ss", f"{start:.3f}"] if start else []) + (["-to", f"{end:.3f}"] if end else [])
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-progress", "pipe:1", *cut, "-i", item["path"],
           "-vf", f"scale={out_w}:{out_h}", "-c:v", "libx264", "-preset", "veryfast", "-b:v", str(vbr),
           "-maxrate", str(int(vbr * 1.3)), "-bufsize", str(vbr * 2), "-pix_fmt", "yuv420p",
           *(["-an"] if mute else ["-c:a", "aac", "-b:a", "128k"]), "-movflags", "+faststart", target]
    total = ((end or meta.get("duration") or 0) - (start or 0)) or 1
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    job["proc"] = proc
    for line in proc.stdout:
        if line.startswith("out_time_ms="):
            try:
                job["progress"] = min(99.0, int(line.split("=")[1]) / 1e6 / total * 100)
            except ValueError:
                pass
    proc.wait()
    job.pop("proc", None)
    if job.get("cancel"):
        raise Cancelled()
    if proc.returncode != 0:
        raise ToolError("Couldn't compress this video.")


def extract_audio(item, folder):
    base = os.path.join(folder, os.path.splitext(item["name"])[0])
    fn = core.CFG.get("audio")
    if fn:
        try:
            return str(fn(item["path"], base))
        except Exception as e:
            if "NO_AUDIO" in str(e):
                raise ToolError(f"“{item['name']}” has no sound.") from None
            raise
    if not core.HAS_FFMPEG:
        raise ToolError("Extracting audio needs ffmpeg. Install it with: pkg install ffmpeg")
    if not video_info(item["path"]).get("audio"):
        raise ToolError(f"“{item['name']}” has no sound.")
    out = base + ".m4a"
    if subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", item["path"], "-vn", "-c:a", "copy", out]).returncode:
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", item["path"], "-vn", "-c:a", "aac", "-b:a", "192k", out],
                       check=True)
    return out


# ---------------------------------------------------------------- jobs

def _stem(item):
    return os.path.splitext(item["name"])[0][:80] or "file"


def _write_bytes(folder, name, data):
    path = os.path.join(folder, name)
    with open(path, "wb") as f:
        f.write(data)
    return path


def _unique(folder, name):
    stem, ext = os.path.splitext(name)
    candidate, n = name, 2
    while os.path.exists(os.path.join(folder, candidate)):
        candidate = f"{stem} ({n}){ext}"
        n += 1
    return os.path.join(folder, candidate)


def _check(job):
    if job.get("cancel"):
        raise Cancelled()


TOOL_KINDS = {"resize": "image", "convert": "image", "privacy": "image", "img2pdf": "image",
              "merge": "pdf", "split": "pdf", "organize": "pdf", "pdfcompress": "pdf",
              "vcompress": "video", "trim": "video", "gif": "video", "audio": "video"}


def run_tool(job, tool, items, o, folder):
    """Do the work; returns the files made, as paths inside `folder`."""
    if tool not in TOOL_KINDS:
        raise ToolError("Unknown tool.")
    get_items([i["id"] for i in items], TOOL_KINDS[tool])
    out = []
    n = len(items)

    def step(i):
        _check(job)
        job["progress"] = i / n * 100

    if tool in ("resize", "convert"):
        for i, item in enumerate(items):
            step(i)
            size = o.get("size", "original") if tool == "resize" else "original"
            quality = o.get("quality", 82) if tool == "resize" else 92
            data, ext = encode_photo(item, size, o.get("format", "jpg"), quality, o.get("strip", True))
            out.append(_write_bytes(folder, os.path.basename(_unique(folder, f"{_stem(item)}.{ext}")), data))
    elif tool == "privacy":
        for i, item in enumerate(items):
            step(i)
            data, ext = clean_photo(item, o.get("mode") == "all")
            out.append(_write_bytes(folder, os.path.basename(_unique(folder, f"{_stem(item)}.{ext}")), data))
    elif tool == "img2pdf":
        target = _unique(folder, f"{_stem(items[0])}.pdf")
        photos_to_pdf(items, target, o.get("page", "fit"))
        out.append(target)
    elif tool == "merge":
        writer = _writer()
        for i, item in enumerate(items):
            step(i)
            writer.append(pdf_reader(item))
        target = _unique(folder, f"{_stem(items[0])} (merged).pdf")
        _write(writer, target)
        out.append(target)
    elif tool == "split":
        item = items[0]
        reader = pdf_reader(item)
        total = len(reader.pages)
        pages = [p for p in (o.get("pages") or []) if 0 <= p < total]
        if o.get("mode") == "each":
            for p in range(total):
                _check(job)
                job["progress"] = p / total * 100
                writer = _writer()
                writer.add_page(reader.pages[p])
                target = _unique(folder, f"{_stem(item)} (page {p + 1}).pdf")
                _write(writer, target)
                out.append(target)
        else:
            if not pages:
                raise ToolError("Select the pages to keep.")
            writer = _writer()
            for p in sorted(pages):
                writer.add_page(reader.pages[p])
            target = _unique(folder, f"{_stem(item)} (pages {pages_label(sorted(pages))}).pdf")
            _write(writer, target)
            out.append(target)
    elif tool == "organize":
        item = items[0]
        reader = pdf_reader(item)
        order = o.get("pages") or [{"p": p, "r": 0} for p in range(len(reader.pages))]
        if not order:
            raise ToolError("There are no pages left to save.")
        writer = _writer()
        for entry in order:
            page = writer.add_page(reader.pages[int(entry["p"])])
            if int(entry.get("r", 0)) % 360:
                page.rotate(int(entry["r"]) % 360)
        target = _unique(folder, f"{_stem(item)} (edited).pdf")
        _write(writer, target)
        out.append(target)
    elif tool == "pdfcompress":
        for i, item in enumerate(items):
            step(i)
            target = _unique(folder, f"{_stem(item)} (compressed).pdf")
            compress_pdf(item, target, o.get("level", "balanced"))
            if os.path.getsize(target) >= item["size"] * 0.97:
                shutil.copyfile(item["path"], target)
                job["note"] = "Already as small as it gets."
            out.append(target)
    elif tool == "vcompress":
        for i, item in enumerate(items):
            _check(job)
            base = i / n * 100
            target = _unique(folder, f"{_stem(item)} (compressed).mp4")
            sub = {"progress": 0.0, "cancel": False}
            job["sub"] = sub

            start, end = (o.get("start"), o.get("end")) if n == 1 and o.get("trim") else (None, None)
            watcher_stop = threading.Event()

            def watch(sub=sub, base=base):
                while not watcher_stop.wait(0.4):
                    job["progress"] = base + sub["progress"] / n
                    if job.get("cancel") and not sub["cancel"]:
                        sub["cancel"] = True
                        if sub.get("native_cancel"):
                            sub["native_cancel"]()
                        if sub.get("proc"):
                            sub["proc"].kill()
            threading.Thread(target=watch, daemon=True).start()
            try:
                compress_video(sub, item, target, o.get("preset", "whatsapp"), float(o.get("limit_mb", 16)),
                               o.get("mute", False), start, end)
            finally:
                watcher_stop.set()
            if sub["cancel"]:
                raise Cancelled()
            out.append(target)
    elif tool == "trim":
        item = items[0]
        start, end = float(o.get("start", 0)), float(o.get("end", 0))
        if end - start < 0.5:
            raise ToolError("Choose a longer part.")
        ext = ".mp4" if core.CFG.get("trim") else os.path.splitext(item["name"])[1] or ".mp4"
        target = _unique(folder, f"{_stem(item)} (clip){ext}")
        core.trim_media(item["path"], target, start, end)
        out.append(target)
    elif tool == "gif":
        item = items[0]
        start, end = float(o.get("start", 0)), float(o.get("end", 0)) or None
        target = _unique(folder, f"{_stem(item)}.gif")
        core.make_gif(item["path"], target, int(o.get("width", 480)), start or None, end)
        out.append(target)
    elif tool == "audio":
        for i, item in enumerate(items):
            step(i)
            out.append(extract_audio(item, folder))
    else:
        raise ToolError("Unknown tool.")
    return out


def _mime(path):
    name = os.path.basename(path).lower()
    if name.endswith(".m4a"):
        return "audio/mp4"
    return mimetypes.guess_type(name)[0] or "application/octet-stream"


def _run(job, tool, items, options):
    folder = os.path.join(stage_root(), "out-" + job["id"])
    os.makedirs(folder, exist_ok=True)
    try:
        paths = run_tool(job, tool, items, options, folder)
        job["status"] = "saving"
        outputs = []
        for path in paths:
            out = {"id": uuid.uuid4().hex[:12], "name": os.path.basename(path), "size": os.path.getsize(path),
                   "mime": _mime(path)}
            save = core.CFG.get("save")
            if save:
                uri, location = str(save(path, out["name"])).split("|", 1)
                out.update(uri=uri, location=location)
            else:
                out["path"] = path
                out["location"] = folder
            outputs.append(out)
        job.update(outputs=[{k: v for k, v in o.items() if k != "path"} for o in outputs], _outputs=outputs,
                   after=sum(o["size"] for o in outputs), status="done", progress=100)
    except Cancelled:
        job.update(status="cancelled")
    except ToolError as e:
        job.update(status="error", error=str(e))
    except Exception as e:
        job.update(status="error", error=f"Something went wrong: {e}")
    finally:
        if core.CFG.get("save"):
            shutil.rmtree(folder, ignore_errors=True)


def api_run(body):
    tool = body.get("tool")
    try:
        items = get_items(body.get("ids") or [])
    except ToolError as e:
        return {"error": str(e)}, 400
    job = {"id": uuid.uuid4().hex[:12], "tool": tool, "status": "working", "progress": 0.0, "error": None,
           "before": sum(i["size"] for i in items), "after": 0, "outputs": [], "count": len(items)}
    JOBS[job["id"]] = job
    threading.Thread(target=_run, args=(job, tool, items, body.get("options") or {}), daemon=True).start()
    return {"id": job["id"]}, 200


def api_job(job_id):
    job = JOBS.get(job_id)
    if not job:
        return {"error": "Not found."}, 404
    return {k: v for k, v in job.items() if not k.startswith("_") and k not in ("sub", "proc", "native_cancel")}, 200


def api_cancel(job_id):
    job = JOBS.get(job_id)
    if job:
        job["cancel"] = True
    return {"ok": True}, 200


def api_estimate(body):
    """Size after resizing/converting photos, measured on a couple of them and scaled to the rest."""
    try:
        items = get_items(body.get("ids") or [], "image")
    except ToolError as e:
        return {"error": str(e)}, 400
    o = body.get("options") or {}
    tool = body.get("tool", "resize")
    before = sum(i["size"] for i in items)
    sample = items[:2]
    ratios = []
    for item in sample:
        size = o.get("size", "original") if tool == "resize" else "original"
        quality = o.get("quality", 82) if tool == "resize" else 92
        data, _ = encode_photo(item, size, o.get("format", "jpg"), quality, o.get("strip", True))
        ratios.append(len(data) / max(1, item["size"]))
    ratio = sum(ratios) / len(ratios)
    return {"before": before, "after": int(before * ratio)}, 200


def caps():
    app = bool(core.CFG.get("app"))
    return {"webp": webp_ok(), "pdf_pages": bool(core.CFG.get("pdf_render")),
            "video": app or core.HAS_FFMPEG, "app": app}


# ---------------------------------------------------------------- HTTP

def _send_file(handler, path, mime, download_name=None):
    size = os.path.getsize(path)
    start, end = 0, size - 1
    rng = handler.headers.get("Range")
    status = 200
    if rng and rng.startswith("bytes="):
        a, _, b = rng[6:].partition("-")
        try:
            if a:
                start = int(a)
                end = int(b) if b else size - 1
            else:
                start = size - int(b)
            end = min(end, size - 1)
            status = 206
        except ValueError:
            start, end = 0, size - 1
    handler.send_response(status)
    handler.send_header("Content-Type", mime or "application/octet-stream")
    handler.send_header("Accept-Ranges", "bytes")
    handler.send_header("Content-Length", str(end - start + 1))
    if status == 206:
        handler.send_header("Content-Range", f"bytes {start}-{end}/{size}")
    if download_name:
        handler.send_header("Content-Disposition", "attachment; filename*=UTF-8''" + quote(download_name))
    handler.end_headers()
    with open(path, "rb") as f:
        f.seek(start)
        left = end - start + 1
        while left > 0:
            chunk = f.read(min(1 << 20, left))
            if not chunk:
                break
            try:
                handler.wfile.write(chunk)
            except (BrokenPipeError, ConnectionResetError):
                return
            left -= len(chunk)


def handle_get(handler, path):
    q = parse_qs(urlparse(handler.path).query)
    parts = path.split("/")  # ["", "api", "tools", what, id]
    what = parts[3] if len(parts) > 3 else ""
    key = parts[4] if len(parts) > 4 else ""
    if what == "items":
        return handler._json(api_items((q.get("ids") or [""])[0].split(",")))
    if what == "job":
        return handler._json(api_job(key))
    if what == "caps":
        return handler._json((caps(), 200))
    if what in ("thumb", "file"):
        item = STAGED.get(key)
        if not item:
            return handler._json(({"error": "Not found."}, 404))
        if what == "file":
            return _send_file(handler, item["path"], item["mime"])
        thumb = thumbnail(item, int((q.get("p") or ["0"])[0]), int((q.get("w") or ["320"])[0]))
        if not thumb:
            return handler._json(({"error": "No preview."}, 404))
        return _send_file(handler, thumb, "image/jpeg")
    if what == "out":
        for job in JOBS.values():
            for o in job.get("_outputs", []):
                if o["id"] == key and o.get("path") and os.path.isfile(o["path"]):
                    return _send_file(handler, o["path"], o["mime"], o["name"])
        return handler._json(({"error": "Not found."}, 404))
    handler._json(({"error": "Not found."}, 404))


def handle_post(handler, path):
    what = path.split("/")[3] if path.count("/") >= 3 else ""
    if what == "upload":
        name = handler.headers.get("X-Name") or "file"
        try:
            from urllib.parse import unquote
            name = unquote(name)
        except Exception:
            pass
        return handler._json(api_upload(name, handler._body()))
    body = handler._json_body()
    if what == "stage":
        return handler._json(api_stage(body))
    if what == "run":
        return handler._json(api_run(body))
    if what == "estimate":
        try:
            return handler._json(api_estimate(body))
        except ToolError as e:
            return handler._json(({"error": str(e)}, 400))
        except Exception as e:
            return handler._json(({"error": str(e)}, 500))
    if what == "cancel":
        return handler._json(api_cancel(body.get("id")))
    handler._json(({"error": "Not found."}, 404))
