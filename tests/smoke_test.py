import socket
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from proxy.server import ProxyServer  # noqa: E402


seen = {}


class OriginHandler(BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'
    counts = {}

    def log_message(self, *args):
        pass

    def do_GET(self):
        self.counts[self.path] = self.counts.get(self.path, 0) + 1
        seen[self.path + ':ua'] = self.headers.get('User-Agent')
        seen[self.path + ':custom'] = self.headers.get('X-Demo')

        if self.path == '/bin':
            body = bytes([0, 159, 255, 10, 13, 200, 65])
        elif self.path == '/chunked':
            self.send_response(200)
            self.send_header('Transfer-Encoding', 'chunked')
            self.send_header('Cache-Control', 'max-age=60')
            self.end_headers()
            self.wfile.write(b'5\r\nhello\r\n6\r\n-world\r\n0\r\n\r\n')
            return
        else:
            body = b'ok'

        self.send_response(200)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Connection', 'keep-alive')
        self.send_header('Cache-Control', 'max-age=60')
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        length = int(self.headers.get('Content-Length', '0'))
        seen['post_body'] = self.rfile.read(length)
        body = b'post-ok'
        self.send_response(200)
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def request(proxy_port, origin_port, method='GET', path='/', body=b''):
    sock = socket.create_connection(('127.0.0.1', proxy_port), timeout=3)
    headers = [
        f'{method} http://127.0.0.1:{origin_port}{path} HTTP/1.1',
        f'Host: 127.0.0.1:{origin_port}',
        'Connection: close',
    ]
    if body:
        headers.append(f'Content-Length: {len(body)}')
    raw = ('\r\n'.join(headers) + '\r\n\r\n').encode('ascii') + body
    sock.sendall(raw)
    data = b''
    while True:
        chunk = sock.recv(4096)
        if not chunk:
            break
        data += chunk
    sock.close()
    return data


def assert_true(name, condition):
    if not condition:
        raise AssertionError(name)
    print(f'[ok] {name}')


def main():
    origin = HTTPServer(('127.0.0.1', 0), OriginHandler)
    origin_port = origin.server_address[1]
    threading.Thread(target=origin.serve_forever, daemon=True).start()

    proxy = ProxyServer(host='127.0.0.1', port=0, no_admin=True,
                        log_file='smoke_test_proxy.log', web_port=0)
    proxy.header_mod.set_add_header('X-Demo', 'yes')
    proxy.header_mod.set_user_agent('Smoke-UA')
    proxy.start()
    proxy_port = proxy.server_socket.getsockname()[1]

    def accept_loop():
        while proxy.running:
            try:
                client, addr = proxy.server_socket.accept()
                proxy.executor.submit(proxy.handle_client, client, addr)
            except Exception:
                break

    threading.Thread(target=accept_loop, daemon=True).start()

    try:
        first = request(proxy_port, origin_port, path='/text')
        second = request(proxy_port, origin_port, path='/text')
        binary = request(proxy_port, origin_port, path='/bin')
        chunked = request(proxy_port, origin_port, path='/chunked')
        posted = request(proxy_port, origin_port, method='POST',
                         path='/post', body=b'0123456789')

        proxy.access.add_blacklist('127.0.0.0/24')
        proxy.access.set_mode('blacklist')
        blocked = request(proxy_port, origin_port, path='/blocked')

        assert_true('GET cache miss then hit',
                    b'X-Cache: MISS' in first and b'X-Cache: HIT' in second
                    and OriginHandler.counts.get('/text') == 1)
        assert_true('binary body is preserved',
                    binary.split(b'\r\n\r\n', 1)[1] == bytes([0, 159, 255, 10, 13, 200, 65]))
        assert_true('chunked response is decoded',
                    chunked.split(b'\r\n\r\n', 1)[1] == b'hello-world')
        assert_true('POST body is forwarded',
                    seen.get('post_body') == b'0123456789' and b'post-ok' in posted)
        assert_true('request headers are modified',
                    seen.get('/text:ua') == 'Smoke-UA' and seen.get('/text:custom') == 'yes')
        assert_true('CIDR blacklist blocks target',
                    b'403' in blocked)
    finally:
        proxy.stop()
        origin.shutdown()
        for name in ('smoke_test_proxy.log', 'blacklist.txt', 'whitelist.txt'):
            path = ROOT / 'proxy' / name
            if path.exists():
                path.unlink()


if __name__ == '__main__':
    main()
