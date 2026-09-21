import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts", "extract"))
import ocr_pdf  # noqa: E402


def test_a_document_with_extracted_text_is_left_alone(tmp_path):
    d = tmp_path / "S" / "RES" / "1"
    d.mkdir(parents=True)
    (d / "resolution.pdf").write_bytes(b"%PDF")
    (d / "resolution.txt").write_text("text the publisher embedded")
    assert not ocr_pdf.needs_ocr(str(d / "resolution.pdf"), "resolution.txt", "resolution-ocr.txt")


def test_a_scan_is_picked_up(tmp_path):
    d = tmp_path / "A" / "1251"
    d.mkdir(parents=True)
    (d / "resolution.pdf").write_bytes(b"%PDF")
    assert ocr_pdf.needs_ocr(str(d / "resolution.pdf"), "resolution.txt", "resolution-ocr.txt")


def test_a_scan_already_read_is_not_read_again(tmp_path):
    d = tmp_path / "A" / "1251"
    d.mkdir(parents=True)
    (d / "resolution.pdf").write_bytes(b"%PDF")
    (d / "resolution-ocr.txt").write_text("already read")
    assert not ocr_pdf.needs_ocr(str(d / "resolution.pdf"), "resolution.txt", "resolution-ocr.txt")


def test_tidy_collapses_what_ocr_leaves():
    assert ocr_pdf.tidy("a   \nb\n\n\n\nc\n\n") == "a\nb\n\nc"
    assert ocr_pdf.tidy("\n\n\n") == ""
