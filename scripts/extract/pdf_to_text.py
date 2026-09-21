"""Write the text of each PDF next to it as resolution.txt.

pdftotext without -layout, because -layout pads every line out to the original
column positions and the result is mostly spaces. These documents are single
column, so the default reading order is right.

A PDF that yields almost nothing is a scan, not a failure. Those are reported
separately and no file is written, so an empty .txt never sits next to a
document that does have text in it.
"""

import argparse
import glob
import os
import re
import subprocess
import sys
from concurrent.futures import ProcessPoolExecutor

# Below this, the extraction found page furniture and no body.
MIN_CHARS = 200


def extract(pdf_path, timeout):
    result = subprocess.run(["pdftotext", pdf_path, "-"],
                            capture_output=True, timeout=timeout)
    if result.returncode != 0:
        return None, result.stderr.decode("utf-8", "ignore")[:200]
    text = result.stdout.decode("utf-8", "ignore")
    return re.sub(r"\n{3,}", "\n\n", text).strip(), None


def process(job):
    """Extract one PDF. Pure enough to run in a pool: it reads one file and
    writes one beside it, and nothing else shares state.
    """
    pdf, name, timeout, overwrite = job
    dest = os.path.join(os.path.dirname(pdf), name)
    if os.path.exists(dest) and not overwrite:
        return "skipped", None
    try:
        text, error = extract(pdf, timeout)
    except subprocess.TimeoutExpired:
        return "failed", f"TIMEOUT {pdf}"
    if text is None:
        return "failed", f"FAILED {pdf}: {error}"
    if len(text) < MIN_CHARS:
        return "scanned", f"NO TEXT (likely a scan) {pdf}"
    with open(dest, "w", encoding="utf-8") as f:
        f.write(text + "\n")
    return "written", None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("root", help="directory holding the PDFs, searched recursively")
    ap.add_argument("--name", default="resolution.txt")
    ap.add_argument("--timeout", type=float, default=120)
    ap.add_argument("--overwrite", action="store_true")
    ap.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 4) // 2))
    args = ap.parse_args()

    pdfs = sorted(glob.glob(os.path.join(args.root, "**", "*.pdf"), recursive=True))
    print(f"pdfs\t{len(pdfs)}", flush=True)

    counts = {"written": 0, "skipped": 0, "scanned": 0, "failed": 0}
    jobs = [(pdf, args.name, args.timeout, args.overwrite) for pdf in pdfs]
    # pdftotext is a separate process doing CPU work, so this scales with cores.
    # Log lines no longer arrive in path order; each one names its own file.
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        for i, (outcome, message) in enumerate(pool.map(process, jobs, chunksize=16), 1):
            counts[outcome] += 1
            if message:
                print(message, flush=True)
            if i % 2000 == 0:
                print(f"{i}/{len(pdfs)} {counts}", flush=True)

    print(f"EXTRACT DONE {counts}", flush=True)
    if counts["failed"]:
        sys.exit(1)


if __name__ == "__main__":
    main()
