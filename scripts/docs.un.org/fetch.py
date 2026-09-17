"""Fetch UN documents from docs.un.org in all six official languages.

See docs/findings/2026-09-17-fetching.md for why it works this way. In short:
an access API answers with an internal path, the path comes back uppercase and
is served lowercase, and the API needs a current-looking set of request headers
or it answers /error.

Built to be interrupted. Every document that lands is recorded in a manifest,
and a rerun skips what the manifest already has, so this can be stopped and
restarted for as long as it takes.
"""

import argparse
import json
import os
import random
import sys
import time
import urllib.error
import urllib.request

LANGUAGES = ("ar", "en", "es", "fr", "ru", "zh")

# l=ja returns the English PDF byte for byte rather than failing, so an
# unrecognised code would silently fill the corpus with duplicate English.
assert "ja" not in LANGUAGES

UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/155.0.0.0 Safari/537.36")

API = "https://documents.un.org/api/symbol/access"
BASE = "https://documents.un.org"

# A 200 carrying the Official Document System single-page app instead of a
# document. It is about 1,303 bytes and is not an error by status code.
APP_PAGE_MAX = 4096


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def headers_for(symbol, lang):
    return {
        "User-Agent": UA,
        "Accept": "application/pdf",
        "Accept-Language": "en-US,en;q=0.9",
        "Sec-Fetch-Site": "same-site",
        "Referer": f"https://docs.un.org/{lang}/{symbol}",
    }


def locate(symbol, lang, timeout):
    """Ask the API for the internal path. Returns the lowercased path or None."""
    url = f"{API}?s={urllib.parse.quote(symbol, safe='/()')}&l={lang}&t=pdf"
    opener = urllib.request.build_opener(NoRedirect)
    req = urllib.request.Request(url, headers=headers_for(symbol, lang))
    try:
        opener.open(req, timeout=timeout)
        return None  # a 200 here means no redirect, so no document
    except urllib.error.HTTPError as exc:
        if exc.code not in (301, 302, 303, 307, 308):
            return None
        location = exc.headers.get("Location") or ""
        if not location.startswith("/doc/"):
            return None  # /error, or something else entirely
        return location.lower()


def fetch_pdf(path, symbol, lang, timeout):
    req = urllib.request.Request(BASE + path, headers=headers_for(symbol, lang))
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        body = resp.read()
    if not body.startswith(b"%PDF"):
        return None
    if len(body) <= APP_PAGE_MAX:
        return None
    return body


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbols", required=True, help="one document symbol per line")
    ap.add_argument("--out", required=True)
    ap.add_argument("--languages", default=",".join(LANGUAGES))
    ap.add_argument("--delay", type=float, default=2.5, help="seconds between requests")
    ap.add_argument("--timeout", type=float, default=120)
    ap.add_argument("--retries", type=int, default=3)
    args = ap.parse_args()

    languages = [l.strip() for l in args.languages.split(",") if l.strip()]
    unknown = [l for l in languages if l not in LANGUAGES]
    if unknown:
        sys.exit(f"not UN official languages, would silently return English: {unknown}")

    os.makedirs(args.out, exist_ok=True)
    manifest_path = os.path.join(args.out, "manifest.jsonl")

    done = set()
    if os.path.exists(manifest_path):
        for line in open(manifest_path, encoding="utf-8"):
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            done.add((rec["symbol"], rec["lang"]))
    print(f"already done: {len(done)}", flush=True)

    symbols = [s.strip() for s in open(args.symbols, encoding="utf-8") if s.strip()]
    print(f"symbols: {len(symbols)}  languages: {languages}", flush=True)

    manifest = open(manifest_path, "a", encoding="utf-8")
    counts = {"saved": 0, "missing": 0, "error": 0, "skipped": 0}

    for i, symbol in enumerate(symbols):
        for lang in languages:
            if (symbol, lang) in done:
                counts["skipped"] += 1
                continue

            body = path = None
            for attempt in range(args.retries):
                try:
                    path = locate(symbol, lang, args.timeout)
                    if path is None:
                        break
                    time.sleep(args.delay * 0.4)
                    body = fetch_pdf(path, symbol, lang, args.timeout)
                    break
                except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, OSError) as exc:
                    # 502 is intermittent here; back off and try again rather
                    # than recording a miss that is really a server hiccup.
                    if attempt == args.retries - 1:
                        counts["error"] += 1
                        manifest.write(json.dumps({
                            "symbol": symbol, "lang": lang, "status": "error",
                            "detail": f"{type(exc).__name__}: {exc}"[:200],
                        }, ensure_ascii=False) + "\n")
                        manifest.flush()
                        body = None
                        break
                    time.sleep(args.delay * (2 ** attempt) + random.random())

            if body:
                safe = symbol.replace("/", "_").replace(" ", "")
                dest = os.path.join(args.out, lang, f"{safe}.pdf")
                os.makedirs(os.path.dirname(dest), exist_ok=True)
                with open(dest, "wb") as f:
                    f.write(body)
                counts["saved"] += 1
                manifest.write(json.dumps({
                    "symbol": symbol, "lang": lang, "status": "saved",
                    "path": path, "bytes": len(body),
                }, ensure_ascii=False) + "\n")
                manifest.flush()
            elif path is None:
                counts["missing"] += 1
                manifest.write(json.dumps({
                    "symbol": symbol, "lang": lang, "status": "missing",
                }, ensure_ascii=False) + "\n")
                manifest.flush()

            time.sleep(args.delay + random.random())

        if (i + 1) % 25 == 0:
            print(f"{i+1}/{len(symbols)} symbols  {counts}", flush=True)

    print(f"FETCH DONE {counts}", flush=True)


if __name__ == "__main__":
    import urllib.parse
    main()
