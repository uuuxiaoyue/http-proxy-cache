import threading
import time
from urllib.parse import urlparse


class StatsCollector:
    """访问统计收集器。"""

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
