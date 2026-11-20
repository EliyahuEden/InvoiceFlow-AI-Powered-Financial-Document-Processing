"""Layout-tolerant rule-based extraction: rules that do not depend on a template's labels
or column order. The texts below are invented for these tests (their labels are deliberately
not in the extractor's lexicon); they are not taken from the benchmark's held-out layouts."""
from __future__ import annotations

from decimal import Decimal

from app.services.extraction import rule_based


def _x(text: str, exclude: set[str] | None = None):
    return rule_based.extract([(1, text)], exclude or {"520000019"})


def _rows(ex):
    return [(ln.description, ln.sku, ln.quantity, ln.unit_price, ln.line_total) for ln in ex.line_items]


def test_rows_with_quantity_first_are_read_by_arithmetic():
    ex = _x("Acme Widgets Ltd\n"
            "Units  Part  Article  Each  Sum\n"
            "3 AC-BOLT-9  Steel bolt M8  2.50  7.50\n"
            "10 AC-NUT-2  Hex nut  0.40  4.00\n")
    assert _rows(ex) == [("Steel bolt M8", "AC-BOLT-9", "3", "2.50", "7.50"),
                         ("Hex nut", "AC-NUT-2", "10", "0.40", "4.00")]


def test_price_before_quantity_is_not_swapped():
    # columns: description, price, quantity, total: the 2-decimal money value is the price
    ex = _x("Acme Widgets Ltd\n"
            "Article  Each  Units  Sum\n"
            "Copper wire 2mm  12.90  4  51.60\n")
    assert _rows(ex) == [("Copper wire 2mm", None, "4", "12.90", "51.60")]


def test_numbers_inside_descriptions_are_kept_in_the_description():
    ex = _x("Acme Widgets Ltd\n"
            "Article  Each  Units  Sum\n"
            "Tape 48 mm roll  6.90  40  276.00\n")
    assert _rows(ex) == [("Tape 48 mm roll", None, "40", "6.90", "276.00")]


def test_totals_found_by_arithmetic_when_labels_are_unknown():
    ex = _x("Acme Widgets Ltd\n"
            "Units  Part  Article  Each  Sum\n"
            "3 AC-BOLT-9  Steel bolt M8  2.50  7.50\n"
            "10 AC-NUT-2  Hex nut  0.40  4.00\n"
            "Goods value  11.50\n"
            "Levy 18%  2.07\n"
            "Please remit  13.57\n")
    assert (ex.subtotal.value, ex.tax_amount.value, ex.total.value) == ("11.50", "2.07", "13.57")
    assert ex.tax_rate.value == "18%"


def test_inconsistent_labelled_totals_are_corrected_by_arithmetic():
    # "Total" inside "Net Total" must not win over the real grand total
    ex = _x("Acme Widgets Ltd\n"
            "Units  Part  Article  Each  Sum\n"
            "4 AC-PIN-1  Pin  5.00  20.00\n"
            "Net Total  20.00\n"
            "VAT 17%  3.40\n"
            "BALANCE OWING  23.40\n")
    assert (ex.subtotal.value, ex.tax_amount.value, ex.total.value) == ("20.00", "3.40", "23.40")


def test_po_number_is_self_identifying():
    ex = _x("Acme Widgets Ltd\nOur file: PO-2026-2609\n")
    assert ex.po_reference.value == "PO-2026-2609"


def test_supplier_name_is_the_company_segment_not_the_document_title():
    assert _x("Acme Widgets Ltd  STATEMENT OF CHARGES\n").supplier_name.value == "Acme Widgets Ltd"
    assert _x('נגב תאורה בע"מ  מסמך לתשלום\n').supplier_name.value == 'נגב תאורה בע"מ'


def test_unlabelled_nine_digit_tax_id_in_header_is_used_but_not_the_customers():
    ex = _x("Acme Widgets Ltd\nRegistry 514000221\nCustomer: Kinneret, 520000019\n")
    assert ex.supplier_tax_id.value == "514000221"
    assert _x("Acme Widgets Ltd\nCustomer: Kinneret 520000019\n").supplier_tax_id.value is None


def test_unlabelled_document_number_and_date_fall_back_to_the_header():
    ex = _x("Acme Widgets Ltd  AW-48213\nWritten 14/07/2026\nCustomer: Kinneret\n")
    assert ex.invoice_number.value == "AW-48213"
    assert ex.invoice_date.value == "14/07/2026"


def test_known_layout_still_uses_its_labels():
    ex = _x("Acme Widgets Ltd  Invoice No: AW-1\nInvoice Date: 01/02/2026\nDue Date: 01/03/2026\n"
            "SKU  Description  Qty  Unit Price  Amount\n"
            "AC-PIN-1  Pin  4  5.00  20.00\n"
            "Subtotal  20.00\nVAT 18%  3.60\nTotal Due  23.60\n")
    assert ex.invoice_number.value == "AW-1" and ex.invoice_date.value == "01/02/2026"
    assert (ex.subtotal.value, ex.tax_amount.value, ex.total.value) == ("20.00", "3.60", "23.60")
    assert _rows(ex) == [("Pin", "AC-PIN-1", "4", "5.00", "20.00")]
    assert ex.subtotal.value == str(Decimal("20.00"))
