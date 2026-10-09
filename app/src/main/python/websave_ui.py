"""The WebSave interface: one self-contained page served by websave.py.

The same page has two modes:
- the full app (tabs Save / Library / Settings, video and playlist screens);
- ?mode=quick, a compact sheet shown over other apps when a link is shared to WebSave.
"""

HTML = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="theme-color" content="#12161F">
<meta name="color-scheme" content="dark">
<title>WebSave</title>
<style>
/* the font ships inside the app, so the screen never waits on the network */
@font-face{font-family:"Onest";src:url("/fonts/onest.woff2") format("woff2");font-weight:100 900;font-style:normal;font-display:swap}
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
body.quick{background:transparent}
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
.bar-head{display:flex;align-items:center;gap:8px;margin:-6px 0 0 -10px}
.icon-btn{width:44px;height:44px;border-radius:50%;border:0;background:none;color:var(--text);display:grid;place-items:center;flex:none}
.icon-btn svg{width:22px;height:22px}

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

.clip-card{display:flex;align-items:center;gap:12px;margin-top:16px;padding:12px 12px 12px 16px;border-radius:16px;
  background:var(--surface);border:1px solid var(--accent)}
.clip-card .txt{flex:1;min-width:0}
.clip-card b{display:block;font-size:14.5px}
.clip-card span{display:block;font-size:13px;color:var(--muted);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.clip-card .pill-btn{min-width:0;padding:10px 16px}

.error{display:flex;gap:12px;align-items:flex-start;justify-content:space-between;margin-top:16px;padding:13px 14px;
  border-radius:14px;background:var(--danger-bg);color:var(--danger);font-size:14.5px;line-height:1.4}
.error button{flex:none;border:0;background:none;color:inherit;font-weight:700;text-decoration:underline;padding:0}

/* ---------- library grid ---------- */
.section-head{display:flex;align-items:baseline;justify-content:space-between;margin:28px 0 12px}
.section-head h2{margin:0;font-size:18px;font-weight:700}
.section-head span,.link-btn{font-size:13.5px;color:var(--muted)}
.link-btn{border:0;background:none;padding:6px 0;color:var(--accent);font-weight:600}
.search{display:flex;align-items:center;gap:10px;margin-top:16px;background:var(--surface);border:1px solid var(--line);border-radius:14px;padding:0 14px}
.search svg{width:18px;height:18px;color:var(--muted);flex:none}
.search input{flex:1;min-width:0;border:0;background:none;outline:none;padding:12px 0;font-size:15.5px}
.search input::placeholder{color:var(--muted)}
.filters{display:flex;gap:8px;margin:12px 0 16px;overflow-x:auto}
.filters button{flex:none;border:1px solid var(--line);border-radius:999px;padding:7px 14px;font-size:13.5px;font-weight:500;background:none;color:var(--text-2)}
.filters button[aria-pressed="true"]{background:var(--text);border-color:var(--text);color:var(--bg);font-weight:700}
.grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px 12px;align-items:start}
.card{display:flex;flex-direction:column;align-items:stretch;justify-content:flex-start;width:100%;text-align:left;border:0;background:none;padding:0;color:inherit}
.thumb{position:relative;aspect-ratio:16/10;border-radius:12px;overflow:hidden;background:var(--raised)}
.thumb img{position:absolute;top:0;right:0;bottom:0;left:0;width:100%;height:100%;object-fit:cover}
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
.switch-row{display:flex;align-items:center;gap:14px;padding:10px 0;border-top:1px solid var(--line-soft)}
.switch-row:first-of-type{border-top:0}
.switch-row .txt{flex:1}
.switch-row .txt b{display:block;font-size:15px;font-weight:600}
.switch-row .txt span{display:block;font-size:13px;color:var(--muted);line-height:1.4;margin-top:2px}
.switch{appearance:none;-webkit-appearance:none;flex:none;width:48px;height:28px;border-radius:999px;background:var(--raised);
  border:1px solid var(--line);position:relative;margin:0;cursor:pointer;transition:background .2s}
