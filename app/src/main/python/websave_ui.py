"""The WebSave interface: one self-contained page served by websave.py."""

HTML = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="theme-color" content="#12161F">
<meta name="color-scheme" content="dark">
<title>WebSave</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Onest:wght@400;500;600;700;800&display=swap" rel="stylesheet">
<style>
:root{
  --bg:#12161F; --surface:#1B2130; --raised:#232A3B; --line:#2A3245; --line-soft:#262D3E;
  --text:#EEF1F6; --text-2:#B7BFCE; --muted:#8F98AB;
  --accent:#F2A93B; --on-accent:#1A1206; --success:#A7E3C4; --danger:#FF8A80; --danger-bg:#3A2121;
  --font:"Onest",system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;
  --nav-h:64px; --safe-b:env(safe-area-inset-bottom);
  color-scheme:dark;
}
*{box-sizing:border-box}
html{-webkit-text-size-adjust:100%;-webkit-tap-highlight-color:transparent}
body{margin:0;background:var(--bg);color:var(--text);font:400 16px/1.5 var(--font);min-height:100vh}
button,input{font:inherit;color:inherit}
button{cursor:pointer}
:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
[hidden]{display:none!important}
.sr-only{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0);white-space:nowrap}

.app{max-width:560px;margin:0 auto;padding:env(safe-area-inset-top) 0 calc(var(--nav-h) + 40px + var(--safe-b))}
.screen{padding:22px 20px 0}

/* ---------- header ---------- */
.head{display:flex;align-items:center;gap:12px}
.head svg{width:44px;height:44px;flex:none}
.head h1{margin:0;font-size:28px;line-height:1.05;font-weight:800;letter-spacing:-.03em}
.head p{margin:3px 0 0;font-size:14px;color:var(--muted)}
.page-title{margin:0;font-size:28px;font-weight:800;letter-spacing:-.03em}

/* ---------- link field ---------- */
.link{display:flex;align-items:center;gap:10px;margin-top:22px;background:var(--surface);border:1px solid var(--line);
  border-radius:999px;padding:6px 6px 6px 18px;transition:border-color .15s}
.link:focus-within{border-color:var(--accent)}
.link svg{flex:none;width:18px;height:18px;color:var(--muted)}
.link input{flex:1;min-width:0;border:0;background:none;outline:none;font-size:16px;padding:8px 0}
.link input::placeholder{color:var(--muted)}
.pill-btn{flex:none;border:0;border-radius:999px;background:var(--accent);color:var(--on-accent);font-weight:700;font-size:15px;
  padding:11px 18px;min-width:84px;display:flex;align-items:center;justify-content:center;gap:6px}
.pill-btn:disabled{opacity:.6;cursor:default}
.chips{display:flex;gap:8px;flex-wrap:wrap;margin-top:14px}
.chips span{font-size:12.5px;color:var(--text-2);background:var(--surface);border-radius:999px;padding:6px 11px}

.error{display:flex;gap:12px;align-items:flex-start;justify-content:space-between;margin-top:16px;padding:13px 14px;
  border-radius:14px;background:var(--danger-bg);color:var(--danger);font-size:14.5px;line-height:1.4}
.error button{flex:none;border:0;background:none;color:inherit;font-weight:700;text-decoration:underline;padding:0}

/* ---------- library grid ---------- */
.section-head{display:flex;align-items:baseline;justify-content:space-between;margin:28px 0 12px}
.section-head h2{margin:0;font-size:18px;font-weight:700}
.section-head span,.link-btn{font-size:13.5px;color:var(--muted)}
.link-btn{border:0;background:none;padding:6px 0;color:var(--accent);font-weight:600}
.grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px 12px;align-items:start}
.card{display:flex;flex-direction:column;align-items:stretch;justify-content:flex-start;width:100%;text-align:left;border:0;background:none;padding:0;color:inherit}
.thumb{position:relative;aspect-ratio:16/10;border-radius:12px;overflow:hidden;background:var(--raised)}
.thumb img{position:absolute;inset:0;width:100%;height:100%;object-fit:cover}
.badge{position:absolute;left:8px;top:8px;font-size:10.5px;font-weight:700;padding:2px 7px;border-radius:999px;color:var(--on-accent);
  font-variant-numeric:tabular-nums}
