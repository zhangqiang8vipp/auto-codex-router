"""Built-in local control panel for Auto Codex Router.

Served by jev_server at http://127.0.0.1:4319/ . Owns the static bilingual
HTML/JS single-page app and a bounded tail reader for the live activity log.
Does not mutate state and never reads secrets.
"""
from __future__ import annotations

import json
import os

PANEL_PATH_TOKENS = ("/", "/panel", "/app", "/index.html")
RECENT_PATHS = ("/control/recent", "/v1/control/recent")
RECENT_LIMIT = 25
_TAIL_BYTES = 200_000


def recent_records(log_path: str, limit: int = RECENT_LIMIT):
    """Return the last `limit` simplified live-log records, oldest->newest."""
    try:
        size = os.path.getsize(log_path)
    except OSError:
        return []
    with open(log_path, "rb") as fh:
        fh.seek(max(0, size - _TAIL_BYTES))
        raw = fh.read().decode("utf-8", "replace")
    lines = raw.splitlines()
    if size > _TAIL_BYTES and lines:
        lines = lines[1:]
    records = []
    for line in lines:
        try:
            rec = json.loads(line)
        except ValueError:
            continue
        if not isinstance(rec, dict):
            continue
        records.append({
            "at": rec.get("at"),
            "model": rec.get("model"),
            "effort": rec.get("effort"),
            "source": rec.get("route_source"),
            "lease_action": rec.get("lease_action"),
            "reason": rec.get("lease_reason"),
            "status": rec.get("status"),
            "step": rec.get("step"),
            "task": (str(rec.get("task") or "")[:80]),
        })
    return records[-limit:]


