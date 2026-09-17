"""Order document symbols newest first.

Only 10,233 of the 39,073 symbols carry a year. The rest date themselves in
other ways, and each series does it differently:

    A/RES/77/198     General Assembly session 77, which is 1945 + 77
    S/PV.8923        Security Council meeting number, monotonic since 1946
    S/2020/495       year as a path segment
    S/RES/2728(2024) year in parentheses
    A/RES/981(X)     session as a Roman numeral

The meeting-number mapping is fitted from documents whose dates were already
extracted: PV.99 is 1946 and PV.8923 is 2021. It is an approximation and is
only ever used for ordering, never recorded as a date.

Symbols that yield nothing sort last, oldest-first among themselves, so that an
unrecognised shape delays nothing that can be dated.
"""

import re

ROMAN = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100, "D": 500, "M": 1000}

YEAR_PAREN = re.compile(r"\(((?:19|20)\d{2})\)")
YEAR_PATH = re.compile(r"/((?:19|20)\d{2})/")
GA_SESSION = re.compile(r"^A/(?:RES|PRST)?/?(\d{1,2})/")
GA_ROMAN = re.compile(r"\(([IVXLC]+)\)")
SC_MEETING = re.compile(r"^S/PV\.(\d+)")
SC_RESOLUTION = re.compile(r"^S/RES/(\d+)")

# The General Assembly session opens in September, so session N spans 1945+N
# into the following year.
GA_EPOCH = 1945

# Fitted from documents with extracted dates: PV.99 in 1946, PV.8923 in 2021.
PV_FIRST_NUMBER, PV_FIRST_YEAR = 99, 1946
PV_LAST_NUMBER, PV_LAST_YEAR = 8923, 2021

# Likewise for Security Council resolution numbers: 1 in 1946, 2699 in 2023.
# Only two symbols need this, S/RES/367 and S/RES/370, the rest carrying the
# year in parentheses. The fit is poor because the Council passed few
# resolutions in its early decades and many later: S/RES/367 lands on 1956 and
# is really 1975. Good enough to order two documents, not good enough to
# believe.
RES_FIRST_NUMBER, RES_FIRST_YEAR = 1, 1946
RES_LAST_NUMBER, RES_LAST_YEAR = 2699, 2023


def roman(value):
    total = previous = 0
    for char in reversed(value):
        current = ROMAN.get(char, 0)
        total = total - current if current < previous else total + current
        previous = max(previous, current)
    return total


def interpolate(number, first_number, first_year, last_number, last_year):
    """A year from a monotonic series number. For ordering only."""
    span = last_number - first_number
    return first_year + (number - first_number) * (last_year - first_year) / span


def approximate_year(symbol):
    """A year for ordering, or None. Not a date: never record this as one."""
    m = YEAR_PAREN.search(symbol)
    if m:
        return int(m.group(1))
    m = YEAR_PATH.search(symbol)
    if m:
        return int(m.group(1))
    m = GA_SESSION.match(symbol)
    if m:
        return GA_EPOCH + int(m.group(1))
    m = GA_ROMAN.search(symbol)
    if m and symbol.startswith("A/"):
        session = roman(m.group(1))
        if session:
            return GA_EPOCH + session
    m = SC_MEETING.match(symbol)
    if m:
        return interpolate(int(m.group(1)), PV_FIRST_NUMBER, PV_FIRST_YEAR,
                           PV_LAST_NUMBER, PV_LAST_YEAR)
    m = SC_RESOLUTION.match(symbol)
    if m:
        return interpolate(int(m.group(1)), RES_FIRST_NUMBER, RES_FIRST_YEAR,
                           RES_LAST_NUMBER, RES_LAST_YEAR)
    return None


def sort_key(symbol):
    """Newest first. Undatable symbols sort last."""
    year = approximate_year(symbol)
    if year is None:
        return (1, 0, symbol)
    # Within a year, a higher trailing number is later.
    numbers = [int(n) for n in re.findall(r"\d+", symbol)]
    return (0, -year, -(numbers[-1] if numbers else 0), symbol)


def newest_first(symbols):
    return sorted(symbols, key=sort_key)
