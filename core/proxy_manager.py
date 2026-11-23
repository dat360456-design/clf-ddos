import asyncio
import time
from dataclasses import dataclass

import httpx

# Đã bổ sung thêm nhiều nguồn chất lượng cao
PROXY_SOURCES = [
    # Nguồn cũ
    "https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/http.txt",
    "https://raw.githubusercontent.com/monosans/proxy-list/main/proxies/http.txt",
    
    # Nguồn mới, cập nhật liên tục
    "https://raw.githubusercontent.com/databay-labs/free-proxy-list/master/http.txt",
    "https://raw.githubusercontent.com/databay-labs/free-proxy-list/master/socks5.txt",
    "https://raw.githubusercontent.com/proxy-free/free-proxy-list/main/socks5.txt",
    "https://proxy-scraper.de/all.txt", 
    "https://raw.githubusercontent.com/theriturajps/proxy-list/main/proxies.txt",
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
    def __init__(self, test_url="http://httpbin.org/ip", timeout=10):
        self.proxies: list[Proxy] = []
        self.test_url = test_url
        self.timeout = timeout
        self._lock = asyncio.Lock()
        self._cursor = 0

    def _parse_proxy_line(self, line: str) -> Proxy | None:
        line = line.strip()
        if not line or line.startswith("#") or ":" not in line:
            return None
        
        scheme = "http" # Mặc định là http nếu không có tiền tố
        
        if line.startswith("socks5://"):
            scheme, line = "socks5", line[9:]
        elif line.startswith("socks4://"):
            scheme, line = "socks4", line[9:]
        elif line.startswith("https://"):
            scheme, line = "https", line[8:]
        elif line.startswith("http://"):
            scheme, line = "http", line[7:]
            
        return Proxy(address=line, scheme=scheme)

    def load_from_file(self, path):
        with open(path) as f:
            for line in f:
                p = self._parse_proxy_line(line)
                if p:
                    self.proxies.append(p)
        print(f"[+] Loaded {len(self.proxies)} proxies from {path}")

    async def scrape_free_proxies(self):
        seen = {p.address for p in self.proxies}
        async with httpx.AsyncClient(timeout=15) as client:
            for src in PROXY_SOURCES:
                try:
                    r = await client.get(src)
                    n = 0
                    for line in r.text.splitlines():
                        p = self._parse_proxy_line(line)
                        if p and p.address not in seen:
                            self.proxies.append(p)
                            seen.add(p.address)
                            n += 1
                    print(f"[+] {src.split('/')[-1]}: +{n} proxies")
                except Exception as e:
                    print(f"[!] Lỗi tải {src}: {e}")
        print(f"[+] Tổng cộng thu thập được: {len(self.proxies)} proxies")

    async def validate(self, workers=300, max_latency=5.0):
        """
        Tăng workers lên 300 để quét nhanh hơn. 
        Lưu ý: Trên a-Shell (iOS) nên giảm xuống 100-150 để tránh treo máy.
        """
        print(f"[*] Đang kiểm tra {len(self.proxies)} proxies ({workers} luồng)...")
        sem = asyncio.Semaphore(workers)
        healthy = []
        checked = 0

        async def check(p: Proxy):
            nonlocal checked
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
                finally:
                    p.healthy = False
                    checked += 1
                    if checked % 500 == 0:
                        print(f"    ... đã quét {checked}/{len(self.proxies)}")

        # Dùng return_exceptions=True để tránh lỗi crash toàn bộ nếu 1 proxy lỗi
        await asyncio.gather(*[check(p) for p in self.proxies], return_exceptions=True)
        
        self.proxies = sorted(healthy, key=lambda x: x.latency)
        print(f"[+] Số proxy sống: {len(self.proxies)}")
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