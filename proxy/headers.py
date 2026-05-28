import threading

from .config import VERSION
from .http_utils import set_header


class HeaderModifier:
    """请求头和响应头修改器。"""

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
        remove_names = {h.lower() for h in self.remove_headers}
        with self._lock:
            for key, value in headers.items():
                if key.lower() in remove_names:
                    continue
                override_key = next((h for h in self.override_headers
                                     if h.lower() == key.lower()), None)
                if override_key:
                    modified[key] = self.override_headers[override_key]
                else:
                    modified[key] = value
            for key, value in self.add_headers.items():
                if not any(h.lower() == key.lower() for h in modified):
                    modified[key] = value
            for key, value in self.override_headers.items():
                if not any(h.lower() == key.lower() for h in modified):
                    modified[key] = value
        return modified

    def modify_response_headers(self, headers):
        set_header(headers, 'X-Proxy-By', VERSION)
        return headers
