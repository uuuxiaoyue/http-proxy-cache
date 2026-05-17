#!/usr/bin/env python3
"""
HTTP 代理缓存服务器
基础功能: 代理转发、缓存、日志、并发连接
拓展功能: 缓存策略、黑白名单、管理控制台、HTTPS隧道、请求头修改
"""

import socket
import threading
import re
import time
import sys
import os
import json
import argparse
import select
from datetime import datetime
from urllib.parse import urlparse
from concurrent.futures import ThreadPoolExecutor
from collections import OrderedDict
from http.server import HTTPServer, BaseHTTPRequestHandler

# ── 配置常量 ─────────────────────────────────────────────
BUFFER_SIZE = 8192
DEFAULT_PORT = 8888
DEFAULT_CACHE_TTL = 300
DEFAULT_MAX_CACHE = 200
DEFAULT_MAX_WORKERS = 50
VERSION = "HTTP-Proxy-Cache/1.0"
HTTP_VERSION = "HTTP/1.1"


# ╔══════════════════════════════════════════════════════════╗
# ║                     缓存模块                              ║
# ╚══════════════════════════════════════════════════════════╝

class CacheEntry:
    """缓存条目"""
    __slots__ = ('data', 'headers', 'status_code', 'created_at',
                 'last_access', 'access_count', 'size', 'ttl')

    def __init__(self, data, headers, status_code, ttl=None):
        self.data = data
        self.headers = headers
        self.status_code = status_code
        self.created_at = time.time()
        self.last_access = time.time()
        self.access_count = 0
        self.size = len(data)
        self.ttl = ttl

    def is_expired(self, default_ttl):
        ttl = self.ttl if self.ttl is not None else default_ttl
        return time.time() - self.created_at > ttl

    def touch(self):
        self.last_access = time.time()
        self.access_count += 1


class CacheManager:
    """缓存管理器 - LRU淘汰 + 时间过期 + 频率优先级"""

    def __init__(self, max_entries=DEFAULT_MAX_CACHE, default_ttl=DEFAULT_CACHE_TTL):
        self.max_entries = max_entries
        self.default_ttl = default_ttl
        self._cache = OrderedDict()
        self._lock = threading.Lock()

    def _make_key(self, method, url):
        return f"{method}:{url}"

    def get(self, method, url):
        key = self._make_key(method, url)
        with self._lock:
            entry = self._cache.get(key)
            if entry is None:
                return None
            if entry.is_expired(self.default_ttl):
                del self._cache[key]
                return None
            entry.touch()
            self._cache.move_to_end(key)
            return (entry.data, entry.headers, entry.status_code)

    def set(self, method, url, data, headers, status_code, ttl=None):
        key = self._make_key(method, url)
        entry = CacheEntry(data, headers, status_code, ttl)
        with self._lock:
            if key in self._cache:
                del self._cache[key]
            elif len(self._cache) >= self.max_entries:
                self._evict()
            self._cache[key] = entry
            self._cache.move_to_end(key)

    def _evict(self):
        if not self._cache:
            return
        expired = [k for k, v in self._cache.items()
                   if v.is_expired(self.default_ttl)]
        if expired:
            for k in expired:
                del self._cache[k]
            return
        for key in list(self._cache.keys()):
            if self._cache[key].access_count <= 5:
                del self._cache[key]
                return
        self._cache.popitem(last=False)

    def clear(self):
        with self._lock:
            self._cache.clear()

    def stats(self):
        with self._lock:
            total = len(self._cache)
            total_size = sum(e.size for e in self._cache.values())
            expired = sum(1 for e in self._cache.values()
                         if e.is_expired(self.default_ttl))
            hot = [(k, e.access_count) for k, e in self._cache.items()
                   if e.access_count > 3]
            hot.sort(key=lambda x: -x[1])
            return {
                'entries': total,
                'total_size': total_size,
                'expired': expired,
                'hot_resources': hot[:10]
            }


# ╔══════════════════════════════════════════════════════════╗
# ║                   访问控制模块                            ║
# ╚══════════════════════════════════════════════════════════╝

class AccessController:
    """黑白名单访问控制"""

    MODE_OFF = 'off'
    MODE_BLACKLIST = 'blacklist'
    MODE_WHITELIST = 'whitelist'

    def __init__(self):
        self.mode = self.MODE_OFF
        self.blacklist = set()
        self.whitelist = set()
        self._lock = threading.Lock()
        self._load_lists()

    def _list_file(self, list_type):
        return os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           f"{list_type}.txt")

    def _load_lists(self):
        for list_type in ('blacklist', 'whitelist'):
            path = self._list_file(list_type)
            if os.path.exists(path):
                with open(path, 'r', encoding='utf-8') as f:
                    items = {line.strip() for line in f
                            if line.strip() and not line.startswith('#')}
                    if list_type == 'blacklist':
                        self.blacklist = items
                    else:
                        self.whitelist = items

    def _save_list(self, list_type):
        path = self._list_file(list_type)
        items = self.blacklist if list_type == 'blacklist' else self.whitelist
        with open(path, 'w', encoding='utf-8') as f:
            for item in sorted(items):
                f.write(item + '\n')

    def _match(self, hostname, pattern):
        if pattern.startswith('*.'):
            return hostname == pattern[2:] or hostname.endswith('.' + pattern[2:])
        return hostname == pattern

    def is_allowed(self, hostname):
        with self._lock:
            if self.mode == self.MODE_OFF:
                return True
            if self.mode == self.MODE_BLACKLIST:
                return not any(self._match(hostname, p) for p in self.blacklist)
            if self.mode == self.MODE_WHITELIST:
                return any(self._match(hostname, p) for p in self.whitelist)
            return True

    def add_blacklist(self, domain):
        with self._lock:
            self.blacklist.add(domain)
            self._save_list('blacklist')

    def remove_blacklist(self, domain):
        with self._lock:
            self.blacklist.discard(domain)
            self._save_list('blacklist')

    def add_whitelist(self, domain):
        with self._lock:
            self.whitelist.add(domain)
            self._save_list('whitelist')

    def remove_whitelist(self, domain):
        with self._lock:
            self.whitelist.discard(domain)
            self._save_list('whitelist')

    def set_mode(self, mode):
        if mode in (self.MODE_OFF, self.MODE_BLACKLIST, self.MODE_WHITELIST):
            self.mode = mode

    def list_blacklist(self):
        return sorted(self.blacklist)

    def list_whitelist(self):
        return sorted(self.whitelist)


