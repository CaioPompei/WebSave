"""
WebSave: salva vídeos da web usando yt-dlp.

No computador ou no Termux:   pip install yt-dlp   e depois   python websave.py
(abre http://127.0.0.1:5000)
No APK: o app Android chama start() e mostra a interface num WebView.
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
TEM_FFMPEG = shutil.which("ffmpeg") is not None
CFG = {
    "app": False,                                   # True quando roda dentro do APK
    "dados": os.path.dirname(os.path.abspath(__file__)),
    "tmp": tempfile.gettempdir(),
    "juntar": None,                                 # função nativa (Android) para juntar vídeo + áudio
    "salvar": None,                                 # função nativa (Android) para salvar na galeria
}

# ---------------------------------------------------------------- motor (yt-dlp)

_yt = None


def _motor_dir():
    return os.path.join(CFG["dados"], "motor")


def yt():
    """Importa o yt-dlp, preferindo uma versão mais nova baixada pelo botão 'Atualizar motor'."""
    global _yt
    if _yt is None:
        rodas = sorted(glob.glob(os.path.join(_motor_dir(), "yt_dlp-*.whl")))
        if rodas:
            sys.path.insert(0, rodas[-1])
        import yt_dlp
        _yt = yt_dlp
    return _yt


def _ssl_ctx():
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        return ssl.create_default_context()


def cookies_path():
    for p in (
        os.path.join(CFG["dados"], "cookies.txt"),
        os.path.expanduser("~/cookies.txt"),
        os.path.expanduser("~/storage/downloads/cookies.txt"),
    ):
        if os.path.isfile(p):
            return p
    return None


def base_opts():
    o = {"quiet": True, "no_warnings": True, "noprogress": True, "no_color": True, "noplaylist": True}
    c = cookies_path()
    if c:
        o["cookiefile"] = c
    return o


def traduzir_erro(e):
    m = str(e).replace("ERROR: ", "").strip()
    baixo = m.lower()
    if "not a bot" in baixo or "sign in to confirm" in baixo:
        if cookies_path():
            return ("O YouTube pediu verificação e os cookies importados não foram aceitos. "
                    "Exporte um cookies.txt novo e importe de novo em Ajustes.", "cookies")
        return ("O YouTube pediu verificação de conta. Importe seus cookies em Ajustes e tente de novo.", "cookies")
    if "unsupported url" in baixo:
        return ("Esse link não é suportado. Confira se ele abre um vídeo no navegador.", None)
    if "private" in baixo:
        return ("Esse vídeo é privado. Só dá para salvar vídeos que abrem sem login.", None)
    if "urlopen error" in baixo or "getaddrinfo" in baixo or "timed out" in baixo:
        return ("Sem conexão com o site. Verifique a internet e tente de novo.", None)
    if "http error 404" in baixo or "unable to download webpage" in baixo:
        return ("Esse endereço não abriu. Confira se o link está completo e se o vídeo ainda existe.", None)
    if "requested format is not available" in baixo:
        return ("Essa qualidade não está disponível para esse vídeo. Escolha outra.", None)
    return (m or "Falha desconhecida ao processar o link.", None)


def _primeiro_video(info):
    if info.get("_type") == "playlist":
        itens = [e for e in (info.get("entries") or []) if e]
        if not itens:
            raise RuntimeError("Nenhum vídeo encontrado nesse link.")
        return itens[0]
    return info


# ---------------------------------------------------------------- escolha de formato

def _pode_juntar():
    return TEM_FFMPEG or CFG["juntar"] is not None


def escolher(info, formato, qualidade):
    """Prefere H.264 + AAC em MP4, que a galeria, o WhatsApp e o CapCut aceitam."""
    fmts = info.get("formats") or []
    limite = {"1080": 1080, "720": 720, "480": 480}.get(qualidade)

    def cabe(f):
        return not limite or (f.get("height") or 0) <= limite

    def so_audio(f):
        return f.get("vcodec") == "none" and f.get("acodec") not in (None, "none")

    def taxa(f):
        return f.get("abr") or f.get("tbr") or 0

    if formato == "audio":
        auds = [f for f in fmts if so_audio(f)]
        m4a = [f for f in auds if f.get("ext") == "m4a"]
        pool = m4a or auds
        return ("unico", max(pool, key=taxa)["format_id"] if pool else "ba/b")

    if _pode_juntar():
        vids = [f for f in fmts if f.get("acodec") == "none" and f.get("ext") == "mp4"
                and (f.get("vcodec") or "").startswith("avc1") and cabe(f)]
        auds = [f for f in fmts if so_audio(f) and f.get("ext") == "m4a"]
        if vids and auds:
            v = max(vids, key=lambda f: (f.get("height") or 0, f.get("tbr") or 0))
            return ("juntar", (v["format_id"], max(auds, key=taxa)["format_id"]))

    juntos = [f for f in fmts if f.get("vcodec") not in (None, "none")
              and f.get("acodec") not in (None, "none") and cabe(f)]
    if juntos:
        pool = [f for f in juntos if f.get("ext") == "mp4"] or juntos
        return ("unico", max(pool, key=lambda f: (f.get("height") or 0, f.get("tbr") or 0))["format_id"])
    h = f"[height<={limite}]" if limite else ""
    return ("unico", f"b{h}[ext=mp4]/b{h}/b")


# ---------------------------------------------------------------- rotas

SITES = {"Youtube": "YouTube", "Twitter": "X", "TikTok": "TikTok", "Instagram": "Instagram",
         "Facebook": "Facebook", "Vimeo": "Vimeo", "Generic": None, "Reddit": "Reddit"}


def r_config():
    try:
        versao = yt().version.__version__
    except Exception:
        versao = "?"
    return {"app": CFG["app"], "cookies": bool(cookies_path()), "ffmpeg": TEM_FFMPEG, "motor": versao}, 200


def r_info(d):
    url = (d.get("url") or "").strip()
    if not url:
        return {"erro": "Cole um link antes de buscar."}, 400
    try:
        with yt().YoutubeDL(base_opts()) as y:
            v = _primeiro_video(y.extract_info(url, download=False))
        alturas = sorted({f.get("height") for f in v.get("formats") or [] if f.get("height")}, reverse=True)
        return {
            "titulo": v.get("title"),
            "thumb": v.get("thumbnail"),
            "duracao": v.get("duration"),
            "canal": v.get("uploader") or v.get("channel"),
            "site": SITES.get(v.get("extractor_key"), v.get("extractor_key")),
            "alturas": alturas,
        }, 200
    except Exception as e:
        texto, codigo = traduzir_erro(e)
        return {"erro": texto, "codigo": codigo}, 400


def _baixar(job_id, url, formato, qualidade):
    job = JOBS[job_id]
    pasta = tempfile.mkdtemp(prefix="websave_", dir=CFG["tmp"])
    faixa = {"ini": 0.0, "peso": 100.0}

    def hook(p):
        if p.get("status") == "downloading":
            total = p.get("total_bytes") or p.get("total_bytes_estimate")
            if total:
                job["progress"] = round(faixa["ini"] + p.get("downloaded_bytes", 0) / total * faixa["peso"], 1)

    def baixar_fmt(info, fmt, prefixo):
        opts = {**base_opts(), "format": fmt, "progress_hooks": [hook],
                "outtmpl": os.path.join(pasta, prefixo + ".%(ext)s")}
        with yt().YoutubeDL(opts) as y:
            y.process_ie_result(y.sanitize_info(info, remove_private_keys=False), download=True)
        feitos = [os.path.join(pasta, f) for f in os.listdir(pasta)
                  if f.startswith(prefixo + ".") and not f.endswith((".part", ".ytdl"))]
        if not feitos:
            raise RuntimeError("O download terminou sem gerar arquivo.")
        return max(feitos, key=os.path.getsize)

    def unico(info, fmt):
        u = baixar_fmt(info, fmt, "u")
        final = os.path.join(pasta, nome + os.path.splitext(u)[1])
        os.replace(u, final)
        return final

    try:
        job["status"] = "analisando"
        with yt().YoutubeDL(base_opts()) as y:
            info = _primeiro_video(y.extract_info(url, download=False))
        nome = yt().utils.sanitize_filename(info.get("title") or "video")[:120].strip() or "video"
        modo, sel = escolher(info, formato, qualidade)

        job["status"] = "baixando"
        if modo == "juntar":
            faixa.update(ini=0, peso=85)
            v = baixar_fmt(info, sel[0], "v")
            faixa.update(ini=85, peso=13)
            a = baixar_fmt(info, sel[1], "a")
            job.update(status="juntando", progress=99)
            final = os.path.join(pasta, nome + ".mp4")
            try:
                if CFG["juntar"]:
                    CFG["juntar"](v, a, final)
                else:
                    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", v, "-i", a, "-map", "0:v:0",
                                    "-map", "1:a:0", "-c", "copy", "-movflags", "+faststart", final], check=True)
            except Exception:
                # se não conseguir juntar, baixa a melhor versão que já vem com áudio
                job.update(status="baixando", progress=0)
                faixa.update(ini=0, peso=100)
                final = unico(info, "b[ext=mp4]/b")
            for f in (v, a):
                if os.path.exists(f):
                    os.remove(f)
        else:
            final = unico(info, sel)

        filename = os.path.basename(final)
        mime = mimetypes.guess_type(filename)[0] or ("audio/mp4" if filename.endswith(".m4a") else "video/mp4")
        job.update(filename=filename, mime=mime)
        if CFG["salvar"]:
            job["status"] = "salvando"
            uri, local = str(CFG["salvar"](final, filename)).split("|", 1)
            job.update(uri=uri, local=local)
            shutil.rmtree(pasta, ignore_errors=True)
        else:
            job["path"] = final
        job.update(status="pronto", progress=100)
    except Exception as e:
        texto, codigo = traduzir_erro(e)
        job.update(status="erro", error=texto, codigo=codigo)
        if not job.get("path"):
            shutil.rmtree(pasta, ignore_errors=True)


def r_baixar(d):
    job_id = uuid.uuid4().hex
    JOBS[job_id] = {"status": "analisando", "progress": 0}
    threading.Thread(target=_baixar, daemon=True,
                     args=(job_id, d.get("url", ""), d.get("formato", "video"), d.get("qualidade", "melhor"))).start()
    return {"id": job_id}, 200


def r_status(job_id):
    job = JOBS.get(job_id)
    if not job:
        return {"erro": "Esse download não existe mais. Comece de novo."}, 404
    return {k: v for k, v in job.items() if k != "path"}, 200


def r_cookies(dados):
    if not dados:
        return {"erro": "O arquivo está vazio."}, 400
    texto = dados.decode("utf-8", "ignore").lower()
    if "youtube" not in texto and "google" not in texto:
        return {"erro": "Esse arquivo não tem cookies do YouTube. Exporte com o YouTube aberto."}, 400
    os.makedirs(CFG["dados"], exist_ok=True)
    with open(os.path.join(CFG["dados"], "cookies.txt"), "wb") as out:
        out.write(dados)
    return {"ok": True}, 200


def r_cookies_remover():
    p = os.path.join(CFG["dados"], "cookies.txt")
    if os.path.isfile(p):
        os.remove(p)
    return {"ok": True}, 200


def r_atualizar():
    """Baixa a versão mais nova do yt-dlp do PyPI. Vale depois de reabrir o app."""
    try:
        ctx = _ssl_ctx()
        with urllib.request.urlopen("https://pypi.org/pypi/yt-dlp/json", timeout=20, context=ctx) as r:
            meta = json.load(r)
        nova = meta["info"]["version"]
        if nova == yt().version.__version__:
            return {"versao": nova, "novo": False}, 200
        roda = next(u for u in meta["urls"] if u["filename"].endswith("py3-none-any.whl"))
        os.makedirs(_motor_dir(), exist_ok=True)
        destino = os.path.join(_motor_dir(), roda["filename"])
        with urllib.request.urlopen(roda["url"], timeout=120, context=ctx) as r, open(destino + ".tmp", "wb") as out:
            shutil.copyfileobj(r, out)
        for velho in glob.glob(os.path.join(_motor_dir(), "yt_dlp-*.whl")):
            os.remove(velho)
        os.replace(destino + ".tmp", destino)
        return {"versao": nova, "novo": True}, 200
    except Exception as e:
        return {"erro": f"Não foi possível atualizar: {e}"}, 500


class Servidor(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *args):
        pass

    def _enviar(self, corpo, tipo, codigo=200, extra=None):
        self.send_response(codigo)
        self.send_header("Content-Type", tipo)
        self.send_header("Content-Length", str(len(corpo)))
        self.send_header("Cache-Control", "no-store")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(corpo)

    def _json(self, resposta):
        obj, codigo = resposta
        self._enviar(json.dumps(obj).encode(), "application/json; charset=utf-8", codigo)

    def _corpo(self):
        n = int(self.headers.get("Content-Length") or 0)
        return self.rfile.read(n) if n else b""

    def _corpo_json(self):
        try:
            return json.loads(self._corpo() or b"{}")
        except ValueError:
            return {}

    def do_GET(self):
        p = urlparse(self.path).path
        if p == "/":
            self._enviar(HTML.encode(), "text/html; charset=utf-8")
        elif p == "/api/ping":
            self._json(({"ok": True}, 200))
        elif p == "/api/config":
            self._json(r_config())
        elif p.startswith("/api/status/"):
            self._json(r_status(p.rsplit("/", 1)[-1]))
        elif p.startswith("/api/arquivo/"):
            job = JOBS.get(p.rsplit("/", 1)[-1])
            if not job or not job.get("path") or not os.path.isfile(job["path"]):
                return self._json(({"erro": "Arquivo não disponível."}, 404))
            self.send_response(200)
            self.send_header("Content-Type", job.get("mime") or "application/octet-stream")
            self.send_header("Content-Length", str(os.path.getsize(job["path"])))
            self.send_header("Content-Disposition", "attachment; filename*=UTF-8''" + quote(job["filename"]))
            self.end_headers()
            with open(job["path"], "rb") as f:
                shutil.copyfileobj(f, self.wfile)
        else:
            self._json(({"erro": "Não encontrado."}, 404))

    def do_POST(self):
        p = urlparse(self.path).path
        if p == "/api/info":
            self._json(r_info(self._corpo_json()))
        elif p == "/api/baixar":
            self._json(r_baixar(self._corpo_json()))
        elif p == "/api/cookies":
            self._json(r_cookies(self._corpo()))
        elif p == "/api/atualizar":
            self._corpo()
            self._json(r_atualizar())
        else:
            self._json(({"erro": "Não encontrado."}, 404))

    def do_DELETE(self):
        if urlparse(self.path).path == "/api/cookies":
            self._json(r_cookies_remover())
        else:
            self._json(({"erro": "Não encontrado."}, 404))


def servir(porta):
    srv = ThreadingHTTPServer(("127.0.0.1", int(porta)), Servidor)
    srv.daemon_threads = True
    srv.serve_forever()


# ---------------------------------------------------------------- Android

def start(porta, dir_dados, dir_cache):
    """Chamado pelo app Android (Chaquopy)."""
    from java import jclass
    nativo = jclass("app.websave.Nativo")
    try:
        import certifi
        os.environ.setdefault("SSL_CERT_FILE", certifi.where())
    except Exception:
        pass
    CFG.update(app=True, dados=dir_dados, tmp=dir_cache,
               juntar=lambda v, a, o: nativo.juntar(v, a, o),
               salvar=lambda p, n: nativo.salvar(p, n))
    threading.Thread(target=servir, args=(porta,), daemon=True).start()
    threading.Thread(target=yt, daemon=True).start()  # pré-carrega o motor


# ---------------------------------------------------------------- interface

HTML = r"""<!doctype html>
<html lang="pt-BR">
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
  --papel:#EDEFF2; --folha:#FFFFFF; --sulco:#E1E5EA; --tinta:#171A1F; --cinza:#5D6571; --linha:#D3D8DE;
  --cobalto:#2443D6; --cobalto-forte:#1B35B3; --trilho:#D5DCF7; --ok:#157F55; --erro:#B42318; --erro-fundo:#FBEAE8;
  --fonte:"Schibsted Grotesk",system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;
  color-scheme:light;
}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){
  --papel:#15181C; --folha:#1E2227; --sulco:#252A30; --tinta:#E9ECF0; --cinza:#9AA3AE; --linha:#30363D;
  --cobalto:#5B7CFF; --cobalto-forte:#4866F0; --trilho:#232C4D; --ok:#3DBB84; --erro:#FF8A80; --erro-fundo:#3A2121;
  color-scheme:dark;
}}
:root[data-theme="dark"]{
  --papel:#15181C; --folha:#1E2227; --sulco:#252A30; --tinta:#E9ECF0; --cinza:#9AA3AE; --linha:#30363D;
  --cobalto:#5B7CFF; --cobalto-forte:#4866F0; --trilho:#232C4D; --ok:#3DBB84; --erro:#FF8A80; --erro-fundo:#3A2121;
  color-scheme:dark;
}
*{box-sizing:border-box}
html{-webkit-text-size-adjust:100%;-webkit-tap-highlight-color:transparent}
body{margin:0;background:var(--papel);color:var(--tinta);font:400 16px/1.5 var(--fonte);
  padding:env(safe-area-inset-top) 0 env(safe-area-inset-bottom)}
