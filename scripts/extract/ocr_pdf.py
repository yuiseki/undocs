#!/usr/bin/env python3
"""Read the scanned PDFs with tesseract, and keep the result apart.

1,864 documents in this collection carry no text layer. They are scans, mostly
General Assembly supplements from around 1950, and pdftotext returns page
furniture or nothing at all from them.

The output is written as resolution-ocr.txt rather than resolution.txt. The two
are not the same kind of thing: one is the text the publisher embedded, the
other is a reading of an image, and a reader who cannot tell them apart cannot
judge what they have. build_jsonl.py carries the distinction through as a
column.

Pages are rendered in chunks rather than all at once. A 90-page document at
300 dpi greyscale is about 700 MB of PGM, and sixteen workers doing that at the
same time is 11 GB of temporary files for no reason.
"""
import argparse
import glob
import os
import re
import shutil
import subprocess
import sys
import tempfile
from concurrent.futures import ProcessPoolExecutor

CHUNK = 10
# Below this the OCR found nothing usable either, and an empty file next to a
# document would claim more than it should.
MIN_CHARS = 200


def needs_ocr(pdf, text_name, ocr_name):
    """A PDF with no extracted text and no OCR yet.

    The absence of resolution.txt is what marks a scan: pdf_to_text.py writes
    no file when what it found was too short to be a document.
    """
    directory = os.path.dirname(pdf)
    return (not os.path.exists(os.path.join(directory, text_name))
            and not os.path.exists(os.path.join(directory, ocr_name)))


def tidy(text):
    """Collapse the whitespace OCR leaves behind, and drop empty pages."""
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def page_count(pdf):
    out = subprocess.run(["pdfinfo", pdf], capture_output=True, timeout=120)
    for line in out.stdout.decode("utf-8", "ignore").splitlines():
        if line.startswith("Pages:"):
            return int(line.split()[1])
    return 0


# tesseract parallelises each page with OpenMP and will take most of the
# machine for it. Sixteen of those against 32 cores put the load average at 56,
# each process holding about 1.8 cores and fighting the other fifteen for the
# rest. One thread each; the parallelism belongs to the pool.
OCR_ENV = dict(os.environ, OMP_THREAD_LIMIT="1")


def read_pages(pdf, first, last, dpi, workdir, timeout):
    subprocess.run(["pdftoppm", "-r", str(dpi), "-gray",
                    "-f", str(first), "-l", str(last), pdf,
                    os.path.join(workdir, "pg")],
                   capture_output=True, timeout=timeout, check=False)
    out = []
    for image in sorted(glob.glob(os.path.join(workdir, "pg*"))):
        base = os.path.splitext(image)[0]
        subprocess.run(["tesseract", image, base, "-l", "eng", "--psm", "1"],
                       capture_output=True, timeout=timeout, check=False,
                       env=OCR_ENV)
        txt = base + ".txt"
        if os.path.exists(txt):
            out.append(open(txt, encoding="utf-8", errors="ignore").read())
        for f in (image, txt):
            if os.path.exists(f):
                os.remove(f)
    return out


def process(job):
    pdf, ocr_name, dpi, timeout = job
    dest = os.path.join(os.path.dirname(pdf), ocr_name)
    workdir = tempfile.mkdtemp(prefix="ocr-")
    try:
        pages = page_count(pdf)
        if not pages:
            return "failed", f"NO PAGES {pdf}", 0
        chunks = []
        for first in range(1, pages + 1, CHUNK):
            chunks.extend(read_pages(pdf, first, min(first + CHUNK - 1, pages),
                                     dpi, workdir, timeout))
        text = tidy("\n\n".join(chunks))
        if len(text) < MIN_CHARS:
            return "empty", f"NOTHING READ {pdf}", pages
        with open(dest, "w", encoding="utf-8") as f:
            f.write(text + "\n")
        return "written", None, pages
    except subprocess.TimeoutExpired:
        return "failed", f"TIMEOUT {pdf}", 0
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("root")
    ap.add_argument("--text-name", default="resolution.txt")
    ap.add_argument("--ocr-name", default="resolution-ocr.txt")
    ap.add_argument("--dpi", type=int, default=300)
    ap.add_argument("--timeout", type=float, default=600)
    ap.add_argument("--limit", type=int, default=0, help="stop after this many")
    ap.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 4) // 2))
    a = ap.parse_args()

    pdfs = [p for p in sorted(glob.glob(os.path.join(a.root, "**", "*.pdf"), recursive=True))
            if needs_ocr(p, a.text_name, a.ocr_name)]
    if a.limit:
        pdfs = pdfs[:a.limit]
    print(f"to read\t{len(pdfs)}", flush=True)

    counts = {"written": 0, "empty": 0, "failed": 0}
    total_pages = 0
    jobs = [(p, a.ocr_name, a.dpi, a.timeout) for p in pdfs]
    with ProcessPoolExecutor(max_workers=a.workers) as pool:
        for i, (outcome, message, pages) in enumerate(pool.map(process, jobs), 1):
            counts[outcome] += 1
            total_pages += pages
            if message:
                print(message, flush=True)
            if i % 25 == 0:
                print(f"{i}/{len(pdfs)} {counts} {total_pages:,} pages", flush=True)

    print(f"OCR DONE {counts} {total_pages:,} pages", flush=True)


if __name__ == "__main__":
    main()
