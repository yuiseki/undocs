"""Tests for how a document's text is chosen and labelled.

1,864 of the 39,363 documents have no text layer and were read by tesseract
instead. A reader who cannot tell the two apart cannot judge what they have, so
the source travels with the text.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts", "extract"))
import build_jsonl  # noqa: E402


def make(tmp_path, symbol, **files):
    d = tmp_path / symbol
    d.mkdir(parents=True, exist_ok=True)
    (d / "resolution.pdf").write_bytes(b"%PDF")
    for name, text in files.items():
        (d / name).write_text(text, encoding="utf-8")
    return d


def test_embedded_text_is_preferred_and_labelled(tmp_path):
    d = make(tmp_path, "S/RES/1", **{"resolution.txt": "the publisher's text"})
    body, source = build_jsonl.read_body(str(d), "resolution.txt", "resolution-ocr.txt")
    assert body == "the publisher's text"
    assert source == "pdf"


def test_ocr_is_used_when_there_is_no_embedded_text(tmp_path):
    d = make(tmp_path, "A/1251", **{"resolution-ocr.txt": "read from the image"})
    body, source = build_jsonl.read_body(str(d), "resolution.txt", "resolution-ocr.txt")
    assert body == "read from the image"
    assert source == "ocr"


def test_embedded_text_wins_when_both_exist(tmp_path):
    """Not a case that should arise, but the answer should not depend on luck."""
    d = make(tmp_path, "S/RES/2", **{"resolution.txt": "embedded",
                                     "resolution-ocr.txt": "scanned"})
    body, source = build_jsonl.read_body(str(d), "resolution.txt", "resolution-ocr.txt")
    assert (body, source) == ("embedded", "pdf")


def test_a_document_with_neither_yields_nothing(tmp_path):
    d = make(tmp_path, "S/RES/3")
    assert build_jsonl.read_body(str(d), "resolution.txt", "resolution-ocr.txt") == (None, None)


def test_the_published_columns_match_what_the_builder_writes():
    """The card described text_source as a column while the table lacked it.

    publish.py names its columns in a list of its own, so a field added to the
    record is silently dropped unless that list is changed too.
    """
    import importlib.util
    here = os.path.dirname(__file__)
    spec = importlib.util.spec_from_file_location(
        "publish", os.path.join(here, "..", "scripts", "publish.py"))
    publish = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(publish)
    published = set(publish.STRING_FIELDS) | set(publish.INT_FIELDS)
    written = {"id", "lang", "body", "n_chars", "text_source", "pdf"}
    written |= {f"date_{k}{suffix}" for k in build_jsonl.DATE_KINDS
                for suffix in ("", "_rule", "_raw")}
    assert written <= published, f"not published: {written - published}"
