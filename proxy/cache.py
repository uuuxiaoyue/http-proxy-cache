import threading
import time
from collections import OrderedDict

from .config import DEFAULT_CACHE_TTL, DEFAULT_MAX_CACHE


class CacheEntry:
    """缓存条目。"""

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
    """缓存管理器：TTL 过期 + LRU 淘汰 + 访问频率保护。"""

    def __init__(self, max_entries=DEFAULT_MAX_CACHE, default_ttl=DEFAULT_CACHE_TTL):
        self.max_entries = max_entries
        self.default_ttl = default_ttl
        self._cache = OrderedDict()
        self._lock = threading.Lock()

    def _make_key(self, method, url):
        return f'{method}:{url}'

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
            for key in expired:
                del self._cache[key]
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
                'hot_resources': hot[:10],
            }
