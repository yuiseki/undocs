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

# Below this, the extraction found page furniture and no body.
MIN_CHARS = 200


def extract(pdf_path, timeout):
    result = subprocess.run(["pdftotext", pdf_path, "-"],
                            capture_output=True, timeout=timeout)
    if result.returncode != 0:
        return None, result.stderr.decode("utf-8", "ignore")[:200]
    text = result.stdout.decode("utf-8", "ignore")
    return re.sub(r"\n{3,}", "\n\n", text).strip(), None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("root", help="directory holding the PDFs, searched recursively")
    ap.add_argument("--name", default="resolution.txt")
    ap.add_argument("--timeout", type=float, default=120)
    ap.add_argument("--overwrite", action="store_true")
    args = ap.parse_args()

    pdfs = sorted(glob.glob(os.path.join(args.root, "**", "*.pdf"), recursive=True))
    print(f"pdfs\t{len(pdfs)}", flush=True)

    counts = {"written": 0, "skipped": 0, "scanned": 0, "failed": 0}
    for i, pdf in enumerate(pdfs):
        dest = os.path.join(os.path.dirname(pdf), args.name)
        if os.path.exists(dest) and not args.overwrite:
            counts["skipped"] += 1
            continue
        try:
            text, error = extract(pdf, args.timeout)
        except subprocess.TimeoutExpired:
            counts["failed"] += 1
            print(f"TIMEOUT {pdf}", flush=True)
            continue
        if text is None:
            counts["failed"] += 1
            print(f"FAILED {pdf}: {error}", flush=True)
            continue
        if len(text) < MIN_CHARS:
            counts["scanned"] += 1
            print(f"NO TEXT (likely a scan) {pdf}", flush=True)
            continue
        with open(dest, "w", encoding="utf-8") as f:
            f.write(text + "\n")
        counts["written"] += 1
        if (i + 1) % 500 == 0:
            print(f"{i+1}/{len(pdfs)} {counts}", flush=True)

    print(f"EXTRACT DONE {counts}", flush=True)
    if counts["failed"]:
        sys.exit(1)


if __name__ == "__main__":
    main()
