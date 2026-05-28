import select
import socket
import threading
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlparse

from .access_control import AccessController
from .cache import CacheManager
from .config import (
    BUFFER_SIZE,
    DEFAULT_CACHE_TTL,
    DEFAULT_MAX_CACHE,
    DEFAULT_MAX_WORKERS,
    DEFAULT_PORT,
    HTTP_VERSION,
)
from .headers import HeaderModifier
from .http_utils import (
    HTTP_REASONS,
    build_request,
    build_response,
    content_length,
    get_cache_ttl_from_headers,
    get_header,
    is_cacheable,
    parse_response_head,
    parse_request,
    parse_response,
    remove_header,
    set_header,
)
from .logging_utils import Logger
from .stats import StatsCollector
from .web_admin import WebAdmin


class ProxyServer:
    """HTTP/HTTPS 代理缓存服务器。"""

    def __init__(self, host='0.0.0.0', port=DEFAULT_PORT,
                 cache_ttl=DEFAULT_CACHE_TTL, max_cache=DEFAULT_MAX_CACHE,
                 max_workers=DEFAULT_MAX_WORKERS, log_file='proxy.log',
                 no_admin=False, web_port=8890, web_host='127.0.0.1'):
        self.host = host
        self.port = port
        self.cache_ttl = cache_ttl
        self.max_workers = max_workers
        self.no_admin = no_admin
        self.web_port = web_port
        self.web_host = web_host
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

        print(f"\n{'=' * 60}")
        print("  HTTP 代理缓存服务器已启动")
        print(f"  代理地址: {self.host}:{self.port}")
        print(f"  Web 管理后台: http://{self.web_host}:{self.web_port}")
        print(f"  缓存 TTL: {self.cache_ttl}s | 最大缓存: {self.cache.max_entries} 条")
        print(f"  工作线程: {self.max_workers}")
        print(f"  访问控制模式: {self.access.mode}")
        if not self.no_admin:
            print("  输入 help 查看管理命令")
        print(f"{'=' * 60}\n")

    def stop(self):
        self.running = False
        if self._web_admin:
            self._web_admin.stop()
        if self.server_socket:
            self.server_socket.close()
        if self.executor:
            self.executor.shutdown(wait=False)
        print('\n服务器已停止。')

    def run(self):
        self.start()
        self._web_admin = WebAdmin(self, host=self.web_host, port=self.web_port)
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
                self._send_error(client_sock, 400, 'Bad Request')
                return

            expected_body_len = content_length(headers)
            while len(body) < expected_body_len:
                chunk = client_sock.recv(min(BUFFER_SIZE, expected_body_len - len(body)))
                if not chunk:
                    break
                body += chunk

            if method == 'CONNECT':
                self._handle_connect(client_sock, url, client_ip)
                return
            if method not in ('GET', 'POST', 'HEAD', 'PUT', 'DELETE', 'OPTIONS'):
                self._send_error(client_sock, 405, f'Method {method} not supported')
                return
            self._handle_http(client_sock, method, url, headers, body, client_ip)
        except socket.timeout:
            pass
        except ConnectionResetError:
            pass
        except Exception as e:
            self.logger.log('ERROR', client_ip, '-', '-', 'ERR', False, extra=f'处理异常: {e}')
        finally:
            try:
                client_sock.close()
            except Exception:
                pass

    def _handle_http(self, client_sock, method, url, headers, body, client_ip):
        try:
            parsed = urlparse(url)
            host_header = get_header(headers, 'Host', '')
            hostname = parsed.hostname or host_header.split(':', 1)[0]
            port = parsed.port or 80
            if not parsed.hostname and ':' in host_header:
                try:
                    port = int(host_header.rsplit(':', 1)[1])
                except ValueError:
                    port = 80
            if not hostname:
                self._send_error(client_sock, 400, 'Missing target host')
                self.stats.record_request(url, 400, False)
                self.logger.log('ERROR', client_ip, method, url, 400, False,
                                extra='缺少目标主机')
                return

            if not self.access.is_allowed(hostname):
                self._send_error(client_sock, 403, f'Access denied: {hostname} is blocked')
                self.stats.record_request(url, 403, False, blocked=True)
                self.logger.log('BLOCK', client_ip, method, url, 403, False,
                                extra=f'已拦截: {hostname}')
                return

            modified_headers = self.header_mod.modify_request_headers(headers)
            set_header(modified_headers, 'Host', get_header(headers, 'Host', hostname))
            remove_header(modified_headers, 'Connection')

            if method == 'GET':
                cached = self.cache.get(method, url)
                if cached is not None:
                    cache_data, cache_headers, cache_status = cached
                    cache_headers = self.header_mod.modify_response_headers(
                        dict(cache_headers) if cache_headers else {})
                    set_header(cache_headers, 'X-Cache', 'HIT')
                    set_header(cache_headers, 'Connection', 'close')
                    response = build_response(cache_status, cache_headers, cache_data)
                    client_sock.sendall(response)
                    self.stats.record_request(url, cache_status, cached=True)
                    self.logger.log('CACHE', client_ip, method, url, cache_status, True,
                                    len(cache_data), extra=f'缓存命中 [{hostname}]')
                    return

            target_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            target_sock.settimeout(15)
            try:
                target_sock.connect((hostname, port))
            except (socket.gaierror, socket.timeout, ConnectionRefusedError, OSError) as e:
                self._send_error(client_sock, 502, f'Cannot connect to {hostname}:{port} - {e}')
                self.stats.record_request(url, 502, False)
                self.logger.log('ERROR', client_ip, method, url, 502, False,
                                extra=f'连接失败: {hostname}:{port}')
                return

            try:
                request_bytes = build_request(method, url, modified_headers, body)
                target_sock.sendall(request_bytes)
                response_data = self._read_upstream_response(target_sock, method)
                if not response_data:
                    self._send_error(client_sock, 502, 'Empty response from upstream')
                    self.stats.record_request(url, 502, False)
                    self.logger.log('ERROR', client_ip, method, url, 502, False,
                                    extra='上游服务器返回空响应')
                    return

                status_code, resp_headers, resp_body = parse_response(response_data)
                if method == 'GET' and is_cacheable(status_code, resp_headers):
                    entry_ttl = get_cache_ttl_from_headers(resp_headers, self.cache_ttl)
                    self.cache.set(method, url, resp_body, resp_headers, status_code, ttl=entry_ttl)

                resp_headers = self.header_mod.modify_response_headers(resp_headers)
                set_header(resp_headers, 'X-Cache', 'MISS')
                set_header(resp_headers, 'Connection', 'close')
                response = build_response(status_code, resp_headers, resp_body)
                client_sock.sendall(response)
                self.stats.record_request(url, status_code, cached=False)
                self.logger.log('INFO', client_ip, method, url, status_code, False,
                                len(resp_body), extra=f'[{hostname}]')
            finally:
                target_sock.close()
        except Exception as e:
            self._send_error(client_sock, 500, f'Internal error: {e}')
            self.stats.record_request(url, 500, False)
            self.logger.log('ERROR', client_ip, method, url, 500, False, extra=f'处理异常: {e}')

    def _read_upstream_response(self, target_sock, method):
        data = b''
        while b'\r\n\r\n' not in data:
            chunk = target_sock.recv(BUFFER_SIZE)
            if not chunk:
                return data
            data += chunk
            if len(data) > 1024 * 1024:
                return data

        status_code, headers, body = parse_response_head(data)
        if self._response_has_no_body(method, status_code):
            return data

        transfer_encoding = (get_header(headers, 'Transfer-Encoding', '') or '').lower()
        if 'chunked' in transfer_encoding:
            while not self._chunked_body_complete(body):
                chunk = target_sock.recv(BUFFER_SIZE)
                if not chunk:
                    break
                data += chunk
                _, _, body = parse_response_head(data)
            return data

        length_header = get_header(headers, 'Content-Length')
        if length_header is not None:
            try:
                expected = max(0, int(length_header))
            except ValueError:
                expected = 0
            while len(body) < expected:
                chunk = target_sock.recv(min(BUFFER_SIZE, expected - len(body)))
                if not chunk:
                    break
                data += chunk
                _, _, body = parse_response_head(data)
            return data

        while True:
            chunk = target_sock.recv(BUFFER_SIZE)
            if not chunk:
                break
            data += chunk
        return data

    def _response_has_no_body(self, method, status_code):
        return method == 'HEAD' or status_code in (204, 304) or 100 <= status_code < 200

    def _chunked_body_complete(self, body):
        pos = 0
        while True:
            line_end = body.find(b'\r\n', pos)
            if line_end < 0:
                return False
            size_line = body[pos:line_end].split(b';', 1)[0].strip()
            try:
                size = int(size_line, 16)
            except ValueError:
                return True
            pos = line_end + 2
            if len(body) < pos + size + 2:
                return False
            pos += size
            if body[pos:pos + 2] != b'\r\n':
                return False
            pos += 2
            if size == 0:
                return True

    def _handle_connect(self, client_sock, url, client_ip):
        try:
            hostname, port = self._parse_connect_target(url)
            if not hostname:
                self._send_error(client_sock, 400, 'Invalid CONNECT target',
                                 status_line=f'{HTTP_VERSION} 400 Bad Request')
                self.stats.record_request(f'https://{url}', 400, False)
                return

            if not self.access.is_allowed(hostname):
                self._send_error(client_sock, 403, f'Access denied: {hostname} is blocked',
                                 status_line=f'{HTTP_VERSION} 403 Forbidden')
                self.stats.record_request(f'https://{url}', 403, False, blocked=True)
                self.logger.log('BLOCK', client_ip, 'CONNECT', f'https://{url}', 403, False,
                                extra=f'已拦截: {hostname}')
                return

            self.logger.log('INFO', client_ip, 'CONNECT', f'https://{url}', 200, False,
                            extra=f'隧道建立 [{hostname}:{port}]')

            target_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            target_sock.settimeout(30)
            try:
                target_sock.connect((hostname, port))
            except Exception:
                self._send_error(client_sock, 502, f'Cannot connect to {hostname}:{port}',
                                 status_line=f'{HTTP_VERSION} 502 Bad Gateway')
                self.stats.record_request(f'https://{url}', 502, False)
                return

            client_sock.sendall(f'{HTTP_VERSION} 200 Connection Established\r\n\r\n'.encode())
            self._relay(client_sock, target_sock)
            self.stats.record_request(f'https://{url}', 200, False)
        except Exception as e:
            self.logger.log('ERROR', client_ip, 'CONNECT', url, 'ERR', False,
                            extra=f'CONNECT 异常: {e}')
        finally:
            try:
                client_sock.close()
            except Exception:
                pass

    def _parse_connect_target(self, target):
        if target.startswith('['):
            end = target.find(']')
            if end < 0:
                return None, None
            hostname = target[1:end]
            rest = target[end + 1:]
            if rest.startswith(':'):
                try:
                    return hostname, int(rest[1:])
                except ValueError:
                    return None, None
            return hostname, 443

        if ':' in target:
            hostname, port_text = target.rsplit(':', 1)
            try:
                return hostname, int(port_text)
            except ValueError:
                return None, None
        return target, 443

    def _relay(self, client_sock, target_sock):
        sockets = [client_sock, target_sock]
        try:
            while True:
                readable, _, exceptional = select.select(sockets, [], sockets, 60)
                if exceptional or not readable:
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
            status_line = f'{HTTP_VERSION} {status_code} {reason}'
        body = f'<html><body><h1>{status_code}</h1><p>{message}</p></body></html>'
        body_bytes = body.encode('utf-8')
        response = (
            f'{status_line}\r\n'
            f'Content-Type: text/html; charset=utf-8\r\n'
            f'Content-Length: {len(body_bytes)}\r\n'
            f'Connection: close\r\n'
            f'\r\n'
        ).encode('utf-8') + body_bytes
        try:
            client_sock.sendall(response)
        except Exception:
            pass

    def _admin_loop(self):
        try:
            import readline  # noqa: F401
        except ImportError:
            try:
                import pyreadline3 as readline  # noqa: F401
            except ImportError:
                pass

        while self.running:
            try:
                cmd = input('proxy> ').strip()
                if cmd:
                    self._handle_admin_cmd(cmd)
            except (EOFError, KeyboardInterrupt):
                print("\n输入 quit 退出管理控制台。")
            except Exception as e:
                print(f'命令执行错误: {e}')

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
        elif cmd in ('quit', 'exit'):
            self._admin_quit()
        else:
            print(f"未知命令: {cmd}，输入 help 查看帮助。")

    def _admin_help(self):
        print("""
管理命令:
  stats                         显示请求数、命中率、热门资源
  cache                         查看缓存状态
  cache list                    列出热门缓存资源
  cache clear                   清空缓存
  blacklist list                显示黑名单
  blacklist add <域名>          添加域名到黑名单
  blacklist del <域名>          从黑名单移除域名
  whitelist list                显示白名单
  whitelist add <域名>          添加域名到白名单
  whitelist del <域名>          从白名单移除域名
  mode <blacklist|whitelist|off> 切换访问控制模式
  clear cache                   清空缓存
  config                        显示当前配置
  config ttl <秒>               修改默认缓存 TTL
  config maxcache <数量>        修改最大缓存条目数
  header list                   显示请求头修改规则
  header add <键> <值>          添加自定义请求头
  header del <键>               删除自定义请求头
  header ua <User-Agent>        设置模拟 User-Agent
  quit / exit                   停止服务器并退出
""")

    def _admin_stats(self):
        s = self.stats.summary()
        print(f"\n{'=' * 50}")
        print('  统计信息')
        print(f"{'=' * 50}")
        print(f"  总请求数:       {s['total']}")
        print(f"  缓存命中:       {s['hits']}")
        print(f"  缓存未命中:     {s['misses']}")
        print(f"  已拦截请求:     {s['blocked']}")
        print(f"  缓存命中率:     {s['hit_rate']:.1f}%")
        uptime = s['uptime']
        h, m, sec = uptime // 3600, (uptime % 3600) // 60, uptime % 60
        print(f"  运行时间:       {int(h)}h {int(m)}m {int(sec)}s")
        if s['total'] > 0:
            rps = s['total'] / uptime if uptime > 0 else 0
            print(f"  平均 QPS:       {rps:.2f}")

        hot_domains = self.stats.get_hot_domains(10)
        if hot_domains:
            print('\n  热门域名 Top10:')
            for i, (domain, count) in enumerate(hot_domains, 1):
                bar = '#' * min(int(count / max(1, hot_domains[0][1]) * 20), 20)
                print(f"  {i:2d}. {domain[:40]:40s} {count:5d} {bar}")

        hot_urls = self.stats.get_hot_urls(10)
        if hot_urls:
            print('\n  热门 URL Top10:')
            for i, (url, count) in enumerate(hot_urls, 1):
                url_short = url[:60] + '...' if len(url) > 60 else url
                print(f"  {i:2d}. {url_short:63s} {count:5d}")

        if self.stats.status_stats:
            print('\n  状态码分布:')
            for code in sorted(self.stats.status_stats.keys()):
                print(f"    {code}: {self.stats.status_stats[code]}")
        print()

    def _admin_cache(self, args):
        if args and args[0] == 'clear':
            self.cache.clear()
            print('缓存已清空。')
            self.logger.log('INFO', 'admin', '-', '-', '-', False, extra='缓存已清空')
        elif args and args[0] == 'list':
            cs = self.cache.stats()
            print(f"缓存条目: {cs['entries']}  总大小: {cs['total_size'] / 1024:.1f} KB  "
                  f"已过期: {cs['expired']}")
            if cs['hot_resources']:
                print('热门缓存资源:')
                for key, count in cs['hot_resources']:
                    print(f"  [{count:4d}] {key[:80]}")
        else:
            cs = self.cache.stats()
            print('\n缓存状态:')
            print(f"  条目数:     {cs['entries']} / {self.cache.max_entries}")
            print(f"  总大小:     {cs['total_size'] / 1024:.1f} KB")
            print(f"  已过期:     {cs['expired']}")
            print(f"  命中率:     {self.stats.hit_rate():.1f}%\n")

    def _admin_blacklist(self, args):
        if not args:
            print('用法: blacklist <list|add|del> [域名]')
            return
        sub = args[0].lower()
        if sub == 'list':
            items = self.access.list_blacklist()
            print(f"黑名单，当前模式: {self.access.mode}")
            for item in items:
                print(f"  - {item}")
            if not items:
                print('  (空)')
        elif sub == 'add' and len(args) >= 2:
            self.access.add_blacklist(args[1])
            print(f"已添加到黑名单: {args[1]}")
        elif sub == 'del' and len(args) >= 2:
            self.access.remove_blacklist(args[1])
            print(f"已从黑名单移除: {args[1]}")
        else:
            print('用法: blacklist add/del <域名>')

    def _admin_whitelist(self, args):
        if not args:
            print('用法: whitelist <list|add|del> [域名]')
            return
        sub = args[0].lower()
        if sub == 'list':
            items = self.access.list_whitelist()
            print(f"白名单，当前模式: {self.access.mode}")
            for item in items:
                print(f"  - {item}")
            if not items:
                print('  (空)')
        elif sub == 'add' and len(args) >= 2:
            self.access.add_whitelist(args[1])
            print(f"已添加到白名单: {args[1]}")
        elif sub == 'del' and len(args) >= 2:
            self.access.remove_whitelist(args[1])
            print(f"已从白名单移除: {args[1]}")
        else:
            print('用法: whitelist add/del <域名>')

    def _admin_mode(self, args):
        if not args:
            print(f"当前访问控制模式: {self.access.mode}")
            print('用法: mode <blacklist|whitelist|off>')
            return
        mode = args[0].lower()
        self.access.set_mode(mode)
        print(f"访问控制模式已切换为: {self.access.mode}")
        self.logger.log('INFO', 'admin', '-', '-', '-', False,
                        extra=f'模式切换为: {self.access.mode}')

    def _admin_clear(self, args):
        if args and args[0] == 'cache':
            self.cache.clear()
            print('缓存已清空。')
        else:
            print('用法: clear cache')

    def _admin_config(self, args):
        if not args:
            print('\n当前配置:')
            print(f"  监听端口:       {self.port}")
            print(f"  Web 后台端口:   {self.web_port}")
            print(f"  缓存 TTL:       {self.cache_ttl}s")
            print(f"  最大缓存条目:   {self.cache.max_entries}")
            print(f"  最大工作线程:   {self.max_workers}")
            print(f"  访问控制模式:   {self.access.mode}")
            print(f"  请求头修改:     {'启用' if self.header_mod.enabled else '禁用'}\n")
        elif args[0] == 'ttl' and len(args) >= 2:
            try:
                ttl = int(args[1])
                self.cache_ttl = ttl
                self.cache.default_ttl = ttl
                print(f'缓存 TTL 已设置为 {ttl}s')
            except ValueError:
                print('请输入有效的秒数。')
        elif args[0] == 'maxcache' and len(args) >= 2:
            try:
                n = int(args[1])
                self.cache.max_entries = n
                print(f'最大缓存条目数已设置为 {n}')
            except ValueError:
                print('请输入有效的数字。')
        else:
            print('用法: config [ttl <秒>|maxcache <数量>]')

    def _admin_header(self, args):
        if not args:
            print('用法: header <list|add|del|ua> [参数]')
            return
        sub = args[0].lower()
        if sub == 'list':
            print('自定义添加请求头:')
            for k, v in self.header_mod.add_headers.items():
                print(f'  + {k}: {v}')
            print('覆盖请求头:')
            for k, v in self.header_mod.override_headers.items():
                print(f'  ~ {k}: {v}')
            print(f"移除请求头: {', '.join(self.header_mod.remove_headers)}")
            print(f"状态: {'启用' if self.header_mod.enabled else '禁用'}")
        elif sub == 'add' and len(args) >= 3:
            self.header_mod.set_add_header(args[1], ' '.join(args[2:]))
            print(f"已添加自定义请求头: {args[1]}: {' '.join(args[2:])}")
        elif sub == 'del' and len(args) >= 2:
            self.header_mod.remove_add_header(args[1])
            print(f'已移除自定义请求头: {args[1]}')
        elif sub == 'ua' and len(args) >= 2:
            ua = ' '.join(args[1:])
            self.header_mod.set_user_agent(ua)
            print(f'User-Agent 已设置为: {ua}')
        else:
            print('用法: header add <键> <值> | header del <键> | header ua <User-Agent>')

    def _admin_quit(self):
        print('正在停止服务器...')
        self.stop()
