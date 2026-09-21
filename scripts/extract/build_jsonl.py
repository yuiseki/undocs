"""Collect the extracted documents into one JSONL.

One line per document per language. The date kinds stay separate, as they are
on disk, and each carries the rule that produced it: a date from the Distr.
header and a date from anywhere in the opening are not equally trustworthy, and
a reader cannot tell them apart from the value alone.

Keys use underscores rather than the hyphens in the filenames, because a
hyphenated column name has to be quoted in SQL and cannot be reached by
attribute access in pandas.
"""

import argparse
import glob
import json
import os
import re

DATE_KINDS = ("distributed", "adopted", "other")

# pdftotext marks a page break with a form feed, which carries no meaning the
# PDF does not already hold and is not something a reader of the text wants.
# "NO COVER (n)" is the scanner's note that a cover page is missing.
PAGE_BREAK = re.compile(r"\f")
NO_COVER = re.compile(r"^(?:NO COVER\s*\(\d+\)\s*)+", re.M)


def clean(text):
    text = NO_COVER.sub("", text)
    text = PAGE_BREAK.sub("\n\n", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def read_date(directory, kind):
    """Return (iso, rule, raw) from date-{kind}.txt, or three Nones."""
    path = os.path.join(directory, f"date-{kind}.txt")
    if not os.path.exists(path):
        return None, None, None
    lines = open(path, encoding="utf-8").read().splitlines()
    date = lines[0].strip() if lines else None
    rule = raw = None
    for line in lines[1:]:
        if line.startswith("rule:"):
            rule = line.split(":", 1)[1].strip()
        elif line.startswith("raw:"):
            raw = line.split(":", 1)[1].strip()
    return date or None, rule, raw


def read_body(directory, text_name, ocr_name):
    """The document's text and where it came from.

    The embedded text first, then the OCR. 1,864 documents have only the
    second: they are scans, and what they carry is a reading of an image
    rather than something a publisher wrote down. The distinction travels with
    the text as a column, because a reader cannot judge the text without it.
    """
    for name, source in ((text_name, "pdf"), (ocr_name, "ocr")):
        path = os.path.join(directory, name)
        if os.path.exists(path):
            body = clean(open(path, encoding="utf-8", errors="ignore").read())
            if body:
                return body, source
    return None, None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", action="append", required=True,
                    metavar="LANG=PATH",
                    help="e.g. en=en/pdfs; repeat for each language")
    ap.add_argument("--text-name", default="resolution.txt")
    ap.add_argument("--ocr-name", default="resolution-ocr.txt")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    total = 0
    per_lang = {}
    per_source = {}
    with open(args.out, "w", encoding="utf-8") as out:
        for spec in args.root:
            lang, _, root = spec.partition("=")
            if not root:
                raise SystemExit(f"expected LANG=PATH, got {spec!r}")
            directories = sorted({os.path.dirname(p) for name in (args.text_name, args.ocr_name)
                                  for p in glob.glob(os.path.join(root, "**", name),
                                                     recursive=True)})
            count = 0
            for directory in directories:
                symbol = directory[len(root):].strip("/")
                body, source = read_body(directory, args.text_name, args.ocr_name)
                if not body:
                    continue
                record = {
                    "id": symbol,
                    "lang": lang,
                    "body": body,
                    "n_chars": len(body),
                    "text_source": source,
                    "pdf": os.path.join(directory, "resolution.pdf"),
                }
                for kind in DATE_KINDS:
                    date, rule, raw = read_date(directory, kind)
                    record[f"date_{kind}"] = date
                    record[f"date_{kind}_rule"] = rule
                    record[f"date_{kind}_raw"] = raw
                out.write(json.dumps(record, ensure_ascii=False) + "\n")
                per_source[source] = per_source.get(source, 0) + 1
                count += 1
            per_lang[lang] = count
            total += count

    print(f"records\t{total}")
    for source, count in sorted(per_source.items()):
        print(f"{source}\t{count}")
    for lang, count in sorted(per_lang.items()):
        print(f"{lang}\t{count}")


if __name__ == "__main__":
    main()