# ╔══════════════════════════════════════════════════════════╗
# ║                   统计收集模块                            ║
# ╚══════════════════════════════════════════════════════════╝

class StatsCollector:
    """统计收集器"""

    def __init__(self):
        self._lock = threading.RLock()
        self.total_requests = 0
        self.cache_hits = 0
        self.cache_misses = 0
        self.blocked_requests = 0
        self.domain_stats = {}
        self.url_stats = {}
        self.status_stats = {}
        self.start_time = time.time()

    def record_request(self, url, status_code, cached, blocked=False):
        with self._lock:
            self.total_requests += 1
            if cached:
                self.cache_hits += 1
            else:
                self.cache_misses += 1
            if blocked:
                self.blocked_requests += 1
            self.status_stats[status_code] = self.status_stats.get(status_code, 0) + 1
            try:
                hostname = urlparse(url).hostname or url
                self.domain_stats[hostname] = self.domain_stats.get(hostname, 0) + 1
            except Exception:
                pass
            self.url_stats[url] = self.url_stats.get(url, 0) + 1

    def hit_rate(self):
        with self._lock:
            total = self.cache_hits + self.cache_misses
            return (self.cache_hits / total * 100) if total > 0 else 0.0

    def uptime(self):
        return time.time() - self.start_time

    def get_hot_domains(self, n=10):
        with self._lock:
            items = sorted(self.domain_stats.items(), key=lambda x: -x[1])
            return items[:n]

    def get_hot_urls(self, n=10):
        with self._lock:
            items = sorted(self.url_stats.items(), key=lambda x: -x[1])
            return items[:n]

    def summary(self):
        with self._lock:
            return {
                'total': self.total_requests,
                'hits': self.cache_hits,
                'misses': self.cache_misses,
                'blocked': self.blocked_requests,
                'hit_rate': self.hit_rate(),
                'uptime': int(self.uptime()),
            }


# ╔══════════════════════════════════════════════════════════╗
# ║                   请求头修改模块                          ║
# ╚══════════════════════════════════════════════════════════╝

class HeaderModifier:
    """请求头修改器"""

    def __init__(self):
        self._lock = threading.Lock()
        self.remove_headers = {'Proxy-Connection', 'Proxy-Authorization'}
        self.add_headers = {}
        self.override_headers = {}
        self.enabled = True

    def set_add_header(self, key, value):
        with self._lock:
            self.add_headers[key] = value

    def remove_add_header(self, key):
        with self._lock:
            self.add_headers.pop(key, None)

    def set_override_header(self, key, value):
        with self._lock:
            self.override_headers[key] = value

    def set_user_agent(self, ua):
        with self._lock:
            self.override_headers['User-Agent'] = ua

    def modify_request_headers(self, headers):
        if not self.enabled:
            return headers
        modified = {}
        with self._lock:
            for key, value in headers.items():
                if key in self.remove_headers:
                    continue
                if key in self.override_headers:
                    modified[key] = self.override_headers[key]
                else:
                    modified[key] = value
            for key, value in self.add_headers.items():
                if key not in modified:
                    modified[key] = value
        return modified

    def modify_response_headers(self, headers):
        headers['X-Proxy-By'] = VERSION
        return headers


# ╔══════════════════════════════════════════════════════════╗
# ║                     日志模块                              ║
# ╚══════════════════════════════════════════════════════════╝

class Logger:
    """日志记录器"""

    def __init__(self, log_file='proxy.log'):
        self.log_file = log_file
        self._lock = threading.Lock()
        self._setup_file()

    def _setup_file(self):
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           self.log_file)
        self._file_path = path

    def _format(self, level, client_ip, method, url, status, cache_hit, size=0, extra=''):
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        cache_str = 'HIT' if cache_hit else 'MISS'
        status_str = str(status) if status else '---'
        parts = [
            f"[{timestamp}]",
            f"[{client_ip or '-':15s}]",
            f"[{method or '-':7s}]",
            f"[{cache_str:4s}]",
            f"[{status_str:>3s}]",
            f"[{size:>6d}]",
        ]
        if url:
            parts.append(url[:100])
        if extra:
            parts.append(extra)
        return ' '.join(parts)

    def log(self, level, client_ip, method, url, status, cache_hit, size=0, extra=''):
        msg = self._format(level, client_ip, method, url, status, cache_hit, size, extra)
        with self._lock:
            try:
                with open(self._file_path, 'a', encoding='utf-8') as f:
                    f.write(msg + '\n')
            except Exception:
                pass
            print(msg)


# ╔══════════════════════════════════════════════════════════╗
# ║                   HTTP 请求解析                           ║
# ╚══════════════════════════════════════════════════════════╝

def parse_request(data):
    """解析HTTP请求，返回 (method, url, headers, body)"""
    try:
        text = data.decode('utf-8', errors='replace')
    except Exception:
        text = data.decode('latin-1', errors='replace')

    parts = text.split('\r\n\r\n', 1)
    header_section = parts[0]
    body = parts[1].encode('latin-1', errors='replace') if len(parts) > 1 else b''

    lines = header_section.split('\r\n')
    if not lines:
        return None, None, {}, b''

    request_line = lines[0].split(' ')
    if len(request_line) < 3:
        return None, None, {}, b''

    method = request_line[0].upper()
    url = request_line[1]

    headers = {}
    for line in lines[1:]:
        if ':' in line:
            key, _, value = line.partition(':')
            headers[key.strip()] = value.strip()

    return method, url, headers, body


def build_request(method, url, headers, body=b''):
    """构建HTTP请求报文"""
    parsed = urlparse(url)
    path = parsed.path or '/'
    if parsed.query:
        path += '?' + parsed.query

    header_lines = [f"{method} {path} {HTTP_VERSION}"]
    for key, value in headers.items():
        header_lines.append(f"{key}: {value}")
    header_lines.append(f"Host: {parsed.hostname}")
    header_lines.append(f"Connection: close")

    request_text = '\r\n'.join(header_lines) + '\r\n\r\n'
    return request_text.encode('utf-8') + body


