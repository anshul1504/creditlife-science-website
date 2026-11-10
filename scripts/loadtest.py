"""Tiny concurrent load test: browse -> add to cart -> view cart, N virtual customers at once.

    python scripts/loadtest.py http://127.0.0.1:8000 --users 20 --rounds 5

It measures response times and error rates of the read/cart path. It does NOT place orders (that would create
real orders and send email); test checkout against a staging copy. Run it against staging, never production.
"""
import argparse
import re
import statistics
import time
from concurrent.futures import ThreadPoolExecutor

import requests


def csrf_from(session, base):
    session.get(base + "/")
    return session.cookies.get("csrftoken", "")


def customer(base, rounds):
    s = requests.Session()
    timings, errors = [], 0
    token = csrf_from(s, base)
    for _ in range(rounds):
        for method, path, data in (
            ("GET", "/", None), ("GET", "/shop/", None), ("GET", "/shop/npr-hb-syrup/", None),
            ("POST", "/cart/add/npr-hb-syrup/", {"qty": 1}), ("GET", "/cart/", None), ("GET", "/api/pincode/?pin=226001", None),
        ):
            start = time.perf_counter()
            try:
                headers = {"X-CSRFToken": token, "X-Requested-With": "XMLHttpRequest", "Referer": base + "/"}
                r = s.request(method, base + path, data=data, headers=headers, timeout=30)
                ok = r.status_code < 400
            except requests.RequestException:
                ok = False
            timings.append(time.perf_counter() - start)
            errors += 0 if ok else 1
    return timings, errors


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("base")
    ap.add_argument("--users", type=int, default=20)
    ap.add_argument("--rounds", type=int, default=5)
    a = ap.parse_args()
    base = re.sub(r"/$", "", a.base)
    t0 = time.perf_counter()
    with ThreadPoolExecutor(max_workers=a.users) as pool:
        results = list(pool.map(lambda _: customer(base, a.rounds), range(a.users)))
    wall = time.perf_counter() - t0
    all_t = sorted(t for r, _ in results for t in r)
    errors = sum(e for _, e in results)
    p = lambda q: all_t[min(len(all_t) - 1, int(len(all_t) * q))]
    print(f"{len(all_t)} requests in {wall:.1f}s ({len(all_t) / wall:.1f} req/s), errors: {errors}")
    print(f"median {statistics.median(all_t) * 1000:.0f} ms, p95 {p(0.95) * 1000:.0f} ms, max {all_t[-1] * 1000:.0f} ms")


if __name__ == "__main__":
    main()
