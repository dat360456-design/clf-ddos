import asyncio
import time
from dataclasses import dataclass

import httpx


PROXY_SOURCES = [
    "https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/http.txt",
    "https://raw.githubusercontent.com/clarketm/proxy-list/master/proxy-list-raw.txt",
    "https://raw.githubusercontent.com/monosans/proxy-list/main/proxies/http.txt",
    "https://raw.githubusercontent.com/ShiftyTR/Proxy-List/master/http.txt",
]


@dataclass
class Proxy:
    address: str
    scheme: str = "http"
    healthy: bool = True
    fails: int = 0
    latency: float = 0.0

    def url(self) -> str:
        return f"{self.scheme}://{self.address}"


class ProxyManager:
    def __init__(self, test_url="http://httpbin.org/ip", timeout=8):
        self.proxies: list[Proxy] = []
        self.test_url = test_url
        self.timeout = timeout
        self._lock = asyncio.Lock()
        self._cursor = 0

    def load_from_file(self, path):
        with open(path) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                scheme = "http"
                if line.startswith("socks5://"):
                    scheme, line = "socks5", line[9:]
                elif line.startswith("http://"):
                    line = line[7:]
                self.proxies.append(Proxy(address=line, scheme=scheme))
        print(f"[+] Loaded {len(self.proxies)} proxies from {path}")

    async def scrape_free_proxies(self):
        seen = {p.address for p in self.proxies}
        async with httpx.AsyncClient(timeout=15) as client:
            for src in PROXY_SOURCES:
                try:
                    r = await client.get(src)
                    n = 0
                    for line in r.text.splitlines():
                        line = line.strip()
                        if not line or ":" not in line or line in seen:
                            continue
                        self.proxies.append(Proxy(address=line))
                        seen.add(line)
                        n += 1
                    print(f"[+] {src.split('/')[-1]}: +{n}")
                except Exception as e:
                    print(f"[!] {src}: {e}")
        print(f"[+] Total: {len(self.proxies)}")

    async def validate(self, workers=150, max_latency=5.0):
        print(f"[*] Validating {len(self.proxies)} proxies ({workers} workers)...")
        sem = asyncio.Semaphore(workers)
        healthy = []

        async def check(p: Proxy):
            async with sem:
                t0 = time.time()
                try:
                    async with httpx.AsyncClient(
                        proxy=p.url(), timeout=self.timeout, verify=False
                    ) as c:
                        r = await c.get(self.test_url)
                        if r.status_code == 200:
                            p.latency = time.time() - t0
                            if p.latency <= max_latency:
                                healthy.append(p)
                                return
                except Exception:
                    pass
                p.healthy = False

        await asyncio.gather(*[check(p) for p in self.proxies])
        self.proxies = sorted(healthy, key=lambda x: x.latency)
        print(f"[+] Healthy: {len(self.proxies)}")
        return self.proxies

    async def get(self):
        async with self._lock:
            if not self.proxies:
                return None
            n = len(self.proxies)
            for _ in range(n):
                p = self.proxies[self._cursor % n]
                self._cursor += 1
                if p.healthy:
                    return p
            return None

    def mark_fail(self, proxy: Proxy):
        proxy.fails += 1
        if proxy.fails >= 3:
            proxy.healthy = False

    def mark_ok(self, proxy: Proxy):
        proxy.fails = max(0, proxy.fails - 1)