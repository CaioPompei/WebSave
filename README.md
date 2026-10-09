# WebSave

Save videos from YouTube, Instagram, TikTok, X and hundreds of other sites straight to your Android gallery.

## Features

- **Save from anywhere**: share a link to WebSave from any app and a small sheet saves it without leaving that app; progress shows in the notifications
- **Quick Settings tile and icon shortcut** ("Save link") for whatever link you copied, plus a "Link copied" card when you open the app
- **Trim** before saving (videos, audio and GIFs)
- **Presets**: For CapCut, For WhatsApp, 60 s clip, Music
- Pick the format (video, GIF or audio) and the quality the video actually offers, with file sizes
- Silent clips (GIFs on X, Reddit, Imgur, Giphy, Tenor) are saved as real animated GIFs
- **Playlists and carousels**: choose which items to save
- **Music with cover art**: audio files get title, artist and cover
- **Save cover image** of any video
- **Library** with search and filters (videos, GIFs, audio)
- **Smart queue**: 2 downloads at a time, automatic retries, optional "only on Wi-Fi"
- **Self-updating engine**: yt-dlp updates itself once a week
- Runs on Android 8 and up, 64-bit and 32-bit ARM, with a light mode for phones under 3 GB of RAM
- Saves to the gallery's WebSave album (`Pictures/WebSave`, audio to `Music/WebSave`)

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
