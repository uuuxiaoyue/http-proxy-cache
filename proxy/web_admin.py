import json
import os
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer


DASHBOARD_HTML = r'''<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>HTTP 代理缓存服务器</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{background:linear-gradient(135deg,#667eea 0%,#764ba2 100%);min-height:100vh;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI','PingFang SC','Microsoft YaHei',sans-serif;color:#2d3748}
.top{height:64px;padding:0 32px;background:rgba(255,255,255,0.95);backdrop-filter:blur(10px);border-bottom:1px solid rgba(0,0,0,0.05);display:flex;align-items:center;justify-content:space-between;box-shadow:0 2px 8px rgba(0,0,0,0.06);position:sticky;top:0;z-index:100}.brand{font-weight:700;font-size:18px;background:linear-gradient(135deg,#667eea,#764ba2);-webkit-background-clip:text;-webkit-text-fill-color:transparent}.meta{color:#718096;font-size:13px}.meta b{color:#4a5568;font-weight:600}
.wrap{max-width:1400px;margin:0 auto;padding:28px}
.stats{display:grid;grid-template-columns:repeat(5,1fr);gap:16px;margin-bottom:24px}
.card{background:#fff;border-radius:12px;padding:20px;box-shadow:0 4px 12px rgba(0,0,0,0.08);transition:all 0.3s ease;position:relative;overflow:hidden}.card::before{content:'';position:absolute;top:0;left:0;right:0;height:3px;background:linear-gradient(90deg,#667eea,#764ba2);opacity:0;transition:opacity 0.3s}.card:hover{transform:translateY(-2px);box-shadow:0 8px 20px rgba(0,0,0,0.12)}.card:hover::before{opacity:1}.label{font-size:13px;color:#718096;font-weight:500;margin-bottom:8px}.value{font-size:28px;font-weight:700;color:#1a202c;line-height:1}.cache-size{font-size:12px;color:#a0aec0;margin-top:4px}
.grid2{display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-bottom:16px}
.panel{background:#fff;border-radius:12px;box-shadow:0 4px 12px rgba(0,0,0,0.08);overflow:hidden;transition:all 0.3s;margin-bottom:16px}.panel:last-child{margin-bottom:0}.panel:hover{box-shadow:0 6px 16px rgba(0,0,0,0.1)}.head{padding:16px 20px;border-bottom:1px solid #edf2f7;display:flex;justify-content:space-between;align-items:center;background:linear-gradient(135deg,#f7fafc,#edf2f7)}.head b{font-size:15px;color:#2d3748;font-weight:600}.head span{background:linear-gradient(135deg,#667eea,#764ba2);color:#fff;padding:2px 10px;border-radius:12px;font-size:12px;font-weight:600}.body{padding:20px}
.row{display:flex;gap:12px;flex-wrap:wrap;align-items:center}
.input{height:38px;padding:0 14px;border:2px solid #e2e8f0;border-radius:8px;font-size:14px;transition:all 0.3s;outline:none;flex:1;min-width:150px}.input:focus{border-color:#667eea;box-shadow:0 0 0 3px rgba(102,126,234,0.1)}.input::placeholder{color:#a0aec0}
.btn{height:38px;padding:0 18px;border:none;border-radius:8px;font-size:14px;font-weight:600;cursor:pointer;transition:all 0.3s;outline:none;position:relative;overflow:hidden}.btn::after{content:'';position:absolute;top:50%;left:50%;width:0;height:0;border-radius:50%;background:rgba(255,255,255,0.3);transform:translate(-50%,-50%);transition:width 0.6s,height 0.6s}.btn:active::after{width:300px;height:300px}.btn:hover{transform:translateY(-1px);box-shadow:0 4px 12px rgba(0,0,0,0.15)}.btn:active{transform:translateY(0)}
.btn.primary{background:linear-gradient(135deg,#667eea,#764ba2);color:#fff}.btn.primary:hover{box-shadow:0 4px 12px rgba(102,126,234,0.4)}
.btn.red{background:linear-gradient(135deg,#f56565,#e53e3e);color:#fff}.btn.red:hover{box-shadow:0 4px 12px rgba(245,101,101,0.4)}
.btn.green{background:linear-gradient(135deg,#48bb78,#38a169);color:#fff}.btn.green:hover{box-shadow:0 4px 12px rgba(72,187,120,0.4)}
.btn.active{background:linear-gradient(135deg,#667eea,#764ba2);color:#fff;box-shadow:0 4px 12px rgba(102,126,234,0.3)}
.btn.secondary{background:#edf2f7;color:#4a5568}.btn.secondary:hover{background:#e2e8f0}
table{width:100%;border-collapse:collapse}td,th{padding:12px 16px;border-bottom:1px solid #edf2f7;text-align:left;font-size:13px}th{color:#718096;font-weight:600;background:#f7fafc}tr:hover{background:#f7fafc;transition:background 0.2s}.empty{color:#a0aec0;font-style:italic}.url{display:block;max-width:420px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;color:#4a5568;font-weight:500}
.log{background:linear-gradient(135deg,#1a202c,#2d3748);color:#e2e8f0;border-radius:8px;padding:16px;font:13px/1.7 'Consolas','Monaco','Courier New',monospace;max-height:320px;overflow-y:auto;scrollbar-width:thin;scrollbar-color:#4a5568 #1a202c}.log::-webkit-scrollbar{width:8px}.log::-webkit-scrollbar-track{background:#1a202c;border-radius:4px}.log::-webkit-scrollbar-thumb{background:#4a5568;border-radius:4px}.log::-webkit-scrollbar-thumb:hover{background:#667eea}.log div{padding:2px 0;border-bottom:1px solid rgba(255,255,255,0.05)}.log div:last-child{border-bottom:none}
.badge{display:inline-block;padding:2px 8px;border-radius:6px;font-size:11px;font-weight:600}.badge.hit{background:#c6f6d5;color:#22543d}.badge.miss{background:#fed7d7;color:#742a2a}.badge.block{background:#fed7d7;color:#742a2a}.badge.error{background:#fed7d7;color:#742a2a}
.refresh-indicator{font-size:11px;color:#a0aec0;font-weight:500}
@keyframes fadeIn{from{opacity:0;transform:translateY(10px)}to{opacity:1;transform:translateY(0)}}.panel,.card{animation:fadeIn 0.5s ease-out}
@media(max-width:900px){.stats,.grid2{grid-template-columns:1fr}.meta{display:none}.wrap{padding:16px}}
</style>
</head>
<body>
<div class="top">
  <div class="brand">🚀 HTTP 代理缓存服务器</div>
  <div class="meta">端口 <b id="proxyPort">--</b> &nbsp;|&nbsp; 运行时间 <b id="uptime">--</b></div>
</div>
<div class="wrap">
  <div class="stats">
    <div class="card"><div class="label">📊 总请求数</div><div class="value" id="totalRequests">0</div></div>
    <div class="card"><div class="label">🎯 缓存命中率</div><div class="value" id="hitRate">0%</div></div>
    <div class="card"><div class="label">💾 缓存条目</div><div class="value" id="cacheEntries">0</div><div class="cache-size" id="cacheSize"></div></div>
    <div class="card"><div class="label">🚫 已拦截</div><div class="value" id="blockedRequests">0</div></div>
    <div class="card"><div class="label">🔐 访问控制</div><div class="value" id="acMode" style="font-size:20px">关闭</div></div>
  </div>

  <div class="grid2">
    <div class="panel"><div class="head"><b>🚫 黑名单</b><span id="blCount">0</span></div><div class="body"><div class="row"><input class="input" id="blInput" placeholder="example.com / 1.2.3.4 / 1.2.3.0/24"><button class="btn red" onclick="addB()"> + 添加</button></div><table style="margin-top:16px"><tbody id="blacklistTable"><tr><td class="empty">暂无条目</td></tr></tbody></table></div></div>
    <div class="panel"><div class="head"><b>✅ 白名单</b><span id="wlCount">0</span></div><div class="body"><div class="row"><input class="input" id="wlInput" placeholder="example.com / 1.2.3.4 / 1.2.3.0/24"><button class="btn green" onclick="addW()"> + 添加</button></div><table style="margin-top:16px"><tbody id="whitelistTable"><tr><td class="empty">暂无条目</td></tr></tbody></table></div></div>
  </div>

  <div class="panel"><div class="head"><b>🔒 访问控制模式</b></div><div class="body row"><button class="btn secondary" id="btnModeOff" onclick="setMode('off')">✅ 全部允许</button><button class="btn secondary" id="btnModeBlacklist" onclick="setMode('blacklist')">🚫 黑名单模式</button><button class="btn secondary" id="btnModeWhitelist" onclick="setMode('whitelist')">✅ 白名单模式</button><button class="btn primary" onclick="clearCache()">🗑️ 清空缓存</button></div></div>

  <div class="panel"><div class="head"><b> 请求头修改</b></div><div class="body">
    <div class="row"><input class="input" id="hKey" placeholder="Header 名称"><input class="input" id="hVal" placeholder="Header 值"><button class="btn primary" onclick="addHeader()"> + 添加请求头</button></div>
    <div class="row" style="margin-top:12px"><input class="input" id="uaVal" style="min-width:360px" placeholder="自定义 User-Agent"><button class="btn secondary" onclick="setUA()"> 设置 User-Agent</button></div>
    <table style="margin-top:16px"><thead><tr><th>类型</th><th>名称</th><th>值</th><th>操作</th></tr></thead><tbody id="headersTable"><tr><td class="empty" colspan="4">暂无规则</td></tr></tbody></table>
  </div></div>

  <div class="grid2">
    <div class="panel"><div class="head"><b>🔥 热门 URL</b></div><div class="body" style="padding:0"><table><tbody id="hotResources"><tr><td class="empty">暂无数据</td></tr></tbody></table></div></div>
    <div class="panel"><div class="head"><b>🌐 热门域名</b></div><div class="body" style="padding:0"><table><tbody id="hotDomains"><tr><td class="empty">暂无数据</td></tr></tbody></table></div></div>
  </div>
  <div class="panel"><div class="head"><b>📋 最近日志</b><span class="refresh-indicator" id="lastRefresh">--</span></div><div class="body"><div class="log" id="logViewer">等待活动...</div></div></div>
</div>
<script>
const A='/api/';
async function J(p){try{const r=await fetch(A+p);return r.ok?r.json():null}catch(e){return null}}
async function P(p,b={}){try{const r=await fetch(A+p,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(b)});return r.ok?r.json():null}catch(e){return null}}
function Q(id,v){document.getElementById(id).textContent=v}
function E(s){const d=document.createElement('div');d.textContent=s;return d.innerHTML}
function U(s){const h=Math.floor(s/3600),m=Math.floor(s%3600/60),sec=s%60;return `${h}h ${m}m ${sec}s`}
function listTable(id,items,type){document.getElementById(id).innerHTML=items.length?items.map(i=>`<tr><td>${E(i)}</td><td style="text-align:right"><button class="btn secondary" onclick="removeItem('${type}','${E(i)}')">🗑️ 移除</button></td></tr>`).join(''):'<tr><td class="empty">暂无条目</td></tr>'}
async function addB(){const i=document.getElementById('blInput');const d=i.value.trim();if(!d)return;await P('blacklist/add',{domain:d});i.value='';refresh()}
async function addW(){const i=document.getElementById('wlInput');const d=i.value.trim();if(!d)return;await P('whitelist/add',{domain:d});i.value='';refresh()}
async function removeItem(t,d){await P(t+'/del',{domain:d});refresh()}
async function setMode(m){await P('mode',{mode:m});refresh()}
async function clearCache(){if(confirm('确认清空所有缓存？')){await P('cache/clear');refresh()}}
async function addHeader(){const k=document.getElementById('hKey'),v=document.getElementById('hVal');if(!k.value.trim())return;await P('headers/add',{key:k.value.trim(),value:v.value});k.value='';v.value='';refresh()}
async function delHeader(k){await P('headers/del',{key:k});refresh()}
async function setUA(){const v=document.getElementById('uaVal').value.trim();if(!v)return;await P('headers/ua',{value:v});refresh()}
function renderHeaders(H){let rows=[];Object.entries(H.add||{}).forEach(([k,v])=>rows.push(`<tr><td><span class="badge hit"> + 添加</span></td><td>${E(k)}</td><td>${E(v)}</td><td><button class="btn secondary" onclick="delHeader('${E(k)}')">🗑️ 移除</button></td></tr>`));Object.entries(H.override||{}).forEach(([k,v])=>rows.push(`<tr><td><span class="badge" style="background:#bee3f8;color:#2a4365">覆盖</span></td><td>${E(k)}</td><td>${E(v)}</td><td></td></tr>`));(H.remove||[]).forEach(k=>rows.push(`<tr><td><span class="badge" style="background:#fed7d7;color:#742a2a">过滤</span></td><td>${E(k)}</td><td></td><td></td></tr>`));document.getElementById('headersTable').innerHTML=rows.join('')||'<tr><td class="empty" colspan="4">暂无规则</td></tr>'}
async function refresh(){
  const[S,C,BL,WL,CF,H,L,HD]=await Promise.all([J('stats'),J('cache'),J('blacklist'),J('whitelist'),J('config'),J('hot'),J('logs?n=40'),J('headers')]);
  if(S){Q('totalRequests',S.total.toLocaleString());Q('hitRate',S.hit_rate.toFixed(1)+'%');Q('blockedRequests',S.blocked);Q('uptime',U(S.uptime));Q('proxyPort',S.port||'--')}
  if(C){Q('cacheEntries',C.entries+' / '+C.max_entries);Q('cacheSize',(C.total_size/1024).toFixed(1)+' KB')}
  if(CF){const m=CF.mode;Q('acMode',m==='off'?'✅ 全部允许':m==='blacklist'?'🚫 黑名单':'✅ 白名单');['Off','Blacklist','Whitelist'].forEach(x=>document.getElementById('btnMode'+x).className='btn secondary');document.getElementById('btnMode'+(m==='off'?'Off':m==='blacklist'?'Blacklist':'Whitelist')).className='btn active'}
  if(BL){listTable('blacklistTable',BL.items,'blacklist');Q('blCount',BL.items.length)}
  if(WL){listTable('whitelistTable',WL.items,'whitelist');Q('wlCount',WL.items.length)}
  if(HD)renderHeaders(HD);
  if(H){document.getElementById('hotResources').innerHTML=H.hot_urls.length?H.hot_urls.map(([u,c],i)=>`<tr><td style="width:40px;color:#a0aec0;font-weight:600">${i+1}</td><td><span class="url" title="${E(u)}">${E(u)}</span></td><td style="width:80px;text-align:center"><span class="badge hit">${c}</span></td></tr>`).join(''):'<tr><td class="empty">暂无数据</td></tr>';document.getElementById('hotDomains').innerHTML=H.hot_domains.length?H.hot_domains.map(([d,c],i)=>`<tr><td style="width:40px;color:#a0aec0;font-weight:600">${i+1}</td><td>${E(d)}</td><td style="width:80px;text-align:center"><span class="badge hit">${c}</span></td></tr>`).join(''):'<tr><td class="empty">暂无数据</td></tr>'}
  if(L&&L.lines){document.getElementById('logViewer').innerHTML=L.lines.map(l=>{let cls='';if(l.level==='cache')cls='color:#68d391';if(l.level==='block')cls='color:#fc8181';if(l.level==='error')cls='color:#fc8181';return `<div style="${cls}">${E(l.text)}</div>`}).join('')||'等待活动...'}
  Q('lastRefresh','最后更新: '+new Date().toLocaleTimeString());
}
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
