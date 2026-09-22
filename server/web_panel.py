"""Built-in local control panel for Auto Codex Router.

Served by jev_server at http://127.0.0.1:4319/ . This module owns the static
HTML/JS page and a small, bounded tail reader for the live activity log. It does
not mutate state and never reads secrets.
"""
from __future__ import annotations

import json
import os

PANEL_PATH_TOKENS = ("/", "/panel", "/app", "/index.html")
RECENT_PATHS = ("/control/recent", "/v1/control/recent")
RECENT_LIMIT = 25
_TAIL_BYTES = 200_000


def recent_records(log_path: str, limit: int = RECENT_LIMIT):
    """Return the last `limit` simplified live-log records, oldest->newest.

    The log can be tens of MB, so only the final ~200KB is read. When that window
    does not reach the start of the file, the first (possibly truncated) line is
    discarded.
    """
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
    --bg:#0e141b; --panel:#161e27; --panel2:#1c2632; --line:#273442;
    --text:#e6edf3; --muted:#93a1b0; --teal:#2dd4bf; --teal-d:#0f766e;
    --green:#34d399; --amber:#fbbf24; --red:#f87171; --blue:#60a5fa;
  }
  *{box-sizing:border-box}
  body{margin:0;background:var(--bg);color:var(--text);
    font:14px/1.5 -apple-system,"Segoe UI",Roboto,"PingFang SC","Microsoft YaHei",sans-serif;}
  .wrap{max-width:980px;margin:0 auto;padding:20px 18px 60px;}
  header.top{display:flex;align-items:center;gap:12px;flex-wrap:wrap;margin-bottom:18px;}
  .brand{display:flex;align-items:center;gap:10px;font-weight:700;font-size:18px;}
  .logo{width:34px;height:34px;border-radius:9px;background:linear-gradient(135deg,var(--teal),var(--teal-d));
    display:grid;place-items:center;font-size:18px;}
  .brand small{display:block;font-weight:500;color:var(--muted);font-size:12px;}
  .spacer{flex:1}
  .langbtn{background:var(--panel);border:1px solid var(--line);color:var(--text);
    border-radius:8px;padding:6px 10px;cursor:pointer;}
  .langbtn:hover{border-color:var(--teal);}
  .grid{display:grid;gap:14px;grid-template-columns:1fr 1fr;}
  .card{background:var(--panel);border:1px solid var(--line);border-radius:13px;padding:16px;}
  .card h2{margin:0 0 12px;font-size:13px;letter-spacing:.04em;text-transform:uppercase;color:var(--muted);}
  .full{grid-column:1/-1}
  /* switch */
  .switchrow{display:flex;align-items:center;gap:16px;}
  .switch{position:relative;width:62px;height:34px;flex:0 0 auto;}
  .switch input{opacity:0;width:0;height:0;}
  .slider{position:absolute;inset:0;background:#3a4756;border-radius:34px;cursor:pointer;transition:.2s;}
  .slider:before{content:"";position:absolute;height:26px;width:26px;left:4px;top:4px;background:#fff;
    border-radius:50%;transition:.2s;}
  .switch input:checked + .slider{background:var(--teal-d);}
  .switch input:checked + .slider:before{transform:translateX(28px);}
  .switch input:disabled + .slider{opacity:.5;cursor:not-allowed;}
  .autotext strong{font-size:16px;}
  .autotext div{color:var(--muted);font-size:12px;}
  .pill{display:inline-block;padding:2px 9px;border-radius:999px;font-size:12px;font-weight:600;}
  .pill.on{background:rgba(45,212,191,.15);color:var(--teal);}
  .pill.off{background:#3a4756;color:var(--muted);}
  .kv{display:grid;grid-template-columns:auto 1fr;gap:7px 14px;}
  .kv dt{color:var(--muted);} .kv dd{margin:0;font-weight:600;}
  .mono{font-family:ui-monospace,Consolas,monospace;}
  .statrow{display:grid;grid-template-columns:repeat(5,1fr);gap:10px;}
  .stat{background:var(--panel2);border-radius:10px;padding:11px 12px;}
  .stat b{display:block;font-size:20px;}
  .stat span{color:var(--muted);font-size:11px;}
  .bar{height:9px;border-radius:6px;background:#3a4756;overflow:hidden;margin-top:13px;display:flex;}
  .bar i{height:100%;display:block;}
  .legend{display:flex;gap:14px;flex-wrap:wrap;margin-top:9px;font-size:12px;color:var(--muted);}
  .dot{display:inline-block;width:9px;height:9px;border-radius:2px;margin-right:5px;}
  table{width:100%;border-collapse:collapse;font-size:13px;}
  th,td{text-align:left;padding:7px 8px;border-bottom:1px solid var(--line);vertical-align:top;}
  th{color:var(--muted);font-weight:600;font-size:11px;text-transform:uppercase;letter-spacing:.03em;}
  tr:last-child td{border-bottom:none;}
  .tag{font-family:ui-monospace,Consolas,monospace;font-size:12px;white-space:nowrap;}
  .st-200{color:var(--green);} .st-err{color:var(--red);} .st-other{color:var(--amber);}
  .note{margin-top:10px;font-size:12px;color:var(--amber);min-height:16px;}
  .muted{color:var(--muted);}
  .ok{color:var(--green);} .warn{color:var(--amber);} .bad{color:var(--red);}
  a{color:var(--teal);}
  @media (max-width:720px){.grid{grid-template-columns:1fr}.statrow{grid-template-columns:repeat(2,1fr)}}
</style>
</head>
<body>
<div class="wrap">
  <header class="top">
    <div class="brand">
      <div class="logo">🧭</div>
      <div data-i18n="brand">Auto Codex Router
        <small data-i18n="brandSub">session-aware model routing · 会话感知模型路由</small>
      </div>
    </div>
    <div class="spacer"></div>
    <button class="langbtn" id="langBtn">中文</button>
  </header>

  <div class="grid">
    <div class="card">
      <h2 data-i18n="autoTitle">Auto routing · 自动路由</h2>
      <div class="switchrow">
        <label class="switch">
          <input type="checkbox" id="autoSwitch">
          <span class="slider"></span>
        </label>
        <div class="autotext">
          <strong id="autoStateLabel">—</strong>
          <div id="autoHint"></div>
        </div>
      </div>
      <div class="note" id="autoNote"></div>
    </div>

    <div class="card">
      <h2 data-i18n="curTitle">Current route · 当前路由</h2>
      <dl class="kv" id="curRoute">
        <dt data-i18n="model">Model</dt><dd id="rModel" class="mono">—</dd>
        <dt data-i18n="effort">Effort</dt><dd id="rEffort" class="mono">—</dd>
        <dt data-i18n="source">Source</dt><dd id="rSource" class="mono">—</dd>
        <dt data-i18n="why">Why</dt><dd id="rWhy" class="mono">—</dd>
        <dt data-i18n="time">Time</dt><dd id="rAt" class="mono">—</dd>
      </dl>
    </div>

    <div class="card full">
      <h2 data-i18n="todayTitle">Today · 今日统计 <span class="muted" id="todayDate"></span></h2>
      <div class="statrow">
        <div class="stat"><b id="sTotal">0</b><span data-i18n="stTotal">Total calls 总请求</span></div>
        <div class="stat"><b id="sJev">0</b><span data-i18n="stJev">Jev decisions 决策</span></div>
        <div class="stat"><b id="sKeep">0</b><span data-i18n="stKeep">Lease keep 复用</span></div>
        <div class="stat"><b id="sEsc">0</b><span data-i18n="stEsc">Escalations 升级</span></div>
        <div class="stat"><b id="sSaved">0</b><span data-i18n="stSaved">Decisions saved 省决策</span></div>
      </div>
      <div class="bar" id="mixBar"></div>
      <div class="legend">
        <span><i class="dot" style="background:var(--blue)"></i><span data-i18n="lgJev">Jev decision 决策</span></span>
        <span><i class="dot" style="background:var(--teal)"></i><span data-i18n="lgKeep">Lease keep 复用</span></span>
        <span><i class="dot" style="background:var(--amber)"></i><span data-i18n="lgEsc">Escalation 升级</span></span>
        <span><i class="dot" style="background:#6b7a8d"></i><span data-i18n="lgOther">Fallback/other 其他</span></span>
      </div>
    </div>

    <div class="card full">
      <h2 data-i18n="actTitle">Live activity · 实时活动</h2>
      <table>
        <thead><tr>
          <th data-i18n="colTime">Time</th>
          <th data-i18n="colModel">Model</th>
          <th data-i18n="colSource">Source</th>
          <th data-i18n="colStatus">Status</th>
          <th data-i18n="colTask">Task</th>
        </tr></thead>
        <tbody id="actBody"><tr><td colspan="5" class="muted">…</td></tr></tbody>
      </table>
    </div>

    <div class="card full">
      <h2 data-i18n="sysTitle">System · 系统</h2>
      <dl class="kv">
        <dt data-i18n="policy">Policy version</dt><dd id="sysPolicy" class="mono">—</dd>
        <dt data-i18n="exact">Exact native route</dt><dd id="sysExact">—</dd>
        <dt data-i18n="router">Router control</dt><dd id="sysAvail">—</dd>
      </dl>
    </div>
  </div>
</div>

<script>
(function(){
  var L = {
    en:{brand:"Auto Codex Router",on:"ON",off:"OFF",autoHintOn:"Requests are routed per turn.",
      autoHintOff:"Codex's own model choice is used.",
      disabled:"Switch busy…",flight:"A routing request is in flight; try again shortly.",
      saved:"saved",none:"No activity yet."},
    zh:{brand:"自动 Codex 路由",on:"开启",off:"关闭",autoHintOn:"按每个会话轮次进行路由。",
      autoHintOff:"使用 Codex 自带的模型选择。",
      disabled:"切换忙…",flight:"有路由请求正在进行，请稍后再试。",
      saved:"已省",none:"暂无活动。"}
  };
  var lang = (navigator.language||"en").toLowerCase().indexOf("zh")===0 ? "zh":"en";
  var lastStatus = null, busy = false;

  function t(k){ return (L[lang]&&L[lang][k])||L.en[k]||k; }
  function el(id){ return document.getElementById(id); }
  function shortModel(m){ if(!m) return "—"; var p=String(m).split("/"); return p[p.length-1]; }

  function applyLang(){
    el("langBtn").textContent = lang==="zh"?"EN":"中文";
    var map={brand:"brand"};
  }
  function setLang(l){ lang=l; document.documentElement.lang = l==="zh"?"zh-CN":"en";
    el("langBtn").textContent = l==="zh"?"EN":"中文"; render(); }
  el("langBtn").addEventListener("click",function(){ setLang(lang==="zh"?"en":"zh"); });

  function sourceLabel(s){
    var zhMap={jev:"Jev 决策",lease:"租约复用",lease_escalation:"失败升级",
      fallback:"兜底",jev_error_fallback:"出错兜底",off:"关闭"};
    var enMap={jev:"Jev decision",lease:"Lease reuse",lease_escalation:"Escalation",
      fallback:"Fallback",jev_error_fallback:"Error fallback",off:"Off"};
    return (lang==="zh"?zhMap:enMap)[s]||s||"—";
  }

  function renderStatus(s){
    var sw=el("autoSwitch");
    sw.checked = !!s.auto;
    sw.disabled = busy;
    el("autoStateLabel").innerHTML = s.auto
      ? '<span class="pill on">'+t("on")+'</span>'
      : '<span class="pill off">'+t("off")+'</span>';
    el("autoHint").textContent = s.auto ? t("autoHintOn") : t("autoHintOff");

    var r=s.route||{};
    el("rModel").textContent = shortModel(r.model);
    el("rEffort").textContent = r.effort||"—";
    el("rSource").textContent = sourceLabel(r.source);
    el("rWhy").textContent = r.lease_reason||r.gate||"—";
    el("rAt").textContent = r.at||"—";

    var d=s.today||{};
    el("todayDate").textContent = d.date?("("+d.date+")"):"";
    el("sTotal").textContent=d.total||0;
    el("sJev").textContent=d.jev_decisions||0;
    el("sKeep").textContent=d.lease_keep||0;
    el("sEsc").textContent=d.local_escalations||0;
    el("sSaved").textContent=(d.jev_saved||0);

    var total=d.total||0;
    function pct(n){ return total? (n/total*100):0; }
    var jev=d.jev_decisions||0, keep=d.lease_keep||0, esc=d.local_escalations||0;
    var other=Math.max(0,total-jev-keep-esc);
    var bar=el("mixBar"); bar.innerHTML="";
    [["var(--blue)",jev],["var(--teal)",keep],["var(--amber)",esc],["#6b7a8d",other]]
      .forEach(function(a){ var i=document.createElement("i"); i.style.width=pct(a[1])+"%";
        i.style.background=a[0]; bar.appendChild(i); });

    el("sysPolicy").textContent=s.policy_version||"—";
    el("sysExact").innerHTML = s.exact_native_route
      ? '<span class="ok">✓</span>' : '<span class="warn">–</span>';
    el("sysAvail").innerHTML = s.available
      ? '<span class="ok">'+(lang==="zh"?"可用":"available")+'</span>'
      : '<span class="bad">'+(s.error||(lang==="zh"?"不可用":"unavailable"))+'</span>';
  }

  function renderRecent(rows){
    var tb=el("actBody");
    if(!rows||!rows.length){ tb.innerHTML='<tr><td colspan="5" class="muted">'+t("none")+'</td></tr>'; return; }
    var html="";
    rows.slice().reverse().forEach(function(r){
      var st=r.status, cls = st===200?"st-200":(st==null?"":"st-err");
      if(st!==200&&st!=null) cls="st-other";
      var src=r.reason||r.source? sourceLabel(r.source):"";
      html+="<tr><td class='tag muted'>"+(r.at||"")+"</td>"+
        "<td class='tag'>"+shortModel(r.model)+(r.effort?(" · "+r.effort):"")+"</td>"+
        "<td class='tag'>"+sourceLabel(r.source)+"</td>"+
        "<td class='tag "+cls+"'>"+(st==null?"—":st)+"</td>"+
        "<td>"+(r.task||"")+"</td></tr>";
    });
    tb.innerHTML=html;
  }

  function refresh(){
    fetch("/control/status").then(function(r){return r.json();})
      .then(function(s){ lastStatus=s; renderStatus(s); el("autoNote").textContent=s.error&&!s.available?s.error:""; })
      .catch(function(){});
    fetch("/control/recent").then(function(r){return r.json();})
      .then(function(d){ renderRecent(d.records||[]); }).catch(function(){});
  }

  el("autoSwitch").addEventListener("change",function(ev){
    var want=ev.target.checked;
    busy=true; el("autoNote").textContent=t("disabled"); renderStatus(lastStatus||{auto:!want});
    fetch("/control/auto",{method:"POST",headers:{"Content-Type":"application/json"},
      body:JSON.stringify({enabled:want})})
      .then(function(r){ return r.json().then(function(j){return {ok:r.ok,j:j};}); })
      .then(function(res){
        busy=false;
        if(!res.ok){ el("autoNote").textContent=t("flight"); }
        lastStatus=res.j; renderStatus(res.j);
      })
      .catch(function(){ busy=false; el("autoNote").textContent=t("flight"); });
  });

  setLang(lang);
  refresh();
  setInterval(refresh, 5000);
})();
</script>
</body>
</html>
'''