button,input{font:inherit;color:inherit}
button{cursor:pointer}
:focus-visible{outline:2px solid var(--cobalto);outline-offset:2px}
[hidden]{display:none!important}

.pagina{max-width:560px;margin:0 auto;padding:0 20px 48px}

.topo{display:flex;align-items:center;justify-content:space-between;height:64px}
.marca{display:flex;align-items:center;gap:9px;font-weight:800;font-size:19px;letter-spacing:-.02em}
.marca svg{width:26px;height:26px;color:var(--cobalto)}
.icone{width:44px;height:44px;margin-right:-10px;border:0;background:none;border-radius:50%;display:grid;place-items:center;color:var(--cinza)}
.icone:active{background:var(--sulco)}
.icone svg{width:22px;height:22px}

.pergunta{display:block;font-size:30px;line-height:1.12;font-weight:700;letter-spacing:-.025em;margin:28px 0 18px}
.campo{display:flex;align-items:center;background:var(--folha);border:1.5px solid var(--linha);border-radius:12px;transition:border-color .15s}
.campo:focus-within{border-color:var(--cobalto)}
.campo input{flex:1;min-width:0;border:0;background:none;outline:none;padding:15px 0 15px 16px;font-size:17px}
.campo input::placeholder{color:var(--cinza);opacity:.7}
.colar{border:0;background:none;color:var(--cobalto);font-weight:600;padding:15px 16px;border-radius:0 12px 12px 0}
.limpar{border:0;background:none;color:var(--cinza);width:40px;height:48px;display:grid;place-items:center}
.limpar svg{width:18px;height:18px}

