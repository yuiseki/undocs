"""Write a document's dates next to it, one file per kind.

    date-distributed.txt   the Distr. header date
    date-adopted.txt       when the body says the resolution was adopted
    date-other.txt         a date found in the opening, kind unknown

These are different facts and are kept apart rather than collapsed into one
field. A/RES/66/165 was distributed on 2012-03-22 and adopted on 2011-12-19;
picking either one would discard the other, and which a reader wants depends on
what they are doing.

date-other is only written when neither of the first two is found. It is the
weakest of the three: a date in the opening of a document is as likely to be a
citation of an older resolution as it is to be this document's own.

Each file holds the ISO date, the pattern that matched, and the text it
matched, so the strength of the claim travels with it.
"""

import argparse
import glob
import os
import re
from collections import Counter

MONTHS = ("January February March April May June July August September "
          "October November December").split()
MONTH_NUMBER = {m: i + 1 for i, m in enumerate(MONTHS)}
DATE = rf"(\d{{1,2}})\s+({'|'.join(MONTHS)})\s+((?:19|20)\d{{2}})"

# Modern layout puts the date on the line after "Distr.: General"; the older
# one runs Distr. / GENERAL / symbol / date down separate lines.
DISTRIBUTED = [
    ("distr", re.compile(rf"Distr\.?\s*:?\s*\w+\s*\n(?:[^\n]*\n){{0,3}}?\s*{DATE}")),
]

# Ordered by how specific they are. Lowercase "adopted on ..." mid-sentence is
# excluded throughout: that is a citation of some other resolution, and it once
# put twenty different 1999 resolutions on 1994-12-09.
ADOPTED = [
    ("meeting", re.compile(rf"at its\s+\d+\w*\s+meeting[^\n]{{0,40}}\n?\s*,?\s*on\s+{DATE}", re.S)),
    ("adopted_by", re.compile(rf"^Adopted by[^\n]{{0,140}}?\bon\s+{DATE}", re.M | re.S)),
    ("resolution_adopted", re.compile(rf"Resolution adopted[^\n]{{0,140}}?\bon\s+{DATE}", re.S)),
    ("resolution_of", re.compile(rf"Resolution\s+\d+\s*\([^)]+\)\s*\n?\s*of\s+{DATE}", re.S)),
]

ANY = re.compile(DATE)

SYMBOL_YEAR = re.compile(r"\(((?:19|20)\d{2})\)|/((?:19|20)\d{2})/")

# The UN was founded in 1945. Anything outside these came from the body.
EARLIEST, LATEST = 1945, 2030

HEAD = 4000


def iso(match):
    day, month, year = match.group(1), match.group(2), match.group(3)
    return f"{year}-{MONTH_NUMBER[month]:02d}-{int(day):02d}", f"{day} {month} {year}"


def first_match(text, patterns, year=None):
    """`year` is the year in the document symbol, used to reject OCR damage.

    S/RES/1139(1997) is distributed 1997-11-21 and its adoption line reads
    1987-11-21: one digit misread. A date more than a year from the symbol's
    own year is not this document's date.
    """
    for name, pattern in patterns:
        m = pattern.search(text)
        if m:
            date, raw = iso(m)
            found = int(date[:4])
            if not EARLIEST <= found <= LATEST:
                continue
            if year is not None and abs(found - year) > 1:
                continue
            return date, name, raw
    return None, None, None


def fallback(text, year):
    for m in ANY.finditer(text):
        date, raw = iso(m)
        found = int(date[:4])
        if not EARLIEST <= found <= LATEST:
            continue
        if year is None or abs(found - year) <= 1:
            return date, "any", raw
    return None, None, None


def symbol_year(symbol):
    m = SYMBOL_YEAR.search(symbol)
    return int(m.group(1) or m.group(2)) if m else None


def write(path, date, rule, raw):
    with open(path, "w", encoding="utf-8") as f:
        f.write(f"{date}\nrule: {rule}\nraw: {raw}\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("root")
    ap.add_argument("--text-name", default="resolution.txt")
    ap.add_argument("--overwrite", action="store_true")
    args = ap.parse_args()

    paths = sorted(glob.glob(os.path.join(args.root, "**", args.text_name), recursive=True))
    print(f"documents\t{len(paths)}", flush=True)

    counts = Counter()
    disagree = []
    for path in paths:
        directory = os.path.dirname(path)
        targets = {k: os.path.join(directory, f"date-{k}.txt")
                   for k in ("distributed", "adopted", "other")}
        if all(os.path.exists(t) for t in targets.values()) and not args.overwrite:
            counts["skipped"] += 1
            continue
        for t in targets.values():
            if args.overwrite and os.path.exists(t):
                os.remove(t)

        symbol = directory[len(args.root):].strip("/")
        year = symbol_year(symbol)
        text = open(path, encoding="utf-8", errors="ignore").read(HEAD)

        d_date, d_rule, d_raw = first_match(text, DISTRIBUTED, year)
        a_date, a_rule, a_raw = first_match(text, ADOPTED, year)

        if d_date:
            write(targets["distributed"], d_date, d_rule, d_raw)
            counts["distributed"] += 1
        if a_date:
            write(targets["adopted"], a_date, a_rule, a_raw)
            counts["adopted"] += 1
        if not d_date and not a_date:
            o_date, o_rule, o_raw = fallback(text, year)
            if o_date:
                write(targets["other"], o_date, o_rule, o_raw)
                counts["other"] += 1
            else:
                counts["none"] += 1

        for kind, date in (("distributed", d_date), ("adopted", a_date)):
            if date and year is not None and abs(int(date[:4]) - year) > 1:
                disagree.append((symbol, kind, date, year))

    print("kind\tcount")
    for kind, count in counts.most_common():
        print(f"{kind}\t{count}")
    print(f"\nsymbol year disagrees by more than a year: {len(disagree)}")
    for symbol, kind, date, year in disagree[:10]:
        print(f"  {symbol:32s} {kind:12s} {date}  symbol_year={year}")


if __name__ == "__main__":
    main()