def parse_response(raw_data):
    """解析HTTP响应，返回 (status_code, headers, body)"""
    try:
        text = raw_data.decode('utf-8', errors='replace')
    except Exception:
        text = raw_data.decode('latin-1', errors='replace')

    parts = text.split('\r\n\r\n', 1)
    header_section = parts[0]
    body = parts[1].encode('latin-1', errors='replace') if len(parts) > 1 else b''

    lines = header_section.split('\r\n')
    if not lines:
        return 0, {}, b''

    status_parts = lines[0].split(' ')
    status_code = int(status_parts[1]) if len(status_parts) >= 2 else 0

    headers = {}
    for line in lines[1:]:
        if ':' in line:
            key, _, value = line.partition(':')
            headers[key.strip()] = value.strip()

    return status_code, headers, body


HTTP_REASONS = {
    200: 'OK', 201: 'Created', 204: 'No Content',
    301: 'Moved Permanently', 302: 'Found', 304: 'Not Modified',
    400: 'Bad Request', 403: 'Forbidden', 404: 'Not Found',
    405: 'Method Not Allowed', 500: 'Internal Server Error',
    502: 'Bad Gateway', 503: 'Service Unavailable',
}


def build_response(status_code, headers, body=b''):
    """构建HTTP响应报文"""
    reason = HTTP_REASONS.get(status_code, 'Unknown')

    lines = [f"{HTTP_VERSION} {status_code} {reason}"]
    for key, value in headers.items():
        lines.append(f"{key}: {value}")
    lines.append(f"Content-Length: {len(body)}")

    response_text = '\r\n'.join(lines) + '\r\n\r\n'
    return response_text.encode('utf-8') + body


def is_cacheable(status_code, headers):
    """判断响应是否可缓存"""
    if status_code not in (200, 203, 204, 206, 300, 301, 302, 304, 307, 404, 405, 410):
        return False
    cache_control = headers.get('Cache-Control', '')
    if 'no-store' in cache_control or 'no-cache' in cache_control or 'private' in cache_control:
        return False
    pragma = headers.get('Pragma', '')
    if 'no-cache' in pragma:
        return False
    cl = headers.get('Content-Length', '0')
    try:
        if int(cl) > 5 * 1024 * 1024:
            return False
    except ValueError:
        pass
    return True


def get_cache_ttl_from_headers(headers, default_ttl):
    """从响应头解析缓存时间"""
    cache_control = headers.get('Cache-Control', '')
    if 'max-age' in cache_control:
        m = re.search(r'max-age=(\d+)', cache_control)
        if m:
            return int(m.group(1))
    if 's-maxage' in cache_control:
        m = re.search(r's-maxage=(\d+)', cache_control)
        if m:
            return int(m.group(1))
    expires = headers.get('Expires', '')
    if expires:
        try:
            from email.utils import parsedate_to_datetime
            exp_dt = parsedate_to_datetime(expires)
            ttl = (exp_dt - datetime.now().timestamp())
            return max(0, int(ttl))
        except Exception:
            pass
    return default_ttl


# ╔══════════════════════════════════════════════════════════╗
# ║                 Web 管理后台                              ║
# ╚══════════════════════════════════════════════════════════╝

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
          <input class="input" id="blInput" placeholder="添加域名..." onkeydown="if(event.key==='Enter')addB()">
          <button class="btn btn-danger" onclick="addB()">拦截</button>
        </div>
        <div style="max-height:220px;overflow-y:auto"><table><tbody id="blacklistTable"><tr><td class="empty">暂无条目</td></tr></tbody></table></div>
      </div>
    </div>
    <div class="panel">
      <div class="panel-header"><h2>白名单</h2><span class="badge badge-green" id="wlCount">0</span></div>
      <div class="panel-body">
        <div class="flex" style="margin-bottom:12px">
          <input class="input" id="wlInput" placeholder="添加域名..." onkeydown="if(event.key==='Enter')addW()">
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

  <div class="row2">
    <div class="panel">
      <div class="panel-header"><h2>热门 URL</h2></div>
      <div class="panel-body" style="padding:0">
        <table><thead><tr><th style="padding-left:20px">#</th><th>URL</th><th>访问次数</th><th></th></tr></thead>
          <tbody id="hotResources"><tr><td colspan="4" class="empty" style="padding-left:20px">等待数据...</td></tr></tbody></table>
      </div>
    </div>
    <div class="panel">
      <div class="panel-header"><h2>热门域名</h2></div>
      <div class="panel-body" style="padding:0">
        <table><thead><tr><th style="padding-left:20px">#</th><th>Domain</th><th>访问次数</th><th></th></tr></thead>
          <tbody id="hotDomains"><tr><td colspan="4" class="empty" style="padding-left:20px">等待数据...</td></tr></tbody></table>
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
  const[S,C,BL,WL,CF,H]=await Promise.all([J('stats'),J('cache'),J('blacklist'),J('whitelist'),J('config'),J('hot')]);
  if(S){Q('totalRequests',S.total.toLocaleString());Q('hitRate',S.hit_rate.toFixed(1)+'%');Q('blockedRequests',S.blocked);Q('uptime',U(S.uptime));Q('proxyPort',S.port||'--')}
  if(C){Q('cacheEntries',C.entries+' / '+C.max_entries);Q('cacheSize',(C.total_size/1024).toFixed(1)+' KB')}
  if(CF){
    const m=CF.mode;const el=document.getElementById('acMode');
    el.textContent=m==='off'?'全部允许':m==='blacklist'?'黑名单':'白名单';
    el.className='stat-value'+(m==='blacklist'?' red':m==='whitelist'?' green':'');
    document.getElementById('btnModeOff').className='btn btn-outline'+(m==='off'?' active':'');
    document.getElementById('btnModeBlacklist').className='btn btn-outline'+(m==='blacklist'?' active':'');
    document.getElementById('btnModeWhitelist').className='btn btn-outline'+(m==='whitelist'?' active':'');
  }
  if(BL){RT('blacklistTable',BL.items,'bl');Q('blCount',BL.items.length)}
  if(WL){RT('whitelistTable',WL.items,'wl');Q('wlCount',WL.items.length)}
  if(H){
    const mxU=H.hot_urls.length>0?H.hot_urls[0][1]:1;
    let uh='';
    H.hot_urls.forEach(([u,c],i)=>{const p=(c/mxU*100).toFixed(0);uh+=`<tr><td style="padding-left:20px;color:var(--text3)">${i+1}</td><td><span class="td-url" title="${u}">${u}</span></td><td style="font-weight:600">${c}</td><td><div class="bar-wrap"><div class="bar-track"><div class="bar-fill" style="width:${p}%"></div></div>${p}%</div></td></tr>`});
    document.getElementById('hotResources').innerHTML=uh||'<tr><td colspan="4" class="empty" style="padding-left:20px">暂无数据</td></tr>';
    const mxD=H.hot_domains.length>0?H.hot_domains[0][1]:1;
    let dh='';
    H.hot_domains.forEach(([d,c],i)=>{const p=(c/mxD*100).toFixed(0);dh+=`<tr><td style="padding-left:20px;color:var(--text3)">${i+1}</td><td>${d}</td><td style="font-weight:600">${c}</td><td><div class="bar-wrap"><div class="bar-track"><div class="bar-fill" style="width:${p}%"></div></div>${p}%</div></td></tr>`});
    document.getElementById('hotDomains').innerHTML=dh||'<tr><td colspan="4" class="empty" style="padding-left:20px">暂无数据</td></tr>';
  }
  const L=await J('logs?n=40');
  if(L&&L.lines){document.getElementById('logViewer').innerHTML=L.lines.map(l=>`<div class="log-entry log-${l.level}">${E(l.text)}</div>`).join('')}
  document.getElementById('lastRefresh').textContent=new Date().toLocaleTimeString();
}

