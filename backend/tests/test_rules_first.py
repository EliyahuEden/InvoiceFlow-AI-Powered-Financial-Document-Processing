"""Rules-first extraction: the free rule-based extractor runs on every invoice and the LLM is
asked only for the fields the rules could not find or that do not add up. A fake LLM is used
here, so these tests never call a paid model."""
from __future__ import annotations

from decimal import Decimal

import pytest

from app.services.documents.text_extraction import PageText
from app.services.extraction.hybrid import extract_rules_first, find_gaps
from app.services.extraction.postprocess import normalize
from app.services.extraction.schema import ExtractedField, ExtractedLine, InvoiceExtraction
from app.services.llm.provider import LLMResult

TEXT = """Acme Supplies Ltd
VAT No. 514000005
Doc ref INV-7781
Date: 05/03/2026
Widget A  2  50.00  100.00
Subtotal 100.00
VAT 18% 18.00
Total ILS 118.00"""
PAGES = [PageText(page_no=1, width=600, height=800, method="native", text=TEXT, words=[])]
ROW = "Widget A  2  50.00  100.00"


def f(value: str | None) -> ExtractedField:
    return ExtractedField(value=value, source_text=value, page=1 if value else None)


def rules(**overrides) -> InvoiceExtraction:
    base = dict(
        supplier_name=f("Acme Supplies Ltd"), supplier_tax_id=f("514000005"), invoice_number=f("INV-7781"),
        invoice_date=f("05/03/2026"), currency=f("ILS"), subtotal=f("100.00"), tax_rate=f("18%"),
        tax_amount=f("18.00"), total=f("118.00"),
        line_items=[ExtractedLine(description="Widget A", quantity="2", unit_price="50.00", line_total="100.00",
                                  source_text=ROW, page=1)],
    )
    base.update(overrides)
    return InvoiceExtraction(**base)


class FakeLLM:
    name, model = "fake", "fake-model"

    def __init__(self, data: dict | None = None, error: Exception | None = None) -> None:
        self.data, self.error, self.calls = data or {}, error, []

    def structured(self, **kw) -> LLMResult:  # noqa: ANN003
        self.calls.append(kw)
        if self.error:
            raise self.error
        return LLMResult(self.name, self.model, 5, 100, 20, data=self.data)


def test_complete_and_consistent_invoice_never_calls_the_llm():
    llm = FakeLLM()
    out = extract_rules_first(llm, PAGES, rules())
    assert llm.calls == []
    assert out.gaps == [] and out.filled == []
    assert out.method == "rule_based"
    assert out.extraction == rules()


def test_missing_field_is_requested_alone_and_merged_into_the_rules_result():
    llm = FakeLLM({"invoice_number": {"value": "INV-7781", "source_text": "Doc ref INV-7781", "page": 1}})
    out = extract_rules_first(llm, PAGES, rules(invoice_number=f(None)))
    assert len(llm.calls) == 1
    assert list(llm.calls[0]["schema"]["properties"]) == ["invoice_number"]  # only the gap is asked for
    assert "invoice_number" in llm.calls[0]["system"] or "invoice_number" in str(llm.calls[0]["content"])
    assert out.gaps == ["invoice_number"] and out.filled == ["invoice_number"]
    assert out.extraction.invoice_number.value == "INV-7781"
    assert out.extraction.total.value == "118.00"  # fields the rules got are kept
    assert out.method == "rules+llm:fake-model"
    assert out.llm_result is not None


def test_value_not_printed_in_the_document_is_rejected():
    llm = FakeLLM({"invoice_number": {"value": "INV-9999", "source_text": "INV-9999", "page": 1}})
    out = extract_rules_first(llm, PAGES, rules(invoice_number=f(None)))
    assert out.filled == []
    assert out.extraction.invoice_number.value is None
    assert out.method == "rule_based"


def test_llm_failure_keeps_the_rules_result():
    out = extract_rules_first(FakeLLM(error=TimeoutError("slow model")), PAGES, rules(invoice_number=f(None)))
    assert out.extraction == rules(invoice_number=f(None))
    assert out.method == "rule_based"
    assert "slow model" in (out.error or "")


def test_totals_that_do_not_add_up_ask_for_the_totals_and_accept_a_consistent_answer():
    llm = FakeLLM({"subtotal": {"value": "100.00"}, "tax_amount": {"value": "18.00"}, "total": {"value": "118.00"}})
    out = extract_rules_first(llm, PAGES, rules(total=f("100.00")))  # rules took the subtotal as total
    assert set(out.gaps) >= {"subtotal", "tax_amount", "total"}
    assert out.filled == ["total"]
    assert normalize(out.extraction, PAGES, "x").total == Decimal("118.00")


def test_answer_that_makes_the_invoice_less_consistent_is_discarded():
    llm = FakeLLM({"line_items": [{"description": "Widget A", "quantity": "2", "unit_price": "50.00",
                                   "line_total": "18.00", "source_text": ROW, "page": 1}]})
    before = rules(line_items=[])
    out = extract_rules_first(llm, PAGES, before)
    assert out.gaps == ["line_items"]
    assert out.extraction == before and out.filled == []