PANEL_HTML = r'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Auto Codex Router · 自动 Codex 路由</title>
<style>
  :root{
    --bg:#f5f5f7; --side:rgba(246,246,248,.82); --panel:#ffffff; --panel2:#f5f5f7;
    --line:rgba(0,0,0,.08); --text:#1d1d1f; --muted:#6e6e73;
    --teal:#34c759; --teal-d:#248a3d; --green:#34c759; --amber:#ff9500;
    --red:#ff3b30; --blue:#007aff; --accent:#007aff; --accent-d:#0066d6;
  }
  *{box-sizing:border-box}
  html,body{height:100%}
  body{margin:0;background:var(--bg);color:var(--text);
    font:14px/1.55 -apple-system,BlinkMacSystemFont,"SF Pro Display","SF Pro Text","Segoe UI",Roboto,"PingFang SC","Microsoft YaHei",sans-serif;}
  .app{display:grid;grid-template-columns:218px 1fr;min-height:100vh;}
  /* sidebar */
  .side{background:var(--side);backdrop-filter:saturate(180%) blur(20px);-webkit-backdrop-filter:saturate(180%) blur(20px);border-right:1px solid var(--line);padding:18px 14px;
    display:flex;flex-direction:column;gap:6px;position:sticky;top:0;height:100vh;}
  .brand{display:flex;align-items:center;gap:10px;font-weight:700;font-size:16px;padding:4px 6px 14px;}
  .logo{width:32px;height:32px;border-radius:9px;background:linear-gradient(135deg,var(--teal),var(--teal-d));
    display:grid;place-items:center;}
  .brand small{display:block;font-weight:500;color:var(--muted);font-size:11px;}
  .navbtn{display:flex;align-items:center;gap:10px;background:none;border:none;color:var(--muted);
    text-align:left;padding:9px 11px;border-radius:9px;cursor:pointer;font-size:14px;width:100%;}
  .navbtn:hover{background:var(--panel);color:var(--text);}
  .navbtn.active{background:rgba(0,122,255,.12);color:var(--accent);font-weight:600;}
  .navbtn .ic{width:18px;text-align:center;}
  .sidefoot{margin-top:auto;font-size:11px;color:var(--muted);padding:8px 6px 0;}
  .health{display:flex;align-items:center;gap:7px;}
  .dotd{width:8px;height:8px;border-radius:50%;background:var(--green);}
  /* main */
  .main{padding:22px 26px 60px;max-width:1080px;width:100%;}
  .topbar{display:none}
  .page{display:none;} .page.active{display:block;}
  h1.pageh{font-size:20px;margin:0 0 16px;}
  .grid{display:grid;gap:14px;grid-template-columns:1fr 1fr;}
  .card{background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:16px 17px;box-shadow:0 1px 2px rgba(0,0,0,.04),0 10px 28px rgba(0,0,0,.05);}
  .card h2{margin:0 0 13px;font-size:12px;letter-spacing:.05em;text-transform:uppercase;color:var(--muted);}
  .full{grid-column:1/-1}
  /* switch */
  .switchrow{display:flex;align-items:center;gap:16px;}
  .switch{position:relative;width:60px;height:33px;flex:0 0 auto;}
  .switch input{opacity:0;width:0;height:0;}
  .slider{position:absolute;inset:0;background:#e9e9eb;border-radius:33px;cursor:pointer;transition:.2s;}
  .slider:before{content:"";position:absolute;height:25px;width:25px;left:4px;top:4px;background:#fff;border-radius:50%;transition:.2s;}
  .switch input:checked + .slider{background:#34c759;}
  .switch input:checked + .slider:before{transform:translateX(27px);}
  .switch input:disabled + .slider{opacity:.5;cursor:not-allowed;}
  .autotext strong{font-size:15px;} .autotext div{color:var(--muted);font-size:12px;margin-top:2px;}
  .pill{display:inline-block;padding:2px 10px;border-radius:999px;font-size:12px;font-weight:600;}
  .pill.on{background:rgba(52,199,89,.15);color:#248a3d;} .pill.off{background:#e9e9eb;color:var(--muted);}
  .pill.ok{background:rgba(52,199,89,.14);color:#248a3d;} .pill.no{background:#e9e9eb;color:var(--muted);}
  .kv{display:grid;grid-template-columns:auto 1fr;gap:8px 14px;margin:0;}
  .kv dt{color:var(--muted);} .kv dd{margin:0;font-weight:600;}
  .mono{font-family:ui-monospace,Consolas,monospace;}
  .statrow{display:grid;grid-template-columns:repeat(5,1fr);gap:10px;}
  .stat{background:var(--panel2);border-radius:10px;padding:11px 12px;}
  .stat b{display:block;font-size:20px;} .stat span{color:var(--muted);font-size:11px;}
  .bar{height:9px;border-radius:6px;background:#e5e5ea;overflow:hidden;margin-top:14px;display:flex;}
  .bar i{height:100%;display:block;}
  .legend{display:flex;gap:14px;flex-wrap:wrap;margin-top:10px;font-size:12px;color:var(--muted);}
  .dot{display:inline-block;width:9px;height:9px;border-radius:2px;margin-right:5px;}
  /* tiers */
  .tiercards{display:grid;grid-template-columns:repeat(4,1fr);gap:11px;}
  .tierc{background:var(--panel2);border:1px solid var(--line);border-radius:11px;padding:13px;}
  .tierc .rank{font-size:11px;color:var(--muted);} .tierc b{display:block;margin:3px 0 6px;}
  .tierc p{margin:0;font-size:12px;color:var(--muted);}
  .effchips{display:flex;flex-wrap:wrap;gap:8px;}
  .eff{background:var(--panel2);border:1px solid var(--line);border-radius:9px;padding:7px 11px;font-size:12px;}
  .eff small{display:block;color:var(--muted);font-size:11px;}
  /* catalog */
  .group{margin-bottom:18px;}
  .group>h3{font-size:14px;margin:0 0 9px;display:flex;align-items:center;gap:9px;}
  .group>h3 .ranktag{background:var(--panel2);border:1px solid var(--line);border-radius:7px;
    font-size:11px;padding:2px 8px;color:var(--muted);}
  .models{display:grid;grid-template-columns:1fr 1fr;gap:11px;}
  .mcard{background:var(--panel2);border:1px solid var(--line);border-radius:11px;padding:13px 14px;}
  .mcard .mh{display:flex;align-items:center;gap:8px;margin-bottom:4px;}
  .mcard .mh b{font-size:14px;}
  .mcard p{margin:0 0 9px;font-size:12px;color:var(--muted);}
  .mchips{display:flex;flex-wrap:wrap;gap:5px;}
  .mchip{font-size:11px;padding:2px 7px;border-radius:6px;background:#ececf0;color:var(--muted);
    font-family:ui-monospace,Consolas,monospace;}
  .mchip.def{background:rgba(0,122,255,.12);color:var(--accent);}
  /* chain */
  .chain{display:flex;flex-direction:column;gap:9px;}
  .chainrow{display:flex;align-items:center;gap:11px;background:var(--panel2);border:1px solid var(--line);
    border-radius:10px;padding:10px 13px;}
  .chainrow .cdot{width:10px;height:10px;border-radius:50%;flex:0 0 auto;}
  .chainrow b{font-size:13px;} .chainrow .cstate{margin-left:auto;font-size:11px;}
  .whatlist{display:flex;flex-direction:column;gap:8px;}
  .whatrow{display:flex;gap:10px;align-items:flex-start;font-size:13px;}
  .whatrow .wic{width:22px;height:22px;border-radius:6px;background:var(--panel2);border:1px solid var(--line);
    display:grid;place-items:center;font-size:12px;flex:0 0 auto;}
  /* table */
  table{width:100%;border-collapse:collapse;font-size:13px;}
  th,td{text-align:left;padding:8px;border-bottom:1px solid var(--line);vertical-align:top;}
  th{color:var(--muted);font-weight:600;font-size:11px;text-transform:uppercase;letter-spacing:.03em;}
  tr:last-child td{border-bottom:none;}
  .tag{font-family:ui-monospace,Consolas,monospace;font-size:12px;white-space:nowrap;}
  .st-200{color:#248a3d;} .st-other{color:var(--amber);}
  /* keys */
  select,input[type=password],input[type=text]{width:100%;background:var(--panel2);border:1px solid var(--line);
    color:var(--text);border-radius:9px;padding:9px 11px;font-size:13px;}
  input:focus,select:focus{outline:none;border-color:var(--accent);}
  .keyform{display:grid;grid-template-columns:160px 1fr auto;gap:9px;align-items:center;margin-top:12px;}
  .btn{background:var(--accent-d);border:none;color:#fff;border-radius:10px;padding:9px 16px;cursor:pointer;font-size:13px;font-weight:600;}
  .btn:hover{background:var(--accent);} .btn:disabled{opacity:.5;cursor:not-allowed;}
  .note{margin-top:10px;font-size:12px;min-height:16px;} .note.ok{color:#248a3d;} .note.bad{color:var(--red);}
  .muted{color:var(--muted);} .okc{color:#248a3d;} .warnc{color:var(--amber);}
  .langbtn{background:var(--panel);border:1px solid var(--line);color:var(--text);border-radius:8px;
    padding:6px 11px;cursor:pointer;margin-left:auto;}
  .langbtn:hover{border-color:var(--accent);}
  @media (max-width:820px){
    .app{grid-template-columns:1fr}
    .side{display:none}
    .topbar{display:flex;align-items:center;gap:10px;margin-bottom:14px;}
    .topbar .brand{padding:0} .main{padding:16px}
    .grid,.models{grid-template-columns:1fr}
    .tiercards{grid-template-columns:1fr 1fr}
    .statrow{grid-template-columns:repeat(2,1fr)}
    .keyform{grid-template-columns:1fr}
  }
</style>
</head>
<body>
<div class="app">
  <aside class="side">
    <div class="brand"><div class="logo">🧭</div><div><span data-i18n="brand">Auto Codex Router</span>
      <small data-i18n="brandSub">session-aware runtime</small></div></div>
    <button class="navbtn active" data-page="overview"><span class="ic">🏠</span><span data-i18n="nav.overview">Overview</span></button>
    <button class="navbtn" data-page="decision"><span class="ic">🧠</span><span data-i18n="nav.decision">Decision</span></button>
    <button class="navbtn" data-page="models"><span class="ic">📦</span><span data-i18n="nav.models">Work Models</span></button>
    <button class="navbtn" data-page="activity"><span class="ic">📡</span><span data-i18n="nav.activity">Live Activity</span></button>
    <button class="navbtn" data-page="keys"><span class="ic">🔑</span><span data-i18n="nav.keys">Keys</span></button>
    <div class="sidefoot"><div class="health"><span class="dotd" id="healthDot"></span><span id="healthText" data-i18n="healthy">service healthy</span></div></div>
  </aside>

  <div class="main">
    <div class="topbar">
      <div class="brand"><div class="logo">🧭</div><span data-i18n="brand">Auto Codex Router</span></div>
      <button class="langbtn" id="langBtn">中文</button>
    </div>
    <div style="display:flex;align-items:center;">
      <h1 class="pageh" id="pageHeading"></h1>
      <button class="langbtn" id="langBtn2" style="margin-bottom:14px;">中文</button>
    </div>

    <!-- OVERVIEW -->
    <section class="page active" id="page-overview">
      <div class="grid">
        <div class="card">
          <h2 data-i18n="ov.auto">Auto routing</h2>
          <div class="switchrow">
            <label class="switch"><input type="checkbox" id="autoSwitch"><span class="slider"></span></label>
            <div class="autotext"><strong id="autoStateLabel"></strong>
              <div id="autoHint"></div></div>
          </div>
          <div class="note" id="autoNote"></div>
        </div>
        <div class="card">
          <h2 data-i18n="ov.current">Current route</h2>
          <dl class="kv">
            <dt data-i18n="ov.model">Model</dt><dd class="mono" id="rModel">—</dd>
            <dt data-i18n="ov.effort">Effort</dt><dd class="mono" id="rEffort">—</dd>
            <dt data-i18n="ov.source">Source</dt><dd class="mono" id="rSource">—</dd>
            <dt data-i18n="ov.why">Why</dt><dd class="mono" id="rWhy">—</dd>
            <dt data-i18n="ov.time">Time</dt><dd class="mono" id="rAt">—</dd>
          </dl>
        </div>
        <div class="card full">
          <h2 data-i18n="ov.today">Today <span class="muted" id="todayDate"></span></h2>
          <div class="statrow">
            <div class="stat"><b id="sTotal">0</b><span data-i18n="ov.stTotal">Total</span></div>
            <div class="stat"><b id="sJev">0</b><span data-i18n="ov.stJev">Decisions</span></div>
            <div class="stat"><b id="sKeep">0</b><span data-i18n="ov.stKeep">Lease keep</span></div>
            <div class="stat"><b id="sEsc">0</b><span data-i18n="ov.stEsc">Escalations</span></div>
            <div class="stat"><b id="sSaved">0</b><span data-i18n="ov.stSaved">Saved</span></div>
          </div>
          <div class="bar" id="mixBar"></div>
          <div class="legend">
            <span><i class="dot" style="background:var(--blue)"></i><span data-i18n="lg.jev">Decision</span></span>
            <span><i class="dot" style="background:var(--teal)"></i><span data-i18n="lg.keep">Lease keep</span></span>
            <span><i class="dot" style="background:var(--amber)"></i><span data-i18n="lg.esc">Escalation</span></span>
            <span><i class="dot" style="background:#aeb2b8"></i><span data-i18n="lg.other">Other</span></span>
          </div>
        </div>
      </div>
    </section>

    <!-- DECISION -->
    <section class="page" id="page-decision">
      <div class="grid">
        <div class="card">
          <h2 data-i18n="dv.judge">Decision judge</h2>
          <div class="chainrow"><span class="cdot" style="background:var(--teal)"></span>
            <b id="judgeName">—</b><span class="cstate" id="judgeKey"></span></div>
        </div>
        <div class="card">
          <h2 data-i18n="dv.what">What it decides</h2>
          <div class="whatlist">
            <div class="whatrow"><span class="wic">🎚️</span><span data-i18n="dv.model_tier">Model tier</span></div>
            <div class="whatrow"><span class="wic">🧠</span><span data-i18n="dv.reasoning_effort">Reasoning effort</span></div>
            <div class="whatrow"><span class="wic">⏳</span><span data-i18n="dv.lease">Route lease</span></div>
          </div>
          <div class="note muted" data-i18n="dv.policy">Policy: KEEP by default; REPLAN only on evidence.</div>
        </div>
        <div class="card full">
          <h2 data-i18n="dv.chain">Decision chain</h2>
          <div class="chain" id="chainList"></div>
        </div>
      </div>
    </section>

    <!-- MODELS -->
    <section class="page" id="page-models">
      <div class="card full" style="margin-bottom:14px;">
        <h2 data-i18n="md.tiers">Model tiers</h2>
        <div class="tiercards" id="tierCards"></div>
      </div>
      <div class="card full" style="margin-bottom:14px;">
        <h2 data-i18n="md.efforts">Reasoning levels</h2>
        <div class="effchips" id="effChips"></div>
      </div>
      <div class="card full">
        <h2 data-i18n="md.catalog">Execution models</h2>
        <div id="catalogGroups"></div>
      </div>
    </section>

    <!-- ACTIVITY -->
    <section class="page" id="page-activity">
      <div class="card full">
        <h2 data-i18n="ac.title">Live activity</h2>
        <table>
          <thead><tr>
            <th data-i18n="ac.time">Time</th><th data-i18n="ac.model">Model</th>
            <th data-i18n="ac.source">Source</th><th data-i18n="ac.status">Status</th>
            <th data-i18n="ac.task">Task</th>
          </tr></thead>
          <tbody id="actBody"></tbody>
        </table>
      </div>
    </section>

    <!-- KEYS -->
    <section class="page" id="page-keys">
      <div class="card full">
        <h2 data-i18n="ks.title">Keys</h2>
        <table>
          <thead><tr><th data-i18n="ks.key">Key</th><th data-i18n="ks.layer">Layer</th>
            <th data-i18n="ks.state">State</th></tr></thead>
          <tbody id="keyRows"></tbody>
        </table>
        <div class="keyform">
          <select id="keyKind"></select>
          <input type="password" id="keyValue" autocomplete="off" spellcheck="false" data-i18n-ph="ks.value">
          <button class="btn" id="keySave" data-i18n="ks.save">Save</button>
        </div>
        <div class="note" id="keyNote" data-i18n="ks.note">Keys are stored locally and never logged.</div>
      </div>
    </section>
  </div>
</div>

<script>
(function(){
  var STR={
  en:{"brand":"Auto Codex Router","brandSub":"session-aware runtime","nav.overview":"Overview",
    "nav.decision":"Decision","nav.models":"Work Models","nav.activity":"Live Activity","nav.keys":"Keys",
    "healthy":"service healthy","ov.auto":"Auto routing","ov.current":"Current route","ov.model":"Model",
    "ov.effort":"Effort","ov.source":"Source","ov.why":"Why","ov.time":"Time","ov.today":"Today",
    "ov.stTotal":"Total","ov.stJev":"Decisions","ov.stKeep":"Lease keep","ov.stEsc":"Escalations",
    "ov.stSaved":"Saved","lg.jev":"Decision","lg.keep":"Lease keep","lg.esc":"Escalation","lg.other":"Other",
    "dv.judge":"Decision judge","dv.what":"What it decides","dv.model_tier":"Model tier",
    "dv.reasoning_effort":"Reasoning effort","dv.lease":"Route lease",
    "dv.policy":"Policy: KEEP by default; REPLAN only on evidence.","dv.chain":"Decision chain",
    "dv.current":"current","dv.available":"available","dv.planned":"planned",
    "md.tiers":"Model tiers","md.efforts":"Reasoning levels","md.catalog":"Execution models",
    "md.special":"special / other","md.default":"default","md.hidden":"hidden from picker",
    "ac.title":"Live activity","ac.time":"Time","ac.model":"Model","ac.source":"Source",
    "ac.status":"Status","ac.task":"Task","ac.none":"No activity yet.",
    "ks.title":"Keys","ks.key":"Key","ks.layer":"Layer","ks.state":"State","ks.decision":"decision",
    "ks.provider":"provider","ks.value":"Paste key","ks.save":"Save","ks.note":"Keys are stored locally and never logged.",
    "ks.configured":"configured","ks.missing":"missing","ks.saved":"Saved.","flight":"Routing in flight; retry shortly.",
    "busy":"Working…","page.overview":"Overview","page.decision":"Decision","page.models":"Work Models",
    "page.activity":"Live Activity","page.keys":"Keys"},
  zh:{"brand":"自动 Codex 路由","brandSub":"会话感知运行时","nav.overview":"总览",
    "nav.decision":"决策层","nav.models":"干活模型","nav.activity":"实时活动","nav.keys":"密钥",
    "healthy":"服务正常","ov.auto":"自动路由","ov.current":"当前路由","ov.model":"模型",
    "ov.effort":"推理强度","ov.source":"来源","ov.why":"原因","ov.time":"时间","ov.today":"今日统计",
    "ov.stTotal":"总请求","ov.stJev":"决策","ov.stKeep":"租约复用","ov.stEsc":"升级",
    "ov.stSaved":"省决策","lg.jev":"决策","lg.keep":"租约复用","lg.esc":"升级","lg.other":"其他",
    "dv.judge":"当前决策者","dv.what":"决策内容","dv.model_tier":"模型挡位",
    "dv.reasoning_effort":"推理强度","dv.lease":"路由租约",
    "dv.policy":"策略：默认保持（KEEP），只有出现证据才重新规划（REPLAN）。","dv.chain":"决策链",
    "dv.current":"当前","dv.available":"可用","dv.planned":"计划中",
    "md.tiers":"模型挡位","md.efforts":"推理强度","md.catalog":"最终干活模型",
    "md.special":"特殊 / 其他","md.default":"默认","md.hidden":"不在选择器显示",
    "ac.title":"实时活动","ac.time":"时间","ac.model":"模型","ac.source":"来源",
    "ac.status":"状态","ac.task":"任务","ac.none":"暂无活动。",
    "ks.title":"密钥","ks.key":"密钥","ks.layer":"层级","ks.state":"状态","ks.decision":"决策",
    "ks.provider":"供应商","ks.value":"粘贴密钥","ks.save":"保存","ks.note":"密钥仅保存在本地，不会被记录。",
    "ks.configured":"已配置","ks.missing":"未配置","ks.saved":"已保存。","flight":"有路由请求进行中，请稍后再试。",
    "busy":"处理中…","page.overview":"总览","page.decision":"决策层","page.models":"干活模型",
    "page.activity":"实时活动","page.keys":"密钥"}
  };
  var lang=(navigator.language||"en").toLowerCase().indexOf("zh")===0?"zh":"en";
  var catalog=null,status=null,busy=false;
  function $(id){return document.getElementById(id);}
  function t(k){var s=STR[lang][k];return s===undefined?k:s;}
  function esc(s){return String(s==null?"":s).replace(/[&<>]/g,function(c)
    {return {"&":"&amp;","<":"&lt;",">":"&gt;"}[c];});}
  function shortModel(m){if(!m)return"—";var p=String(m).split("/");return p[p.length-1];}

  var SOURCE_ZH={jev:"Jev 决策",lease:"租约复用",lease_escalation:"失败升级",
    fallback:"兜底",jev_error_fallback:"出错兜底",off:"关闭"};
  var SOURCE_EN={jev:"Jev decision",lease:"Lease reuse",lease_escalation:"Escalation",
    fallback:"Fallback",jev_error_fallback:"Error fallback",off:"Off"};
  function sourceLabel(s){return (lang==="zh"?SOURCE_ZH:SOURCE_EN)[s]||s||"—";}

  function localize(){
    document.documentElement.lang=lang==="zh"?"zh-CN":"en";
    document.querySelectorAll("[data-i18n]").forEach(function(e){e.textContent=t(e.getAttribute("data-i18n"));});
    document.querySelectorAll("[data-i18n-ph]").forEach(function(e){e.placeholder=t(e.getAttribute("data-i18n-ph"));});
    $("langBtn").textContent=lang==="zh"?"EN":"中文";
    $("langBtn2").textContent=lang==="zh"?"EN":"中文";
    ["overview","decision","models","activity","keys"].forEach(function(p){
      if($("page-"+p).classList.contains("active")) $("pageHeading").textContent=t("page."+p);
    });
  }
  function setLang(l){lang=l;localize();renderAll();}
  $("langBtn").addEventListener("click",function(){setLang(lang==="zh"?"en":"zh");});
  $("langBtn2").addEventListener("click",function(){setLang(lang==="zh"?"en":"zh");});

  document.querySelectorAll(".navbtn").forEach(function(b){
    b.addEventListener("click",function(){
      document.querySelectorAll(".navbtn").forEach(function(x){x.classList.remove("active");});
      document.querySelectorAll(".page").forEach(function(x){x.classList.remove("active");});
      b.classList.add("active");
      var p=b.getAttribute("data-page");
      $("page-"+p).classList.add("active");
      $("pageHeading").textContent=t("page."+p);
    });
  });

  function renderStatus(s){
    status=s;
    var sw=$("autoSwitch"); sw.checked=!!s.auto; sw.disabled=busy;
    $("autoStateLabel").innerHTML=s.auto?'<span class="pill on">'+(lang==="zh"?"开启":"ON")+'</span>'
      :'<span class="pill off">'+(lang==="zh"?"关闭":"OFF")+'</span>';
    $("autoHint").textContent=s.auto
      ?(lang==="zh"?"每个用户轮次路由，续接沿用该路由。":"Each user turn is routed; continuations keep the route.")
      :(lang==="zh"?"使用 Codex 自带的模型选择。":"Codex's own model choice goes through.");
    var r=s.route||{};
    $("rModel").textContent=shortModel(r.model);
    $("rEffort").textContent=r.effort||"—";
    $("rSource").textContent=sourceLabel(r.source);
    $("rWhy").textContent=r.lease_reason||r.gate||"—";
    $("rAt").textContent=r.at||"—";
    var d=s.today||{};
    $("todayDate").textContent=d.date?("("+d.date+")"):"";
    $("sTotal").textContent=d.total||0;$("sJev").textContent=d.jev_decisions||0;
    $("sKeep").textContent=d.lease_keep||0;$("sEsc").textContent=d.local_escalations||0;
    $("sSaved").textContent=d.jev_saved||0;
    var total=d.total||0;function pct(n){return total?(n/total*100):0;}
    var jev=d.jev_decisions||0,keep=d.lease_keep||0,esc=d.local_escalations||0;
    var other=Math.max(0,total-jev-keep-esc),bar=$("mixBar");bar.innerHTML="";
    [["var(--blue)",jev],["var(--teal)",keep],["var(--amber)",esc],["#aeb2b8",other]]
      .forEach(function(a){var i=document.createElement("i");i.style.width=pct(a[1])+"%";
        i.style.background=a[0];bar.appendChild(i);});
    $("healthDot").style.background=s.available?"var(--green)":"var(--red)";
    $("healthText").textContent=s.available?t("healthy"):(s.error||"");
  }

  function tierShort(id){var p=String(id).split("-");return p[p.length-1];}
  function renderCatalog(c){
    catalog=c;
    // tiers
    $("tierCards").innerHTML=c.tiers.map(function(tx){
      return '<div class="tierc"><span class="rank">#'+tx.rank+'</span><b class="mono">'+
        esc(tierShort(tx.id))+'</b><p>'+esc(tx.profile)+'</p></div>';}).join("");
    // efforts
    $("effChips").innerHTML=c.efforts.map(function(e){
      return '<span class="eff mono">'+e.id+'<small>'+esc(e.profile)+'</small></span>';}).join("");
    // catalog groups
    var html="";
    c.execution.forEach(function(g){
      var title=g.tier==="special"?t("md.special"):esc(tierShort(g.tier));
      html+='<div class="group"><h3><span class="ranktag">'+title+'</span></h3>';
      html+='<div class="models">'+g.models.map(function(m){
        var chips=m.efforts.map(function(e){
          return '<span class="mchip'+(e.effort===m.default_effort?" def":"")+'">'+e.effort+
            (e.effort===m.default_effort?" · "+t("md.default"):"")+'</span>';}).join("");
        var hidden=m.visibility==="hide"?'<span class="pill off">'+t("md.hidden")+'</span>':"";
        return '<div class="mcard"><div class="mh"><b>'+esc(m.name)+'</b>'+hidden+'</div><p>'+
          esc(m.description)+'</p><div class="mchips">'+chips+'</div></div>';
      }).join("")+'</div></div>';
    });
    $("catalogGroups").innerHTML=html;
    // decision
    var j=c.decision.judge;
    $("judgeName").textContent=j.name;
    $("judgeKey").innerHTML=j.key_configured
      ?'<span class="pill ok">'+t("ks.configured")+'</span>'
      :'<span class="pill no">'+t("ks.missing")+'</span>';
    $("chainList").innerHTML=c.decision.chain.map(function(r){
      var color=r.current?"var(--accent)":(r.available?"var(--green)":"#aeb2b8");
      var state=r.current?t("dv.current"):(r.available?t("dv.available"):t("dv.planned"));
      return '<div class="chainrow"><span class="cdot" style="background:'+color+'"></span><b>'+
        esc(r.name)+'</b><span class="cstate muted">'+state+'</span></div>';}).join("");
    // keys
    $("keyRows").innerHTML=c.keys.map(function(k){
      var layer=k.layer==="decision"?t("ks.decision"):t("ks.provider");
      var st=k.configured?'<span class="pill ok">'+t("ks.configured")+'</span>'
        :'<span class="pill no">'+t("ks.missing")+'</span>';
      return '<tr><td class="tag">'+k.env+'</td><td>'+layer+'</td><td>'+st+'</td></tr>';}).join("");
    $("keyKind").innerHTML=c.keys.map(function(k){
      return '<option value="'+k.kind+'">'+k.env+'</option>';}).join("");
  }

  function renderRecent(rows){
    var tb=$("actBody");
    if(!rows||!rows.length){tb.innerHTML='<tr><td colspan="5" class="muted">'+t("ac.none")+'</td></tr>';return;}
    tb.innerHTML=rows.slice().reverse().map(function(r){
      var cls=r.status===200?"st-200":"st-other";
      return '<tr><td class="tag muted">'+(r.at||"")+'</td><td class="tag">'+shortModel(r.model)+
        (r.effort?" · "+r.effort:"")+'</td><td class="tag">'+sourceLabel(r.source)+'</td><td class="tag '+
        cls+'">'+(r.status==null?"—":r.status)+'</td><td>'+esc(r.task)+'</td></tr>';}).join("");
  }

  function renderAll(){if(status)renderStatus(status);if(catalog)renderCatalog(catalog);}

  function refresh(){
    fetch("/control/status").then(function(r){return r.json();})
      .then(renderStatus).catch(function(){});
    fetch("/control/catalog").then(function(r){return r.json();})
      .then(renderCatalog).catch(function(){});
    fetch("/control/recent").then(function(r){return r.json();})
      .then(function(d){renderRecent(d.records||[]);}).catch(function(){});
  }

  $("autoSwitch").addEventListener("change",function(ev){
    var want=ev.target.checked;busy=true;$("autoNote").textContent=t("busy");
    if(status)renderStatus(Object.assign({},status,{auto:!want}));
    fetch("/control/auto",{method:"POST",headers:{"Content-Type":"application/json"},
      body:JSON.stringify({enabled:want})})
      .then(function(r){return r.json().then(function(j){return{ok:r.ok,j:j};});})
      .then(function(res){busy=false;if(!res.ok)$("autoNote").textContent=t("flight");
        renderStatus(res.j);})
      .catch(function(){busy=false;$("autoNote").textContent=t("flight");});
  });

  $("keySave").addEventListener("click",function(){
    var kind=$("keyKind").value,value=$("keyValue").value.trim();
    if(!value)return;
    $("keySave").disabled=true;$("keyNote").textContent=t("busy");
    fetch("/control/key",{method:"POST",headers:{"Content-Type":"application/json"},
      body:JSON.stringify({kind:kind,value:value})})
      .then(function(r){return r.json().then(function(j){return{ok:r.ok,j:j};});})
      .then(function(res){$("keySave").disabled=false;
        $("keyNote").className="note "+(res.ok?"ok":"bad");
        $("keyNote").textContent=res.ok?t("ks.saved"):(res.j.error||t("flight"));
        $("keyValue").value="";
        fetch("/control/catalog").then(function(r){return r.json();}).then(renderCatalog);})
      .catch(function(){$("keySave").disabled=false;$("keyNote").className="note bad";
        $("keyNote").textContent=t("flight");});
  });

  localize();refresh();
  setInterval(refresh,5000);
})();
</script>
</body>
</html>
'''
