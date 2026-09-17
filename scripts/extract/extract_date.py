"""Write each document's date next to it as date.txt.

Three rules, tried in order, because the documents come in two generations.
Modern ones carry a distribution date in a fixed header position; older ones
have no header at all and state the date in running text.

The file records which rule fired, not just the date, so that a reader can
tell a header field from a guess:

    1996-04-30
    rule: distr
    raw: 30 April 1996

Where a document symbol carries a year, the extracted date is checked against
it. A disagreement is reported rather than corrected: for General Assembly
resolutions the distribution date genuinely differs from the adoption date,
often by months and sometimes across a year boundary.
"""

import argparse
import glob
import os
import re
import sys
from collections import Counter

MONTHS = ("January February March April May June July August September "
          "October November December").split()
MONTH_NUMBER = {m: i + 1 for i, m in enumerate(MONTHS)}
MONTH_ALT = "|".join(MONTHS)

DATE = rf"(\d{{1,2}})\s+({MONTH_ALT})\s+((?:19|20)\d{{2}})"

# Two header layouts. The modern one puts the date on the line after
# "Distr.: General"; the older one runs Distr. / GENERAL / symbol / date down
# separate lines, so allow a few lines of anything in between.
DISTR = re.compile(rf"Distr\.?\s*:?\s*\w+\s*\n(?:[^\n]*\n){{0,3}}?\s*{DATE}")

# "Adopted by the Security Council at its 8941st meeting, on 22 December 2021".
# Anchored to the start of a line and capital A: lowercase "adopted on ..."
# inside a sentence is a citation of some other resolution, which put twenty
# 1999 resolutions on 1994-12-09.
ADOPTED = re.compile(rf"^Adopted[^\n]{{0,120}}?\bon\s+{DATE}", re.M | re.S)
ANY = re.compile(DATE)

# S/RES/2615(2021), A/RES/66/165, S/1994/1009
SYMBOL_YEAR = re.compile(r"\(((?:19|20)\d{2})\)|/((?:19|20)\d{2})/")

# The UN was founded in 1945 and this corpus runs to the present, so anything
# outside these bounds came from the body rather than from the document's own
# header. Two symbols with no year in them picked up 1923 and 1928 this way.
EARLIEST = 1945
LATEST = 2030

# How far into the document to look. The header and the adoption line are both
# near the top, and a date found deep in the body is likely a citation of some
# other document.
HEAD = 4000


def iso(match):
    day, month, year = match.group(1), match.group(2), match.group(3)
    # Only the date itself, not the whole match: the older header layout spans
    # several lines and would otherwise make date.txt a variable number of them.
    return f"{year}-{MONTH_NUMBER[month]:02d}-{int(day):02d}", f"{day} {month} {year}"


def find_date(text, year=None):
    """Return (iso date, rule, raw) or (None, None, None).

    `year` is the year in the document symbol, when it has one. It is used only
    to reject candidates from the weakest rule: a date that comes from anywhere
    in the text is as likely to be a citation of an older resolution as it is
    to be this document's own date.
    """
    for rule, pattern in (("distr", DISTR), ("adopted", ADOPTED)):
        m = pattern.search(text)
        if m:
            date, raw = iso(m)
            return date, rule, raw.strip()

    for m in ANY.finditer(text):
        date, raw = iso(m)
        found = int(date[:4])
        if not EARLIEST <= found <= LATEST:
            continue
        if year is None or abs(found - year) <= 1:
            return date, "any", raw.strip()
    return None, None, None


def symbol_year(symbol):
    m = SYMBOL_YEAR.search(symbol)
    if not m:
        return None
    return int(m.group(1) or m.group(2))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("root")
    ap.add_argument("--text-name", default="resolution.txt")
    ap.add_argument("--out-name", default="date.txt")
    ap.add_argument("--overwrite", action="store_true")
    args = ap.parse_args()

    paths = sorted(glob.glob(os.path.join(args.root, "**", args.text_name), recursive=True))
    print(f"documents\t{len(paths)}", flush=True)

    rules = Counter()
    mismatches = []
    none_found = []

    for path in paths:
        dest = os.path.join(os.path.dirname(path), args.out_name)
        if os.path.exists(dest) and not args.overwrite:
            rules["skipped"] += 1
            continue

        symbol = os.path.dirname(path)[len(args.root):].strip("/")
        year = symbol_year(symbol)
        text = open(path, encoding="utf-8", errors="ignore").read(HEAD)
        date, rule, raw = find_date(text, year)
        if date is None:
            rules["none"] += 1
            none_found.append(path)
            continue

        if year is not None and abs(int(date[:4]) - year) > 1:
            mismatches.append((symbol, date, rule, year))

        with open(dest, "w", encoding="utf-8") as f:
            f.write(f"{date}\nrule: {rule}\nraw: {raw}\n")
        rules[rule] += 1

    print("rule\tcount")
    for rule, count in rules.most_common():
        print(f"{rule}\t{count}")
    print(f"\nno date found: {len(none_found)}")
    for p in none_found[:10]:
        print(f"  {p}")
    print(f"\nsymbol year disagrees by more than a year: {len(mismatches)}")
    for symbol, date, rule, year in mismatches[:10]:
        print(f"  {symbol:34s} date={date} rule={rule} symbol_year={year}")


if __name__ == "__main__":
    main()
