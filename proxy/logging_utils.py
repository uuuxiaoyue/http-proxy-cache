import os
import threading
from datetime import datetime


class Logger:
    """代理访问日志记录器。"""

    def __init__(self, log_file='proxy.log'):
        self.log_file = log_file
        self._lock = threading.Lock()
        self._setup_file()

    def _setup_file(self):
        self._file_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                       self.log_file)

    def _format(self, level, client_ip, method, url, status, cache_hit, size=0, extra=''):
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        cache_str = 'HIT' if cache_hit else 'MISS'
        status_str = str(status) if status else '---'
        parts = [
            f'[{timestamp}]',
            f'[{client_ip or "-":15s}]',
            f'[{method or "-":7s}]',
            f'[{cache_str:4s}]',
            f'[{status_str:>3s}]',
            f'[{size:>6d}]',
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
