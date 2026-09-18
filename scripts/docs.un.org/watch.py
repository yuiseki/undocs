#!/usr/bin/env python3
"""Watch a running fetch and stop it when the numbers go wrong.

A monitor that only writes to a log repeats the problem it is there to catch:
this collection has twice run for hours in a state that a single look would
have caught. So this one acts. When the failure rate stays high it sends the
fetch SIGTERM, because a refused request costs a document and the manifest
fills with records that have to be repaired afterwards.

    python3 scripts/docs.un.org/watch.py --pid 1234 --manifest data/fetch-manifest.jsonl
"""
import argparse
import json
import os
import signal
import sys
import time

# Measured on this API: four workers hold 0.31%, ten workers reach 13.4%.
# Two percent is well clear of the first and well under the second.
WARN = 2.0
HALT = 5.0
# A failure and an absence recorded for the same document was a real bug here,
# and the two counts moving together is its signature. Cheap to keep watching.
TWIN = 0.95


def tally(manifest_path):
    counts = {"saved": 0, "error": 0, "missing": 0}
    if not os.path.exists(manifest_path):
        return counts
    with open(manifest_path, encoding="utf-8") as f:
        for line in f:
            try:
                status = json.loads(line)["status"]
            except Exception:
                continue
            if status in counts:
                counts[status] += 1
    return counts


def assess(previous, current, breaches):
    """What to do about this sample. Returns (verdict, message, breaches).

    Rates are measured over the interval, not since the beginning, so a long
    healthy run cannot dilute a problem that started ten minutes ago.
    """
    d = {k: current[k] - previous[k] for k in current}
    attempted = d["saved"] + d["error"] + d["missing"]
    if attempted == 0:
        return "idle", "nothing attempted this interval", breaches

    rate = d["error"] / attempted * 100
    note = (f"{d['saved']} saved, {d['error']} refused, {d['missing']} absent "
            f"({rate:.1f}% refused)")

    if d["error"] and d["missing"]:
        ratio = min(d["error"], d["missing"]) / max(d["error"], d["missing"])
        if ratio >= TWIN and d["error"] > 20:
            return "halt", note + "; refusals and absences are moving together, " \
                                  "which is how the double-record bug looked", breaches

    if rate >= HALT:
        breaches += 1
        if breaches >= 2:
            return "halt", note + f"; over {HALT}% twice running", breaches
        return "warn", note + f"; over {HALT}%, one more and I stop it", breaches
    if rate >= WARN:
        return "warn", note + f"; over {WARN}%", 0
    return "ok", note, 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pid", type=int, required=True)
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--interval", type=float, default=600)
    ap.add_argument("--pidfile", default=None,
                    help="write this process's pid here, so the caller never "
                         "has to guess it from ps output")
    a = ap.parse_args()

    # Reading a pid back out of ps means matching on a command line, and the
    # shell running that match has the same words in its own. That mistake has
    # been made three times here; writing the pid down removes the guess.
    if a.pidfile:
        with open(a.pidfile, "w", encoding="utf-8") as f:
            f.write(f"{os.getpid()}\n")

    previous = tally(a.manifest)
    breaches = 0
    print(f"watching pid {a.pid}, sampling every {a.interval:.0f}s", flush=True)
    while True:
        time.sleep(a.interval)
        try:
            os.kill(a.pid, 0)
        except OSError:
            print(f"{time.strftime('%H:%M:%S')}  fetch {a.pid} is gone", flush=True)
            return 0
        current = tally(a.manifest)
        verdict, note, breaches = assess(previous, current, breaches)
        previous = current
        print(f"{time.strftime('%H:%M:%S')}  {verdict:5s} {note}", flush=True)
        if verdict == "halt":
            os.kill(a.pid, signal.SIGTERM)
            print(f"{time.strftime('%H:%M:%S')}  sent SIGTERM to {a.pid}", flush=True)
            return 1


if __name__ == "__main__":
    sys.exit(main())
