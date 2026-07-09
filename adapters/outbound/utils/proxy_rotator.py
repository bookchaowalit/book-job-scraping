"""
Proxy rotation for avoiding IP bans.
Supports: free proxy lists, paid proxy APIs, self-hosted proxies.
"""

import random
import logging
from typing import List, Optional, Dict

logger = logging.getLogger(__name__)


class ProxyRotator:
    """Rotate through a pool of proxies."""

    def __init__(self, proxies: List[str] = None):
        self.proxies = proxies or []
        self.current_index = 0
        self.failed: set = set()

    def add_proxy(self, proxy: str):
        """Add proxy in format: http://user:pass@host:port"""
        self.proxies.append(proxy)

    def get_proxy(self) -> Optional[str]:
        """Get next working proxy."""
        available = [p for p in self.proxies if p not in self.failed]
        if not available:
            self.failed.clear()  # reset if all failed
            available = self.proxies
        if not available:
            return None
        proxy = available[self.current_index % len(available)]
        self.current_index += 1
        return proxy

    def mark_failed(self, proxy: str):
        """Mark a proxy as failed."""
        self.failed.add(proxy)
        logger.warning(f"Proxy failed: {proxy}")

    def get_proxy_dict(self) -> Optional[Dict[str, str]]:
        """Get proxy as dict for httpx/requests."""
        proxy = self.get_proxy()
        if not proxy:
            return None
        return {"http://": proxy, "https://": proxy}


# Free proxy sources (use for testing, not production)
FREE_PROXY_SOURCES = [
    "https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/http.txt",
    "https://raw.githubusercontent.com/monosans/proxy-list/main/proxies/http.txt",
]


def load_free_proxies() -> List[str]:
    """Load free proxies from public lists (for testing only)."""
    import httpx
    proxies = []
    for source_url in FREE_PROXY_SOURCES:
        try:
            resp = httpx.get(source_url, timeout=10)
            for line in resp.text.strip().split("\n"):
                line = line.strip()
                if line:
                    proxies.append(f"http://{line}")
        except Exception as e:
            logger.error(f"Failed to load proxies from {source_url}: {e}")
    return proxies