.switch::after{content:"";position:absolute;top:3px;left:3px;width:20px;height:20px;border-radius:50%;background:var(--text-2);transition:transform .2s,background .2s}
.switch:checked{background:var(--accent);border-color:var(--accent)}
.switch:checked::after{transform:translateX(20px);background:var(--on-accent)}

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
.hero img{position:absolute;top:0;right:0;bottom:0;left:0;width:100%;height:100%;object-fit:cover}
.hero .back{position:absolute;left:14px;top:calc(14px + env(safe-area-inset-top));width:44px;height:44px;border-radius:50%;border:0;
  background:rgba(18,22,31,.65);color:#fff;display:grid;place-items:center;z-index:2}
.hero .back svg{width:20px;height:20px}
.hero .cover-btn{position:absolute;right:14px;top:calc(14px + env(safe-area-inset-top));height:36px;border-radius:999px;border:0;
  background:rgba(18,22,31,.65);color:#fff;font-size:13px;font-weight:600;padding:0 12px;display:flex;align-items:center;gap:6px;z-index:2}
.hero .cover-btn svg{width:16px;height:16px}
.hero .dur{right:14px;bottom:34px;font-size:12px;padding:2px 7px;border-radius:5px}
.sheet-body{position:relative;margin-top:-22px;background:var(--bg);border-radius:24px 24px 0 0;padding:22px 20px 0}
.v-title{font-size:21px;line-height:1.28;font-weight:700;letter-spacing:-.015em;margin:0}
.v-meta{display:flex;flex-wrap:wrap;column-gap:12px;color:var(--muted);font-size:14px;margin-top:6px}
.notice{margin-top:14px;padding:11px 13px;background:var(--surface);border-radius:12px;font-size:13.5px;line-height:1.45;color:var(--text-2)}
.presets{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px;margin-top:18px}
.presets button{min-width:0;display:flex;flex-direction:column;align-items:flex-start;gap:1px;border:1px solid var(--line);border-radius:14px;
  background:var(--surface);padding:9px 13px;text-align:left}
.presets button b{font-size:14px;font-weight:700}
.presets button span{font-size:12px;color:var(--muted)}
.presets button[aria-pressed="true"]{border-color:var(--accent);background:#2A2416}
.pills{display:flex;gap:8px;margin-top:18px;flex-wrap:wrap}
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
.trim{margin-top:16px;background:var(--surface);border-radius:16px;padding:6px 16px}
.trim .switch-row{border-top:0}
.trim-body{padding:4px 0 14px}
.range{display:grid;grid-template-columns:48px 1fr 64px;align-items:center;gap:10px;margin-top:8px}
.range label{font-size:13.5px;color:var(--muted)}
.range input{width:100%;accent-color:var(--accent);margin:0;height:28px}
.range output{font-size:14px;font-weight:600;text-align:right;font-variant-numeric:tabular-nums}
.trim-note{font-size:12.5px;color:var(--muted);margin:10px 0 0}
.action{margin-top:22px;padding-bottom:8px}
.big-btn{width:100%;height:56px;border:0;border-radius:16px;background:var(--accent);color:var(--on-accent);font-weight:700;font-size:16px;
  display:flex;align-items:center;justify-content:center;gap:8px}
.big-btn.ghost{background:var(--raised);color:var(--text)}
.big-btn:disabled{opacity:.55;cursor:default}
.big-btn svg{width:20px;height:20px}
.progress-row{display:flex;justify-content:space-between;font-size:13.5px;color:var(--text-2);margin-bottom:8px;font-variant-numeric:tabular-nums}
.track{height:6px;border-radius:3px;background:var(--raised);overflow:hidden}
.track i{display:block;height:100%;width:0;background:var(--accent);transition:width .4s}
.hint{margin:10px 0 0;font-size:13px;color:var(--muted)}
.done-text{display:flex;gap:10px;align-items:flex-start;font-size:14.5px;line-height:1.45;color:var(--text-2);margin-bottom:14px}
.done-text svg{flex:none;width:22px;height:22px;color:var(--success)}
.two{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px}

/* ---------- playlist screen ---------- */
.pl-meta{color:var(--muted);font-size:14px;margin:4px 0 0}
.pl-tools{display:flex;justify-content:space-between;align-items:center;margin:18px 0 8px}
.pl-list{background:var(--surface);border-radius:16px;overflow:hidden}
.pl-item{display:flex;align-items:center;gap:12px;width:100%;border:0;background:none;text-align:left;padding:10px 14px;border-bottom:1px solid var(--line-soft)}
.pl-item:last-child{border-bottom:0}
.check{width:22px;height:22px;border-radius:7px;border:2px solid #3A4359;flex:none;display:grid;place-items:center}
.check svg{width:14px;height:14px;color:var(--on-accent);opacity:0}
.pl-item[aria-checked="true"] .check{background:var(--accent);border-color:var(--accent)}
.pl-item[aria-checked="true"] .check svg{opacity:1}
.pl-thumb{width:64px;height:40px;border-radius:7px;background:var(--raised);overflow:hidden;flex:none;position:relative}
.pl-thumb img{width:100%;height:100%;object-fit:cover}
.pl-item .t{flex:1;min-width:0;font-size:14px;font-weight:600;line-height:1.3;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
.pl-item .d{font-size:12.5px;color:var(--muted);font-variant-numeric:tabular-nums}
.sticky-action{position:sticky;bottom:0;background:linear-gradient(transparent,var(--bg) 30%);padding:24px 0 calc(16px + var(--safe-b))}

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

/* ---------- quick sheet (shared from another app) ---------- */
.q-scrim{position:fixed;top:0;right:0;bottom:0;left:0;background:rgba(5,7,12,.55)}
.q-sheet{position:fixed;left:0;right:0;bottom:0;max-width:560px;margin:0 auto;background:var(--surface);border-radius:24px 24px 0 0;
  padding:10px 18px calc(20px + var(--safe-b));animation:up .22s ease-out}
@keyframes up{from{transform:translateY(40px);opacity:0}}
.q-row{display:flex;gap:12px;align-items:center;margin-bottom:16px}
.q-row .pl-thumb{width:88px;height:56px;border-radius:10px}
.q-row .t{font-size:15.5px;font-weight:700;line-height:1.3;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
.q-row .m{font-size:13px;color:var(--muted);margin-top:2px}
.q-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(96px,1fr));gap:10px}
.q-grid .big-btn{height:52px;font-size:15px}
.q-more{display:block;margin:14px auto 0;border:0;background:none;color:var(--accent);font-weight:600;padding:8px}
.q-msg{display:flex;gap:12px;align-items:center;font-size:15px;line-height:1.45;color:var(--text-2);padding:8px 2px 16px}
.q-msg svg{flex:none;width:24px;height:24px}

/* ---------- older WebViews (Android 8 to 10 without updates) ---------- */
@supports not (aspect-ratio:1){
  .thumb,.hero{height:0;padding-top:62.5%}
}
.no-flexgap .head>*+*,.no-flexgap .link>*+*,.no-flexgap .clip-card>*+*,.no-flexgap .q-row>*+*,.no-flexgap .switch-row>*+*,
.no-flexgap .search>*+*,.no-flexgap .error>*+*,.no-flexgap .done-text>*+*,.no-flexgap .as-item>*+*,.no-flexgap .pl-item>*+*,
.no-flexgap .q-msg>*+*,.no-flexgap .big-btn>*+*,.no-flexgap .pill-btn>*+*,.no-flexgap .cover-btn>*+*{margin-left:10px}
.no-flexgap .chips>*,.no-flexgap .pills>*,.no-flexgap .row-btns>*,.no-flexgap .filters>*,.no-flexgap .v-meta>*{margin:0 8px 8px 0}
.no-flexgap .nav button>*+*{margin-top:3px}
.webview-hint{margin-top:16px;padding:13px 14px;border-radius:14px;background:var(--surface);border:1px solid var(--line);
  font-size:14px;line-height:1.45;color:var(--text-2)}
.webview-hint b{color:var(--text)}
.webview-hint button{display:block;margin-top:10px}

@media (prefers-reduced-motion:reduce){*{transition:none!important;animation:none!important}}
@keyframes spin{to{transform:rotate(360deg)}}
.spin{animation:spin .8s linear infinite}
</style>
</head>
<body>
<div class="app" id="app">

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

    <div class="clip-card" id="clipCard" hidden>
      <div class="txt"><b>Link copied</b><span id="clipHost"></span></div>
      <button type="button" class="pill-btn" id="clipSave">Save</button>
      <button type="button" class="icon-btn" id="clipDismiss" aria-label="Dismiss"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M6 6l12 12M18 6 6 18"/></svg></button>
    </div>

    <div class="webview-hint" id="webviewHint" hidden></div>

    <div class="chips" aria-label="Supported sites"><span>YouTube</span><span>Instagram</span><span>TikTok</span><span>X</span><span>Facebook</span><span>Vimeo</span></div>
    <div class="error" id="saveError" role="alert" hidden><span></span><button type="button" data-open-settings hidden>Settings</button></div>

    <div class="section-head"><h2>Recent</h2><button type="button" class="link-btn" id="seeAll" hidden>See all</button></div>
    <div class="grid" id="recentGrid"></div>
    <div class="empty" id="recentEmpty" hidden><b>Nothing saved yet</b>Paste a link above, or tap Share in YouTube, Instagram or TikTok and pick WebSave.</div>
  </main>

  <!-- ================= LIBRARY ================= -->
  <main class="screen" id="tab-library" hidden>
    <div class="section-head" style="margin:4px 0 0"><h1 class="page-title">Library</h1><span id="libCount"></span></div>
    <label class="search">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/></svg>
      <span class="sr-only">Search your library</span>
      <input id="libSearch" type="search" placeholder="Search by title or site">
    </label>
    <div class="filters" role="group" aria-label="Filter by type">
      <button type="button" data-filter="all" aria-pressed="true">All</button>
      <button type="button" data-filter="video" aria-pressed="false">Videos</button>
      <button type="button" data-filter="gif" aria-pressed="false">GIFs</button>
      <button type="button" data-filter="audio" aria-pressed="false">Audio</button>
    </div>
    <div class="grid" id="libGrid"></div>
    <div class="empty" id="libEmpty" hidden><b>Your library is empty</b>Everything you save shows up here.</div>
  </main>

  <!-- ================= SETTINGS ================= -->
  <main class="screen" id="tab-settings" hidden>
    <h1 class="page-title" style="margin-top:4px">Settings</h1>
    <section class="group">
      <h3>Downloads</h3>
      <label class="switch-row">
        <span class="txt"><b>Only on Wi-Fi</b><span>Downloads wait for Wi-Fi instead of using mobile data.</span></span>
        <input type="checkbox" class="switch" id="setWifi">
      </label>
      <p style="margin:8px 0 0" id="parallelText">Up to 2 downloads run at once; the rest wait in line and retry on their own if the connection drops.</p>
    </section>
    <section class="group">
      <h3>Download engine</h3>
      <label class="switch-row">
        <span class="txt"><b>Update automatically</b><span>Checks once a week, so links keep working when sites change.</span></span>
        <input type="checkbox" class="switch" id="setAuto">
      </label>
      <p style="margin-top:6px"><span class="state" id="engineState"></span></p>
      <div class="row-btns"><button type="button" class="btn" id="update">Update now</button></div>
      <div class="about" style="margin-top:10px"><span>Installed version</span><b id="aboutEngine">…</b></div>
    </section>
    <section class="group">
      <h3>YouTube cookies</h3>
      <p>Use these when YouTube asks for account verification. Export a cookies.txt file with YouTube open and import it here. <span class="state" id="cookieState"></span></p>
      <div class="row-btns">
        <label class="btn primary" for="cookieFile" tabindex="0" role="button" id="cookieLabel">Import cookies.txt</label>
        <input type="file" id="cookieFile" accept=".txt,text/plain" hidden>
        <button type="button" class="btn" id="cookieRemove" hidden>Remove</button>
      </div>
    </section>
    <section class="group" id="shortcutsGroup">
      <h3>Shortcuts</h3>
      <p>Share a link to WebSave from any app to save it without leaving that app. You can also add the <b>Save link</b> tile to your Quick Settings, or long-press the WebSave icon, to save whatever link you copied.</p>
    </section>
    <section class="group">
      <h3>Saved files</h3>
      <p>Videos, GIFs and covers go to the WebSave album in your gallery (Pictures/WebSave). Audio goes to Music/WebSave, with title, artist and cover art.</p>
    </section>
  </main>

  <!-- ================= VIDEO ================= -->
  <main class="video-view" id="view-video" hidden>
    <div class="hero">
      <img id="vThumb" alt="" referrerpolicy="no-referrer">
      <button class="back" id="vBack" aria-label="Back"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M15 5l-7 7 7 7"/></svg></button>
      <button class="cover-btn" id="vCover"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="3" y="4" width="18" height="16" rx="3"/><circle cx="9" cy="10" r="2"/><path d="m21 16-5-5-9 9"/></svg><span>Save cover</span></button>
      <span class="dur" id="vDur" hidden></span>
    </div>
    <div class="sheet-body">
      <h1 class="v-title" id="vTitle"></h1>
      <div class="v-meta" id="vMeta"></div>
      <div class="notice" id="vNotice" hidden></div>

      <div class="presets" id="vPresets" role="group" aria-label="Quick settings"></div>
      <div class="pills" role="radiogroup" aria-label="Format" id="vKinds"></div>
      <div class="options" role="radiogroup" aria-label="Quality" id="vOptions"></div>

      <section class="trim" id="vTrim" hidden>
        <label class="switch-row">
          <span class="txt"><b>Trim</b><span id="trimSummary">Save only part of it</span></span>
          <input type="checkbox" class="switch" id="trimOn">
        </label>
        <div class="trim-body" id="trimBody" hidden>
          <div class="range"><label for="trimStart">Start</label><input type="range" id="trimStart" min="0" step="1"><output id="trimStartOut" for="trimStart"></output></div>
          <div class="range"><label for="trimEnd">End</label><input type="range" id="trimEnd" min="0" step="1"><output id="trimEndOut" for="trimEnd"></output></div>
          <p class="trim-note" id="trimNote">Videos are cut at the nearest keyframe, so they may start up to a couple of seconds early.</p>
        </div>
      </section>

      <div class="error" id="videoError" role="alert" hidden><span></span><button type="button" data-open-settings hidden>Settings</button></div>

      <div class="action" id="actIdle">
        <button type="button" class="big-btn" id="download"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 4v11m0 0-4-4m4 4 4-4M5 19h14"/></svg><span id="downloadLabel">Download</span></button>
      </div>
      <div class="action" id="actBusy" hidden>
        <div class="progress-row"><span id="busyLabel">Preparing</span><span id="busyAmount"></span></div>
        <div class="track"><i id="busyBar"></i></div>
        <p class="hint">You can leave the app; progress shows in your notifications.</p>
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

  <!-- ================= PLAYLIST ================= -->
  <main class="screen" id="view-playlist" hidden>
    <div class="bar-head">
      <button class="icon-btn" id="plBack" aria-label="Back"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M15 5l-7 7 7 7"/></svg></button>
    </div>
    <h1 class="v-title" id="plTitle" style="margin-top:4px"></h1>
    <p class="pl-meta" id="plMeta"></p>
    <div class="pills" role="radiogroup" aria-label="Format" id="plKinds">
      <button type="button" role="radio" aria-checked="true" data-kind="video">Video</button>
      <button type="button" role="radio" aria-checked="false" data-kind="audio">Audio only</button>
    </div>
    <div class="pills" role="radiogroup" aria-label="Quality" id="plQuality" style="margin-top:10px">
      <button type="button" role="radio" aria-checked="true" data-q="best">Best</button>
      <button type="button" role="radio" aria-checked="false" data-q="720">Up to 720p</button>
      <button type="button" role="radio" aria-checked="false" data-q="480">Up to 480p</button>
    </div>
    <div class="pl-tools"><span class="pl-meta" id="plSelected" style="margin:0"></span><button type="button" class="link-btn" id="plAll">Select all</button></div>
    <div class="pl-list" id="plList" role="group" aria-label="Items"></div>
    <div class="sticky-action"><button type="button" class="big-btn" id="plDownload"></button></div>
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
    <button type="button" class="as-item" id="isCover"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="3" y="4" width="18" height="16" rx="3"/><circle cx="9" cy="10" r="2"/><path d="m21 16-5-5-9 9"/></svg>Save cover image</button>
    <button type="button" class="as-item" id="isAgain"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M4 12a8 8 0 0 1 14-5.3M20 12a8 8 0 0 1-14 5.3M18 3v4h-4M6 21v-4h4"/></svg>Save again with other options</button>
    <button type="button" class="as-item danger" id="isRemove"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M4 7h16M9 7V4h6v3M6 7l1 13h10l1-13"/></svg>Remove from library</button>
  </div>
</dialog>

<!-- ================= QUICK SHEET ================= -->
<div id="quick" hidden>
  <div class="q-scrim" id="qScrim"></div>
  <section class="q-sheet" role="dialog" aria-label="Save with WebSave">
    <div class="grab"></div>
    <div id="qBody"></div>
  </section>
</div>

<script>
// older WebViews don't support "gap" in flex layouts; detect it once and use margins instead
(function(){
  const d = document.createElement("div");
  d.style.cssText = "display:flex;flex-direction:column;row-gap:1px;position:absolute;visibility:hidden";
  d.appendChild(document.createElement("div")); d.appendChild(document.createElement("div"));
  document.documentElement.appendChild(d);
  if(d.scrollHeight !== 1) document.documentElement.classList.add("no-flexgap");
  d.remove();
})();
const $ = s => document.querySelector(s);
const $$ = s => [...document.querySelectorAll(s)];
const native = window.WebSaveAndroid || null;
const params = new URLSearchParams(location.search);
const QUICK = params.get("mode") === "quick";
const SPIN = '<svg class="spin" viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2.6" stroke-linecap="round"><path d="M12 3a9 9 0 1 0 9 9"/></svg>';
const ICON_OK = '<svg viewBox="0 0 24 24" fill="none" stroke="#A7E3C4" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><path d="m5 12.5 4.5 4.5L19 7.5"/></svg>';
const ICON_WARN = '<svg viewBox="0 0 24 24" fill="none" stroke="#FF8A80" stroke-width="2.2" stroke-linecap="round"><circle cx="12" cy="12" r="9"/><path d="M12 7v6M12 16.5v.5"/></svg>';
const ACTIVE = ["waiting_wifi","queued","retrying","analyzing","downloading","merging","converting","trimming","saving"];
const STATUS_LABEL = {waiting_wifi:"Waiting for Wi-Fi", queued:"Waiting in line", retrying:"Connection dropped, retrying",
  analyzing:"Preparing", downloading:"Downloading", merging:"Merging audio and video", converting:"Creating GIF",
  trimming:"Trimming", saving:"Saving to your gallery"};
const state = {tab:"save", view:"tabs", video:null, kinds:["video"], kind:"video", quality:null, preset:null,
  trim:{on:false, start:0, end:0}, job:null, timer:null, items:[], historyTimer:null, sheetItem:null,
  filter:"all", search:"", lastClip:"", playlist:null, plSelected:new Set(), plKind:"video", plQuality:"best"};

/* ---------- helpers ---------- */
async function api(path, opts={}){
  const r = await fetch(path, opts);
  const d = await r.json().catch(()=>({}));
  if(!r.ok){ const e = new Error(d.error || "The local server didn't respond. Reopen the app."); e.code = d.code; throw e; }
  return d;
}
const postJSON = (path, body) => api(path, {method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify(body)});
const esc = s => String(s == null ? "" : s).replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
function duration(s){
  if(s == null || s === "") return "";
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
function looksLikeLink(t){ return /^https?:\/\/[\w-]+(\.[\w-]+)+\S*$/i.test(t || ""); }
function hostOf(u){ try{ return new URL(u).hostname.replace(/^www\./, ""); }catch(e){ return u; } }
const PALETTE = ["#3D4F73","#6B4E3D","#3E5E4C","#5A4672","#4C5A6B","#6B3D4F"];
function tint(id){ let h = 0; for(const c of String(id)) h = (h*31 + c.charCodeAt(0)) >>> 0; return PALETTE[h % PALETTE.length]; }
const KIND_NAME = {audio:"Audio", gif:"GIF"};
function showError(box, msg, code){
  box.querySelector("span").textContent = msg;
  box.querySelector("[data-open-settings]").hidden = code !== "cookies";
  box.hidden = false;
}
let notifAsked = false;
function startedDownload(){
  if(!native) return;
  if(!notifAsked){ notifAsked = true; try{ native.requestNotifications(); }catch(e){} }
  try{ native.watchDownloads(); }catch(e){}
}

/* ---------- navigation ---------- */
const VIEWS = ["tab-save","tab-library","tab-settings","view-video","view-playlist"];
function showOnly(id){ VIEWS.forEach(v => $("#" + v).hidden = v !== id); window.scrollTo(0,0); }
function showTab(tab){
  state.tab = tab; state.view = "tabs";
  showOnly("tab-" + tab); $("#nav").hidden = false;
  $$("#nav button").forEach(b => {
    if(b.dataset.tab === tab) b.setAttribute("aria-current", "page"); else b.removeAttribute("aria-current");
  });
  if(tab === "settings") loadSettings(); else loadHistory();
}
function showView(id){ state.view = id; showOnly(id); $("#nav").hidden = true; }
window.handleBack = function(){
  if($("#itemSheet").open){ $("#itemSheet").close(); return true; }
  if(QUICK){ closeQuick(); return true; }
  if(state.view !== "tabs"){ showTab(state.tab); return true; }
  if(state.tab !== "save"){ showTab("save"); return true; }
  return false;
};
$$("#nav button").forEach(b => b.addEventListener("click", () => showTab(b.dataset.tab)));
$("#seeAll").addEventListener("click", () => showTab("library"));
$("#vBack").addEventListener("click", () => showTab(state.tab));
$("#plBack").addEventListener("click", () => showTab(state.tab));
$$("[data-open-settings]").forEach(b => b.addEventListener("click", () => showTab("settings")));

/* ---------- clipboard card ---------- */
function checkClipboard(){
  if(!native || QUICK || state.view !== "tabs" || state.tab !== "save") return;
  let t = ""; try{ t = native.paste(); }catch(e){}
  const link = extractLink(t);
  if(!looksLikeLink(link) || link === state.lastClip || state.items.some(i => i.url === link)) return;
  state.lastClip = link;
  $("#clipHost").textContent = hostOf(link) + link.replace(/^https?:\/\/[^/]+/, "").slice(0, 40);
  $("#clipCard").hidden = false;
  $("#clipSave").onclick = () => { $("#clipCard").hidden = true; receiveLink(link); };
}
$("#clipDismiss").addEventListener("click", () => { $("#clipCard").hidden = true; });
window.onAppFocus = function(){ if(QUICK) quickFocus(); else checkClipboard(); };

/* ---------- library ---------- */
function cardHTML(item){
  const meta = [item.site, KIND_NAME[item.kind] || item.label].filter(Boolean).join(", ");
  let badge;
  if(item.active){
    const waiting = ["waiting_wifi","queued"].includes(item.status);
    badge = `<span class="badge" style="background:${waiting ? "#C9D2E3" : "var(--accent)"}">${waiting ? (item.status === "queued" ? "In line" : "Wi-Fi") : Math.floor(item.progress||0) + "%"}</span>`;
  }
  else if(item.kind === "audio") badge = `<span class="badge" style="background:#C9D2E3">Audio</span>`;
  else if(item.kind === "gif") badge = `<span class="badge" style="background:#D2C4F5">GIF</span>`;
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
function filteredItems(){
  const q = state.search.trim().toLowerCase();
  return state.items.filter(i => {
    const kind = i.kind === "audio" || i.kind === "gif" ? i.kind : "video";
    if(state.filter !== "all" && kind !== state.filter) return false;
    return !q || `${i.title || ""} ${i.site || ""} ${i.channel || ""}`.toLowerCase().includes(q);
  });
}
function renderLibrary(){
  const items = state.items;
  $("#recentGrid").innerHTML = items.slice(0, 4).map(cardHTML).join("");
  $("#recentEmpty").hidden = items.length > 0;
  $("#seeAll").hidden = items.length <= 4;
  const shown = filteredItems();
  $("#libGrid").innerHTML = shown.map(cardHTML).join("");
  $("#libEmpty").hidden = shown.length > 0;
  $("#libEmpty").innerHTML = items.length ? "<b>Nothing found</b>Try another word or filter." : "<b>Your library is empty</b>Everything you save shows up here.";
  const saved = items.filter(i => !i.active).length;
  $("#libCount").textContent = saved ? `${saved} saved` : "";
}
async function loadHistory(){
  // nothing to repaint while the app is in the background; the notification shows progress
  if(document.hidden){ clearTimeout(state.historyTimer); return; }
  try{ state.items = (await api("/api/history")).items || []; }catch(e){ return; }
  renderLibrary();
  clearTimeout(state.historyTimer);
  if(state.items.some(i => i.active) && state.view === "tabs") state.historyTimer = setTimeout(loadHistory, 1500);
}
$("#libSearch").addEventListener("input", e => { state.search = e.target.value; renderLibrary(); });
$$(".filters button").forEach(b => b.addEventListener("click", () => {
  state.filter = b.dataset.filter;
  $$(".filters button").forEach(x => x.setAttribute("aria-pressed", String(x === b)));
  renderLibrary();
}));
document.addEventListener("click", e => {
  const card = e.target.closest(".card"); if(!card) return;
  const item = state.items.find(i => i.id === card.dataset.id); if(!item) return;
  if(item.active){ reopenJob(item); return; }
  openItemSheet(item);
});
function openItemSheet(item){
  state.sheetItem = item;
  $("#isTitle").textContent = item.title || "Untitled video";
  $("#isSub").textContent = [item.site, KIND_NAME[item.kind] || item.label, bytes(item.size), item.location].filter(Boolean).join(", ");
  $("#isShare").hidden = !(native && item.uri);
  $("#isCover").hidden = !item.thumbnail;
  $("#isAgain").hidden = !item.url;
  $("#itemSheet").showModal();
}
$("#itemSheet").addEventListener("click", e => { if(e.target === $("#itemSheet")) $("#itemSheet").close(); });
$("#isOpen").addEventListener("click", () => {
  const it = state.sheetItem; $("#itemSheet").close();
  if(native && it.uri) native.open(it.uri, it.mime || "video/mp4"); else location.href = "/api/file/" + it.id;
});
$("#isShare").addEventListener("click", () => { const it = state.sheetItem; $("#itemSheet").close(); native.share(it.uri, it.mime || "video/mp4"); });
$("#isCover").addEventListener("click", () => { const it = state.sheetItem; $("#itemSheet").close(); saveCover(it.thumbnail, it.title); });
$("#isAgain").addEventListener("click", () => { const it = state.sheetItem; $("#itemSheet").close(); showTab("save"); receiveLink(it.url); });
$("#isRemove").addEventListener("click", async () => {
  const it = state.sheetItem; $("#itemSheet").close();
  await api("/api/history/" + it.id, {method:"DELETE"}).catch(()=>{}); loadHistory();
});

async function saveCover(url, title, button){
  if(button){ button.disabled = true; button.querySelector("span").textContent = "Saving…"; }
  try{
    const r = await postJSON("/api/thumbnail", {url, title});
    if(r.id) location.href = "/api/file/" + r.id;
    toast(r.location ? `Cover saved to ${r.location}` : "Cover sent to your downloads");
  }catch(e){ toast(e.message); }
  if(button){ button.disabled = false; button.querySelector("span").textContent = "Save cover"; }
}
function toast(msg){
  if(native && native.toast){ native.toast(msg); return; }
  const t = document.createElement("div");
  t.textContent = msg;
  t.style.cssText = "position:fixed;left:50%;bottom:110px;transform:translateX(-50%);background:#EEF1F6;color:#12161F;padding:10px 16px;border-radius:12px;font-size:14px;font-weight:600;z-index:20;max-width:90%";
  document.body.appendChild(t); setTimeout(() => t.remove(), 2600);
}

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
  $("#saveError").hidden = true; $("#clipCard").hidden = true;
  const b = $("#go"); b.disabled = true; b.innerHTML = SPIN;
  try{
    const d = await postJSON("/api/info", {url});
    if(d.playlist) openPlaylist(d); else openVideo(d);
    $("#url").value = "";
  }catch(err){ showError($("#saveError"), err.message, err.code); }
  b.disabled = false; updateGo();
}
function receiveLink(t){
  if(state.view !== "tabs" && !state.job) showTab("save");
  $("#url").value = extractLink(t); updateGo(); find();
}
window.receiveLink = receiveLink;

/* ---------- video screen ---------- */
const KIND_LABELS = {video:"Video", gif:"GIF", audio:"Audio only"};
function availableKinds(d){
  const kinds = d.gif_like ? ["gif", "video"] : ["video"];
  if(!d.gif_like && (!d.duration || d.duration <= 60)) kinds.push("gif");
  if(d.has_audio !== false) kinds.push("audio");
  return kinds;
}
function bestUnder(limit){
  const q = state.video.qualities.find(x => x.res <= limit);
  return q ? q.value : (state.video.qualities.length ? state.video.qualities[state.video.qualities.length - 1].value : "best");
}
function presetsFor(d){
  if(d.gif_like || !d.qualities.length) return [];
  const list = [
    {id:"capcut", title:"For CapCut", sub:"Sharpest H.264", apply:() => ({kind:"video", quality:bestUnder(1080), trim:null})},
    {id:"whatsapp", title:"For WhatsApp", sub:"Small, still clear", apply:() => ({kind:"video", quality:bestUnder(480), trim:null})},
  ];
  if(d.duration && d.duration > 60) list.push({id:"clip", title:"60 s clip", sub:"720p, first minute",
    apply:() => ({kind:"video", quality:bestUnder(720), trim:{start:0, end:60}})});
  if(d.has_audio !== false) list.push({id:"music", title:"Music", sub:"Audio with cover", apply:() => ({kind:"audio", quality:"best", trim:null})});
  return list;
}
function openVideo(d){
  state.video = d; state.kinds = availableKinds(d); state.kind = state.kinds[0]; state.preset = null;
  state.quality = d.qualities.length ? d.qualities[0].value : "best";
  state.trim = {on:false, start:0, end:Math.round(d.duration || 0)};
  stopTracking(); state.job = null;
  const img = $("#vThumb"); img.hidden = !d.thumbnail; img.src = d.thumbnail || ""; img.onerror = () => { img.hidden = true; };
  $(".hero").style.background = tint(d.url);
  $("#vCover").hidden = !d.thumbnail;
  $("#vDur").hidden = !d.duration; $("#vDur").textContent = duration(d.duration);
  $("#vTitle").textContent = d.title || "Untitled video";
  $("#vMeta").innerHTML = [d.channel, d.site].filter(Boolean).map(t => `<span>${esc(t)}</span>`).join("");
  $("#vNotice").hidden = !d.notice; $("#vNotice").textContent = d.notice || "";
  $("#videoError").hidden = true;
  setupTrim(); renderOptions(); setAction("idle"); showView("view-video");
}
function currentOption(){
  const d = state.video;
  if(state.kind === "audio") return {label:"Audio", size:d.audio_size};
  if(state.kind === "gif") return {label:"GIF", size:null};
  const q = d.qualities.find(x => x.value === state.quality);
  return q ? {label:resLabel(q.res), size:q.size} : {label:"Original", size:null};
}
function renderOptions(){
  const d = state.video;
  const presets = presetsFor(d);
  $("#vPresets").hidden = !presets.length;
  $("#vPresets").innerHTML = presets.map(p =>
    `<button type="button" data-preset="${p.id}" aria-pressed="${state.preset === p.id}"><b>${p.title}</b><span>${p.sub}</span></button>`).join("");
  $("#vKinds").innerHTML = state.kinds.map(k =>
    `<button type="button" role="radio" aria-checked="${k === state.kind}" data-kind="${k}">${KIND_LABELS[k]}</button>`).join("");
  let rows;
  if(state.kind === "audio") rows = [{value:"best", label:"Best audio", tag:"M4A with cover", size:d.audio_size}];
  else if(state.kind === "gif") rows = [{value:"480", label:"480 px wide", tag:"Sharper", size:null},
                                        {value:"320", label:"320 px wide", tag:"Smaller file", size:null}];
  else if(d.qualities.length) rows = d.qualities.slice(0,5).map(q => ({value:q.value, label:resLabel(q.res), tag:resTag(q.res), size:q.size}));
  else rows = [{value:"best", label:"Original", tag:"", size:null}];
  if(!rows.some(r => r.value === state.quality)) state.quality = rows[0].value;
  $("#vOptions").innerHTML = rows.map(r => `<button type="button" class="option" role="radio" aria-checked="${r.value === state.quality}" data-q="${r.value}">
    <span class="radio"><i></i></span><span class="lbl">${esc(r.label)}</span><span class="tag">${esc(r.tag)}</span><span class="size">${bytes(r.size)}</span></button>`).join("");
  const o = currentOption();
  const what = state.kind === "audio" ? "Download audio" : state.kind === "gif" ? "Save as GIF" : `Download ${o.label}`;
  $("#downloadLabel").textContent = state.trim.on ? `${what}, ${duration(state.trim.end - state.trim.start)}` : what;
  $("#trimNote").hidden = state.kind === "gif";
}
$("#vPresets").addEventListener("click", e => {
  const b = e.target.closest("button"); if(!b || state.job) return;
  const p = presetsFor(state.video).find(x => x.id === b.dataset.preset); if(!p) return;
  const v = p.apply();
  state.preset = p.id; state.kind = v.kind; state.quality = v.quality;
  if(v.trim){ setTrim(true, v.trim.start, Math.min(v.trim.end, Math.round(state.video.duration))); }
  else setTrim(false);
  renderOptions();
});
$("#vKinds").addEventListener("click", e => {
  const b = e.target.closest("button"); if(!b || state.job) return;
  state.kind = b.dataset.kind; state.preset = null;
  // GIFs work best short: suggest the first 10 seconds of a longer clip
  if(state.kind === "gif" && state.video.duration > 15 && !state.trim.on) setTrim(true, 0, 10);
  renderOptions();
});
$("#vOptions").addEventListener("click", e => {
  const b = e.target.closest(".option"); if(!b || state.job) return;
  state.quality = b.dataset.q; state.preset = null; renderOptions();
});
$("#vCover").addEventListener("click", () => saveCover(state.video.thumbnail, state.video.title, $("#vCover")));

/* ---------- trim ---------- */
function setupTrim(){
  const d = Math.round(state.video.duration || 0);
  $("#vTrim").hidden = !(d > 2);
  ["#trimStart", "#trimEnd"].forEach(s => { $(s).max = d; });
  setTrim(false);
}
function setTrim(on, start, end){
  const d = Math.round(state.video.duration || 0);
  state.trim.on = on;
  if(start != null) state.trim.start = Math.max(0, Math.min(start, d - 1));
  if(end != null) state.trim.end = Math.max(state.trim.start + 1, Math.min(end, d));
  if(!on){ state.trim.start = 0; state.trim.end = d; }
  $("#trimOn").checked = on; $("#trimBody").hidden = !on;
  $("#trimStart").value = state.trim.start; $("#trimEnd").value = state.trim.end;
  paintTrim();
}
function paintTrim(){
  $("#trimStartOut").textContent = duration(state.trim.start);
  $("#trimEndOut").textContent = duration(state.trim.end);
  $("#trimSummary").textContent = state.trim.on
    ? `${duration(state.trim.start)} to ${duration(state.trim.end)} (${duration(state.trim.end - state.trim.start)})`
    : "Save only part of it";
}
$("#trimOn").addEventListener("change", e => { setTrim(e.target.checked, 0, Math.round(state.video.duration)); state.preset = null; renderOptions(); });
$("#trimStart").addEventListener("input", e => {
  state.trim.start = Math.min(+e.target.value, state.trim.end - 1); e.target.value = state.trim.start; state.preset = null; paintTrim(); renderOptions();
});
$("#trimEnd").addEventListener("input", e => {
  state.trim.end = Math.max(+e.target.value, state.trim.start + 1); e.target.value = state.trim.end; state.preset = null; paintTrim(); renderOptions();
});

/* ---------- download ---------- */
function setAction(which){
  $("#actIdle").hidden = which !== "idle";
  $("#actBusy").hidden = which !== "busy";
  $("#actDone").hidden = which !== "done";
  $$("#vKinds button, #vOptions .option, #vPresets button, #trimOn, #trimStart, #trimEnd").forEach(b => b.disabled = which === "busy");
}
function trimPayload(){
  const d = Math.round(state.video.duration || 0);
  return state.trim.on && (state.trim.start > 0 || state.trim.end < d) ? {start:state.trim.start, end:state.trim.end} : null;
}
async function startDownload(body){
  const r = await postJSON("/api/download", body);
  startedDownload();
  return r.id;
}
$("#download").addEventListener("click", async () => {
  const d = state.video, o = currentOption();
  $("#videoError").hidden = true;
  setAction("busy"); paintBusy({status:"queued", progress:0});
  try{
    const trim = trimPayload();
    const id = await startDownload({url:d.url, kind:state.kind, quality:state.quality, label:o.label, trim,
      title:d.title, thumbnail:d.thumbnail, duration:trim ? trim.end - trim.start : d.duration, channel:d.channel, site:d.site});
    state.job = {id, size:trim && d.duration ? o.size * (trim.end - trim.start) / d.duration : o.size};
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
  $("#busyLabel").textContent = STATUS_LABEL[s.status] || "Preparing";
  const size = state.job && state.job.size;
  $("#busyAmount").textContent = s.status === "downloading" ? (size ? `${bytes(size*p/100) || "0 MB"} of ${bytes(size)}` : `${Math.floor(p)}%`) : "";
  $("#busyBar").style.width = (["analyzing","queued","waiting_wifi","retrying"].includes(s.status) ? 2 : p) + "%";
}
function stopTracking(){ clearTimeout(state.timer); }
async function track(){
  stopTracking();
  const job = state.job; if(!job) return;
  if(document.hidden) return;
  let s;
  try{ s = await api("/api/status/" + job.id); }catch(e){ state.timer = setTimeout(track, 1000); return; }
  if(state.job !== job) return;
  if(ACTIVE.includes(s.status)){ paintBusy(s); state.timer = setTimeout(track, 600); return; }
  state.job = null;
  if(s.status === "done"){
    setAction("done");
    if(native && s.uri){
      $("#doneText").textContent = s.warning ? `${s.warning} It's in ${s.location}.`
        : s.mime === "image/gif" ? `Saved to ${s.location}. It plays as an animated GIF in your gallery.`
        : s.mime && s.mime.startsWith("audio") ? `Saved to ${s.location}, with title, artist and cover.`
        : `Saved to ${s.location}. It's in your gallery and ready for CapCut.`;
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
  openVideo({url:item.url, title:item.title, thumbnail:item.thumbnail, duration:item.duration, channel:item.channel,
    site:item.site, qualities:[], audio_size:null, notice:null});
  $("#vPresets").hidden = true; $("#vTrim").hidden = true; $("#vKinds").innerHTML = "";
  $("#vOptions").innerHTML = `<div class="option"><span class="lbl">${esc(KIND_NAME[item.kind] || item.label || "Video")}</span></div>`;
  state.job = {id:item.id, size:null};
  setAction("busy"); track();
}

/* ---------- playlists and carousels ---------- */
function openPlaylist(d){
  state.playlist = d; state.plSelected = new Set(d.entries.map(e => e.index));
  $("#plTitle").textContent = d.title;
  $("#plMeta").textContent = [d.channel, d.site, `${d.count} items`].filter(Boolean).join(", ")
    + (d.count > d.entries.length ? ` (showing the first ${d.entries.length})` : "");
  $("#plList").innerHTML = d.entries.map(e => `<button type="button" class="pl-item" role="checkbox" aria-checked="true" data-i="${e.index}">
    <span class="check"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><path d="m5 12.5 4.5 4.5L19 7.5"/></svg></span>
    <span class="pl-thumb" style="background:${tint(e.index + d.url)}">${e.thumbnail ? `<img src="${esc(e.thumbnail)}" alt="" loading="lazy" referrerpolicy="no-referrer" onerror="this.remove()">` : ""}</span>
    <span class="t">${esc(e.title)}</span><span class="d">${duration(e.duration)}</span></button>`).join("");
  paintPlaylist(); showView("view-playlist");
}
function paintPlaylist(){
  const n = state.plSelected.size, total = state.playlist.entries.length;
  $$("#plList .pl-item").forEach(b => b.setAttribute("aria-checked", String(state.plSelected.has(+b.dataset.i))));
  $("#plSelected").textContent = `${n} of ${total} selected`;
  $("#plAll").textContent = n === total ? "Select none" : "Select all";
  $("#plDownload").textContent = n ? `Download ${n} ${n === 1 ? "item" : "items"}` : "Select at least one item";
  $("#plDownload").disabled = !n;
  $$("#plKinds button").forEach(b => b.setAttribute("aria-checked", String(b.dataset.kind === state.plKind)));
  $$("#plQuality button").forEach(b => b.setAttribute("aria-checked", String(b.dataset.q === state.plQuality)));
  $("#plQuality").hidden = state.plKind === "audio";
}
$("#plList").addEventListener("click", e => {
  const b = e.target.closest(".pl-item"); if(!b) return;
  const i = +b.dataset.i; state.plSelected.has(i) ? state.plSelected.delete(i) : state.plSelected.add(i); paintPlaylist();
});
$("#plAll").addEventListener("click", () => {
  const all = state.playlist.entries.map(e => e.index);
  state.plSelected = state.plSelected.size === all.length ? new Set() : new Set(all); paintPlaylist();
});
$("#plKinds").addEventListener("click", e => { const b = e.target.closest("button"); if(b){ state.plKind = b.dataset.kind; paintPlaylist(); } });
$("#plQuality").addEventListener("click", e => { const b = e.target.closest("button"); if(b){ state.plQuality = b.dataset.q; paintPlaylist(); } });
async function downloadPlaylist(entries, kind, quality){
  const d = state.playlist;
  const label = kind === "audio" ? "Audio" : ({best:"Best", "720":"720p", "480":"480p"}[quality]);
  for(const e of entries){
    await startDownload({url:d.url, item:e.index, kind, quality, label, title:e.title, thumbnail:e.thumbnail,
      duration:e.duration, channel:d.channel, site:d.site});
  }
}
$("#plDownload").addEventListener("click", async () => {
  const chosen = state.playlist.entries.filter(e => state.plSelected.has(e.index));
  $("#plDownload").disabled = true; $("#plDownload").innerHTML = SPIN;
  try{ await downloadPlaylist(chosen, state.plKind, state.plQuality); showTab("library"); }
  catch(err){ toast(err.message); paintPlaylist(); }
});

/* ---------- settings ---------- */
async function loadSettings(){
  try{
    const c = await api("/api/config");
    $("#cookieState").textContent = c.cookies ? "Cookies imported." : "No cookies imported.";
    $("#cookieRemove").hidden = !c.cookies;
    $("#aboutEngine").textContent = `yt-dlp ${c.engine}`;
    $("#setWifi").checked = !!c.settings.wifi_only;
    $("#setAuto").checked = !!c.settings.auto_update;
    const last = c.settings.last_update_check;
    $("#engineState").textContent = c.settings.engine_note ||
      (last ? `Last checked ${new Date(last * 1000).toLocaleDateString()}.` : "Not checked yet.");
    $("#shortcutsGroup").hidden = !c.app;
    $("#parallelText").textContent = c.parallel === 1
      ? "This phone runs one download at a time to stay smooth; the rest wait in line and retry on their own if the connection drops."
      : `Up to ${c.parallel || 2} downloads run at once; the rest wait in line and retry on their own if the connection drops.`;
  }catch(e){}
}
async function saveSetting(key, value){ await postJSON("/api/settings", {[key]: value}).catch(()=>{}); }
$("#setWifi").addEventListener("change", e => saveSetting("wifi_only", e.target.checked));
$("#setAuto").addEventListener("change", e => saveSetting("auto_update", e.target.checked));
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
  b.disabled = false; b.textContent = "Update now";
});

/* ---------- quick sheet: shared from another app ---------- */
function closeQuick(){ if(native) native.close(); }
function quickRender(html){ $("#qBody").innerHTML = html; }
function quickMessage(icon, text, buttons=""){
  quickRender(`<div class="q-msg">${icon}<span>${esc(text)}</span></div>${buttons}`);
}
function quickOpenFull(url){ if(native) native.openFull(url || ""); }
async function quickStart(link){
  quickMessage(SPIN, "Reading the link…");
  let d;
  try{ d = await postJSON("/api/info", {url:link}); }
  catch(err){
    quickMessage(ICON_WARN, err.message, `<div class="q-grid"><button class="big-btn ghost" id="qClose">Close</button><button class="big-btn" id="qFull">Open WebSave</button></div>`);
    $("#qClose").onclick = closeQuick; $("#qFull").onclick = () => quickOpenFull(link); return;
  }
  const thumb = `<span class="pl-thumb" style="background:${tint(link)}">${d.thumbnail ? `<img src="${esc(d.thumbnail)}" alt="" referrerpolicy="no-referrer" onerror="this.remove()">` : ""}</span>`;
  if(d.playlist){
    state.playlist = d;
    quickRender(`<div class="q-row">${thumb}<div><div class="t">${esc(d.title)}</div><div class="m">${d.count} items${d.site ? ", " + esc(d.site) : ""}</div></div></div>
      <div class="q-grid"><button class="big-btn" id="qAllVideo">Save all</button><button class="big-btn ghost" id="qAllAudio">All as audio</button></div>
      <button class="q-more" id="qFull">Choose items in WebSave</button>`);
    $("#qAllVideo").onclick = () => quickGo(() => downloadPlaylist(d.entries, "video", "best"), `${d.entries.length} items`);
    $("#qAllAudio").onclick = () => quickGo(() => downloadPlaylist(d.entries, "audio", "best"), `${d.entries.length} items`);
    $("#qFull").onclick = () => quickOpenFull(link);
    return;
  }
  const meta = [d.site, duration(d.duration)].filter(Boolean).join(", ");
  const best = d.qualities.length ? d.qualities[0] : null;
  const buttons = [];
  if(d.gif_like) buttons.push(["gif", "480", "GIF", "GIF"]);
  buttons.push(["video", best ? best.value : "best", best ? `Video ${resLabel(best.res)}` : "Video", best ? resLabel(best.res) : "Original"]);
  if(!d.gif_like && d.has_audio !== false) buttons.push(["audio", "best", "Audio", "Audio"]);
  quickRender(`<div class="q-row">${thumb}<div><div class="t">${esc(d.title || "Untitled video")}</div><div class="m">${esc(meta)}</div></div></div>
    <div class="q-grid">${buttons.map((b, i) => `<button class="big-btn${i ? " ghost" : ""}" data-i="${i}">${esc(b[2])}</button>`).join("")}</div>
    <button class="q-more" id="qFull">More options: trim, quality, GIF</button>`);
  $$("#qBody .q-grid button").forEach(btn => btn.onclick = () => {
    const [kind, quality, , label] = buttons[+btn.dataset.i];
    quickGo(() => startDownload({url:d.url, kind, quality, label, title:d.title, thumbnail:d.thumbnail,
      duration:d.duration, channel:d.channel, site:d.site}), d.title);
  });
  $("#qFull").onclick = () => quickOpenFull(link);
}
async function quickGo(fn, what){
  quickMessage(SPIN, "Starting…");
  try{
    await fn();
    quickMessage(ICON_OK, "Saving to your gallery. Follow the progress in your notifications.");
    setTimeout(closeQuick, 1400);
  }catch(err){
    quickMessage(ICON_WARN, err.message, `<div class="q-grid"><button class="big-btn ghost" id="qClose">Close</button></div>`);
    $("#qClose").onclick = closeQuick;
  }
}
let quickClipboardPending = false;
function quickFocus(){
  if(!quickClipboardPending) return;
  let t = ""; try{ t = native.paste(); }catch(e){}
  const link = extractLink(t);
  if(looksLikeLink(link)){ quickClipboardPending = false; quickStart(link); }
}
function initQuick(){
  document.body.classList.add("quick");
  $("#app").hidden = true; $("#nav").hidden = true; $("#quick").hidden = false;
  $("#qScrim").onclick = closeQuick;
  const link = params.get("url");
  if(link){ quickStart(link); return; }
  // opened from the Quick Settings tile or the icon shortcut: use the copied link
  quickClipboardPending = true;
  quickMessage(SPIN, "Looking for a copied link…");
  quickFocus();
  setTimeout(() => {
    if(!quickClipboardPending) return;
    quickMessage(ICON_WARN, "No link copied. Copy a video link first, then try again.",
      `<div class="q-grid"><button class="big-btn ghost" id="qClose">Close</button><button class="big-btn" id="qFull">Open WebSave</button></div>`);
    $("#qClose").onclick = closeQuick; $("#qFull").onclick = () => quickOpenFull("");
  }, 1500);
}

document.addEventListener("visibilitychange", () => {
  if(document.hidden || QUICK) return;
  if(state.job) track();
  else if(state.view === "tabs") loadHistory();
});

/* ---------- outdated WebView ---------- */
window.showWebViewHint = function(version){
  const box = $("#webviewHint");
  box.innerHTML = `<b>Make WebSave faster</b><br>This phone's Android System WebView (version ${esc(version)}) is out of date, which slows down apps like this one. Updating it is free.`
    + (native && native.openStore ? `<button type="button" class="btn" id="webviewUpdate">Update in Play Store</button>` : "");
  box.hidden = false;
  const b = $("#webviewUpdate"); if(b) b.onclick = () => native.openStore("com.google.android.webview");
};

/* ---------- start ---------- */
if(QUICK){ initQuick(); }
else{
  updateGo(); showTab("save");
  const initial = params.get("url");
  if(initial){ history.replaceState(null, "", "/"); receiveLink(initial); }
  setTimeout(checkClipboard, 600);
}
</script>
</body>
</html>"""
