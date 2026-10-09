# WebSave

Salva vídeos do YouTube, Instagram, TikTok, X e centenas de outros sites direto na galeria do Android.

## Gerar o APK

Este repositório compila o APK sozinho pelo GitHub Actions a cada envio para `main`.
O arquivo aparece em **Releases** (`WebSave.apk`). Baixe pelo celular e instale.

## Usar no Termux ou no computador (sem APK)

```
pip install -U yt-dlp
python app/src/main/python/websave.py
```

Abra http://127.0.0.1:5000. Instale o ffmpeg para ter vídeo acima de 360p.
