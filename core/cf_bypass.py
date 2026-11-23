import httpx

def make_session(proxy: str | None = None):
    # Dùng httpx thay vì curl_cffi
    s = httpx.Client(proxy=proxy, timeout=15, verify=False)
    s.headers.update({
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-User": "?1",
        "Upgrade-Insecure-Requests": "1",
    })
    return s

def detect_protection(session, url: str) -> str:
    try:
        r = session.get(url, follow_redirects=True)
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