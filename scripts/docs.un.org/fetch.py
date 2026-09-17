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
import threading
import time
from concurrent.futures import ThreadPoolExecutor
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


class Refused(Exception):
    """The API answered, but not with a document path.

    A 429, a 403, a 5xx, or a 302 to /error. None of these says the document
    is absent; they say the request did not succeed. Conflating them with
    absence writes a permanent miss into the manifest for a document that
    exists, and the manifest is what a rerun trusts.
    """


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def document_path(root, lang, symbol):
    """{root}/{lang}/pdfs/{symbol}/resolution.pdf, matching the existing tree.

    The symbol is the directory path: S/1994/1009 becomes S/1994/1009. Segments
    are checked so that a malformed symbol cannot write outside the tree.
    """
    segments = [seg for seg in symbol.split("/") if seg not in ("", ".", "..")]
    if not segments:
        raise ValueError(f"symbol has no usable path: {symbol!r}")
    return os.path.join(root, lang, "pdfs", *segments, "resolution.pdf")


def headers_for(symbol, lang):
    return {
        "User-Agent": UA,
        "Accept": "application/pdf",
        "Accept-Language": "en-US,en;q=0.9",
        "Sec-Fetch-Site": "same-site",
        "Referer": f"https://docs.un.org/{lang}/{symbol}",
    }


def locate(symbol, lang, timeout):
    """Ask the API for the internal path.

    Returns the lowercased path, or None when the API says there is no such
    document. A None here is the only thing this script treats as missing;
    everything else that goes wrong is a failure to be retried.
    """
    url = f"{API}?s={urllib.parse.quote(symbol, safe='/()')}&l={lang}&t=pdf"
    opener = urllib.request.build_opener(NoRedirect)
    req = urllib.request.Request(url, headers=headers_for(symbol, lang))
    try:
        opener.open(req, timeout=timeout)
        # A 200 with no redirect is the API saying it has nothing for this
        # symbol. This is the only response that means the document is absent.
        return None
    except urllib.error.HTTPError as exc:
        if exc.code not in (301, 302, 303, 307, 308):
            raise Refused(f"HTTP {exc.code}") from exc
        location = exc.headers.get("Location") or ""
        if not location.startswith("/doc/"):
            raise Refused(f"redirected to {location[:60]}")
        return location.lower()


class NotAPdf(Exception):
    """The server answered 200 with something that is not a document.

    Usually the Official Document System app page, about 1,303 bytes of HTML.
    It is a transient failure, not a statement that the document is absent, so
    it has to be retried rather than recorded as missing.
    """


# Everything here means "the request did not succeed", never "the document is
# absent". Refused belongs in this tuple as much as NotAPdf does: it was left
# out once, and the first 429 then escaped the worker and ended the whole run.
TRANSIENT = (urllib.error.HTTPError, urllib.error.URLError, TimeoutError,
             OSError, NotAPdf, Refused)


def fetch_pdf(path, symbol, lang, timeout):
    req = urllib.request.Request(BASE + path, headers=headers_for(symbol, lang))
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        body = resp.read()
    if not body.startswith(b"%PDF") or len(body) <= APP_PAGE_MAX:
        raise NotAPdf(f"{len(body)} bytes, not a PDF")
    return body


# A document is done when it was fetched, or when the API said it does not
# exist. A recorded failure is neither: it says the request did not succeed,
# and the manifest is what a rerun trusts, so treating it as done would write
# a permanent miss for a document that is really there.
DONE = ("saved", "missing")


