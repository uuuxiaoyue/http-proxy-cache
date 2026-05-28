import re
from datetime import datetime
from email.utils import parsedate_to_datetime
from urllib.parse import urlparse

from .config import HTTP_VERSION


HEADER_END = b'\r\n\r\n'
HOP_BY_HOP_HEADERS = {
    'connection',
    'keep-alive',
    'proxy-authenticate',
    'proxy-authorization',
    'proxy-connection',
    'te',
    'trailer',
    'transfer-encoding',
    'upgrade',
}


def get_header(headers, name, default=None):
    target = name.lower()
    for key, value in headers.items():
        if key.lower() == target:
            return value
    return default


def set_header(headers, name, value):
    target = name.lower()
    for key in list(headers.keys()):
        if key.lower() == target:
            del headers[key]
    headers[name] = value


def remove_header(headers, name):
    target = name.lower()
    for key in list(headers.keys()):
        if key.lower() == target:
            del headers[key]


def split_http_message(data):
    head, sep, body = data.partition(HEADER_END)
    if not sep:
        return data, b''
    return head, body


def parse_headers(lines):
    headers = {}
    current_key = None
    for line in lines:
        if not line:
            continue
        if line[0] in ' \t' and current_key:
            headers[current_key] += ' ' + line.strip()
            continue
        if ':' in line:
            key, _, value = line.partition(':')
            current_key = key.strip()
            headers[current_key] = value.strip()
    return headers


def parse_request(data):
    head, body = split_http_message(data)
    try:
        header_text = head.decode('iso-8859-1')
    except UnicodeDecodeError:
        return None, None, {}, b''

    lines = header_text.split('\r\n')
    if not lines:
        return None, None, {}, b''

    request_line = lines[0].split()
    if len(request_line) < 3:
        return None, None, {}, b''

    method = request_line[0].upper()
    url = request_line[1]
    headers = parse_headers(lines[1:])
    return method, url, headers, body


def content_length(headers):
    value = get_header(headers, 'Content-Length')
    if value is None:
        return 0
    try:
        return max(0, int(value))
    except ValueError:
        return 0


def request_target(url):
    parsed = urlparse(url)
    if parsed.scheme and parsed.netloc:
        path = parsed.path or '/'
        if parsed.query:
            path += '?' + parsed.query
        return path
    return url or '/'


def host_header_value(parsed):
    if not parsed.hostname:
        return ''
    host = parsed.hostname
    if ':' in host and not host.startswith('['):
        host = f'[{host}]'
    if parsed.port:
        default_port = 443 if parsed.scheme == 'https' else 80
        if parsed.port != default_port:
            return f'{host}:{parsed.port}'
    return host


def build_request(method, url, headers, body=b''):
    parsed = urlparse(url)
    outgoing = dict(headers)

    for key in list(outgoing.keys()):
        if key.lower() in HOP_BY_HOP_HEADERS or key.lower() in {'host', 'content-length'}:
            del outgoing[key]

    host_value = host_header_value(parsed) or get_header(headers, 'Host', '')
    if host_value:
        outgoing['Host'] = host_value
    outgoing['Connection'] = 'close'
    if body:
        outgoing['Content-Length'] = str(len(body))

    lines = [f'{method} {request_target(url)} {HTTP_VERSION}']
    for key, value in outgoing.items():
        lines.append(f'{key}: {value}')
    return ('\r\n'.join(lines) + '\r\n\r\n').encode('iso-8859-1') + body


def parse_response(raw_data):
    status_code, headers, body = parse_response_head(raw_data)
    if 'chunked' in (get_header(headers, 'Transfer-Encoding', '') or '').lower():
        body = decode_chunked_body(body)
        remove_header(headers, 'Transfer-Encoding')
        remove_header(headers, 'Trailer')
    return status_code, headers, body


def parse_response_head(raw_data):
    head, body = split_http_message(raw_data)
    try:
        header_text = head.decode('iso-8859-1')
    except UnicodeDecodeError:
        return 0, {}, b''

    lines = header_text.split('\r\n')
    if not lines:
        return 0, {}, b''

    status_parts = lines[0].split(None, 2)
    try:
        status_code = int(status_parts[1]) if len(status_parts) >= 2 else 0
    except ValueError:
        status_code = 0

    headers = parse_headers(lines[1:])
    return status_code, headers, body


def decode_chunked_body(data):
    decoded = bytearray()
    pos = 0
    while True:
        line_end = data.find(b'\r\n', pos)
        if line_end < 0:
            return bytes(decoded)
        size_line = data[pos:line_end].split(b';', 1)[0].strip()
        try:
            size = int(size_line, 16)
        except ValueError:
            return data
        pos = line_end + 2
        if size == 0:
            return bytes(decoded)
        decoded.extend(data[pos:pos + size])
        pos += size + 2


HTTP_REASONS = {
    200: 'OK', 201: 'Created', 204: 'No Content',
    301: 'Moved Permanently', 302: 'Found', 304: 'Not Modified',
    400: 'Bad Request', 403: 'Forbidden', 404: 'Not Found',
    405: 'Method Not Allowed', 500: 'Internal Server Error',
    502: 'Bad Gateway', 503: 'Service Unavailable',
}


def build_response(status_code, headers, body=b''):
    reason = HTTP_REASONS.get(status_code, 'Unknown')
    outgoing = dict(headers)
    remove_header(outgoing, 'Content-Length')
    remove_header(outgoing, 'Transfer-Encoding')
    set_header(outgoing, 'Content-Length', str(len(body)))

    lines = [f'{HTTP_VERSION} {status_code} {reason}']
    for key, value in outgoing.items():
        lines.append(f'{key}: {value}')

    return ('\r\n'.join(lines) + '\r\n\r\n').encode('iso-8859-1') + body


def is_cacheable(status_code, headers):
    if status_code not in (200, 203, 300, 301, 302, 307, 404, 405, 410):
        return False
    cache_control = (get_header(headers, 'Cache-Control', '') or '').lower()
    if 'no-store' in cache_control or 'no-cache' in cache_control or 'private' in cache_control:
        return False
    pragma = (get_header(headers, 'Pragma', '') or '').lower()
    if 'no-cache' in pragma:
        return False
    try:
        if int(get_header(headers, 'Content-Length', '0') or 0) > 5 * 1024 * 1024:
            return False
    except ValueError:
        pass
    return True


def get_cache_ttl_from_headers(headers, default_ttl):
    cache_control = get_header(headers, 'Cache-Control', '') or ''
    max_age = re.search(r'(?:^|,)\s*s?max-age=(\d+)', cache_control, re.IGNORECASE)
    if max_age:
        return int(max_age.group(1))

    expires = get_header(headers, 'Expires', '')
    if expires:
        try:
            exp_dt = parsedate_to_datetime(expires)
            now = datetime.now(exp_dt.tzinfo) if exp_dt.tzinfo else datetime.now()
            return max(0, int((exp_dt - now).total_seconds()))
        except Exception:
            pass
    return default_ttl
