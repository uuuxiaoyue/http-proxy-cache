import json
import os
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer


DASHBOARD_HTML = r'''<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>&#72;&#84;&#84;&#80; &#20195;&#29702;&#32531;&#23384;&#26381;&#21153;&#22120;</title>
<style>
*{box-sizing:border-box}body{margin:0;background:#f7f7f4;color:#1f2328;font-family:system-ui,-apple-system,"Segoe UI",Arial,sans-serif}.top{height:56px;padding:0 28px;background:#fff;border-bottom:1px solid #ddd;display:flex;align-items:center;justify-content:space-between}.brand{font-weight:700}.meta{color:#666;font-size:13px}.wrap{max-width:1200px;margin:0 auto;padding:24px}.stats{display:grid;grid-template-columns:repeat(5,1fr);gap:12px}.card,.panel{background:#fff;border:1px solid #ddd;border-radius:8px}.card{padding:16px}.label{font-size:12px;color:#666}.value{font-size:26px;font-weight:700;margin-top:4px}.grid2{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-top:16px}.panel{margin-top:16px;overflow:hidden}.head{padding:12px 14px;border-bottom:1px solid #ddd;display:flex;justify-content:space-between;align-items:center}.body{padding:14px}.row{display:flex;gap:8px;flex-wrap:wrap;align-items:center}.input{height:34px;padding:0 10px;border:1px solid #ccc;border-radius:6px}.btn{height:34px;padding:0 12px;border:1px solid #ccc;border-radius:6px;background:#fff;cursor:pointer}.btn:hover{background:#f1f1ed}.btn.primary{background:#2563eb;color:#fff;border-color:#2563eb}.btn.red{background:#dc2626;color:#fff;border-color:#dc2626}.btn.green{background:#059669;color:#fff;border-color:#059669}.btn.active{border-color:#2563eb;color:#2563eb;background:#eff6ff}table{width:100%;border-collapse:collapse}td,th{padding:8px 10px;border-bottom:1px solid #e5e5e5;text-align:left;font-size:13px}th{color:#666}.empty{color:#777}.url{display:block;max-width:420px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.log{background:#111827;color:#d1d5db;border-radius:6px;padding:12px;font:12px/1.6 Consolas,monospace;max-height:300px;overflow:auto}@media(max-width:900px){.stats,.grid2{grid-template-columns:1fr}.meta{display:none}}
</style>
</head>
<body>
<div class="top"><div class="brand">&#72;&#84;&#84;&#80; &#20195;&#29702;&#32531;&#23384;&#26381;&#21153;&#22120;</div><div class="meta">&#31471;&#21475; <b id="proxyPort">--</b> &nbsp; &#36816;&#34892;&#26102;&#38388; <b id="uptime">--</b></div></div>
<div class="wrap">
  <div class="stats">
    <div class="card"><div class="label">&#24635;&#35831;&#27714;&#25968;</div><div class="value" id="totalRequests">0</div></div>
    <div class="card"><div class="label">&#32531;&#23384;&#21629;&#20013;&#29575;</div><div class="value" id="hitRate">0%</div></div>
    <div class="card"><div class="label">&#32531;&#23384;&#26465;&#30446;</div><div class="value" id="cacheEntries">0</div><div class="label" id="cacheSize"></div></div>
    <div class="card"><div class="label">&#24050;&#25318;&#25130;</div><div class="value" id="blockedRequests">0</div></div>
    <div class="card"><div class="label">&#35775;&#38382;&#25511;&#21046;</div><div class="value" id="acMode">&#20851;&#38381;</div></div>
  </div>

  <div class="grid2">
    <div class="panel"><div class="head"><b>&#40657;&#21517;&#21333;</b><span id="blCount">0</span></div><div class="body"><div class="row"><input class="input" id="blInput" placeholder="example.com / 1.2.3.4 / 1.2.3.0/24"><button class="btn red" onclick="addB()">&#28155;&#21152;</button></div><table><tbody id="blacklistTable"><tr><td class="empty">&#26242;&#26080;&#26465;&#30446;</td></tr></tbody></table></div></div>
    <div class="panel"><div class="head"><b>&#30333;&#21517;&#21333;</b><span id="wlCount">0</span></div><div class="body"><div class="row"><input class="input" id="wlInput" placeholder="example.com / 1.2.3.4 / 1.2.3.0/24"><button class="btn green" onclick="addW()">&#28155;&#21152;</button></div><table><tbody id="whitelistTable"><tr><td class="empty">&#26242;&#26080;&#26465;&#30446;</td></tr></tbody></table></div></div>
  </div>

  <div class="panel"><div class="head"><b>&#35775;&#38382;&#25511;&#21046;&#27169;&#24335;</b></div><div class="body row"><button class="btn" id="btnModeOff" onclick="setMode('off')">&#20840;&#37096;&#20801;&#35768;</button><button class="btn" id="btnModeBlacklist" onclick="setMode('blacklist')">&#40657;&#21517;&#21333;&#27169;&#24335;</button><button class="btn" id="btnModeWhitelist" onclick="setMode('whitelist')">&#30333;&#21517;&#21333;&#27169;&#24335;</button><button class="btn" onclick="clearCache()">&#28165;&#31354;&#32531;&#23384;</button></div></div>

  <div class="panel"><div class="head"><b>&#35831;&#27714;&#22836;&#20462;&#25913;</b></div><div class="body">
    <div class="row"><input class="input" id="hKey" placeholder="Header"><input class="input" id="hVal" placeholder="Value"><button class="btn primary" onclick="addHeader()">&#28155;&#21152;&#35831;&#27714;&#22836;</button></div>
    <div class="row" style="margin-top:8px"><input class="input" id="uaVal" style="min-width:360px" placeholder="User-Agent"><button class="btn" onclick="setUA()">&#35774;&#32622; User-Agent</button></div>
    <table style="margin-top:10px"><thead><tr><th>&#31867;&#22411;</th><th>&#21517;&#31216;</th><th>&#20540;</th><th></th></tr></thead><tbody id="headersTable"><tr><td class="empty" colspan="4">&#26242;&#26080;&#35268;&#21017;</td></tr></tbody></table>
  </div></div>

  <div class="grid2">
    <div class="panel"><div class="head"><b>&#28909;&#38376; URL</b></div><table><tbody id="hotResources"><tr><td class="empty">&#26242;&#26080;&#25968;&#25454;</td></tr></tbody></table></div>
    <div class="panel"><div class="head"><b>&#28909;&#38376;&#22495;&#21517;</b></div><table><tbody id="hotDomains"><tr><td class="empty">&#26242;&#26080;&#25968;&#25454;</td></tr></tbody></table></div>
  </div>
  <div class="panel"><div class="head"><b>&#26368;&#36817;&#26085;&#24535;</b><span id="lastRefresh">--</span></div><div class="body"><div class="log" id="logViewer">&#31561;&#24453;&#27963;&#21160;...</div></div></div>
</div>
<script>
const A='/api/';
async function J(p){try{const r=await fetch(A+p);return r.ok?r.json():null}catch(e){return null}}
async function P(p,b={}){try{const r=await fetch(A+p,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(b)});return r.ok?r.json():null}catch(e){return null}}
function Q(id,v){document.getElementById(id).textContent=v}
function E(s){const d=document.createElement('div');d.textContent=s;return d.innerHTML}
function U(s){const h=Math.floor(s/3600),m=Math.floor(s%3600/60),sec=s%60;return `${h}h ${m}m ${sec}s`}
function listTable(id,items,type){document.getElementById(id).innerHTML=items.length?items.map(i=>`<tr><td>${E(i)}</td><td style="text-align:right"><button class="btn" onclick="removeItem('${type}','${E(i)}')">&#31227;&#38500;</button></td></tr>`).join(''):'<tr><td class="empty">&#26242;&#26080;&#26465;&#30446;</td></tr>'}
async function addB(){const i=document.getElementById('blInput');const d=i.value.trim();if(!d)return;await P('blacklist/add',{domain:d});i.value='';refresh()}
async function addW(){const i=document.getElementById('wlInput');const d=i.value.trim();if(!d)return;await P('whitelist/add',{domain:d});i.value='';refresh()}
async function removeItem(t,d){await P(t+'/del',{domain:d});refresh()}
async function setMode(m){await P('mode',{mode:m});refresh()}
async function clearCache(){if(confirm('\u786e\u8ba4\u6e05\u7a7a\u6240\u6709\u7f13\u5b58\uff1f')){await P('cache/clear');refresh()}}
async function addHeader(){const k=document.getElementById('hKey'),v=document.getElementById('hVal');if(!k.value.trim())return;await P('headers/add',{key:k.value.trim(),value:v.value});k.value='';v.value='';refresh()}
async function delHeader(k){await P('headers/del',{key:k});refresh()}
async function setUA(){const v=document.getElementById('uaVal').value.trim();if(!v)return;await P('headers/ua',{value:v});refresh()}
function renderHeaders(H){let rows=[];Object.entries(H.add||{}).forEach(([k,v])=>rows.push(`<tr><td>&#28155;&#21152;</td><td>${E(k)}</td><td>${E(v)}</td><td><button class="btn" onclick="delHeader('${E(k)}')">&#31227;&#38500;</button></td></tr>`));Object.entries(H.override||{}).forEach(([k,v])=>rows.push(`<tr><td>&#35206;&#30422;</td><td>${E(k)}</td><td>${E(v)}</td><td></td></tr>`));(H.remove||[]).forEach(k=>rows.push(`<tr><td>&#36807;&#28388;</td><td>${E(k)}</td><td></td><td></td></tr>`));document.getElementById('headersTable').innerHTML=rows.join('')||'<tr><td class="empty" colspan="4">&#26242;&#26080;&#35268;&#21017;</td></tr>'}
async function refresh(){
  const[S,C,BL,WL,CF,H,L,HD]=await Promise.all([J('stats'),J('cache'),J('blacklist'),J('whitelist'),J('config'),J('hot'),J('logs?n=40'),J('headers')]);
  if(S){Q('totalRequests',S.total.toLocaleString());Q('hitRate',S.hit_rate.toFixed(1)+'%');Q('blockedRequests',S.blocked);Q('uptime',U(S.uptime));Q('proxyPort',S.port||'--')}
  if(C){Q('cacheEntries',C.entries+' / '+C.max_entries);Q('cacheSize',(C.total_size/1024).toFixed(1)+' KB')}
  if(CF){const m=CF.mode;Q('acMode',m==='off'?'\u5168\u90e8\u5141\u8bb8':m==='blacklist'?'\u9ed1\u540d\u5355':'\u767d\u540d\u5355');['Off','Blacklist','Whitelist'].forEach(x=>document.getElementById('btnMode'+x).className='btn');document.getElementById('btnMode'+(m==='off'?'Off':m==='blacklist'?'Blacklist':'Whitelist')).className='btn active'}
  if(BL){listTable('blacklistTable',BL.items,'blacklist');Q('blCount',BL.items.length)}
  if(WL){listTable('whitelistTable',WL.items,'whitelist');Q('wlCount',WL.items.length)}
  if(HD)renderHeaders(HD);
  if(H){document.getElementById('hotResources').innerHTML=H.hot_urls.length?H.hot_urls.map(([u,c],i)=>`<tr><td>${i+1}</td><td><span class="url" title="${E(u)}">${E(u)}</span></td><td>${c}</td></tr>`).join(''):'<tr><td class="empty">&#26242;&#26080;&#25968;&#25454;</td></tr>';document.getElementById('hotDomains').innerHTML=H.hot_domains.length?H.hot_domains.map(([d,c],i)=>`<tr><td>${i+1}</td><td>${E(d)}</td><td>${c}</td></tr>`).join(''):'<tr><td class="empty">&#26242;&#26080;&#25968;&#25454;</td></tr>'}
  if(L&&L.lines){document.getElementById('logViewer').innerHTML=L.lines.map(l=>`<div>${E(l.text)}</div>`).join('')||'\u7b49\u5f85\u6d3b\u52a8...'}
  Q('lastRefresh',new Date().toLocaleTimeString());
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
