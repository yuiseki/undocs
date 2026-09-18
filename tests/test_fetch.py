"""Tests for the parts of the fetcher that decide what a response means.

The bug these were written for: locate() raises Refused, work() did not catch
it, and ThreadPoolExecutor.map re-raised it in the consuming loop, so the first
429 ended the whole run while writing nothing to the manifest. The run looked
like a clean stop.
"""
import os
import sys
import urllib.error
import urllib.request

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts", "docs.un.org"))
import fetch  # noqa: E402


class FakeOpener:
    def __init__(self, raises=None):
        self.raises = raises

    def open(self, req, timeout=None):
        if self.raises:
            raise self.raises
        return None


def http_error(code, location=None):
    headers = {"Location": location} if location else {}
    return urllib.error.HTTPError("u", code, "msg", headers, None)


def use(monkey, opener):
    monkey(lambda *a, **k: opener)


def with_opener(opener, fn):
    original = urllib.request.build_opener
    urllib.request.build_opener = lambda *a, **k: opener
    try:
        return fn()
    finally:
        urllib.request.build_opener = original


def test_transient_includes_every_retryable_failure():
    # Refused and NotAPdf are raised by this module, so forgetting either one
    # here is what lets an exception escape the worker.
    assert fetch.Refused in fetch.TRANSIENT
    assert fetch.NotAPdf in fetch.TRANSIENT


def test_locate_returns_none_only_for_a_plain_200():
    got = with_opener(FakeOpener(), lambda: fetch.locate("S/RES/1", "en", 5))
    assert got is None


def test_locate_lowercases_a_document_redirect():
    opener = FakeOpener(http_error(302, "/doc/UNDOC/GEN/N21/148/80/PDF/N2114880.pdf"))
    got = with_opener(opener, lambda: fetch.locate("S/RES/1", "en", 5))
    assert got == "/doc/undoc/gen/n21/148/80/pdf/n2114880.pdf"


def test_locate_refuses_rather_than_reporting_absence():
    for code in (403, 429, 500, 502, 503):
        opener = FakeOpener(http_error(code))
        try:
            with_opener(opener, lambda: fetch.locate("S/RES/1", "en", 5))
        except fetch.Refused:
            continue
        raise AssertionError(f"HTTP {code} did not raise Refused")


def test_document_path_places_the_pdf_under_the_symbol():
    got = fetch.document_path("/out", "en", "A/74/49(VOL.I)")
    assert got == "/out/en/pdfs/A/74/49(VOL.I)/resolution.pdf"


def test_document_path_refuses_to_escape_the_tree():
    got = fetch.document_path("/out", "en", "../../etc/passwd")
    assert got == "/out/en/pdfs/etc/passwd/resolution.pdf"


def test_resume_retries_failures_but_not_absences(tmp_path):
    """A recorded failure must not become a permanent miss.

    Raising the worker count produced 2,362 HTTP 503s in half an hour. Every
    one of them was written to the manifest, and the manifest is what a rerun
    trusts, so treating an error as done would have silently dropped 2,362
    documents that exist.
    """
    m = tmp_path / "manifest.jsonl"
    m.write_text("\n".join([
        '{"symbol": "S/RES/1", "lang": "en", "status": "saved"}',
        '{"symbol": "S/RES/2", "lang": "en", "status": "missing"}',
        '{"symbol": "S/RES/3", "lang": "en", "status": "error", "detail": "Refused: HTTP 503"}',
        'not json at all',
    ]) + "\n", encoding="utf-8")
    done = fetch.already_done(str(m))
    assert ("S/RES/1", "en") in done      # fetched, do not fetch again
    assert ("S/RES/2", "en") in done      # the API says it does not exist
    assert ("S/RES/3", "en") not in done  # refused, must be tried again


def test_resume_of_a_missing_manifest_is_empty(tmp_path):
    assert fetch.already_done(str(tmp_path / "nothing.jsonl")) == set()


def test_outcome_records_absence_only_when_the_api_said_so():
    """Absence has to be stated, never inferred from a missing path.

    The worker left `path` as None whenever locate() raised, so a refused
    request fell through the absence branch and was recorded as missing as
    well as as an error. Every one of 2,952 failures got both, and the missing
    record made each of them permanently done.
    """
    assert fetch.outcome(b"%PDF-1.4", absent=False) == "saved"
    assert fetch.outcome(b"%PDF-1.4", absent=True) == "saved"
    assert fetch.outcome(None, absent=True) == "missing"
    # Nothing to record: the failure was already written when it happened.
    assert fetch.outcome(None, absent=False) is None