.dur{position:absolute;right:8px;bottom:8px;background:rgba(0,0,0,.72);color:#fff;font-size:10.5px;font-weight:600;padding:1px 5px;border-radius:4px;
  font-variant-numeric:tabular-nums}
.bar{position:absolute;left:0;right:0;bottom:0;height:4px;background:rgba(0,0,0,.5)}
.bar i{display:block;height:100%;background:var(--accent);transition:width .4s}
.card .t{font-size:13.5px;font-weight:600;line-height:1.3;margin-top:8px;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
.card .m{font-size:12px;color:var(--muted);margin-top:3px}
.empty{margin-top:8px;padding:28px 20px;border:1px dashed var(--line);border-radius:16px;text-align:center;color:var(--muted);font-size:14.5px;line-height:1.5}
.empty b{display:block;color:var(--text);font-size:16px;margin-bottom:4px}

/* ---------- settings ---------- */
.group{margin-top:18px;background:var(--surface);border-radius:18px;padding:18px}
.group h3{margin:0 0 4px;font-size:16px}
.group p{margin:0 0 14px;color:var(--muted);font-size:14px;line-height:1.5}
.group .state{color:var(--text-2);font-weight:500}
.row-btns{display:flex;gap:10px;flex-wrap:wrap}
.btn{border:1px solid var(--line);border-radius:12px;background:var(--raised);color:var(--text);font-weight:600;font-size:15px;padding:11px 16px}
.btn.primary{background:var(--accent);border-color:var(--accent);color:var(--on-accent)}
.btn:disabled{opacity:.6;cursor:default}
.about{display:flex;justify-content:space-between;font-size:14px;color:var(--muted);padding:6px 0}
.about b{color:var(--text-2);font-weight:500}

/* ---------- bottom navigation ---------- */
.nav{position:fixed;left:16px;right:16px;bottom:calc(16px + var(--safe-b));max-width:528px;margin:0 auto;height:var(--nav-h);
  border-radius:22px;background:var(--surface);border:1px solid var(--line);display:flex;align-items:stretch;justify-content:space-around;z-index:5}
.nav button{flex:1;border:0;background:none;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:3px;
  font-size:11.5px;font-weight:500;color:var(--muted)}
.nav button svg{width:22px;height:22px}
.nav button[aria-current="page"]{color:var(--accent);font-weight:600}

/* ---------- video screen ---------- */
.video-view{padding:0}
.hero{position:relative;aspect-ratio:16/10;max-height:300px;width:100%;background:var(--raised);overflow:hidden}
.hero img{position:absolute;inset:0;width:100%;height:100%;object-fit:cover}
.hero .back{position:absolute;left:14px;top:calc(14px + env(safe-area-inset-top));width:44px;height:44px;border-radius:50%;border:0;
  background:rgba(18,22,31,.65);color:#fff;display:grid;place-items:center;z-index:2}
.hero .back svg{width:20px;height:20px}
.hero .dur{right:14px;bottom:34px;font-size:12px;padding:2px 7px;border-radius:5px}
.sheet-body{position:relative;margin-top:-22px;background:var(--bg);border-radius:24px 24px 0 0;padding:22px 20px 0}
.v-title{font-size:21px;line-height:1.28;font-weight:700;letter-spacing:-.015em;margin:0}
.v-meta{display:flex;flex-wrap:wrap;column-gap:12px;color:var(--muted);font-size:14px;margin-top:6px}
.notice{margin-top:14px;padding:11px 13px;background:var(--surface);border-radius:12px;font-size:13.5px;line-height:1.45;color:var(--text-2)}
.pills{display:flex;gap:8px;margin-top:20px}
.pills button{border:1px solid var(--line);border-radius:999px;padding:10px 18px;font-weight:500;font-size:14.5px;background:none;color:var(--text-2)}
.pills button[aria-checked="true"]{background:var(--text);border-color:var(--text);color:var(--bg);font-weight:700}
.options{margin-top:16px;background:var(--surface);border-radius:16px;overflow:hidden}
.option{display:flex;align-items:center;gap:14px;width:100%;border:0;background:none;text-align:left;padding:14px 16px;border-bottom:1px solid var(--line-soft)}
.option:last-child{border-bottom:0}
.radio{width:20px;height:20px;border-radius:50%;border:2px solid #3A4359;display:grid;place-items:center;flex:none}
.radio i{width:10px;height:10px;border-radius:50%}
.option[aria-checked="true"] .radio{border-color:var(--accent)}
.option[aria-checked="true"] .radio i{background:var(--accent)}
.option .lbl{flex:1;font-weight:600;font-size:15.5px}
.option .tag{font-size:13px;color:var(--muted)}
.option .size{font-size:13.5px;color:var(--text-2);font-variant-numeric:tabular-nums;min-width:62px;text-align:right}
.action{margin-top:22px;padding-bottom:8px}
.big-btn{width:100%;height:56px;border:0;border-radius:16px;background:var(--accent);color:var(--on-accent);font-weight:700;font-size:16px;
  display:flex;align-items:center;justify-content:center;gap:8px}
.big-btn.ghost{background:var(--raised);color:var(--text)}
.big-btn svg{width:20px;height:20px}
.progress-row{display:flex;justify-content:space-between;font-size:13.5px;color:var(--text-2);margin-bottom:8px;font-variant-numeric:tabular-nums}
.track{height:6px;border-radius:3px;background:var(--raised);overflow:hidden}
.track i{display:block;height:100%;width:0;background:var(--accent);transition:width .4s}
.hint{margin:10px 0 0;font-size:13px;color:var(--muted)}
.done-text{display:flex;gap:10px;align-items:flex-start;font-size:14.5px;line-height:1.45;color:var(--text-2);margin-bottom:14px}
.done-text svg{flex:none;width:22px;height:22px;color:var(--success)}
.two{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px}

/* ---------- action sheet ---------- */
dialog{border:0;padding:0;margin:auto auto 0;width:100%;max-width:560px;border-radius:22px 22px 0 0;background:var(--surface);color:var(--text)}
dialog::backdrop{background:rgba(5,7,12,.6)}
.as{padding:10px 16px calc(18px + var(--safe-b))}
.grab{width:36px;height:4px;border-radius:2px;background:var(--line);margin:4px auto 14px}
.as h2{margin:0 4px 4px;font-size:16px;line-height:1.35;font-weight:700}
.as .sub{margin:0 4px 12px;font-size:13px;color:var(--muted)}
.as-item{display:flex;align-items:center;gap:14px;width:100%;border:0;background:none;text-align:left;padding:14px 8px;border-radius:12px;font-size:15.5px;font-weight:500}
.as-item:active{background:var(--raised)}
.as-item svg{width:22px;height:22px;color:var(--text-2)}
.as-item.danger,.as-item.danger svg{color:var(--danger)}

@media (prefers-reduced-motion:reduce){*{transition:none!important;animation:none!important}}
@keyframes spin{to{transform:rotate(360deg)}}
.spin{animation:spin .8s linear infinite}
</style>
</head>
<body>
<div class="app">

  <!-- ================= SAVE ================= -->
  <main class="screen" id="tab-save">
    <header class="head">
      <svg viewBox="0 0 100 100" aria-hidden="true"><rect width="100" height="100" rx="24" fill="#1B2130"/><path d="M50 0V40" stroke="#EEF1F6" stroke-width="3.2" stroke-linecap="round"/><g stroke="#F2A93B" stroke-width="4.4" stroke-linecap="round" stroke-linejoin="round" fill="none"><path d="M45 47L34 38L29 44M44 51L28 48L22 55M44 56L30 61L26 70M46 61L37 71L36 80"/><path d="M55 47L66 38L71 44M56 51L72 48L78 55M56 56L70 61L74 70M54 61L63 71L64 80"/></g><circle cx="50" cy="46" r="6.5" fill="#F2A93B"/><ellipse cx="50" cy="63" rx="11" ry="13" fill="#F2A93B"/></svg>
      <div><h1>WebSave</h1><p>Save from any link</p></div>
    </header>

    <form class="link" id="form" autocomplete="off">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><path d="M10 14a4 4 0 0 0 5.7 0l3-3a4 4 0 0 0-5.7-5.7l-1 1M14 10a4 4 0 0 0-5.7 0l-3 3a4 4 0 0 0 5.7 5.7l1-1"/></svg>
      <label for="url" class="sr-only">Video link</label>
      <input id="url" type="url" inputmode="url" enterkeyhint="go" placeholder="Paste a link" spellcheck="false">
      <button class="pill-btn" id="go" type="submit">Paste</button>
    </form>
    <div class="chips" aria-label="Supported sites"><span>YouTube</span><span>Instagram</span><span>TikTok</span><span>X</span><span>Facebook</span><span>Vimeo</span></div>
    <div class="error" id="saveError" role="alert" hidden><span></span><button type="button" data-open-settings hidden>Settings</button></div>

    <div class="section-head"><h2>Recent</h2><button type="button" class="link-btn" id="seeAll" hidden>See all</button></div>
    <div class="grid" id="recentGrid"></div>
    <div class="empty" id="recentEmpty" hidden><b>Nothing saved yet</b>Paste a link above, or tap Share in YouTube, Instagram or TikTok and pick WebSave.</div>
  </main>

  <!-- ================= LIBRARY ================= -->
  <main class="screen" id="tab-library" hidden>
    <div class="section-head" style="margin-top:4px"><h1 class="page-title">Library</h1><span id="libCount"></span></div>
    <div class="grid" id="libGrid"></div>
    <div class="empty" id="libEmpty" hidden><b>Your library is empty</b>Everything you save shows up here.</div>
  </main>

  <!-- ================= SETTINGS ================= -->
  <main class="screen" id="tab-settings" hidden>
    <h1 class="page-title" style="margin-top:4px">Settings</h1>
    <section class="group">
      <h3>YouTube cookies</h3>
      <p>Use these when YouTube asks for account verification. Export a cookies.txt file with YouTube open and import it here. <span class="state" id="cookieState"></span></p>
      <div class="row-btns">
        <label class="btn primary" for="cookieFile" tabindex="0" role="button" id="cookieLabel">Import cookies.txt</label>
        <input type="file" id="cookieFile" accept=".txt,text/plain" hidden>
        <button type="button" class="btn" id="cookieRemove" hidden>Remove</button>
      </div>
    </section>
    <section class="group">
      <h3>Download engine</h3>
      <p>Sites change often. If a link stops working, update. <span class="state" id="engineState"></span></p>
      <div class="row-btns"><button type="button" class="btn" id="update">Update engine</button></div>
    </section>
    <section class="group">
      <h3>Saved files</h3>
      <p>Videos go to Movies/WebSave and audio to Music/WebSave, so they show up in your gallery, music player and editors like CapCut.</p>
      <div class="about"><span>Engine version</span><b id="aboutEngine">…</b></div>
    </section>
  </main>

  <!-- ================= VIDEO ================= -->
  <main class="video-view" id="view-video" hidden>
    <div class="hero">
      <img id="vThumb" alt="" referrerpolicy="no-referrer">
      <button class="back" id="vBack" aria-label="Back"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M15 5l-7 7 7 7"/></svg></button>
      <span class="dur" id="vDur" hidden></span>
    </div>
    <div class="sheet-body">
      <h1 class="v-title" id="vTitle"></h1>
      <div class="v-meta" id="vMeta"></div>
      <div class="notice" id="vNotice" hidden></div>

      <div class="pills" role="radiogroup" aria-label="Format">
        <button type="button" role="radio" aria-checked="true" data-kind="video">Video</button>
        <button type="button" role="radio" aria-checked="false" data-kind="audio">Audio only</button>
      </div>
      <div class="options" role="radiogroup" aria-label="Quality" id="vOptions"></div>

      <div class="error" id="videoError" role="alert" hidden><span></span><button type="button" data-open-settings hidden>Settings</button></div>

      <div class="action" id="actIdle">
        <button type="button" class="big-btn" id="download"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 4v11m0 0-4-4m4 4 4-4M5 19h14"/></svg><span id="downloadLabel">Download</span></button>
      </div>
      <div class="action" id="actBusy" hidden>
        <div class="progress-row"><span id="busyLabel">Preparing</span><span id="busyAmount"></span></div>
        <div class="track"><i id="busyBar"></i></div>
        <p class="hint">You can leave this screen; the download keeps going.</p>
        <button type="button" class="big-btn ghost" id="cancel" style="margin-top:14px">Cancel</button>
      </div>
      <div class="action" id="actDone" hidden>
        <div class="done-text"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><path d="m5 12.5 4.5 4.5L19 7.5"/></svg><span id="doneText"></span></div>
        <div class="two" id="doneNative">
          <button type="button" class="big-btn ghost" id="doneOpen">Open</button>
          <button type="button" class="big-btn" id="doneShare">Send to…</button>
        </div>
      </div>
    </div>
  </main>
</div>

<nav class="nav" id="nav" aria-label="Main">
  <button type="button" data-tab="save" aria-current="page"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 4v11m0 0-4-4m4 4 4-4M5 19h14"/></svg>Save</button>
  <button type="button" data-tab="library"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="3" y="5" width="18" height="14" rx="3"/><path d="M10 9.5v5l4-2.5z"/></svg>Library</button>
  <button type="button" data-tab="settings"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><path d="M4 7h10M18 7h2M4 17h4M12 17h8"/><circle cx="16" cy="7" r="2"/><circle cx="10" cy="17" r="2"/></svg>Settings</button>
</nav>

<dialog id="itemSheet" aria-labelledby="isTitle">
  <div class="as">
    <div class="grab"></div>
    <h2 id="isTitle"></h2>
    <p class="sub" id="isSub"></p>
    <button type="button" class="as-item" id="isOpen"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="3" y="5" width="18" height="14" rx="3"/><path d="M10 9.5v5l4-2.5z"/></svg>Open</button>
    <button type="button" class="as-item" id="isShare"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="18" cy="5" r="3"/><circle cx="6" cy="12" r="3"/><circle cx="18" cy="19" r="3"/><path d="M8.6 13.5l6.8 4M15.4 6.5l-6.8 4"/></svg>Send to…</button>
    <button type="button" class="as-item" id="isAgain"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M4 12a8 8 0 0 1 14-5.3M20 12a8 8 0 0 1-14 5.3M18 3v4h-4M6 21v-4h4"/></svg>Save again in another quality</button>
    <button type="button" class="as-item danger" id="isRemove"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M4 7h16M9 7V4h6v3M6 7l1 13h10l1-13"/></svg>Remove from library</button>
  </div>
</dialog>

<script>
const $ = s => document.querySelector(s);
const $$ = s => [...document.querySelectorAll(s)];
const native = window.WebSaveAndroid || null;
const SPIN = '<svg class="spin" viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2.6" stroke-linecap="round"><path d="M12 3a9 9 0 1 0 9 9"/></svg>';
const state = {tab:"save", view:"tabs", video:null, kind:"video", quality:null, job:null, timer:null, items:[], historyTimer:null, sheetItem:null};

/* ---------- helpers ---------- */
async function api(path, opts={}){
  const r = await fetch(path, opts);
  const d = await r.json().catch(()=>({}));
  if(!r.ok){ const e = new Error(d.error || "The local server didn't respond. Reopen the app."); e.code = d.code; throw e; }
  return d;
}
const postJSON = (path, body) => api(path, {method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify(body)});
const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
function duration(s){
  if(!s) return "";
  s = Math.round(s); const h = Math.floor(s/3600), m = Math.floor(s%3600/60), x = String(s%60).padStart(2,"0");
  return h ? `${h}:${String(m).padStart(2,"0")}:${x}` : `${m}:${x}`;
}
function bytes(n){
  if(!n) return "";
  if(n >= 1e9) return (n/1e9).toFixed(1) + " GB";
  if(n >= 1e6) return Math.round(n/1e6) + " MB";
  return Math.max(1, Math.round(n/1e3)) + " KB";
}
function resLabel(r){ return r >= 2160 ? "4K" : r >= 1440 ? "1440p" : `${r}p`; }
function resTag(r){ return r >= 2160 ? "Ultra HD" : r >= 1080 ? "Full HD" : r >= 720 ? "HD" : ""; }
function extractLink(t){ const m = (t||"").match(/https?:\/\/\S+/); return m ? m[0] : (t||"").trim(); }
const PALETTE = ["#3D4F73","#6B4E3D","#3E5E4C","#5A4672","#4C5A6B","#6B3D4F"];
function tint(id){ let h = 0; for(const c of String(id)) h = (h*31 + c.charCodeAt(0)) >>> 0; return PALETTE[h % PALETTE.length]; }
function showError(box, msg, code){
  box.querySelector("span").textContent = msg;
  box.querySelector("[data-open-settings]").hidden = code !== "cookies";
  box.hidden = false;
}

/* ---------- navigation ---------- */
function showTab(tab){
  state.tab = tab; state.view = "tabs";
  for(const t of ["save","library","settings"]) $("#tab-" + t).hidden = t !== tab;
  $("#view-video").hidden = true; $("#nav").hidden = false;
  $$("#nav button").forEach(b => {
    if(b.dataset.tab === tab) b.setAttribute("aria-current", "page"); else b.removeAttribute("aria-current");
  });
  if(tab === "settings") loadSettings(); else loadHistory();
  window.scrollTo(0,0);
}
function showVideo(){
  state.view = "video";
  for(const t of ["save","library","settings"]) $("#tab-" + t).hidden = true;
  $("#view-video").hidden = false; $("#nav").hidden = true;
  window.scrollTo(0,0);
}
window.handleBack = function(){
  if($("#itemSheet").open){ $("#itemSheet").close(); return true; }
  if(state.view === "video"){ showTab(state.tab); return true; }
  if(state.tab !== "save"){ showTab("save"); return true; }
  return false;
};
$$("#nav button").forEach(b => b.addEventListener("click", () => showTab(b.dataset.tab)));
$("#seeAll").addEventListener("click", () => showTab("library"));
$("#vBack").addEventListener("click", () => showTab(state.tab));
$$("[data-open-settings]").forEach(b => b.addEventListener("click", () => showTab("settings")));

/* ---------- library ---------- */
function cardHTML(item){
  const meta = [item.site, item.kind === "audio" ? "Audio" : item.label].filter(Boolean).join(", ");
  let badge = "";
  if(item.active) badge = `<span class="badge" style="background:var(--accent)">${Math.floor(item.progress||0)}%</span>`;
  else if(item.kind === "audio") badge = `<span class="badge" style="background:#C9D2E3">Audio</span>`;
  else badge = `<span class="badge" style="background:var(--success)">Saved</span>`;
  const img = item.thumbnail ? `<img src="${esc(item.thumbnail)}" alt="" loading="lazy" referrerpolicy="no-referrer" onerror="this.remove()">` : "";
  return `<button type="button" class="card" data-id="${esc(item.id)}">
    <div class="thumb" style="background:${tint(item.id)}">${img}${badge}
      ${item.duration ? `<span class="dur">${duration(item.duration)}</span>` : ""}
      ${item.active ? `<div class="bar"><i style="width:${item.progress||0}%"></i></div>` : ""}
    </div>
    <div class="t">${esc(item.title || "Untitled video")}</div>
    <div class="m">${esc(meta)}</div></button>`;
}
function renderLibrary(){
  const items = state.items;
  const recent = items.slice(0, 4);
  $("#recentGrid").innerHTML = recent.map(cardHTML).join("");
  $("#recentEmpty").hidden = items.length > 0;
  $("#seeAll").hidden = items.length <= 4;
  $("#libGrid").innerHTML = items.map(cardHTML).join("");
  $("#libEmpty").hidden = items.length > 0;
  const saved = items.filter(i => !i.active).length;
  $("#libCount").textContent = saved ? `${saved} saved` : "";
}
async function loadHistory(){
  try{ state.items = (await api("/api/history")).items || []; }catch(e){ return; }
  renderLibrary();
  clearTimeout(state.historyTimer);
  if(state.items.some(i => i.active) && state.view === "tabs") state.historyTimer = setTimeout(loadHistory, 1500);
}
document.addEventListener("click", e => {
  const card = e.target.closest(".card"); if(!card) return;
  const item = state.items.find(i => i.id === card.dataset.id); if(!item) return;
  if(item.active){ reopenJob(item); return; }
  openItemSheet(item);
});
function openItemSheet(item){
  state.sheetItem = item;
  $("#isTitle").textContent = item.title || "Untitled video";
  $("#isSub").textContent = [item.site, item.kind === "audio" ? "Audio" : item.label, bytes(item.size), item.location].filter(Boolean).join(", ");
  $("#isShare").hidden = !(native && item.uri);
  $("#isAgain").hidden = !item.url;
  $("#itemSheet").showModal();
}
$("#itemSheet").addEventListener("click", e => { if(e.target === $("#itemSheet")) $("#itemSheet").close(); });
$("#isOpen").addEventListener("click", () => {
  const it = state.sheetItem; $("#itemSheet").close();
  if(native && it.uri) native.open(it.uri, it.mime || "video/mp4"); else location.href = "/api/file/" + it.id;
});
$("#isShare").addEventListener("click", () => { const it = state.sheetItem; $("#itemSheet").close(); native.share(it.uri, it.mime || "video/mp4"); });
$("#isAgain").addEventListener("click", () => { const it = state.sheetItem; $("#itemSheet").close(); showTab("save"); receiveLink(it.url); });
$("#isRemove").addEventListener("click", async () => {
  const it = state.sheetItem; $("#itemSheet").close();
  await api("/api/history/" + it.id, {method:"DELETE"}).catch(()=>{}); loadHistory();
});

/* ---------- find ---------- */
function updateGo(){ $("#go").textContent = $("#url").value.trim() ? "Find" : "Paste"; }
$("#url").addEventListener("input", updateGo);
$("#form").addEventListener("submit", async e => {
  e.preventDefault();
  if(!$("#url").value.trim()){
    let t = "";
    try{ t = native ? native.paste() : await navigator.clipboard.readText(); }catch(err){}
    if(!t){ showError($("#saveError"), "The clipboard is empty. Copy the link in the video's app first."); return; }
    $("#url").value = extractLink(t); updateGo();
  }
  find();
});
async function find(){
  const url = extractLink($("#url").value);
  if(!url) return;
  $("#url").value = url;
  $("#saveError").hidden = true;
  const b = $("#go"); b.disabled = true; b.innerHTML = SPIN;
  try{
    const d = await postJSON("/api/info", {url});
    openVideo(d);
    $("#url").value = "";
  }catch(err){ showError($("#saveError"), err.message, err.code); }
  b.disabled = false; updateGo();
}
function receiveLink(t){ if(state.view === "video" && !state.job) showTab("save"); $("#url").value = extractLink(t); updateGo(); find(); }
window.receiveLink = receiveLink;

/* ---------- video screen ---------- */
function openVideo(d){
  state.video = d; state.kind = "video"; state.quality = d.qualities.length ? d.qualities[0].value : "best";
  stopTracking(); state.job = null;
  const img = $("#vThumb"); img.hidden = !d.thumbnail; img.src = d.thumbnail || ""; img.onerror = () => { img.hidden = true; };
  $(".hero").style.background = tint(d.url);
  $("#vDur").hidden = !d.duration; $("#vDur").textContent = duration(d.duration);
  $("#vTitle").textContent = d.title || "Untitled video";
  $("#vMeta").innerHTML = [d.channel, d.site].filter(Boolean).map(t => `<span>${esc(t)}</span>`).join("");
  $("#vNotice").hidden = !d.notice; $("#vNotice").textContent = d.notice || "";
  $("#videoError").hidden = true;
  renderOptions(); setAction("idle"); showVideo();
}
function currentOption(){
  const d = state.video;
  if(state.kind === "audio") return {label:"Audio", size:d.audio_size};
  const q = d.qualities.find(x => x.value === state.quality);
  return q ? {label:resLabel(q.res), size:q.size} : {label:"Original", size:null};
}
function renderOptions(){
  const d = state.video;
  $$(".pills button").forEach(b => b.setAttribute("aria-checked", String(b.dataset.kind === state.kind)));
  let rows;
  if(state.kind === "audio") rows = [{value:"best", label:"Best audio", tag:"M4A", size:d.audio_size}];
  else if(d.qualities.length) rows = d.qualities.slice(0,5).map(q => ({value:q.value, label:resLabel(q.res), tag:resTag(q.res), size:q.size}));
  else rows = [{value:"best", label:"Original", tag:"", size:null}];
  if(!rows.some(r => r.value === state.quality)) state.quality = rows[0].value;
  $("#vOptions").innerHTML = rows.map(r => `<button type="button" class="option" role="radio" aria-checked="${r.value === state.quality}" data-q="${r.value}">
    <span class="radio"><i></i></span><span class="lbl">${esc(r.label)}</span><span class="tag">${esc(r.tag)}</span><span class="size">${bytes(r.size)}</span></button>`).join("");
  const o = currentOption();
  $("#downloadLabel").textContent = state.kind === "audio" ? "Download audio" : `Download ${o.label}`;
}
$$(".pills button").forEach(b => b.addEventListener("click", () => { if(state.job) return; state.kind = b.dataset.kind; renderOptions(); }));
$("#vOptions").addEventListener("click", e => {
  const b = e.target.closest(".option"); if(!b || state.job) return;
  state.quality = b.dataset.q; renderOptions();
});

function setAction(which){
  $("#actIdle").hidden = which !== "idle";
  $("#actBusy").hidden = which !== "busy";
  $("#actDone").hidden = which !== "done";
  $$(".pills button, .option").forEach(b => b.disabled = which === "busy");
}
$("#download").addEventListener("click", async () => {
  const d = state.video, o = currentOption();
  $("#videoError").hidden = true;
  setAction("busy"); paintBusy({status:"analyzing", progress:0});
  try{
    const {id} = await postJSON("/api/download", {url:d.url, kind:state.kind, quality:state.quality, label:o.label,
      title:d.title, thumbnail:d.thumbnail, duration:d.duration, channel:d.channel, site:d.site});
    state.job = {id, size:o.size};
    track();
  }catch(err){ setAction("idle"); showError($("#videoError"), err.message, err.code); }
});
$("#cancel").addEventListener("click", async () => {
  if(!state.job) return;
  $("#busyLabel").textContent = "Cancelling";
  await postJSON("/api/cancel/" + state.job.id, {}).catch(()=>{});
});
function paintBusy(s){
  const p = Math.max(0, Math.min(100, s.progress || 0));
  const labels = {analyzing:"Preparing", downloading:"Downloading", merging:"Merging audio and video", saving:"Saving to your gallery"};
  $("#busyLabel").textContent = labels[s.status] || "Preparing";
  const size = state.job && state.job.size;
  $("#busyAmount").textContent = s.status === "downloading" ? (size ? `${bytes(size*p/100) || "0 MB"} of ${bytes(size)}` : `${Math.floor(p)}%`) : "";
  $("#busyBar").style.width = (s.status === "analyzing" ? 2 : p) + "%";
}
function stopTracking(){ clearTimeout(state.timer); }
async function track(){
  stopTracking();
  const job = state.job; if(!job) return;
  let s;
  try{ s = await api("/api/status/" + job.id); }catch(e){ state.timer = setTimeout(track, 1000); return; }
  if(state.job !== job) return;
  if(["analyzing","downloading","merging","saving"].includes(s.status)){ paintBusy(s); state.timer = setTimeout(track, 600); return; }
  state.job = null;
  if(s.status === "done"){
    setAction("done");
    if(native && s.uri){
      $("#doneText").textContent = `Saved to ${s.location}. It's in your gallery and ready for CapCut.`;
      $("#doneNative").hidden = false;
      $("#doneOpen").onclick = () => native.open(s.uri, s.mime);
      $("#doneShare").onclick = () => native.share(s.uri, s.mime);
    }else{
      $("#doneText").textContent = `${s.filename} was sent to your browser's downloads.`;
      $("#doneNative").hidden = true;
      location.href = "/api/file/" + job.id;
    }
  }else if(s.status === "cancelled"){
    setAction("idle");
  }else{
    setAction("idle"); showError($("#videoError"), s.error, s.code);
  }
}
async function reopenJob(item){
  state.video = {url:item.url, title:item.title, thumbnail:item.thumbnail, duration:item.duration, channel:item.channel,
    site:item.site, qualities:[], audio_size:null, notice:null};
  openVideo(state.video);
  $("#vOptions").innerHTML = `<div class="option"><span class="lbl">${esc(item.kind === "audio" ? "Audio" : item.label || "Video")}</span></div>`;
  state.job = {id:item.id, size:null};
  setAction("busy"); track();
}

/* ---------- settings ---------- */
async function loadSettings(){
  try{
    const c = await api("/api/config");
    $("#cookieState").textContent = c.cookies ? "Cookies imported." : "No cookies imported.";
    $("#cookieRemove").hidden = !c.cookies;
    $("#engineState").textContent = "";
    $("#aboutEngine").textContent = `yt-dlp ${c.engine}`;
  }catch(e){}
}
$("#cookieLabel").addEventListener("keydown", e => { if(e.key === "Enter" || e.key === " "){ e.preventDefault(); $("#cookieFile").click(); } });
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
updateGo(); showTab("save");
const initial = new URLSearchParams(location.search).get("url");
if(initial){ history.replaceState(null, "", "/"); receiveLink(initial); }
</script>
</body>
</html>"""
