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
  --bg:#faf7f2;
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
  --red:#dc2626;
  --red-bg:#fef2f2;
  --amber:#d97706;
  --amber-bg:#fffbeb;
  --shadow-sm:0 1px 2px rgba(0,0,0,.04);
  --shadow:0 1px 3px rgba(0,0,0,.06),0 1px 2px rgba(0,0,0,.04);
  --shadow-md:0 4px 6px rgba(0,0,0,.04),0 2px 4px rgba(0,0,0,.04);
  --radius:12px;
  --radius-sm:8px;
}
body{
  font-family:system-ui,-apple-system,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;
  background:var(--bg);color:var(--text);line-height:1.5;
  -webkit-font-smoothing:antialiased;
}
.header{
  background:var(--surface);border-bottom:1px solid var(--border);
  padding:0 32px;height:56px;display:flex;align-items:center;justify-content:space-between;
  position:sticky;top:0;z-index:10;
}
.header-brand{display:flex;align-items:center;gap:10px}
.header-logo{
  width:28px;height:28px;background:var(--accent);border-radius:7px;
  display:flex;align-items:center;justify-content:center;color:#fff;font-size:14px;
}
.header h1{font-size:15px;font-weight:600;letter-spacing:-.01em}
.header-meta{display:flex;align-items:center;gap:20px;font-size:13px;color:var(--text2)}
.header-meta span{display:flex;align-items:center;gap:6px}
.status-dot{
  width:7px;height:7px;background:var(--green);border-radius:50%;
  animation:pulse 2s ease-in-out infinite;
}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:.4}}
.container{max-width:1280px;margin:0 auto;padding:28px 32px}
.stats{display:grid;grid-template-columns:repeat(5,1fr);gap:14px;margin-bottom:28px}
@media(max-width:1000px){.stats{grid-template-columns:repeat(3,1fr)}}
@media(max-width:600px){.stats{grid-template-columns:1fr 1fr}}
.stat-card{
  background:var(--surface);border-radius:var(--radius);padding:18px 20px;
  box-shadow:var(--shadow-sm);border:1px solid var(--border);
  transition:box-shadow .2s;
}
.stat-card:hover{box-shadow:var(--shadow-md)}
.stat-label{font-size:12px;font-weight:500;color:var(--text3);text-transform:uppercase;letter-spacing:.04em;margin-bottom:6px}
.stat-value{font-size:28px;font-weight:700;letter-spacing:-.02em;color:var(--text)}
.stat-value.green{color:var(--green)}
.stat-value.red{color:var(--red)}
.stat-value.amber{color:var(--amber)}
.stat-value.accent{color:var(--accent)}
.stat-sub{font-size:12px;color:var(--text3);margin-top:4px}
.row2{display:grid;grid-template-columns:1fr 1fr;gap:14px;margin-bottom:28px}
@media(max-width:800px){.row2{grid-template-columns:1fr}}
.panel{
  background:var(--surface);border-radius:var(--radius);
  box-shadow:var(--shadow-sm);border:1px solid var(--border);overflow:hidden;
}
.panel-header{
  padding:16px 20px;border-bottom:1px solid var(--border);
  display:flex;align-items:center;justify-content:space-between;
}
.panel-header h2{font-size:14px;font-weight:600;letter-spacing:-.01em}
.panel-body{padding:16px 20px}
table{width:100%;border-collapse:collapse}
thead th{
  text-align:left;padding:8px 12px 8px 0;font-size:11px;font-weight:600;
  color:var(--text3);text-transform:uppercase;letter-spacing:.04em;
  border-bottom:1px solid var(--border);
}
tbody td{padding:10px 12px 10px 0;font-size:13px;border-bottom:1px solid var(--border)}
tbody tr:last-child td{border-bottom:none}
tbody tr:hover{background:var(--accent-light)}
.td-url{max-width:320px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;display:block}
.bar-wrap{display:flex;align-items:center;gap:8px;min-width:80px}
.bar-track{flex:1;height:6px;background:var(--border);border-radius:3px;overflow:hidden}
.bar-fill{height:100%;background:var(--accent);border-radius:3px;transition:width .4s ease}
.btn{
  display:inline-flex;align-items:center;gap:5px;
  padding:7px 14px;border:1px solid transparent;border-radius:7px;
  font-size:13px;font-weight:500;cursor:pointer;transition:all .15s;white-space:nowrap;
  font-family:inherit;
}
.btn-primary{background:var(--accent);color:#fff;border-color:var(--accent)}
.btn-primary:hover{background:var(--accent-hover)}
.btn-outline{background:var(--surface);color:var(--text);border-color:var(--border)}
.btn-outline:hover{background:var(--bg)}
.btn-outline.active{background:var(--accent-light);color:var(--accent);border-color:var(--accent);font-weight:600}
.btn-danger{background:var(--red);color:#fff;border-color:var(--red)}
.btn-danger:hover{background:#b91c1c}
.btn-success{background:var(--green);color:#fff;border-color:var(--green)}
.btn-success:hover{background:#047857}
.btn-xs{padding:3px 10px;font-size:11px;border-radius:5px}
.input{
  padding:8px 12px;border:1px solid var(--border);border-radius:7px;
  font-size:13px;font-family:inherit;color:var(--text);
  background:var(--surface);width:200px;transition:border-color .15s,box-shadow .15s;
}
.input:focus{outline:none;border-color:var(--accent);box-shadow:0 0 0 3px var(--accent-light)}
.input::placeholder{color:var(--text3)}
.flex{display:flex;gap:8px;align-items:center;flex-wrap:wrap}
.log-viewer{
  background:#1e1e2e;border-radius:var(--radius-sm);padding:14px 16px;
  max-height:320px;overflow-y:auto;
  font-family:'SF Mono','Cascadia Code','Fira Code','Consolas',monospace;
  font-size:12px;line-height:1.7;
}
.log-entry{padding:1px 0;border-bottom:1px solid rgba(255,255,255,.04);white-space:pre-wrap;word-break:break-all}
.log-info{color:#a6adc8}
.log-cache{color:#a6e3a1}
.log-block{color:#cba6f7}
.log-error{color:#f38ba8}
.empty{color:var(--text3);font-size:13px;padding:12px 0}
.badge{display:inline-flex;align-items:center;padding:2px 8px;border-radius:10px;font-size:11px;font-weight:600}
.badge-green{background:var(--green-bg);color:var(--green)}
.badge-red{background:var(--red-bg);color:var(--red)}
.badge-accent{background:var(--accent-light);color:var(--accent)}
.footer-bar{
  display:flex;justify-content:space-between;align-items:center;
  padding:12px 0 0;color:var(--text3);font-size:11px;
}
</style>
</head>
<body>
<div class="header">
  <div class="header-brand">
    <div class="header-logo">&uarr;&darr;</div>
    <h1>HTTP 代理缓存服务器</h1>
  </div>
  <div class="header-meta">
    <span>端口 <b id="proxyPort">--</b></span>
    <span>运行时间 <b id="uptime">--</b></span>
    <span class="status-dot"></span>运行中
  </div>
</div>

<div class="container">
  <div class="stats">
    <div class="stat-card"><div class="stat-label">总请求数</div><div class="stat-value" id="totalRequests">0</div></div>
    <div class="stat-card"><div class="stat-label">缓存命中率</div><div class="stat-value green" id="hitRate">0%</div></div>
    <div class="stat-card"><div class="stat-label">缓存条目</div><div class="stat-value accent" id="cacheEntries">0</div><div class="stat-sub" id="cacheSize"></div></div>
    <div class="stat-card"><div class="stat-label">已拦截</div><div class="stat-value amber" id="blockedRequests">0</div></div>
    <div class="stat-card"><div class="stat-label">访问控制</div><div class="stat-value" id="acMode" style="font-size:20px">关闭</div></div>
  </div>

  <div class="row2">
    <div class="panel">
      <div class="panel-header"><h2>黑名单</h2><span class="badge badge-red" id="blCount">0</span></div>
      <div class="panel-body">
        <div class="flex" style="margin-bottom:12px">
          <input class="input" id="blInput" placeholder="example.com / 1.2.3.4 / 1.2.3.0/24" style="flex:1" onkeydown="if(event.key==='Enter')addB()">
          <button class="btn btn-danger" onclick="addB()">拦截</button>
        </div>
        <div style="max-height:220px;overflow-y:auto"><table><tbody id="blacklistTable"><tr><td class="empty">暂无条目</td></tr></tbody></table></div>
      </div>
    </div>
    <div class="panel">
      <div class="panel-header"><h2>白名单</h2><span class="badge badge-green" id="wlCount">0</span></div>
      <div class="panel-body">
        <div class="flex" style="margin-bottom:12px">
          <input class="input" id="wlInput" placeholder="example.com / 1.2.3.4 / 1.2.3.0/24" style="flex:1" onkeydown="if(event.key==='Enter')addW()">
          <button class="btn btn-success" onclick="addW()">允许</button>
        </div>
        <div style="max-height:220px;overflow-y:auto"><table><tbody id="whitelistTable"><tr><td class="empty">暂无条目</td></tr></tbody></table></div>
      </div>
    </div>
  </div>

  <div class="panel" style="margin-bottom:28px">
    <div class="panel-header"><h2>访问控制模式</h2></div>
    <div class="panel-body">
      <div class="flex">
        <button class="btn btn-outline active" id="btnModeOff" onclick="setMode('off')">全部允许</button>
        <button class="btn btn-outline" id="btnModeBlacklist" onclick="setMode('blacklist')">黑名单模式</button>
        <button class="btn btn-outline" id="btnModeWhitelist" onclick="setMode('whitelist')">白名单模式</button>
        <span style="flex:1"></span>
        <button class="btn btn-outline" onclick="clearCache()">清空缓存</button>
      </div>
    </div>
  </div>

  <div class="panel" style="margin-bottom:28px">
    <div class="panel-header"><h2>请求头修改</h2></div>
    <div class="panel-body">
      <div class="flex" style="margin-bottom:12px">
        <input class="input" id="hKey" placeholder="Header 名称" style="width:160px">
        <input class="input" id="hVal" placeholder="Header 值" style="flex:1">
        <button class="btn btn-primary" onclick="addHeader()">添加请求头</button>
      </div>
      <div class="flex" style="margin-bottom:12px">
        <input class="input" id="uaVal" placeholder="自定义 User-Agent" style="flex:1">
        <button class="btn btn-outline" onclick="setUA()">设置 User-Agent</button>
      </div>
      <table><thead><tr><th>类型</th><th>名称</th><th>值</th><th style="width:80px">操作</th></tr></thead>
        <tbody id="headersTable"><tr><td class="empty" colspan="4">暂无规则</td></tr></tbody></table>
    </div>
  </div>

  <div class="row2">
    <div class="panel">
      <div class="panel-header"><h2>热门 URL</h2></div>
      <div class="panel-body" style="padding:0">
        <table><thead><tr><th style="padding-left:20px">#</th><th>URL</th><th>访问次数</th><th></th></tr></thead>
          <tbody id="hotResources"><tr><td colspan="4" class="empty" style="padding-left:20px">暂无数据</td></tr></tbody></table>
      </div>
    </div>
    <div class="panel">
      <div class="panel-header"><h2>热门域名</h2></div>
      <div class="panel-body" style="padding:0">
        <table><thead><tr><th style="padding-left:20px">#</th><th>Domain</th><th>访问次数</th><th></th></tr></thead>
          <tbody id="hotDomains"><tr><td colspan="4" class="empty" style="padding-left:20px">暂无数据</td></tr></tbody></table>
      </div>
    </div>
  </div>

  <div class="panel">
    <div class="panel-header"><h2>实时日志</h2></div>
    <div class="panel-body" style="padding:0">
      <div class="log-viewer" id="logViewer"><span style="color:#6c7086">等待活动...</span></div>
    </div>
  </div>

  <div class="footer-bar">
    <span>每 2 秒自动刷新</span>
    <span>最后更新: <span id="lastRefresh">--</span></span>
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
    document.getElementById('hotResources').innerHTML=H.hot_urls.length?H.hot_urls.map(([u,c],i)=>`<tr><td style="padding-left:20px;color:var(--text3)">${i+1}</td><td><span class="td-url" title="${E(u)}">${E(u)}</span></td><td style="font-weight:600">${c}</td><td></td></tr>`).join(''):'<tr><td colspan="4" class="empty" style="padding-left:20px">暂无数据</td></tr>';
    document.getElementById('hotDomains').innerHTML=H.hot_domains.length?H.hot_domains.map(([d,c],i)=>`<tr><td style="padding-left:20px;color:var(--text3)">${i+1}</td><td>${E(d)}</td><td style="font-weight:600">${c}</td><td></td></tr>`).join(''):'<tr><td colspan="4" class="empty" style="padding-left:20px">暂无数据</td></tr>';
  }
  if(L&&L.lines){document.getElementById('logViewer').innerHTML=L.lines.map(l=>`<div class="log-entry log-${l.level}">${E(l.text)}</div>`).join('')}
  Q('lastRefresh',new Date().toLocaleTimeString());
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