def already_done(manifest_path):
    done = set()
    if not os.path.exists(manifest_path):
        return done
    with open(manifest_path, encoding="utf-8") as f:
        for line in f:
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            if rec.get("status") in DONE:
                done.add((rec["symbol"], rec["lang"]))
    return done


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbols", required=True, help="one document symbol per line")
    ap.add_argument("--out", required=True,
                    help="repository root; files land at {out}/{lang}/pdfs/{symbol}/resolution.pdf")
    ap.add_argument("--manifest", default=None,
                    help="default {out}/data/fetch-manifest.jsonl")
    ap.add_argument("--languages", default=",".join(LANGUAGES))
    ap.add_argument("--delay", type=float, default=2.5,
                    help="seconds a worker waits after finishing a document")
    ap.add_argument("--workers", type=int, default=4,
                    help="documents fetched at once. Measured against this "
                         "server: throughput is linear to 4, flat past 8, and "
                         "nothing was refused at 12. A browser opens 6 "
                         "connections to a host, so 4 to 6 is one reader's "
                         "worth of load.")
    ap.add_argument("--timeout", type=float, default=120)
    ap.add_argument("--retries", type=int, default=3)
    ap.add_argument("--order", choices=("newest", "file"), default="newest",
                    help="newest first, or the order the symbols file is in")
    args = ap.parse_args()

    languages = [l.strip() for l in args.languages.split(",") if l.strip()]
    unknown = [l for l in languages if l not in LANGUAGES]
    if unknown:
        sys.exit(f"not UN official languages, would silently return English: {unknown}")

    os.makedirs(args.out, exist_ok=True)
    manifest_path = args.manifest or os.path.join(args.out, "data", "fetch-manifest.jsonl")
    os.makedirs(os.path.dirname(manifest_path), exist_ok=True)

    done = already_done(manifest_path)
    print(f"already done: {len(done)}", flush=True)

    symbols = [s.strip() for s in open(args.symbols, encoding="utf-8") if s.strip()]
    if args.order == "newest":
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from order import newest_first
        symbols = newest_first(symbols)
    print(f"symbols: {len(symbols)}  languages: {languages}  "
          f"order: {args.order}  workers: {args.workers}", flush=True)

    manifest = open(manifest_path, "a", encoding="utf-8")
    manifest_lock = threading.Lock()
    counts = {"saved": 0, "missing": 0, "error": 0, "skipped": 0}
    counts_lock = threading.Lock()

    def record(entry):
        with manifest_lock:
            manifest.write(json.dumps(entry, ensure_ascii=False) + "\n")
            manifest.flush()

    def bump(key):
        with counts_lock:
            counts[key] += 1

    def work(job):
        symbol, lang = job
        if (symbol, lang) in done:
            bump("skipped")
            return

        body = path = None
        for attempt in range(args.retries):
            try:
                path = locate(symbol, lang, args.timeout)
                if path is None:
                    break
                time.sleep(args.delay * 0.4)
                body = fetch_pdf(path, symbol, lang, args.timeout)
                break
            except TRANSIENT as exc:
                # 502s and app pages are both intermittent here. Back off and
                # try again rather than recording a miss that is really a
                # server hiccup.
                if attempt == args.retries - 1:
                    bump("error")
                    record({"symbol": symbol, "lang": lang, "status": "error",
                            "detail": f"{type(exc).__name__}: {exc}"[:200]})
                    body = None
                    break
                time.sleep(args.delay * (2 ** attempt) + random.random())

        if body:
            dest = document_path(args.out, lang, symbol)
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            with open(dest, "wb") as f:
                f.write(body)
            bump("saved")
            record({"symbol": symbol, "lang": lang, "status": "saved",
                    "path": path, "bytes": len(body)})
        elif path is None:
            bump("missing")
            record({"symbol": symbol, "lang": lang, "status": "missing"})

        time.sleep(args.delay + random.random())

    def guarded(job):
        """Record an unexpected failure instead of letting it end the run.

        pool.map re-raises in the consuming loop, so without this one bad job
        stops every other job and the manifest keeps no trace of why.
        """
        try:
            return work(job)
        except Exception as exc:  # noqa: BLE001 - the point is to catch everything
            bump("error")
            record({"symbol": job[0], "lang": job[1], "status": "error",
                    "detail": f"unhandled {type(exc).__name__}: {exc}"[:200]})

    jobs = [(symbol, lang) for symbol in symbols for lang in languages]
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        for i, _ in enumerate(pool.map(guarded, jobs), 1):
            if i % 200 == 0:
                with counts_lock:
                    print(f"{i}/{len(jobs)} jobs  {dict(counts)}", flush=True)

    manifest.close()
    print(f"FETCH DONE {counts}", flush=True)


if __name__ == "__main__":
    import urllib.parse
    main()
