import json
import os
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

DASHBOARD_HTML = r'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>HTTP 代理缓存服务器 - 管理面板</title>
<style>
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
:root{
  --bg:#f8f5f0;
  --surface:#fffefb;
  --border:#e8e3d8;
  --text:#1a1d23;
  --text2:#6b6560;
  --text3:#9c9488;
  --accent:#d97904;
  --accent-light:#fef7ed;
  --accent-hover:#b86503;
  --green:#059669;
  --green-bg:#ecfdf5;
  --green-light:#d1fae5;
  --red:#dc2626;
  --red-bg:#fef2f2;
  --red-light:#fecaca;
  --amber:#d97706;
  --amber-bg:#fffbeb;
  --amber-light:#fde68a;
  --purple:#7c3aed;
  --purple-bg:#f5f3ff;
  --blue:#2563eb;
  --blue-bg:#eff6ff;
  --shadow-sm:0 1px 2px rgba(0,0,0,.03);
  --shadow:0 2px 4px rgba(0,0,0,.06),0 1px 2px rgba(0,0,0,.04);
  --shadow-md:0 8px 16px rgba(0,0,0,.08),0 4px 8px rgba(0,0,0,.04);
  --shadow-lg:0 20px 32px rgba(0,0,0,.12),0 8px 16px rgba(0,0,0,.06);
  --radius:14px;
  --radius-sm:10px;
  --radius-xs:6px;
}
body{
  font-family:'Inter',system-ui,-apple-system,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;
  background:var(--bg);color:var(--text);line-height:1.6;
  -webkit-font-smoothing:antialiased;
  background-image:
    radial-gradient(circle at 20% 30%,rgba(217,121,4,0.02) 0%,transparent 50%),
    radial-gradient(circle at 80% 70%,rgba(124,58,237,0.02) 0%,transparent 50%);
}
.header{
  background:var(--surface);border-bottom:1px solid var(--border);
  padding:0 32px;height:60px;display:flex;align-items:center;justify-content:space-between;
  position:sticky;top:0;z-index:100;
  box-shadow:0 2px 8px rgba(0,0,0,.04);
  backdrop-filter:blur(8px);
  background:var(--surface);
}
.header-brand{display:flex;align-items:center;gap:12px}
.header-logo{
  width:32px;height:32px;
  background:linear-gradient(135deg,#d97904 0%,#b86503 100%);
  border-radius:8px;
  display:flex;align-items:center;justify-content:center;
  color:#fff;font-size:16px;
  box-shadow:0 2px 8px rgba(217,121,4,.3);
}
.header h1{font-size:16px;font-weight:600;letter-spacing:-.01em;color:var(--text)}
.header-meta{display:flex;align-items:center;gap:20px;font-size:13px;color:var(--text2)}
.header-meta span{display:flex;align-items:center;gap:6px;font-weight:500}
.status-dot{
  width:8px;height:8px;background:var(--green);border-radius:50%;
  animation:pulse 2s ease-in-out infinite;
  box-shadow:0 0 8px rgba(5,150,105,.4);
}
@keyframes pulse{0%,100%{opacity:1;transform:scale(1)}50%{opacity:.6;transform:scale(.9)}}
.container{max-width:1240px;margin:0 auto;padding:20px 24px}
.stats{display:grid;grid-template-columns:repeat(5,1fr);gap:16px;margin-bottom:20px}
@media(max-width:1100px){.stats{grid-template-columns:repeat(3,1fr)}}
@media(max-width:700px){.stats{grid-template-columns:1fr 1fr}}
.stat-card{
  background:var(--surface);border-radius:var(--radius);
  box-shadow:var(--shadow);border:1px solid var(--border);
  transition:all .3s cubic-bezier(.4,0,.2,1);
  position:relative;overflow:hidden;
  padding:18px 22px;
  display:flex;align-items:center;gap:16px;
}
.stat-card::before{
  content:'';position:absolute;top:0;left:0;right:0;height:3px;
  background:linear-gradient(90deg,transparent,var(--accent),transparent);
  opacity:0;transition:opacity .3s;
}
.stat-card:hover{transform:translateY(-4px);box-shadow:var(--shadow-lg)}
.stat-card:hover::before{opacity:1}
.stat-icon{
  width:48px;height:48px;min-width:48px;border-radius:12px;
  display:flex;align-items:center;justify-content:center;
  transition:transform .3s;
}
.stat-card:hover .stat-icon{transform:scale(1.1) rotate(5deg)}
.stat-icon.blue{background:linear-gradient(135deg,#dbeafe,#bfdbfe);color:#2563eb}
.stat-icon.green{background:linear-gradient(135deg,#d1fae5,#a7f3d0);color:#059669}
.stat-icon.purple{background:linear-gradient(135deg,#ede9fe,#ddd6fe);color:#7c3aed}
.stat-icon.amber{background:linear-gradient(135deg,#fef3c7,#fde68a);color:#d97706}
.stat-icon.indigo{background:linear-gradient(135deg,#e0e7ff,#c7d2fe);color:#4f46e5}
.stat-content{flex:1;min-width:0}
.stat-label{font-size:12px;font-weight:600;color:var(--text3);text-transform:uppercase;letter-spacing:.05em;margin-bottom:4px}
.stat-value{font-size:24px;font-weight:700;letter-spacing:-.03em;color:var(--text);line-height:1.2}
.stat-value.green{color:var(--green)}
.stat-value.red{color:var(--red)}
.stat-value.amber{color:var(--amber)}
.stat-value.accent{color:var(--accent)}
.stat-sub{font-size:12px;color:var(--text3);margin-top:2px;font-weight:500}
.row2{display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-bottom:20px}
@media(max-width:850px){.row2{grid-template-columns:1fr}}
.panel{
  background:var(--surface);border-radius:var(--radius);
  box-shadow:var(--shadow);border:1px solid var(--border);overflow:hidden;
  transition:all .3s cubic-bezier(.4,0,.2,1);
}
.panel:hover{box-shadow:var(--shadow-md)}
.panel-header{
  padding:14px 20px;border-bottom:1px solid var(--border);
  display:flex;align-items:center;justify-content:space-between;
  background:var(--surface);
}
.panel-header h2{font-size:15px;font-weight:600;letter-spacing:-.01em;color:var(--text);display:flex;align-items:center;gap:8px}
.panel-body{padding:16px 20px}
table{width:100%;border-collapse:collapse}
thead th{
  text-align:left;padding:10px 12px 10px 0;font-size:11px;font-weight:600;
  color:var(--text3);text-transform:uppercase;letter-spacing:.04em;
  border-bottom:2px solid var(--border);
}
tbody td{padding:10px 12px 10px 0;font-size:13px;border-bottom:1px solid rgba(232,227,216,.5)}
tbody tr:last-child td{border-bottom:none}
tbody tr{transition:all .2s}
tbody tr:hover{background:var(--accent-light)}
.td-url{max-width:320px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;display:block;color:var(--text);font-weight:500}
.bar-wrap{display:flex;align-items:center;gap:6px;min-width:80px}
.bar-track{flex:1;height:6px;background:var(--border);border-radius:3px;overflow:hidden}
.bar-fill{height:100%;background:linear-gradient(90deg,var(--accent),var(--amber));border-radius:3px;transition:width .6s cubic-bezier(.4,0,.2,1)}
.btn{
  display:inline-flex;align-items:center;gap:6px;
  padding:8px 16px;border:1px solid transparent;border-radius:var(--radius-xs);
  font-size:13px;font-weight:500;cursor:pointer;transition:all .2s;white-space:nowrap;
  font-family:inherit;position:relative;overflow:hidden;
}
.btn::after{
  content:'';position:absolute;top:50%;left:50%;width:0;height:0;
  border-radius:50%;background:rgba(255,255,255,.3);
  transform:translate(-50%,-50%);transition:width .4s,height .4s;
}
.btn:active::after{width:200px;height:200px}
.btn-primary{background:linear-gradient(135deg,#d97904 0%,#b86503 100%);color:#fff;border-color:var(--accent);box-shadow:0 2px 8px rgba(217,121,4,.25)}
.btn-primary:hover{transform:translateY(-1px);box-shadow:0 4px 12px rgba(217,121,4,.35)}
.btn-outline{background:var(--surface);color:var(--text);border-color:var(--border)}
.btn-outline:hover{background:var(--accent-light);border-color:var(--accent);color:var(--accent)}
.btn-outline.active{background:linear-gradient(135deg,#fef7ed 0%,#fff7ed 100%);color:var(--accent);border-color:var(--accent);font-weight:600;box-shadow:0 2px 8px rgba(217,121,4,.15)}
.btn-danger{background:linear-gradient(135deg,#dc2626 0%,#b91c1c 100%);color:#fff;border-color:var(--red);box-shadow:0 2px 8px rgba(220,38,38,.2)}
.btn-danger:hover{transform:translateY(-1px);box-shadow:0 4px 12px rgba(220,38,38,.3)}
.btn-success{background:linear-gradient(135deg,#059669 0%,#047857 100%);color:#fff;border-color:var(--green);box-shadow:0 2px 8px rgba(5,150,105,.2)}
.btn-success:hover{transform:translateY(-1px);box-shadow:0 4px 12px rgba(5,150,105,.3)}
.btn-xs{padding:4px 12px;font-size:11px;border-radius:var(--radius-xs)}
.input{
  padding:9px 14px;border:1.5px solid var(--border);border-radius:var(--radius-xs);
  font-size:13px;font-family:inherit;color:var(--text);
  background:var(--surface);width:200px;
  transition:all .25s cubic-bezier(.4,0,.2,1);
}
.input:focus{outline:none;border-color:var(--accent);box-shadow:0 0 0 4px rgba(217,121,4,.1),0 2px 8px rgba(217,121,4,.15);transform:translateY(-1px)}
.input::placeholder{color:var(--text3)}
.flex{display:flex;gap:8px;align-items:center;flex-wrap:wrap}
.log-viewer{
  background:linear-gradient(180deg,#1e1e2e 0%,#1a1a2e 100%);
  border-radius:var(--radius-sm);padding:16px 18px;
  max-height:340px;overflow-y:auto;
  font-family:'SF Mono','Cascadia Code','Fira Code','Consolas',monospace;
  font-size:12px;line-height:1.8;
  border:1px solid rgba(255,255,255,.05);
  box-shadow:inset 0 2px 8px rgba(0,0,0,.3);
}
.log-viewer::-webkit-scrollbar{width:8px}
.log-viewer::-webkit-scrollbar-track{background:transparent}
.log-viewer::-webkit-scrollbar-thumb{background:#3a3a4e;border-radius:4px}
.log-viewer::-webkit-scrollbar-thumb:hover{background:#4a4a5e}
.log-entry{padding:3px 0;border-bottom:1px solid rgba(255,255,255,.03);white-space:pre-wrap;word-break:break-all;position:relative;padding-left:16px}
.log-entry::before{content:'▸';position:absolute;left:0;color:var(--text3);opacity:.3}
.log-info{color:#a6adc8}
.log-cache{color:#a6e3a1}
.log-block{color:#cba6f7}
.log-error{color:#f38ba8}
.empty{color:var(--text3);font-size:13px;padding:16px 0;text-align:center}
.badge{display:inline-flex;align-items:center;gap:4px;padding:3px 10px;border-radius:20px;font-size:11px;font-weight:600}
.badge-green{background:linear-gradient(135deg,#ecfdf5 0%,#d1fae5 100%);color:var(--green)}
.badge-red{background:linear-gradient(135deg,#fef2f2 0%,#fecaca 100%);color:var(--red)}
.badge-accent{background:linear-gradient(135deg,#fef7ed 0%,#fde68a 100%);color:var(--accent)}
.badge-purple{background:linear-gradient(135deg,#f5f3ff 0%,#ddd6fe 100%);color:var(--purple)}
.badge-blue{background:linear-gradient(135deg,#eff6ff 0%,#bfdbfe 100%);color:var(--blue)}
.footer-bar{
  display:flex;justify-content:space-between;align-items:center;
  padding:16px 0 0;color:var(--text3);font-size:12px;font-weight:500;
}
.loading-skeleton{
  background:linear-gradient(90deg,var(--border) 25%,rgba(255,255,255,.6) 50%,var(--border) 75%);
  background-size:200% 100%;
  animation:shimmer 1.5s infinite;
  border-radius:var(--radius-xs);
}
@keyframes shimmer{0%{background-position:200% 0}100%{background-position:-200% 0}}
.fade-in{animation:fadeIn .5s ease-out}
@keyframes fadeIn{from{opacity:0;transform:translateY(12px)}to{opacity:1;transform:translateY(0)}}
.panel{animation:fadeIn .5s ease-out backwards}
.panel:nth-child(1){animation-delay:.05s}
.panel:nth-child(2){animation-delay:.1s}
.panel:nth-child(3){animation-delay:.15s}
.refresh-indicator{
  display:inline-flex;align-items:center;gap:6px;
  font-size:11px;color:var(--text3);font-weight:500;
}
.refresh-indicator::before{
  content:'';width:6px;height:6px;background:var(--green);border-radius:50%;
  animation:pulse 2s ease-in-out infinite;
}
</style>
</head>
<body>
<div class="header">
  <div class="header-brand">
    <div class="header-logo">
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/></svg>
    </div>
    <h1>HTTP 代理缓存服务器</h1>
  </div>
  <div class="header-meta">
    <span>
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="2" y="2" width="20" height="8" rx="2" ry="2"/><rect x="2" y="14" width="20" height="8" rx="2" ry="2"/><line x1="6" y1="6" x2="6.01" y2="6"/><line x1="6" y1="18" x2="6.01" y2="18"/></svg>
      端口 <b id="proxyPort">--</b>
    </span>
    <span>
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>
      运行时间 <b id="uptime">--</b>
    </span>
    <span><span class="status-dot"></span>运行中</span>
  </div>
</div>

<div class="container">
  <div class="stats">
    <div class="stat-card fade-in">
      <div class="stat-icon blue">
        <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/><polyline points="10 9 9 9 8 9"/></svg>
      </div>
      <div class="stat-content">
        <div class="stat-label">总请求数</div>
        <div class="stat-value" id="totalRequests">0</div>
      </div>
    </div>
    <div class="stat-card fade-in">
      <div class="stat-icon green">
        <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/></svg>
      </div>
      <div class="stat-content">
        <div class="stat-label">缓存命中率</div>
        <div class="stat-value green" id="hitRate">0%</div>
      </div>
    </div>
    <div class="stat-card fade-in">
      <div class="stat-icon purple">
        <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><ellipse cx="12" cy="5" rx="9" ry="3"/><path d="M21 12c0 1.66-4 3-9 3s-9-1.34-9-3"/><path d="M3 5v14c0 1.66 4 3 9 3s9-1.34 9-3V5"/></svg>
      </div>
      <div class="stat-content">
        <div class="stat-label">缓存条目</div>
        <div class="stat-value accent" id="cacheEntries">0</div>
        <div class="stat-sub" id="cacheSize"></div>
      </div>
    </div>
    <div class="stat-card fade-in">
      <div class="stat-icon amber">
        <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>
      </div>
      <div class="stat-content">
        <div class="stat-label">已拦截</div>
        <div class="stat-value amber" id="blockedRequests">0</div>
      </div>
    </div>
    <div class="stat-card fade-in">
      <div class="stat-icon indigo">
        <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="11" width="18" height="11" rx="2" ry="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/></svg>
      </div>
      <div class="stat-content">
        <div class="stat-label">访问控制</div>
        <div class="stat-value" id="acMode">全部允许</div>
      </div>
    </div>
  </div>

  <div class="row2">
    <div class="panel">
      <div class="panel-header">
        <h2>
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="color:var(--red)"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>
          黑名单
        </h2>
        <span class="badge badge-red" id="blCount">0</span>
      </div>
      <div class="panel-body">
        <div class="flex" style="margin-bottom:12px">
          <input class="input" id="blInput" placeholder="example.com / 1.2.3.4 / 1.2.3.0/24" style="flex:1" onkeydown="if(event.key==='Enter')addB()">
          <button class="btn btn-danger" onclick="addB()">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
            拦截
          </button>
        </div>
        <div style="max-height:240px;overflow-y:auto"><table><tbody id="blacklistTable"><tr><td class="empty">暂无条目</td></tr></tbody></table></div>
      </div>
    </div>
    <div class="panel">
      <div class="panel-header">
        <h2>
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="color:var(--green)"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></svg>
          白名单
        </h2>
        <span class="badge badge-green" id="wlCount">0</span>
      </div>
      <div class="panel-body">
        <div class="flex" style="margin-bottom:16px">
          <input class="input" id="wlInput" placeholder="example.com / 1.2.3.4 / 1.2.3.0/24" style="flex:1" onkeydown="if(event.key==='Enter')addW()">
          <button class="btn btn-success" onclick="addW()">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
            允许
          </button>
        </div>
        <div style="max-height:240px;overflow-y:auto"><table><tbody id="whitelistTable"><tr><td class="empty">暂无条目</td></tr></tbody></table></div>
      </div>
    </div>
  </div>

  <div class="panel" style="margin-bottom:20px">
    <div class="panel-header">
      <h2>
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="11" width="18" height="11" rx="2" ry="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/></svg>
        访问控制模式
      </h2>
    </div>
    <div class="panel-body">
      <div class="flex">
        <button class="btn btn-outline active" id="btnModeOff" onclick="setMode('off')">全部允许</button>
        <button class="btn btn-outline" id="btnModeBlacklist" onclick="setMode('blacklist')">黑名单模式</button>
        <button class="btn btn-outline" id="btnModeWhitelist" onclick="setMode('whitelist')">白名单模式</button>
        <span style="flex:1"></span>
        <button class="btn btn-outline" onclick="clearCache()">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>
          清空缓存
        </button>
      </div>
    </div>
  </div>

  <div class="panel" style="margin-bottom:20px">
    <div class="panel-header">
      <h2>
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>
        请求头修改
      </h2>
    </div>
    <div class="panel-body">
      <div class="flex" style="margin-bottom:10px">
        <input class="input" id="hKey" placeholder="Header 名称" style="width:200px !important;">
        <input class="input" id="hVal" placeholder="Header 值" style="width:200px !important;">
        <button class="btn btn-primary" onclick="addHeader()">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
          添加请求头
        </button>
      </div>
      <div class="flex" style="margin-bottom:12px">
        <input class="input" id="uaVal" placeholder="自定义 User-Agent" style="width:400px !important;">
        <button class="btn btn-outline" onclick="setUA()">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 20h9"/><path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4L16.5 3.5z"/></svg>
          设置 User-Agent
        </button>
      </div>
      <table><thead><tr><th>类型</th><th>名称</th><th>值</th><th style="width:90px">操作</th></tr></thead>
        <tbody id="headersTable"><tr><td class="empty" colspan="4">暂无规则</td></tr></tbody></table>
    </div>
  </div>

  <div class="row2">
    <div class="panel">
      <div class="panel-header">
        <h2>
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="color:var(--accent)"><polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/></svg>
          热门 URL
        </h2>
      </div>
      <div class="panel-body" style="padding:0">
        <table><thead><tr><th style="padding-left:24px">#</th><th>URL</th><th>访问次数</th><th style="padding-right:24px"></th></tr></thead>
          <tbody id="hotResources"><tr><td colspan="4" class="empty">暂无数据</td></tr></tbody></table>
      </div>
    </div>
    <div class="panel">
      <div class="panel-header">
        <h2>
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="color:var(--green)"><circle cx="12" cy="12" r="10"/><line x1="2" y1="12" x2="22" y2="12"/><path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/></svg>
          热门域名
        </h2>
      </div>
      <div class="panel-body" style="padding:0">
        <table><thead><tr><th style="padding-left:24px">#</th><th>Domain</th><th>访问次数</th><th style="padding-right:24px"></th></tr></thead>
          <tbody id="hotDomains"><tr><td colspan="4" class="empty">暂无数据</td></tr></tbody></table>
      </div>
    </div>
  </div>

  <div class="panel">
    <div class="panel-header">
      <h2>
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/><polyline points="10 9 9 9 8 9"/></svg>
        实时日志
      </h2>
      <span class="refresh-indicator" id="lastRefresh">最后更新: --</span>
    </div>
    <div class="panel-body" style="padding:0">
      <div class="log-viewer" id="logViewer"><span style="color:#6c7086">等待活动...</span></div>
    </div>
  </div>

  <div class="footer-bar">
    <span>每 2 秒自动刷新</span>
    <span id="statusText">系统运行正常</span>
  </div>
</div>

<script>
const A='/api/';
async function J(p){try{const r=await fetch(A+p);return r.ok?r.json():null}catch(e){return null}}
async function P(p,b={}){try{const r=await fetch(A+p,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(b)});return r.ok?r.json():null}catch(e){return null}}

async function refresh(){
  const[S,C,BL,WL,CF,H,L,HD]=await Promise.all([J('stats'),J('cache'),J('blacklist'),J('whitelist'),J('config'),J('hot'),J('logs?n=40'),J('headers')]);
  if(S){Q('totalRequests',S.total.toLocaleString());Q('hitRate',S.hit_rate.toFixed(1)+'%');Q('blockedRequests',S.blocked);Q('uptime',U(S.uptime));Q('proxyPort',S.port||'--')}
  if(C){Q('cacheEntries',C.entries+' / '+C.max_entries);Q('cacheSize',(C.total_size/1024).toFixed(1)+' KB')}
  if(CF){
    const m=CF.mode;
    Q('acMode',m==='off'?'全部允许':m==='blacklist'?'黑名单':'白名单');
    document.getElementById('btnModeOff').className='btn btn-outline'+(m==='off'?' active':'');
    document.getElementById('btnModeBlacklist').className='btn btn-outline'+(m==='blacklist'?' active':'');
    document.getElementById('btnModeWhitelist').className='btn btn-outline'+(m==='whitelist'?' active':'');
  }
  if(BL){RT('blacklistTable',BL.items,'blacklist');Q('blCount',BL.items.length)}
  if(WL){RT('whitelistTable',WL.items,'whitelist');Q('wlCount',WL.items.length)}
  if(HD)renderHeaders(HD);
  if(H){
    const mxU=H.hot_urls.length>0?H.hot_urls[0][1]:1;
    document.getElementById('hotResources').innerHTML=H.hot_urls.length?H.hot_urls.map(([u,c],i)=>{const p=(c/mxU*100).toFixed(0);return `<tr><td style="padding-left:24px;color:var(--text3);font-weight:600">${i+1}</td><td><span class="td-url" title="${E(u)}">${E(u)}</span></td><td style="font-weight:600">${c}</td><td style="padding-right:24px"><div class="bar-wrap"><div class="bar-track"><div class="bar-fill" style="width:${p}%"></div></div><span style="font-size:11px;color:var(--text3)">${p}%</span></div></td></tr>`}).join(''):'<tr><td colspan="4" class="empty">暂无数据</td></tr>';
    const mxD=H.hot_domains.length>0?H.hot_domains[0][1]:1;
    document.getElementById('hotDomains').innerHTML=H.hot_domains.length?H.hot_domains.map(([d,c],i)=>{const p=(c/mxD*100).toFixed(0);return `<tr><td style="padding-left:24px;color:var(--text3);font-weight:600">${i+1}</td><td>${E(d)}</td><td style="font-weight:600">${c}</td><td style="padding-right:24px"><div class="bar-wrap"><div class="bar-track"><div class="bar-fill" style="width:${p}%"></div></div><span style="font-size:11px;color:var(--text3)">${p}%</span></div></td></tr>`}).join(''):'<tr><td colspan="4" class="empty">暂无数据</td></tr>';
  }
  if(L&&L.lines){document.getElementById('logViewer').innerHTML=L.lines.map(l=>`<div class="log-entry log-${l.level}">${E(l.text)}</div>`).join('')}
  Q('lastRefresh','最后更新: '+new Date().toLocaleTimeString());
}

function RT(id,items,type){
  if(items.length===0){document.getElementById(id).innerHTML='<tr><td class="empty">暂无条目</td></tr>';return}
  document.getElementById(id).innerHTML=items.map(i=>`<tr><td style="font-weight:500">${E(i)}</td><td style="text-align:right"><button class="btn btn-outline btn-xs" onclick="removeItem('${type}','${E(i)}')">移除</button></td></tr>`).join('')
}
function Q(id,v){document.getElementById(id).textContent=v}
function E(s){const d=document.createElement('div');d.textContent=s;return d.innerHTML}
function U(s){const h=Math.floor(s/3600),m=Math.floor(s%3600/60),sec=s%60;return h+'h '+m+'m '+sec+'s'}
async function addB(){const i=document.getElementById('blInput');const d=i.value.trim();if(!d)return;await P('blacklist/add',{domain:d});i.value='';refresh()}
async function addW(){const i=document.getElementById('wlInput');const d=i.value.trim();if(!d)return;await P('whitelist/add',{domain:d});i.value='';refresh()}
async function removeItem(t,d){await P(t+'/del',{domain:d});refresh()}
async function setMode(m){await P('mode',{mode:m});refresh()}
async function clearCache(){if(confirm('确认清空所有缓存？')){await P('cache/clear');refresh()}}
async function addHeader(){const k=document.getElementById('hKey'),v=document.getElementById('hVal');if(!k.value.trim())return;await P('headers/add',{key:k.value.trim(),value:v.value});k.value='';v.value='';refresh()}
async function delHeader(k){await P('headers/del',{key:k});refresh()}
async function setUA(){const v=document.getElementById('uaVal').value.trim();if(!v)return;await P('headers/ua',{value:v});refresh()}
function renderHeaders(H){let rows=[];Object.entries(H.add||{}).forEach(([k,v])=>rows.push(`<tr><td><span class="badge badge-green">添加</span></td><td>${E(k)}</td><td>${E(v)}</td><td><button class="btn btn-outline btn-xs" onclick="delHeader('${E(k)}')">移除</button></td></tr>`));Object.entries(H.override||{}).forEach(([k,v])=>rows.push(`<tr><td><span class="badge badge-accent">覆盖</span></td><td>${E(k)}</td><td>${E(v)}</td><td></td></tr>`));(H.remove||[]).forEach(k=>rows.push(`<tr><td><span class="badge badge-red">过滤</span></td><td>${E(k)}</td><td>—</td><td></td></tr>`));document.getElementById('headersTable').innerHTML=rows.join('')||'<tr><td class="empty" colspan="4">暂无规则</td></tr>'}
refresh();setInterval(refresh,2000);
</script>
</body>
</html>'''


class WebAdminHandler(BaseHTTPRequestHandler):
    proxy_server = None

    def log_message(self, format, *args):
        pass

    def _send_json(self, data, status=200):
        body = json.dumps(data, ensure_ascii=False).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(body)

    def _send_html(self, html, status=200):
        body = html.encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_error_json(self, msg, status=400):
        self._send_json({'error': msg}, status)

    def _read_body(self):
        length = int(self.headers.get('Content-Length', 0))
        if length <= 0:
            return {}
        try:
            return json.loads(self.rfile.read(length).decode('utf-8'))
        except Exception:
            return {}

    def do_GET(self):
        try:
            self._do_GET()
        except Exception as e:
            self._send_json({'error': str(e)}, 500)

    def _do_GET(self):
        path = self.path.split('?', 1)[0]
        ps = self.proxy_server
        if path in ('/', '/index.html'):
            self._send_html(DASHBOARD_HTML)
        elif path == '/api/stats':
            data = ps.stats.summary()
            data['port'] = ps.port
            self._send_json(data)
        elif path == '/api/cache':
            data = ps.cache.stats()
            data['max_entries'] = ps.cache.max_entries
            self._send_json(data)
        elif path == '/api/blacklist':
            self._send_json({'items': ps.access.list_blacklist(), 'mode': ps.access.mode})
        elif path == '/api/whitelist':
            self._send_json({'items': ps.access.list_whitelist(), 'mode': ps.access.mode})
        elif path == '/api/config':
            self._send_json({'mode': ps.access.mode, 'cache_ttl': ps.cache_ttl,
                             'max_cache': ps.cache.max_entries,
                             'header_mod_enabled': ps.header_mod.enabled})
        elif path == '/api/headers':
            self._send_json({'add': ps.header_mod.add_headers,
                             'override': ps.header_mod.override_headers,
                             'remove': sorted(ps.header_mod.remove_headers),
                             'enabled': ps.header_mod.enabled})
        elif path == '/api/hot':
            self._send_json({'hot_domains': ps.stats.get_hot_domains(10),
                             'hot_urls': ps.stats.get_hot_urls(10)})
        elif path == '/api/logs':
            n = 40
            if '?' in self.path:
                import urllib.parse as up
                params = up.parse_qs(self.path.split('?', 1)[1])
                n = int(params.get('n', [40])[0])
            self._send_json({'lines': self._read_log_tail(n)})
        else:
            self._send_error_json('Not found', 404)

    def do_POST(self):
        ps = self.proxy_server
        path = self.path.split('?', 1)[0]
        data = self._read_body()

        if path == '/api/blacklist/add':
            domain = data.get('domain', '').strip()
            if domain:
                ps.access.add_blacklist(domain)
            self._send_json({'ok': True})
        elif path == '/api/blacklist/del':
            domain = data.get('domain', '').strip()
            if domain:
                ps.access.remove_blacklist(domain)
            self._send_json({'ok': True})
        elif path == '/api/whitelist/add':
            domain = data.get('domain', '').strip()
            if domain:
                ps.access.add_whitelist(domain)
            self._send_json({'ok': True})
        elif path == '/api/whitelist/del':
            domain = data.get('domain', '').strip()
            if domain:
                ps.access.remove_whitelist(domain)
            self._send_json({'ok': True})
        elif path == '/api/mode':
            ps.access.set_mode(data.get('mode', 'off'))
            self._send_json({'ok': True, 'mode': ps.access.mode})
        elif path == '/api/cache/clear':
            ps.cache.clear()
            self._send_json({'ok': True})
        elif path == '/api/headers/add':
            key = data.get('key', '').strip()
            if key:
                ps.header_mod.set_add_header(key, data.get('value', ''))
            self._send_json({'ok': True})
        elif path == '/api/headers/del':
            key = data.get('key', '').strip()
            if key:
                ps.header_mod.remove_add_header(key)
            self._send_json({'ok': True})
        elif path == '/api/headers/ua':
            value = data.get('value', '').strip()
            if value:
                ps.header_mod.set_user_agent(value)
            self._send_json({'ok': True})
        else:
            self._send_error_json('Not found', 404)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()

    def _read_log_tail(self, n=50):
        try:
            log_path = self.proxy_server.logger._file_path
            if not os.path.exists(log_path):
                return []
            with open(log_path, 'r', encoding='utf-8', errors='replace') as f:
                lines = f.readlines()[-n:]
            result = []
            for line in lines:
                text = line.rstrip('\n')
                level = 'info'
                if '[HIT ' in text:
                    level = 'cache'
                if '已拦截' in text or '[BLOCK' in text:
                    level = 'block'
                if '[ERROR' in text or '[ERR' in text:
                    level = 'error'
                result.append({'text': text, 'level': level})
            return result
        except Exception:
            return []


class WebAdmin:
    def __init__(self, proxy_server, host='0.0.0.0', port=8890):
        self.proxy_server = proxy_server
        self.host = host
        self.port = port
        self.httpd = None
        self.thread = None

    def start(self):
        WebAdminHandler.proxy_server = self.proxy_server
        self.httpd = HTTPServer((self.host, self.port), WebAdminHandler)
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()
        actual_port = self.httpd.server_address[1]
        print(f'Web admin started: http://{self.host}:{actual_port}')

    def stop(self):
        if self.httpd:
            self.httpd.shutdown()
            self.httpd.server_close()
