# WebSave

Save videos from YouTube, Instagram, TikTok, X and hundreds of other sites straight to your Android gallery.

## Features

- Paste a link or share it from any app with **Share → WebSave**
- Pick the format (video or audio only) and the quality the video actually offers, with file sizes
- Saves H.264 + AAC MP4 files to the gallery's WebSave album (`Pictures/WebSave`, audio to `Music/WebSave`), ready for WhatsApp and CapCut
- Silent clips (GIFs on X, Reddit, Imgur, Giphy, Tenor) are saved as real animated GIFs
- **Library** keeps every download: open it, send it to another app, save it again in another quality or remove it
- Downloads keep running in the background and can be cancelled
- Import YouTube cookies and update the download engine (yt-dlp) from Settings

## Build

GitHub Actions builds the APK on every push to `main`:

1. Compiles [QuickJS-ng](https://github.com/quickjs-ng/quickjs) for Android (YouTube needs a JavaScript runtime)
2. Builds the app with Gradle and [Chaquopy](https://chaquo.com/chaquopy/) (Python on Android)
3. Publishes `WebSave.apk` under **Releases**

## Run on desktop or Termux

```
pip install -U "yt-dlp[default]"
python app/src/main/python/websave.py
```

Then open http://127.0.0.1:5000. Install ffmpeg for qualities above 360p, and a JavaScript
runtime (Deno, Node.js or QuickJS) for full YouTube support.

## Project layout

| Path | What it is |
| --- | --- |
| `app/src/main/python/websave.py` | Local server, yt-dlp logic, history |
| `app/src/main/python/websave_ui.py` | The whole interface (one HTML page) |
| `app/src/main/java/app/websave/MainActivity.kt` | WebView host, share intent, Python startup |
| `app/src/main/java/app/websave/Native.kt` | Audio/video muxing and saving to the gallery |
| `app/src/main/java/app/websave/JsBridge.kt` | Clipboard, open and share for the page |
