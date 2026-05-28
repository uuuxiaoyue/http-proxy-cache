import ipaddress
import os
import socket
import threading
import time


class AccessController:
    """黑名单和白名单访问控制。"""

    MODE_OFF = 'off'
    MODE_BLACKLIST = 'blacklist'
    MODE_WHITELIST = 'whitelist'
    DNS_CACHE_TTL = 60

    def __init__(self):
        self.mode = self.MODE_OFF
        self.blacklist = set()
        self.whitelist = set()
        self._lock = threading.RLock()
        self._dns_cache = {}
        self._load_lists()

    def _list_file(self, list_type):
        return os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            f'{list_type}.txt')

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

    def _resolve_ips(self, hostname):
        host = hostname.strip('[]').lower()
        now = time.time()
        with self._lock:
            cached = self._dns_cache.get(host)
            if cached and now - cached[0] < self.DNS_CACHE_TTL:
                return cached[1]

        ips = set()
        try:
            ipaddress.ip_address(host)
            ips.add(host)
        except ValueError:
            try:
                for result in socket.getaddrinfo(host, None):
                    ips.add(result[4][0])
            except socket.gaierror:
                pass

        with self._lock:
            self._dns_cache[host] = (now, ips)
        return ips

    def _match_domain(self, hostname, pattern):
        host = hostname.strip('[]').lower()
        rule = pattern.lower()
        if rule.startswith('*.'):
            suffix = rule[2:]
            return host == suffix or host.endswith('.' + suffix)
        return host == rule

    def _match_ip(self, ips, pattern):
        try:
            network = ipaddress.ip_network(pattern, strict=False)
        except ValueError:
            return False
        for ip in ips:
            try:
                if ipaddress.ip_address(ip) in network:
                    return True
            except ValueError:
                continue
        return False

    def _match(self, hostname, pattern):
        pattern = pattern.strip()
        if not pattern:
            return False
        if self._match_domain(hostname, pattern):
            return True
        return self._match_ip(self._resolve_ips(hostname), pattern)

    def is_allowed(self, hostname):
        with self._lock:
            mode = self.mode
            blacklist = set(self.blacklist)
            whitelist = set(self.whitelist)

        if mode == self.MODE_OFF:
            return True
        if mode == self.MODE_BLACKLIST:
            return not any(self._match(hostname, p) for p in blacklist)
        if mode == self.MODE_WHITELIST:
            return any(self._match(hostname, p) for p in whitelist)
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
            with self._lock:
                self.mode = mode

    def list_blacklist(self):
        with self._lock:
            return sorted(self.blacklist)

    def list_whitelist(self):
        with self._lock:
            return sorted(self.whitelist)
