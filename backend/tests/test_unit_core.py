"""Pure unit tests: money arithmetic, parsing, Hebrew bidi handling, upload validation."""
from __future__ import annotations

import io
from datetime import date
from decimal import Decimal

import pytest

from app.core.money import D, detect_currency, parse_amount, round_money, within_tolerance
from app.services.documents.hebrew import detect_language, segment_direction, visual_to_logical
from app.services.documents.validation import UploadRejected, validate_upload
from app.services.extraction.parsing import parse_date, parse_percent, parse_tax_id


@pytest.mark.parametrize("raw,expected", [
    ("1,234.56", "1234.56"), ("1.234,56", "1234.56"), ("₪ 7,633.42", "7633.42"), ("(12.00)", "-12.00"),
    ("12,5", "12.5"), ("1,234", "1234"), ("$3,455.04", "3455.04"), ("10903.20₪", "10903.20"), ("-50", "-50"),
    ("abc", None), ("", None), (None, None),
])
def test_parse_amount(raw, expected):
    v = parse_amount(raw)
    assert (v is None and expected is None) or v == Decimal(expected)


def test_money_rejects_float_and_rounds_half_up():
    with pytest.raises(TypeError):
        D(0.1)
    assert round_money(Decimal("2.345")) == Decimal("2.35")
    assert D("0.1") + D("0.2") == Decimal("0.3")  # exact, unlike float


def test_tolerance_is_max_of_abs_and_pct():
    assert within_tolerance(Decimal("100"), Decimal("100.90"), Decimal("0.05"), Decimal("1"))
    assert not within_tolerance(Decimal("100"), Decimal("101.01"), Decimal("0.05"), Decimal("1"))
    assert within_tolerance(Decimal("2"), Decimal("2.05"), Decimal("0.05"), Decimal("1"))  # abs floor wins


def test_detect_currency():
    assert detect_currency("סה\"כ ₪ 100") == "ILS"
    assert detect_currency("Total $5") == "USD"
    assert detect_currency("100 ש\"ח") == "ILS"


@pytest.mark.parametrize("raw,expected", [
    ("09/09/2026", date(2026, 9, 9)), ("11.09.2026", date(2026, 9, 11)), ("09/09/26", date(2026, 9, 9)),
    ("2026-09-16", date(2026, 9, 16)), ("16 Sep 2026", date(2026, 9, 16)), ("16 בספטמבר 2026", date(2026, 9, 16)),
    ("31/02/2026", None), ("tomorrow", None),
])
def test_parse_date(raw, expected):
    assert parse_date(raw) == expected


def test_parse_tax_id_and_percent():
    assert parse_tax_id("51-400012-7") == "514000127"
    assert parse_tax_id("12") is None
    assert parse_percent("מע\"מ 18%") == Decimal("18")


def test_visual_to_logical_hebrew_with_numbers_and_brackets():
    # Visual order (as drawn): reversed Hebrew, numbers left-to-right, mirrored brackets.
    logical = "פולי קפה (ארגז 1000) 60 118.00"
    from bidi import get_display

    from app.services.documents.hebrew import MIRROR

    visual = get_display(logical, base_dir="R").translate(MIRROR)
    assert visual != logical
    assert visual_to_logical(visual, "R") == logical


def test_segment_direction_and_language():
    assert segment_direction("םולש", "L") == "R"
    assert segment_direction("Invoice No: 123", "R") == "L"
    assert detect_language("חשבונית מס מספר") == "he"
    assert detect_language("Tax invoice number") == "en"
    assert detect_language("חשבונית Invoice number total מס") == "mixed"


def test_upload_validation_rejects_bad_files():
    with pytest.raises(UploadRejected):
        validate_upload(b"", "x.pdf")
    with pytest.raises(UploadRejected, match="Unsupported"):
        validate_upload(b"MZ\x90\x00 this is an exe", "invoice.pdf")  # extension lies
    with pytest.raises(UploadRejected, match="damaged"):
        validate_upload(b"%PDF-1.7\n garbage", "broken.pdf")


def test_upload_validation_accepts_png_and_checks_size(monkeypatch):
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (40, 20), "white").save(buf, "PNG")
    vf = validate_upload(buf.getvalue(), "../../etc/passwd.png")
    assert vf.mime_type == "image/png" and "/" not in vf.safe_filename and ".." not in vf.safe_filename.split(".")[0]
    from app.core import config

    monkeypatch.setattr(config.get_settings(), "max_upload_bytes", 10)
    with pytest.raises(UploadRejected, match="limit"):
        validate_upload(buf.getvalue(), "big.png")


def test_upload_validation_page_limit(monkeypatch):
    from app.core import config
    from app.demo.render import render_invoice_pdf
    from app.demo.spec import INVOICES

    pdf = render_invoice_pdf(INVOICES[11])  # two pages
    monkeypatch.setattr(config.get_settings(), "max_pdf_pages", 1)
    with pytest.raises(UploadRejected, match="pages"):
        validate_upload(pdf, "multi.pdf")