function RT(id,items,type){
  if(items.length===0){document.getElementById(id).innerHTML='<tr><td class="empty">暂无条目</td></tr>';return}
  document.getElementById(id).innerHTML=items.map(i=>`<tr><td style="font-weight:500">${E(i)}</td><td style="text-align:right"><button class="btn btn-outline btn-xs" onclick="removeItem('${type}','${E(i)}')">移除</button></td></tr>`).join('')
}
function Q(id,v){document.getElementById(id).textContent=v}
async function addB(){const i=document.getElementById('blInput');const d=i.value.trim();if(!d)return;await P('blacklist/add',{domain:d});i.value='';refresh()}
async function addW(){const i=document.getElementById('wlInput');const d=i.value.trim();if(!d)return;await P('whitelist/add',{domain:d});i.value='';refresh()}
async function removeItem(t,d){await P(t+'/del',{domain:d});refresh()}
async function setMode(m){await P('mode',{mode:m});refresh()}
async function clearCache(){if(confirm('确认清空所有缓存？')){await P('cache/clear');refresh()}}
function U(s){const h=Math.floor(s/3600),m=Math.floor(s%3600/60);return h+'h '+m+'m'}
function E(s){const d=document.createElement('div');d.textContent=s;return d.innerHTML}
refresh();setInterval(refresh,2000);
</script>
</body>
</html>'''


class WebAdminHandler(BaseHTTPRequestHandler):
    """Web 管理后台请求处理器"""

    proxy_server = None

    def log_message(self, format, *args):
        pass

    def _send_json(self, data, status=200):
        body = json.dumps(data, ensure_ascii=False).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', len(body))
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(body)

    def _send_html(self, html, status=200):
        body = html.encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.send_header('Content-Length', len(body))
        self.end_headers()
        self.wfile.write(body)

    def _send_error_json(self, msg, status=400):
        self._send_json({'error': msg}, status)

    def _read_body(self):
        length = int(self.headers.get('Content-Length', 0))
        if length > 0:
            raw = self.rfile.read(length)
            try:
                return json.loads(raw.decode('utf-8'))
            except Exception:
                return {}
        return {}

    def do_GET(self):
        try:
            self._do_GET()
        except Exception as e:
            import traceback
            traceback.print_exc()
            self._send_json({'error': str(e)}, 500)

    def _do_GET(self):
        path = self.path.split('?')[0]

        if path == '/' or path == '/index.html':
            self._send_html(DASHBOARD_HTML)
            return

        ps = self.proxy_server

        if path == '/api/stats':
            s = ps.stats.summary()
            s['port'] = ps.port
            self._send_json(s)
        elif path == '/api/cache':
            cs = ps.cache.stats()
            cs['max_entries'] = ps.cache.max_entries
            self._send_json(cs)
        elif path == '/api/blacklist':
            self._send_json({
                'items': ps.access.list_blacklist(),
                'mode': ps.access.mode,
            })
        elif path == '/api/whitelist':
            self._send_json({
                'items': ps.access.list_whitelist(),
                'mode': ps.access.mode,
            })
        elif path == '/api/config':
            self._send_json({
                'mode': ps.access.mode,
                'port': ps.port,
                'cache_ttl': ps.cache_ttl,
                'max_cache': ps.cache.max_entries,
                'header_mod_enabled': ps.header_mod.enabled,
            })
        elif path == '/api/hot':
            self._send_json({
                'hot_domains': ps.stats.get_hot_domains(10),
                'hot_urls': ps.stats.get_hot_urls(10),
            })
        elif path == '/api/logs':
            n = 50
            qs = self.path.split('?')
            if len(qs) > 1:
                import urllib.parse as up
                params = up.parse_qs(qs[1])
                n = int(params.get('n', [50])[0])
            lines = self._read_log_tail(n)
            self._send_json({'lines': lines})
        else:
            self._send_error_json('Not Found', 404)

    def do_POST(self):
        path = self.path.split('?')[0]
        body = self._read_body()
        ps = self.proxy_server

        if path == '/api/blacklist/add':
            domain = body.get('domain', '').strip()
            if domain:
                ps.access.add_blacklist(domain)
                self._send_json({'ok': True, 'domain': domain})
            else:
                self._send_error_json('缺少 domain 参数')
        elif path == '/api/blacklist/del':
            domain = body.get('domain', '').strip()
            if domain:
                ps.access.remove_blacklist(domain)
                self._send_json({'ok': True, 'domain': domain})
            else:
                self._send_error_json('缺少 domain 参数')
        elif path == '/api/whitelist/add':
            domain = body.get('domain', '').strip()
            if domain:
                ps.access.add_whitelist(domain)
                self._send_json({'ok': True, 'domain': domain})
            else:
                self._send_error_json('缺少 domain 参数')
        elif path == '/api/whitelist/del':
            domain = body.get('domain', '').strip()
            if domain:
                ps.access.remove_whitelist(domain)
                self._send_json({'ok': True, 'domain': domain})
            else:
                self._send_error_json('缺少 domain 参数')
        elif path == '/api/mode':
            mode = body.get('mode', 'off')
            ps.access.set_mode(mode)
            self._send_json({'ok': True, 'mode': ps.access.mode})
        elif path == '/api/cache/clear':
            ps.cache.clear()
            self._send_json({'ok': True})
        else:
            self._send_error_json('Not Found', 404)

    def do_OPTIONS(self):
        self.send_response(200)
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
                lines = f.readlines()
            recent = lines[-n:]
            result = []
            for line in recent:
                level = 'info'
                line = line.rstrip('\n\r')
                if 'HIT' in line or '缓存命中' in line:
                    level = 'cache'
                elif 'BLOCKED' in line:
                    level = 'block'
                elif 'ERROR' in line or '异常' in line or '失败' in line:
                    level = 'error'
                result.append({'text': line, 'level': level})
            return result
        except Exception:
            return []


class WebAdmin:
    """Web 管理后台服务器"""

    def __init__(self, proxy_server, host='0.0.0.0', port=8890):
        self.proxy_server = proxy_server
        self.host = host
        self.port = port
        self._httpd = None
        self._thread = None

    def start(self):
        WebAdminHandler.proxy_server = self.proxy_server
        self._httpd = HTTPServer((self.host, self.port), WebAdminHandler)
        self._thread = threading.Thread(target=self._httpd.serve_forever, daemon=True)
        self._thread.start()
        print(f"  Web 管理后台: http://{'localhost' if self.host == '0.0.0.0' else self.host}:{self.port}")

    def stop(self):
        if self._httpd:
            self._httpd.shutdown()


# ╔══════════════════════════════════════════════════════════╗
# ║                   代理服务器主类                          ║
# ╚══════════════════════════════════════════════════════════╝

class ProxyServer:
    """HTTP/HTTPS 代理缓存服务器"""

    def __init__(self, host='0.0.0.0', port=DEFAULT_PORT,
                 cache_ttl=DEFAULT_CACHE_TTL, max_cache=DEFAULT_MAX_CACHE,
                 max_workers=DEFAULT_MAX_WORKERS, log_file='proxy.log',
                 no_admin=False, web_port=8890):
        self.host = host
        self.port = port
        self.cache_ttl = cache_ttl
        self.max_workers = max_workers
        self.no_admin = no_admin
        self.web_port = web_port
        self.running = False

        self.cache = CacheManager(max_entries=max_cache, default_ttl=cache_ttl)
        self.access = AccessController()
        self.stats = StatsCollector()
        self.header_mod = HeaderModifier()
        self.logger = Logger(log_file=log_file)

        self.server_socket = None
        self.executor = None
        self._admin_thread = None
        self._web_admin = None

    def start(self):
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server_socket.bind((self.host, self.port))
        self.server_socket.listen(128)
        self.server_socket.settimeout(1.0)

        self.executor = ThreadPoolExecutor(max_workers=self.max_workers)
        self.running = True

        print(f"\n{'='*60}")
        print(f"  HTTP 代理缓存服务器已启动")
        print(f"  代理地址: {self.host}:{self.port}")
        print(f"  缓存TTL: {self.cache_ttl}s | 最大缓存: {self.cache.max_entries}条")
        print(f"  工作线程: {self.max_workers}")
        print(f"  访问控制模式: {self.access.mode}")
        if not self.no_admin:
            print(f"  输入 'help' 查看管理命令")
        print(f"{'='*60}\n")

    def stop(self):
        self.running = False
        if self._web_admin:
            self._web_admin.stop()
        if self.server_socket:
            self.server_socket.close()
        if self.executor:
            self.executor.shutdown(wait=False)
        print("\n服务器已停止。")

    def run(self):
        self.start()
        self._web_admin = WebAdmin(self, host=self.host, port=self.web_port)
        self._web_admin.start()
        if not self.no_admin:
            self._admin_thread = threading.Thread(target=self._admin_loop, daemon=True)
            self._admin_thread.start()
        while self.running:
            try:
                client_sock, client_addr = self.server_socket.accept()
                self.executor.submit(self.handle_client, client_sock, client_addr)
            except socket.timeout:
                continue
            except OSError:
                if self.running:
                    break

    def handle_client(self, client_sock, client_addr):
        client_ip = client_addr[0]
        try:
            client_sock.settimeout(30)
            data = b''
            while b'\r\n\r\n' not in data:
                chunk = client_sock.recv(BUFFER_SIZE)
                if not chunk:
                    return
                data += chunk
                if len(data) > 65536:
                    break
            if not data:
                return
            method, url, headers, body = parse_request(data)
            if method is None or url is None:
                self._send_error(client_sock, 400, "Bad Request")
                return
            if method == 'CONNECT':
                self._handle_connect(client_sock, url, client_ip)
                return
            if method not in ('GET', 'POST', 'HEAD', 'PUT', 'DELETE', 'OPTIONS'):
                self._send_error(client_sock, 405, f"Method {method} not supported")
                return
            self._handle_http(client_sock, method, url, headers, body, client_ip)
        except socket.timeout:
            pass
        except ConnectionResetError:
            pass
        except Exception as e:
            self.logger.log('ERROR', client_ip, '-', '-', 'ERR', False, extra=f"处理异常: {e}")
        finally:
            try:
                client_sock.close()
            except Exception:
                pass

    def _handle_http(self, client_sock, method, url, headers, body, client_ip):
        try:
            parsed = urlparse(url)
            hostname = parsed.hostname or ''
            port = parsed.port or 80

            if not self.access.is_allowed(hostname):
                self._send_error(client_sock, 403, f"Access denied: {hostname} is blocked")
                self.stats.record_request(url, 403, False, blocked=True)
                self.logger.log('BLOCK', client_ip, method, url, 403, False,
                               extra=f"BLOCKED: {hostname}")
                return

            modified_headers = self.header_mod.modify_request_headers(headers)
            modified_headers['Host'] = hostname
            if 'Connection' in modified_headers:
                del modified_headers['Connection']

            cache_hit = False
            if method in ('GET', 'HEAD'):
                cached = self.cache.get(method, url)
                if cached is not None:
                    cache_data, cache_headers, cache_status = cached
                    cache_headers = self.header_mod.modify_response_headers(
                        dict(cache_headers) if cache_headers else {})
                    cache_headers['X-Cache'] = 'HIT'
                    cache_headers['Content-Length'] = str(len(cache_data))
                    cache_headers['Connection'] = 'close'
                    response = build_response(cache_status, cache_headers, cache_data)
                    client_sock.sendall(response)
                    cache_hit = True
                    self.stats.record_request(url, cache_status, cached=True)
                    self.logger.log('CACHE', client_ip, method, url, cache_status, True,
                                   len(cache_data), extra=f"缓存命中 [{hostname}]")
                    return

            target_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            target_sock.settimeout(15)
            try:
                target_sock.connect((hostname, port))
            except (socket.gaierror, socket.timeout, ConnectionRefusedError, OSError) as e:
                self._send_error(client_sock, 502, f"Cannot connect to {hostname}:{port} - {e}")
                self.stats.record_request(url, 502, False)
                self.logger.log('ERROR', client_ip, method, url, 502, False,
                               extra=f"连接失败: {hostname}:{port}")
                return

            try:
                request_bytes = build_request(method, url, modified_headers, body)
                target_sock.sendall(request_bytes)
                response_data = b''
                while True:
                    chunk = target_sock.recv(BUFFER_SIZE)
                    if not chunk:
                        break
                    response_data += chunk
                if not response_data:
                    self._send_error(client_sock, 502, "Empty response from upstream")
                    self.stats.record_request(url, 502, False)
                    self.logger.log('ERROR', client_ip, method, url, 502, False,
                                   extra="上游服务器空响应")
                    return
                status_code, resp_headers, resp_body = parse_response(response_data)

                if method in ('GET', 'HEAD') and is_cacheable(status_code, resp_headers):
                    entry_ttl = get_cache_ttl_from_headers(resp_headers, self.cache_ttl)
                    self.cache.set(method, url, resp_body, resp_headers, status_code, ttl=entry_ttl)

                resp_headers = self.header_mod.modify_response_headers(resp_headers)
                resp_headers['X-Cache'] = 'MISS'
                resp_headers['Connection'] = 'close'
                response = build_response(status_code, resp_headers, resp_body)
                client_sock.sendall(response)
                self.stats.record_request(url, status_code, cached=False)
                self.logger.log('INFO', client_ip, method, url, status_code, False,
                               len(resp_body), extra=f"[{hostname}]")
            finally:
                target_sock.close()
        except Exception as e:
            self._send_error(client_sock, 500, f"Internal error: {e}")
            self.stats.record_request(url, 500, False)
            self.logger.log('ERROR', client_ip, method, url, 500, False, extra=f"处理异常: {e}")

    def _handle_connect(self, client_sock, url, client_ip):
        try:
            parts = url.split(':')
            hostname = parts[0]
            port = int(parts[1]) if len(parts) > 1 else 443

            if not self.access.is_allowed(hostname):
                self._send_error(client_sock, 403, f"Access denied: {hostname} is blocked",
                                status_line=f"{HTTP_VERSION} 403 Forbidden")
                self.stats.record_request(f"https://{url}", 403, False, blocked=True)
                self.logger.log('BLOCK', client_ip, 'CONNECT', f"https://{url}", 403, False,
                               extra=f"BLOCKED: {hostname}")
                return

            self.logger.log('INFO', client_ip, 'CONNECT', f"https://{url}", 200, False,
                           extra=f"隧道建立 [{hostname}:{port}]")

            target_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            target_sock.settimeout(30)
            try:
                target_sock.connect((hostname, port))
            except Exception as e:
                self._send_error(client_sock, 502, f"Cannot connect to {hostname}:{port}",
                                status_line=f"{HTTP_VERSION} 502 Bad Gateway")
                self.stats.record_request(f"https://{url}", 502, False)
                return

            client_sock.sendall(f"{HTTP_VERSION} 200 Connection Established\r\n\r\n".encode())
            self._relay(client_sock, target_sock, client_ip, hostname)
            self.stats.record_request(f"https://{url}", 200, False)
        except Exception as e:
            self.logger.log('ERROR', client_ip, 'CONNECT', url, 'ERR', False,
                           extra=f"CONNECT异常: {e}")
        finally:
            try:
                client_sock.close()
            except Exception:
                pass

    def _relay(self, client_sock, target_sock, client_ip, hostname):
        sockets = [client_sock, target_sock]
        try:
            while True:
                readable, _, exceptional = select.select(sockets, [], sockets, 60)
                if exceptional:
                    break
                if not readable:
                    break
                for sock in readable:
                    data = sock.recv(BUFFER_SIZE)
                    if not data:
                        return
                    if sock is client_sock:
                        target_sock.sendall(data)
                    else:
                        client_sock.sendall(data)
        except Exception:
            pass
        finally:
            try:
                target_sock.close()
            except Exception:
                pass

    def _send_error(self, client_sock, status_code, message, status_line=None):
        if status_line is None:
            reason = HTTP_REASONS.get(status_code, 'Error')
            status_line = f"{HTTP_VERSION} {status_code} {reason}"
        body = f"<html><body><h1>{status_code}</h1><p>{message}</p></body></html>"
        body_bytes = body.encode('utf-8')
        response = (
            f"{status_line}\r\n"
            f"Content-Type: text/html; charset=utf-8\r\n"
            f"Content-Length: {len(body_bytes)}\r\n"
            f"Connection: close\r\n"
            f"\r\n"
        ).encode('utf-8') + body_bytes
        try:
            client_sock.sendall(response)
        except Exception:
            pass

    # ── 管理控制台 ──────────────────────────────────────

    def _admin_loop(self):
        try:
            import readline
        except ImportError:
            try:
                import pyreadline3 as readline
            except ImportError:
                pass
        while self.running:
            try:
                cmd = input('proxy> ').strip()
                if not cmd:
                    continue
                self._handle_admin_cmd(cmd)
            except (EOFError, KeyboardInterrupt):
                print("\n使用 'quit' 退出管理控制台")
            except Exception as e:
                print(f"命令执行错误: {e}")

    def _handle_admin_cmd(self, cmd_line):
        parts = cmd_line.split()
        cmd = parts[0].lower() if parts else ''
        args = parts[1:] if len(parts) > 1 else []

        if cmd == 'help':
            self._admin_help()
        elif cmd == 'stats':
            self._admin_stats()
        elif cmd == 'cache':
            self._admin_cache(args)
        elif cmd == 'blacklist':
            self._admin_blacklist(args)
        elif cmd == 'whitelist':
            self._admin_whitelist(args)
        elif cmd == 'mode':
            self._admin_mode(args)
        elif cmd == 'clear':
            self._admin_clear(args)
        elif cmd == 'config':
            self._admin_config(args)
        elif cmd == 'header':
            self._admin_header(args)
        elif cmd == 'quit' or cmd == 'exit':
            self._admin_quit()
        else:
            print(f"未知命令: {cmd}，输入 'help' 查看帮助")

    def _admin_help(self):
        print("""
管理命令:
  stats                  - 显示统计信息（请求数、命中率、热门资源）
  cache [clear|list]     - 查看缓存状态 或 清空缓存
  blacklist list         - 显示黑名单
  blacklist add <域名>   - 添加域名到黑名单
  blacklist del <域名>   - 从黑名单移除域名
  whitelist list         - 显示白名单
  whitelist add <域名>   - 添加域名到白名单
  whitelist del <域名>   - 从白名单移除域名
  mode <blacklist|whitelist|off> - 切换访问控制模式
  clear cache            - 清空所有缓存
  config                 - 显示当前配置
  config ttl <秒>        - 修改缓存过期时间
  config maxcache <数量> - 修改最大缓存条目数
  header list            - 显示请求头修改规则
  header add <键> <值>   - 添加自定义请求头
  header del <键>        - 删除自定义请求头
  header ua <User-Agent> - 设置模拟User-Agent
  quit / exit            - 停止服务器并退出
""")

    def _admin_stats(self):
        s = self.stats.summary()
        print(f"\n{'='*50}")
        print(f"  统计信息")
        print(f"{'='*50}")
        print(f"  总请求数:     {s['total']}")
        print(f"  缓存命中:     {s['hits']}")
        print(f"  缓存未命中:   {s['misses']}")
        print(f"  已拦截请求:   {s['blocked']}")
        print(f"  缓存命中率:   {s['hit_rate']:.1f}%")
        uptime = s['uptime']
        h, m, sec = uptime // 3600, (uptime % 3600) // 60, uptime % 60
        print(f"  运行时间:     {int(h)}h {int(m)}m {int(sec)}s")
        if s['total'] > 0:
            rps = s['total'] / uptime if uptime > 0 else 0
            print(f"  平均QPS:      {rps:.2f}")
        print()
        hot_domains = self.stats.get_hot_domains(10)
        if hot_domains:
            print(f"  热门域名 Top10:")
            for i, (domain, count) in enumerate(hot_domains, 1):
                bar = '#' * min(int(count / max(1, hot_domains[0][1]) * 20), 20)
                print(f"  {i:2d}. {domain[:40]:40s} {count:5d} {bar}")
            print()
        hot_urls = self.stats.get_hot_urls(10)
        if hot_urls:
            print(f"  热门资源 Top10:")
            for i, (url, count) in enumerate(hot_urls, 1):
                url_short = url[:60] + '...' if len(url) > 60 else url
                print(f"  {i:2d}. {url_short:63s} {count:5d}")
            print()
        if self.stats.status_stats:
            print(f"  状态码分布:")
            for code in sorted(self.stats.status_stats.keys()):
                print(f"    {code}: {self.stats.status_stats[code]}")
            print()

    def _admin_cache(self, args):
        if args and args[0] == 'clear':
            self.cache.clear()
            print("缓存已清空。")
            self.logger.log('INFO', 'admin', '-', '-', '-', False, extra="缓存已清空")
        elif args and args[0] == 'list':
            cs = self.cache.stats()
            print(f"缓存条目: {cs['entries']}  总大小: {cs['total_size']/1024:.1f} KB  "
                  f"已过期: {cs['expired']}")
            if cs['hot_resources']:
                print("热门缓存资源:")
                for key, count in cs['hot_resources']:
                    print(f"  [{count:4d}] {key[:80]}")
        else:
            cs = self.cache.stats()
            print(f"\n缓存状态:")
            print(f"  条目数:   {cs['entries']} / {self.cache.max_entries}")
            print(f"  总大小:   {cs['total_size']/1024:.1f} KB")
            print(f"  已过期:   {cs['expired']}")
            print(f"  命中率:   {self.stats.hit_rate():.1f}%")
            print()

    def _admin_blacklist(self, args):
        if not args:
            print("用法: blacklist <list|add|del> [参数]")
            return
        sub = args[0].lower()
        if sub == 'list':
            items = self.access.list_blacklist()
            print(f"黑名单 (当前模式: {self.access.mode}):")
            for item in items:
                print(f"  - {item}")
            if not items:
                print("  (空)")
        elif sub == 'add' and len(args) >= 2:
            self.access.add_blacklist(args[1])
            print(f"已添加 '{args[1]}' 到黑名单")
        elif sub == 'del' and len(args) >= 2:
            self.access.remove_blacklist(args[1])
            print(f"已从黑名单移除 '{args[1]}'")
        else:
            print("用法: blacklist add/del <域名>")

    def _admin_whitelist(self, args):
        if not args:
            print("用法: whitelist <list|add|del> [参数]")
            return
        sub = args[0].lower()
        if sub == 'list':
            items = self.access.list_whitelist()
            print(f"白名单 (当前模式: {self.access.mode}):")
            for item in items:
                print(f"  - {item}")
            if not items:
                print("  (空)")
        elif sub == 'add' and len(args) >= 2:
            self.access.add_whitelist(args[1])
            print(f"已添加 '{args[1]}' 到白名单")
        elif sub == 'del' and len(args) >= 2:
            self.access.remove_whitelist(args[1])
            print(f"已从白名单移除 '{args[1]}'")
        else:
            print("用法: whitelist add/del <域名>")

    def _admin_mode(self, args):
        if not args:
            print(f"当前访问控制模式: {self.access.mode}")
            print("用法: mode <blacklist|whitelist|off>")
            return
        mode = args[0].lower()
        self.access.set_mode(mode)
        print(f"访问控制模式已切换为: {self.access.mode}")
        self.logger.log('INFO', 'admin', '-', '-', '-', False,
                       extra=f"模式切换为: {self.access.mode}")

    def _admin_clear(self, args):
        if args and args[0] == 'cache':
            self.cache.clear()
            print("缓存已清空。")
        else:
            print("用法: clear cache")

    def _admin_config(self, args):
        if not args:
            print(f"\n当前配置:")
            print(f"  监听端口:     {self.port}")
            print(f"  缓存TTL:      {self.cache_ttl}s")
            print(f"  最大缓存条目: {self.cache.max_entries}")
            print(f"  最大工作线程: {self.max_workers}")
            print(f"  访问控制模式: {self.access.mode}")
            print(f"  请求头修改:   {'启用' if self.header_mod.enabled else '禁用'}")
            print()
        elif args[0] == 'ttl' and len(args) >= 2:
            try:
                ttl = int(args[1])
                self.cache_ttl = ttl
                self.cache.default_ttl = ttl
                print(f"缓存TTL已设置为 {ttl}s")
            except ValueError:
                print("请输入有效的秒数")
        elif args[0] == 'maxcache' and len(args) >= 2:
            try:
                n = int(args[1])
                self.cache.max_entries = n
                print(f"最大缓存条目已设置为 {n}")
            except ValueError:
                print("请输入有效的数字")
        else:
            print("用法: config [ttl <秒>|maxcache <数量>]")

    def _admin_header(self, args):
        if not args:
            print("用法: header <list|add|del|ua|remove-add> [参数]")
            return
        sub = args[0].lower()
        if sub == 'list':
            print("自定义添加请求头:")
            for k, v in self.header_mod.add_headers.items():
                print(f"  + {k}: {v}")
            print("覆盖请求头:")
            for k, v in self.header_mod.override_headers.items():
                print(f"  ~ {k}: {v}")
            print(f"移除请求头: {', '.join(self.header_mod.remove_headers)}")
            print(f"状态: {'启用' if self.header_mod.enabled else '禁用'}")
        elif sub == 'add' and len(args) >= 3:
            self.header_mod.set_add_header(args[1], ' '.join(args[2:]))
            print(f"已添加自定义请求头: {args[1]}: {' '.join(args[2:])}")
        elif sub == 'del' and len(args) >= 2:
            self.header_mod.remove_add_header(args[1])
            print(f"已移除自定义请求头: {args[1]}")
        elif sub == 'ua' and len(args) >= 2:
            ua = ' '.join(args[1:])
            self.header_mod.set_user_agent(ua)
            print(f"User-Agent 已设置为: {ua}")
        else:
            print("用法: header add <键> <值> | header del <键> | header ua <UA字符串>")

    def _admin_quit(self):
        print("正在停止服务器...")
        self.stop()


# ╔══════════════════════════════════════════════════════════╗
# ║                      主入口                              ║
# ╚══════════════════════════════════════════════════════════╝

def main():
    parser = argparse.ArgumentParser(
        description='HTTP 代理缓存服务器',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python proxy_server.py                           # 默认端口 8888
  python proxy_server.py -p 8080                   # 指定端口
  python proxy_server.py --cache-ttl 600           # 缓存10分钟
  python proxy_server.py --max-cache 500           # 最大500条缓存
  python proxy_server.py --no-admin                # 禁用管理控制台
        """)
    parser.add_argument('-p', '--port', type=int, default=DEFAULT_PORT,
                       help=f'代理监听端口 (默认: {DEFAULT_PORT})')
    parser.add_argument('--cache-ttl', type=int, default=DEFAULT_CACHE_TTL,
                       help=f'缓存过期时间/秒 (默认: {DEFAULT_CACHE_TTL})')
    parser.add_argument('--max-cache', type=int, default=DEFAULT_MAX_CACHE,
                       help=f'最大缓存条目数 (默认: {DEFAULT_MAX_CACHE})')
    parser.add_argument('--workers', type=int, default=DEFAULT_MAX_WORKERS,
                       help=f'最大工作线程数 (默认: {DEFAULT_MAX_WORKERS})')
    parser.add_argument('--log-file', type=str, default='proxy.log',
                       help='日志文件路径 (默认: proxy.log)')
    parser.add_argument('--no-admin', action='store_true',
                       help='禁用管理控制台')
    parser.add_argument('--web-port', type=int, default=8890,
                       help=f'Web 管理后台端口 (默认: 8890)')

    args = parser.parse_args()

    proxy = ProxyServer(
        host='0.0.0.0',
        port=args.port,
        cache_ttl=args.cache_ttl,
        max_cache=args.max_cache,
        max_workers=args.workers,
        log_file=args.log_file,
        no_admin=args.no_admin,
        web_port=args.web_port,
    )

    try:
        proxy.run()
    except KeyboardInterrupt:
        proxy.stop()
        print("\n服务器已通过 Ctrl+C 停止。")


if __name__ == '__main__':
    main()
