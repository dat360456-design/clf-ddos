from curl_cffi import requests as cffi_requests


IMPERSONATE_PROFILES = [
    "chrome124", "chrome123", "chrome120", "chrome119",
    "safari17_0", "safari17_2_ios",
    "firefox133", "firefox128", "edge101",
]


def make_session(proxy: str | None = None, profile: str = "chrome124"):
    s = cffi_requests.Session(
        impersonate=profile,
        proxies={"http": proxy, "https": proxy} if proxy else None,
    )
    s.headers.update({
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-User": "?1",
        "Upgrade-Insecure-Requests": "1",
    })
    return s


def detect_protection(session, url: str) -> str:
    """Returns: none | js_challenge | turnstile | blocked"""
    try:
        r = session.get(url, timeout=15, allow_redirects=True)
    except Exception:
        return "blocked"

    text = r.text.lower()
    if r.headers.get("cf-mitigated") == "challenge":
        if "turnstile" in text or "cf-turnstile" in text:
            return "turnstile"
        return "js_challenge"
    if r.status_code in (403, 503) and "cloudflare" in text:
        return "js_challenge"
    if r.status_code == 200:
        return "none"
    return "blocked"


def solve_js_challenge(session, url: str) -> bool:
    """TLS-impersonated session can often pass the legacy JS challenge transparently.
    Will NOT work on Turnstile."""
    try:
        session.get(url, timeout=15)  # trigger challenge
        r = session.get(url, timeout=15)  # retry with cookies set
        if "cf_clearance" in session.cookies:
            return True
        return r.status_code == 200 and "cf-mitigated" not in r.headers
    except Exception:
        return False