.primario{width:100%;margin-top:12px;border:0;border-radius:12px;padding:15px;font-weight:700;font-size:17px;
  background:var(--tinta);color:var(--papel)}
.primario:disabled{opacity:.55;cursor:default}
.ajuda{color:var(--cinza);font-size:14px;margin:12px 0 0}

.erro{display:flex;gap:12px;align-items:flex-start;justify-content:space-between;margin-top:20px;padding:13px 14px;
  border-radius:10px;background:var(--erro-fundo);color:var(--erro);font-size:15px;line-height:1.4}
.erro button{flex:none;border:0;background:none;color:inherit;font-weight:700;text-decoration:underline;padding:0}

.video{margin-top:32px;padding-top:28px;border-top:1px solid var(--linha)}
.capa{display:block;width:100%;aspect-ratio:16/9;object-fit:cover;border-radius:10px;background:var(--sulco)}
.titulo{font-size:20px;line-height:1.3;font-weight:600;letter-spacing:-.01em;margin:16px 0 6px;
  display:-webkit-box;-webkit-line-clamp:3;-webkit-box-orient:vertical;overflow:hidden}
.meta{display:flex;flex-wrap:wrap;column-gap:14px;color:var(--cinza);font-size:14px;margin:0}
.meta .dur{font-variant-numeric:tabular-nums}