def _watch():
    import importlib.util
    path = os.path.join(os.path.dirname(__file__), "..", "scripts", "docs.un.org", "watch.py")
    spec = importlib.util.spec_from_file_location("watch", path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def test_watch_leaves_a_healthy_run_alone():
    w = _watch()
    before = {"saved": 100, "error": 1, "missing": 5}
    after = {"saved": 400, "error": 2, "missing": 8}   # 0.3% refused
    verdict, _, _ = w.assess(before, after, 0)
    assert verdict == "ok"


def test_watch_stops_a_run_that_is_being_refused():
    w = _watch()
    before = {"saved": 100, "error": 0, "missing": 0}
    after = {"saved": 140, "error": 60, "missing": 0}  # 30% refused
    verdict, _, breaches = w.assess(before, after, 0)
    assert verdict == "warn" and breaches == 1
    verdict, _, _ = w.assess(before, after, breaches)
    assert verdict == "halt"


def test_watch_catches_refusals_and_absences_moving_together():
    w = _watch()
    before = {"saved": 0, "error": 0, "missing": 0}
    after = {"saved": 500, "error": 30, "missing": 30}
    verdict, message, _ = w.assess(before, after, 0)
    assert verdict == "halt" and "moving together" in message


def test_watch_measures_the_interval_not_the_whole_run():
    # A long healthy history must not dilute a bad ten minutes.
    w = _watch()
    before = {"saved": 50000, "error": 10, "missing": 100}
    after = {"saved": 50010, "error": 110, "missing": 100}
    verdict, _, _ = w.assess(before, after, 1)
    assert verdict == "halt"


def test_only_one_fetch_may_hold_the_lock(tmp_path):
    """Two fetches against this API is how the refusal rate reached a third.

    Three of them ran together for hours because the recorded pid belonged to
    the shell wrapper, not to python, so every stop killed the wrapper and left
    the fetch running. A lock makes the launcher's mistake harmless.
    """
    lock = tmp_path / "fetch.lock"
    held = fetch.take_lock(str(lock))
    assert held is not None
    assert fetch.take_lock(str(lock)) is None      # a second one is refused
    fetch.release_lock(held)
    assert fetch.take_lock(str(lock)) is not None  # released, so free again


def test_a_lock_left_by_a_dead_process_is_taken_over(tmp_path):
    lock = tmp_path / "fetch.lock"
    lock.write_text("999999999\n", encoding="utf-8")   # a pid that cannot exist
    assert fetch.take_lock(str(lock)) is not None


def test_the_error_page_means_the_document_does_not_exist():
    """A 302 to /error is deterministic, so it is an absence, not a refusal.

    Eight symbols that the fetch had filed as refusals were probed three times
    each against a server that was answering a known-good symbol in under two
    seconds. All twenty-four probes returned the error page. The symbols are
    implausible on their face: S/PRST/2009/341 when that series runs to about
    thirty a year, A/RES/64/299 when session 64 passed about 120.

    Filing these as refusals cost three requests each and left the watcher
    stopping healthy runs over a failure rate made of absences.
    """
    opener = FakeOpener(http_error(302, "https://documents.un.org/error"))
    assert with_opener(opener, lambda: fetch.locate("S/PRST/2009/341", "en", 5)) is None


def test_a_server_refusal_is_still_a_refusal():
    for code in (403, 429, 500, 502, 503):
        opener = FakeOpener(http_error(code))
        try:
            with_opener(opener, lambda: fetch.locate("S/RES/1", "en", 5))
        except fetch.Refused:
            continue
        raise AssertionError(f"HTTP {code} should still raise Refused")


def test_a_redirect_somewhere_unexpected_is_not_treated_as_absence():
    # Only the error page is known to mean absence. Anything else is a surprise
    # and must not be filed as an answer.
    opener = FakeOpener(http_error(302, "https://example.com/somewhere-else"))
    try:
        with_opener(opener, lambda: fetch.locate("S/RES/1", "en", 5))
    except fetch.Refused:
        return
    raise AssertionError("an unexpected redirect was treated as an answer")
