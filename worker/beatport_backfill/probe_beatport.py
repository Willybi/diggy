#!/usr/bin/env python
"""L0 — Beatport residential-IP scrape probe (GO/NO-GO gate). Stdlib + curl_cffi only.

Runs on the HOST (Windows PC, or a container NAT-ed behind the same residential
line) to answer ONE question before we build the full local Beatport backfill
tool: does the user's residential IP get blocked (403 Cloudflare) when it scrapes
Beatport's search page at the sustained rate of the prod drain?

It reproduces the prod drain's HTTP fingerprint EXACTLY (so the answer is
representative of what the real tool would do):

  - transport  = curl_cffi ``requests.Session(impersonate="chrome124")`` — the same
                 Chrome TLS/JA3 impersonation that ``HttpPool.beatport_get``
                 (``server/workers/async_http.py``) uses to bypass Cloudflare's TLS
                 fingerprinting. The bare stdlib ``requests`` / ``urllib`` would get
                 blocked on the TLS handshake alone, which is precisely the failure
                 mode we must NOT reproduce here — a 403 from a naked client tells
                 us nothing about the residential IP's reputation.
  - URL        = ``https://www.beatport.com/search?q=<term>&type=tracks`` — the exact
                 shape ``BeatportClient.search_track`` scrapes.
  - pacing     = 1.5 s between requests (~0.66 rps), the prod ``RATE_LIMIT`` in
                 ``server/api/beatport/client.py``.
  - success    = presence of ``<script id="__NEXT_DATA__" ...>`` in the HTML, the
                 SSR payload the server extracts (same regex).

It sends ~20 requests over ~5 realistic electronic title+artist search terms and
prints, per request, the HTTP status and whether ``__NEXT_DATA__`` was present,
then a summary (count of 200 / 403 / other, count with the payload).

It performs NO prod connection, NO ssh, NO DB write — pure outbound HTTP to
beatport.com. It is a throwaway diagnostic; there is nothing pure to unit-test.

Usage
-----
Two documented ways to run it (both exit the residential line, so both are valid):

(a) Directly, if curl_cffi installs on the host:

        pip install curl_cffi
        python worker/beatport_backfill/probe_beatport.py

    Options:
        --requests N   total number of requests to send (default 20)
        --interval S   seconds between requests (default 1.5, ~0.66 rps)

(b) Via a throwaway container, if the host install is troublesome. The container
    egresses through the host NAT = the SAME residential IP, so it stays
    representative:

        docker run --rm \
          -v "/c/Users/willi/Desktop/diggy/worker/beatport_backfill":/w \
          python:3.11-slim \
          sh -c "pip install curl_cffi && python /w/probe_beatport.py"

    (On Windows PowerShell, use the path form your Docker accepts for the -v mount,
     e.g. "C:\\Users\\willi\\Desktop\\diggy\\worker\\beatport_backfill".)

Interpretation (the GO/NO-GO criteria to report back)
-----------------------------------------------------
  GO     — the vast majority (~>=18/20) return HTTP 200 AND carry __NEXT_DATA__.
           The residential IP scrapes cleanly at the sustained rate → build the
           full local tool.
  NO-GO / re-evaluate — any 403 appears (Cloudflare is blocking the IP at the
           sustained rate), or many 200s lack __NEXT_DATA__ (page served but
           payload withheld / challenged). Re-assess pacing or the whole approach
           before investing further.
"""

import argparse
import functools
import re
import sys
import time

# progress must stay ordered even when stdout is piped/redirected
print = functools.partial(print, flush=True)  # noqa: A001

BASE_URL = "https://www.beatport.com"
IMPERSONATE = "chrome124"  # same as HttpPool.beatport_get
DEFAULT_REQUESTS = 20
DEFAULT_INTERVAL = 1.5  # seconds, ~0.66 rps — prod RATE_LIMIT

# same SSR-payload marker the server extracts (api/beatport/client.py)
_NEXT_DATA_RE = re.compile(
    r'<script id="__NEXT_DATA__" type="application/json">', re.DOTALL
)

