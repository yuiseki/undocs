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


def test_locate_refuses_a_redirect_to_the_error_page():
    opener = FakeOpener(http_error(302, "https://documents.un.org/error"))
    try:
        with_opener(opener, lambda: fetch.locate("S/RES/1", "en", 5))
    except fetch.Refused:
        return
    raise AssertionError("a redirect to /error did not raise Refused")


def test_document_path_places_the_pdf_under_the_symbol():
    got = fetch.document_path("/out", "en", "A/74/49(VOL.I)")
    assert got == "/out/en/pdfs/A/74/49(VOL.I)/resolution.pdf"


def test_document_path_refuses_to_escape_the_tree():
    got = fetch.document_path("/out", "en", "../../etc/passwd")
    assert got == "/out/en/pdfs/etc/passwd/resolution.pdf"