def test_missing_line_items_are_filled():
    llm = FakeLLM({"line_items": [{"description": "Widget A", "quantity": "2", "unit_price": "50.00",
                                   "line_total": "100.00", "source_text": ROW, "page": 1}]})
    out = extract_rules_first(llm, PAGES, rules(line_items=[]))
    assert out.filled == ["line_items"]
    assert len(out.extraction.line_items) == 1


@pytest.mark.parametrize(("overrides", "expected"), [
    ({}, []),
    # a missing currency alone is not worth a call: it is often not printed, or lost by OCR, and a
    # text-only model cannot recover it (measured on the benchmark: 0 of 12 such calls helped)
    ({"supplier_name": f(None), "currency": f(None)}, ["supplier_name"]),
    ({"currency": f(None)}, []),
    ({"line_items": []}, ["line_items"]),
    ({"total": f("100.00")}, ["subtotal", "tax_amount", "total"]),
    ({"tax_rate": f("2")}, ["tax_rate", "tax_amount"]),
    ({"invoice_number": f("INV-0000")}, ["invoice_number"]),  # not printed: discarded, so it is a gap
    # a total nothing can confirm (no subtotal + VAT, lines do not sum to it) is a gap
    ({"subtotal": f(None), "tax_amount": f(None)}, ["subtotal", "tax_amount", "total"]),
    # ...but subtotal × (1 + rate) or VAT-inclusive lines confirm it
    ({"tax_amount": f(None)}, []),
    ({"subtotal": f(None), "tax_amount": f(None), "line_items": [ExtractedLine(
        description="Widget A", quantity="1", unit_price="118.00", line_total="118.00", source_text="Total ILS 118.00",
        page=1)]}, []),
])
def test_find_gaps(overrides, expected):
    assert find_gaps(normalize(rules(**overrides), PAGES, "rule_based")) == expected


def test_pipeline_defaults_to_rules_first():
    from app.core.config import Settings

    assert Settings().extraction_mode == "rules_first"


def test_pipeline_rules_first_skips_the_llm_for_a_clean_invoice(monkeypatch):
    from app.services import processing

    monkeypatch.setattr(processing.rule_based, "extract", lambda *a, **k: rules())
    llm = FakeLLM()
    ex, method, calls = processing.choose_extraction(llm, PAGES, b"", "application/pdf", set(), "rules_first")
    assert llm.calls == [] and method == "rule_based" and ex == rules()
    assert [c["model"] for c in calls] == ["rule-based-extractor"]


def test_pipeline_rules_first_records_the_targeted_llm_call(monkeypatch):
    from app.services import processing

    monkeypatch.setattr(processing.rule_based, "extract", lambda *a, **k: rules(invoice_number=f(None)))
    llm = FakeLLM({"invoice_number": {"value": "INV-7781"}})
    ex, method, calls = processing.choose_extraction(llm, PAGES, b"", "application/pdf", set(), "rules_first")
    assert method == "rules+llm:fake-model" and ex.invoice_number.value == "INV-7781"
    llm_call = calls[-1]
    assert llm_call["prompt_version"] == "extract-v3-fields"
    assert llm_call["meta"]["gaps"] == ["invoice_number"] and llm_call["meta"]["filled"] == ["invoice_number"]


def test_pipeline_llm_first_still_sends_the_whole_invoice(monkeypatch):
    from app.services import processing

    monkeypatch.setattr(processing, "page_images_for_ocr_pages", lambda *a, **k: [])
    llm = FakeLLM(rules().model_dump())
    ex, method, _ = processing.choose_extraction(llm, PAGES, b"", "application/pdf", set(), "llm_first")
    assert len(llm.calls) == 1 and "line_items" in llm.calls[0]["schema"]["properties"]
    assert method == "llm:fake-model"


def test_llm_output_token_cap_is_configurable(monkeypatch):
    from app.core.config import get_settings
    from app.services.extraction.llm_extractor import extract_with_llm

    monkeypatch.setenv("LLM_MAX_OUTPUT_TOKENS", "3000")
    get_settings.cache_clear()
    try:
        llm = FakeLLM({"invoice_number": {"value": "INV-7781"}})
        extract_with_llm(llm, PAGES, fields=["invoice_number"])
        assert llm.calls[0]["max_tokens"] == 3000
    finally:
        get_settings.cache_clear()


def test_provider_json_validation_error_is_retried_once():
    class Flaky(FakeLLM):
        def structured(self, **kw):  # noqa: ANN003
            self.calls.append(kw)
            if len(self.calls) == 1:
                raise RuntimeError("Error code: 400 - {'error': {'code': 'json_validate_failed'}}")
            return LLMResult(self.name, self.model, 5, 100, 20, data=self.data)

    from app.services.extraction.llm_extractor import extract_with_llm

    llm = Flaky({"invoice_number": {"value": "INV-7781"}})
    ex, _, retries = extract_with_llm(llm, PAGES, fields=["invoice_number"])
    assert ex.invoice_number.value == "INV-7781" and retries == 1 and len(llm.calls) == 2