# realistic, varied electronic "artist title" search terms
SEARCH_TERMS = [
    "Bicep Glue",
    "Four Tet Baby",
    "Peggy Gou It Makes You Forget",
    "Bonobo Kerala",
    "Jamie xx Gosh",
]


def _quote(term: str) -> str:
    """URL-encode a search term (curl_cffi ships the requests-style quote)."""
    from curl_cffi import requests as curl_requests

    return curl_requests.utils.quote(term)


def run_probe(total_requests: int, interval: float) -> int:
    """Send `total_requests` paced search requests; print rows + summary.

    Returns a process exit code: 0 if the run reads as GO (all 200 + payload),
    1 otherwise (a 403 or a missing payload appeared) — so a caller/CI can gate
    on it, but the human-readable verdict is the table + summary below.
    """
    try:
        from curl_cffi import requests as curl_requests
    except ImportError:
        print(
            "ERROR: curl_cffi is not installed. Install it first:\n"
            "    pip install curl_cffi\n"
            "or run this probe via the container form documented in the module "
            "docstring.",
        )
        return 2

    session = curl_requests.Session(impersonate=IMPERSONATE)

    print(
        f"Beatport residential-IP probe — {total_requests} requests, "
        f"{interval:.2f}s apart (~{1 / interval:.2f} rps), impersonate={IMPERSONATE}"
    )
    print(f"{'#':>3}  {'status':>6}  {'__NEXT_DATA__':>13}  term")
    print("-" * 60)

    n_200 = 0
    n_403 = 0
    n_other = 0
    n_payload = 0

    for i in range(total_requests):
        term = SEARCH_TERMS[i % len(SEARCH_TERMS)]
        url = f"{BASE_URL}/search?q={_quote(term)}&type=tracks"

        if i > 0:
            time.sleep(interval)

        status: object = "ERR"
        has_payload = False
        try:
            resp = session.get(url, timeout=20)
            status = resp.status_code
            has_payload = bool(_NEXT_DATA_RE.search(resp.text or ""))
            if status == 200:
                n_200 += 1
            elif status == 403:
                n_403 += 1
            else:
                n_other += 1
            if has_payload:
                n_payload += 1
        except Exception as e:  # noqa: BLE001 — a network error is a probe result
            status = f"ERR:{type(e).__name__}"
            n_other += 1

        print(f"{i + 1:>3}  {str(status):>6}  {str(has_payload):>13}  {term}")

    print("-" * 60)
    print(
        f"SUMMARY  total={total_requests}  200={n_200}  403={n_403}  "
        f"other/err={n_other}  with __NEXT_DATA__={n_payload}"
    )

    ok = n_200 == total_requests and n_payload == total_requests
    if ok:
        print(
            f"VERDICT: GO — all {total_requests} returned 200 with __NEXT_DATA__. "
            "The residential IP scrapes cleanly at the sustained rate."
        )
    elif n_403 > 0:
        print(
            f"VERDICT: NO-GO / re-evaluate — {n_403} request(s) returned 403 "
            "(Cloudflare is blocking the IP at the sustained rate)."
        )
    else:
        print(
            "VERDICT: re-evaluate — no clean full pass. Check the missing "
            "__NEXT_DATA__ / non-200 rows above before building the tool."
        )
    return 0 if ok else 1


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Probe whether the residential IP is blocked by Beatport "
        "at the prod scrape rate (GO/NO-GO gate)."
    )
    parser.add_argument(
        "--requests",
        type=int,
        default=DEFAULT_REQUESTS,
        help=f"total number of requests to send (default {DEFAULT_REQUESTS})",
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=DEFAULT_INTERVAL,
        help=f"seconds between requests (default {DEFAULT_INTERVAL}, ~0.66 rps)",
    )
    args = parser.parse_args()

    if args.requests < 1:
        parser.error("--requests must be >= 1")
    if args.interval < 0:
        parser.error("--interval must be >= 0")

    return run_probe(args.requests, args.interval)


if __name__ == "__main__":
    sys.exit(main())