.opcao{border:0;margin:22px 0 0;padding:0}
.opcao legend{font-size:14px;font-weight:600;color:var(--cinza);margin-bottom:8px;padding:0}
.seg{display:flex;background:var(--sulco);border-radius:10px;padding:3px}
.seg label{flex:1;position:relative}
.seg input{position:absolute;opacity:0;inset:0;margin:0}
.seg span{display:block;text-align:center;padding:9px 4px;border-radius:8px;font-weight:500;font-size:15px;color:var(--cinza);
  font-variant-numeric:tabular-nums}
.seg input:checked+span{background:var(--folha);color:var(--tinta);font-weight:600;box-shadow:0 0 0 1px var(--linha)}
.seg input:focus-visible+span{outline:2px solid var(--cobalto);outline-offset:1px}

/* o botão é a barra de progresso */
.salvar{position:relative;display:block;width:100%;height:56px;margin-top:26px;border:0;padding:0;border-radius:12px;overflow:hidden;
  font-weight:700;font-size:17px;font-variant-numeric:tabular-nums;--p:100%}
.salvar .camada{position:absolute;inset:0;display:flex;align-items:center;justify-content:center;gap:8px}
.salvar .base{background:var(--trilho);color:var(--tinta)}
.salvar .cheia{background:var(--cobalto);color:#fff;clip-path:inset(0 calc(100% - var(--p)) 0 0);transition:clip-path .35s ease-out,background-color .3s}
.salvar.feito .cheia{background:var(--ok)}
.salvar:disabled{cursor:default}
.salvar svg{width:20px;height:20px}
.estado{min-height:21px;margin:10px 0 0;color:var(--cinza);font-size:14px;line-height:1.5}
.acoes{display:flex;gap:10px;margin-top:14px}
.acoes button{flex:1;padding:13px;border-radius:12px;border:1.5px solid var(--linha);background:var(--folha);font-weight:600}
.outro{display:block;margin:18px auto 0;border:0;background:none;color:var(--cobalto);font-weight:600;padding:8px}

/* ajustes */
dialog{border:0;padding:0;margin:auto auto 0;width:100%;max-width:560px;border-radius:18px 18px 0 0;background:var(--folha);color:var(--tinta)}
dialog::backdrop{background:rgba(10,14,20,.45)}
.folha{padding:8px 20px calc(24px + env(safe-area-inset-bottom))}
.alca{width:36px;height:4px;border-radius:2px;background:var(--linha);margin:4px auto 14px}
.folha h2{font-size:22px;letter-spacing:-.02em;margin:0 0 4px}
.bloco{padding:18px 0;border-bottom:1px solid var(--linha)}
.bloco:last-of-type{border-bottom:0}
.bloco h3{font-size:16px;margin:0 0 4px}
.bloco p{margin:0 0 12px;color:var(--cinza);font-size:14px;line-height:1.5}
.bloco .situacao{color:var(--tinta);font-weight:500}
.linha-botoes{display:flex;gap:10px;flex-wrap:wrap}
.sec{padding:11px 16px;border-radius:10px;border:1.5px solid var(--linha);background:none;font-weight:600}
.sec.forte{background:var(--tinta);color:var(--folha);border-color:var(--tinta)}
.fechar{width:100%;margin-top:8px}

@media (prefers-reduced-motion:reduce){*{transition:none!important;animation:none!important}}
@keyframes gira{to{transform:rotate(360deg)}}
.gira{animation:gira .8s linear infinite}
</style>
</head>
<body>
<div class="pagina">
  <header class="topo">
    <div class="marca">
      <svg viewBox="0 0 26 26" fill="none" aria-hidden="true"><rect x="1" y="1" width="24" height="24" rx="7" fill="currentColor"/>
        <path d="M13 6.5v9m0 0-3.6-3.6M13 15.5l3.6-3.6M7.5 19h11" stroke="#fff" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/></svg>
      WebSave
    </div>
    <button class="icone" id="abrirAjustes" aria-label="Ajustes">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" aria-hidden="true">
        <path d="M4 7h10M18 7h2M4 17h4M12 17h8"/><circle cx="16" cy="7" r="2"/><circle cx="10" cy="17" r="2"/></svg>
    </button>
  </header>

  <form id="form" autocomplete="off">
    <label class="pergunta" for="url">Cole o link do vídeo</label>
    <div class="campo">
      <input id="url" type="url" inputmode="url" enterkeyhint="search" placeholder="https://" spellcheck="false">
      <button type="button" class="limpar" id="limpar" aria-label="Limpar link" hidden>
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M6 6l12 12M18 6 6 18"/></svg>
      </button>
      <button type="button" class="colar" id="colar">Colar</button>
    </div>
    <button class="primario" id="buscar">Buscar vídeo</button>
    <p class="ajuda" id="ajuda">Funciona com YouTube, Instagram, TikTok, X, Facebook, Vimeo e centenas de outros sites.</p>
  </form>

  <div class="erro" id="erro" role="alert" hidden><span id="erroTexto"></span><button type="button" id="erroAcao" hidden>Abrir ajustes</button></div>

  <section class="video" id="video" hidden aria-live="polite">
    <img class="capa" id="capa" alt="" referrerpolicy="no-referrer">
    <h1 class="titulo" id="titulo"></h1>
    <p class="meta" id="meta"></p>

    <fieldset class="opcao">
      <legend>Formato</legend>
      <div class="seg" id="formatos">
        <label><input type="radio" name="formato" value="video" checked><span>Vídeo</span></label>
        <label><input type="radio" name="formato" value="audio"><span>Só áudio</span></label>
      </div>
    </fieldset>
    <fieldset class="opcao" id="qualidadeBloco">
      <legend>Qualidade</legend>
      <div class="seg" id="qualidades"></div>
    </fieldset>

    <button class="salvar" id="salvar" type="button">
      <span class="camada base"><span class="rotulo"></span></span>
      <span class="camada cheia" aria-hidden="true"><span class="rotulo"></span></span>
    </button>
    <p class="estado" id="estado"></p>
    <div class="acoes" id="acoes" hidden>
      <button type="button" id="abrirArquivo">Abrir</button>
      <button type="button" id="enviarArquivo">Enviar para…</button>
    </div>
    <button type="button" class="outro" id="outro" hidden>Salvar outro vídeo</button>
  </section>
</div>

<dialog id="ajustes" aria-labelledby="ajustesTitulo">
  <div class="folha">
    <div class="alca"></div>
    <h2 id="ajustesTitulo">Ajustes</h2>
    <div class="bloco">
      <h3>Cookies do YouTube</h3>
      <p>Use quando o YouTube pedir verificação de conta. Exporte um arquivo cookies.txt com o YouTube aberto e importe aqui. <span class="situacao" id="cookieSituacao"></span></p>
      <div class="linha-botoes">
        <label class="sec forte" for="cookieArquivo" tabindex="0" role="button">Importar cookies.txt</label>
        <input type="file" id="cookieArquivo" accept=".txt,text/plain" hidden>
        <button type="button" class="sec" id="cookieRemover" hidden>Remover</button>
      </div>
    </div>
    <div class="bloco">
      <h3>Motor de download</h3>
      <p>Os sites mudam com frequência. Se um link parar de funcionar, atualize. <span class="situacao" id="motorSituacao"></span></p>
      <div class="linha-botoes"><button type="button" class="sec" id="atualizar">Atualizar motor</button></div>
    </div>
    <button type="button" class="primario fechar" id="fecharAjustes">Fechar</button>
  </div>
</dialog>

<script>
const $ = s => document.querySelector(s);
const nativo = window.WebSaveAndroid || null;
const SVG_OK = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><path d="m5 12.5 4.5 4.5L19 7.5"/></svg>';
const SVG_GIRA = '<svg class="gira" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round"><path d="M12 3a9 9 0 1 0 9 9"/></svg>';
let estado = {url:"", alturas:[], job:null, timer:null, ocupado:false};

async function api(caminho, opts={}){
  const r = await fetch(caminho, opts);
  const d = await r.json().catch(()=>({}));
  if(!r.ok){ const e = new Error(d.erro || "O servidor local não respondeu. Reabra o app."); e.codigo = d.codigo; throw e; }
  return d;
}
const postJSON = (c, corpo) => api(c, {method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify(corpo)});

function duracao(s){
  if(!s) return "";
  s = Math.round(s); const h = Math.floor(s/3600), m = Math.floor(s%3600/60), x = String(s%60).padStart(2,"0");
  return h ? `${h}:${String(m).padStart(2,"0")}:${x}` : `${m}:${x}`;
}
function pareceLink(t){ return /^(https?:\/\/)?[\w-]+(\.[\w-]+)+\S*$/i.test((t||"").trim()); }
function extrairLink(t){ const m = (t||"").match(/https?:\/\/\S+/); return m ? m[0] : (t||"").trim(); }

function mostrarErro(msg, codigo){
  $("#erroTexto").textContent = msg;
  $("#erroAcao").hidden = codigo !== "cookies";
  $("#erro").hidden = false;
}
function limparErro(){ $("#erro").hidden = true; }

/* ---------- botão salvar = barra de progresso ---------- */
function botao(texto, p, {icone="", feito=false, ativo=true}={}){
  const b = $("#salvar");
  b.style.setProperty("--p", p + "%");
  b.classList.toggle("feito", feito);
  b.disabled = !ativo;
  b.querySelectorAll(".rotulo").forEach(r => r.innerHTML = icone + `<span>${texto}</span>`);
  b.setAttribute("aria-label", texto);
}
function rotuloSalvar(){ return formato() === "audio" ? "Salvar áudio" : "Salvar vídeo"; }
function pronto(){
  clearInterval(estado.timer); estado.ocupado = false; estado.job = null;
  botao(rotuloSalvar(), 100); $("#estado").textContent = ""; $("#acoes").hidden = true; $("#outro").hidden = true;
}

const formato = () => document.querySelector('input[name="formato"]:checked').value;
const qualidade = () => (document.querySelector('input[name="qualidade"]:checked')||{}).value || "melhor";

function montarQualidades(alturas){
  const opcoes = [["melhor","Melhor"]];
  [[1080,"1080p"],[720,"720p"],[480,"480p"]].forEach(([h,n]) => { if(alturas.some(a => a >= h)) opcoes.push([String(h), n]); });
  $("#qualidades").innerHTML = opcoes.map(([v,n],i) =>
    `<label><input type="radio" name="qualidade" value="${v}" ${i===0?"checked":""}><span>${n}</span></label>`).join("");
  $("#qualidadeBloco").hidden = opcoes.length < 2;
}

/* ---------- buscar ---------- */
async function buscar(){
  const url = extrairLink($("#url").value);
  if(!url){ mostrarErro("Cole um link antes de buscar."); $("#url").focus(); return; }
  $("#url").value = url; atualizarCampo();
  limparErro(); pronto();
  const b = $("#buscar"); b.disabled = true; b.textContent = "Buscando…";
  try{
    const d = await postJSON("/api/info", {url});
    estado.url = url;
    const capa = $("#capa"); capa.hidden = !d.thumb; capa.src = d.thumb || "";
    $("#titulo").textContent = d.titulo || "Vídeo sem título";
    $("#meta").innerHTML = "";
    [d.canal, d.site, duracao(d.duracao)].forEach((t,i) => { if(!t) return; const s = document.createElement("span"); s.textContent = t; if(i===2) s.className = "dur"; $("#meta").appendChild(s); });
    montarQualidades(d.alturas || []);
    document.querySelector('input[name="formato"][value="video"]').checked = true;
    $("#qualidadeBloco").hidden = $("#qualidades").children.length < 2;
    pronto();
    $("#video").hidden = false; $("#ajuda").hidden = true;
    $("#video").scrollIntoView({behavior: matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth", block:"start"});
  }catch(e){ $("#video").hidden = true; mostrarErro(e.message, e.codigo); }
  b.disabled = false; b.textContent = "Buscar vídeo";
}

/* ---------- salvar ---------- */
async function salvar(){
  if(estado.ocupado) return;
  estado.ocupado = true; limparErro();
  $("#acoes").hidden = true; $("#outro").hidden = true;
  botao("Preparando…", 0, {icone:SVG_GIRA, ativo:false});
  $("#estado").textContent = "Lendo as informações do vídeo.";
  try{
    const {id} = await postJSON("/api/baixar", {url:estado.url, formato:formato(), qualidade:qualidade()});
    estado.job = id;
    estado.timer = setInterval(() => acompanhar(id), 600);
  }catch(e){ pronto(); mostrarErro(e.message, e.codigo); }
}

async function acompanhar(id){
  let s; try{ s = await api("/api/status/" + id); }catch(e){ return; }
  if(estado.job !== id) return;
  const p = Math.max(2, Math.min(100, s.progress || 0));
  if(s.status === "analisando"){ botao("Preparando…", 0, {icone:SVG_GIRA, ativo:false}); }
  else if(s.status === "baixando"){ botao(`Baixando ${Math.floor(p)}%`, p, {ativo:false}); $("#estado").textContent = "Pode sair do app, o download continua."; }
  else if(s.status === "juntando"){ botao("Juntando áudio e vídeo", 99, {icone:SVG_GIRA, ativo:false}); $("#estado").textContent = "Quase lá."; }
  else if(s.status === "salvando"){ botao("Salvando", 100, {icone:SVG_GIRA, ativo:false}); }
  else if(s.status === "erro"){ pronto(); mostrarErro(s.error, s.codigo); }
  else if(s.status === "pronto"){
    clearInterval(estado.timer); estado.ocupado = false;
    botao("Salvo", 100, {icone:SVG_OK, feito:true, ativo:false});
    $("#outro").hidden = false;
    if(nativo && s.uri){
      $("#estado").textContent = `Está em ${s.local}. Já aparece na galeria e no CapCut.`;
      $("#acoes").hidden = false;
      $("#abrirArquivo").onclick = () => nativo.abrir(s.uri, s.mime);
      $("#enviarArquivo").onclick = () => nativo.compartilhar(s.uri, s.mime);
    }else{
      $("#estado").textContent = `${s.filename} foi enviado para os downloads do navegador.`;
      location.href = "/api/arquivo/" + id;
    }
  }
}

/* ---------- campo ---------- */
function atualizarCampo(){ const vazio = !$("#url").value; $("#limpar").hidden = vazio; $("#colar").hidden = !vazio; }
async function colar(){
  let t = "";
  try{ t = nativo ? nativo.colar() : await navigator.clipboard.readText(); }catch(e){}
  if(!t){ mostrarErro("A área de transferência está vazia. Copie o link no app do vídeo e tente de novo."); return; }
  $("#url").value = extrairLink(t); atualizarCampo();
  if(pareceLink($("#url").value)) buscar();
}
function receberLink(t){ $("#url").value = extrairLink(t); atualizarCampo(); buscar(); }
window.receberLink = receberLink;

$("#form").addEventListener("submit", e => { e.preventDefault(); buscar(); });
$("#url").addEventListener("input", atualizarCampo);
$("#colar").addEventListener("click", colar);
$("#limpar").addEventListener("click", () => { $("#url").value = ""; atualizarCampo(); $("#url").focus(); });
$("#salvar").addEventListener("click", salvar);
$("#outro").addEventListener("click", () => {
  pronto(); $("#video").hidden = true; $("#ajuda").hidden = false; $("#url").value = ""; atualizarCampo();
  window.scrollTo(0,0); $("#url").focus();
});
document.addEventListener("change", e => { if(e.target.name === "formato" || e.target.name === "qualidade"){
  $("#qualidadeBloco").hidden = formato() === "audio" || $("#qualidades").children.length < 2;
  if(!estado.ocupado) pronto();
}});

/* ---------- ajustes ---------- */
async function carregarAjustes(){
  try{
    const c = await api("/api/config");
    $("#cookieSituacao").textContent = c.cookies ? "Cookies importados." : "Nenhum cookie importado.";
    $("#cookieRemover").hidden = !c.cookies;
    $("#motorSituacao").textContent = `Versão instalada: ${c.motor}.`;
  }catch(e){}
}
function abrirAjustes(){ carregarAjustes(); $("#ajustes").showModal(); }
$("#abrirAjustes").addEventListener("click", abrirAjustes);
$("#erroAcao").addEventListener("click", abrirAjustes);
$("#fecharAjustes").addEventListener("click", () => $("#ajustes").close());
$("#ajustes").addEventListener("click", e => { if(e.target === $("#ajustes")) $("#ajustes").close(); });
document.querySelector('label[for="cookieArquivo"]').addEventListener("keydown", e => { if(e.key === "Enter" || e.key === " "){ e.preventDefault(); $("#cookieArquivo").click(); }});
$("#cookieArquivo").addEventListener("change", async e => {
  const f = e.target.files[0]; if(!f) return;
  try{ await api("/api/cookies", {method:"POST", body:await f.arrayBuffer()}); $("#cookieSituacao").textContent = "Cookies importados. Tente o link de novo."; $("#cookieRemover").hidden = false; }
  catch(err){ $("#cookieSituacao").textContent = err.message; }
  e.target.value = "";
});
$("#cookieRemover").addEventListener("click", async () => { await api("/api/cookies", {method:"DELETE"}); carregarAjustes(); });
$("#atualizar").addEventListener("click", async () => {
  const b = $("#atualizar"); b.disabled = true; b.textContent = "Atualizando…";
  try{
    const r = await api("/api/atualizar", {method:"POST"});
    $("#motorSituacao").textContent = r.novo ? `Versão ${r.versao} baixada. Feche e abra o WebSave para usar.` : `Você já tem a versão mais nova (${r.versao}).`;
  }catch(e){ $("#motorSituacao").textContent = e.message; }
  b.disabled = false; b.textContent = "Atualizar motor";
});

/* ---------- início ---------- */
pronto(); atualizarCampo();
const inicial = new URLSearchParams(location.search).get("url");
if(inicial){ history.replaceState(null, "", "/"); receberLink(inicial); }
</script>
</body>
</html>"""


if __name__ == "__main__":
    import webbrowser
    print("WebSave rodando em http://127.0.0.1:5000  (CTRL+C para parar)")
    if cookies_path():
        print("Usando cookies:", cookies_path())
    if not TEM_FFMPEG:
        print("Aviso: ffmpeg não encontrado. A qualidade fica limitada (instale com: pkg install ffmpeg).")
    threading.Timer(1.2, lambda: webbrowser.open("http://127.0.0.1:5000")).start()
    try:
        servir(5000)
    except KeyboardInterrupt:
        pass
