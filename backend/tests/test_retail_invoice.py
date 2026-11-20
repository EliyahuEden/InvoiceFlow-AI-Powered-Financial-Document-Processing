"""A Hebrew retail (consumer-style) tax invoice: two-column header shared with the customer
block, VAT-inclusive line prices, a discount line, an ID number on a line that mentions VAT,
a header font missing a glyph, and the whole page printed twice. All details are fictional;
the layout mirrors a real invoice that exposed these problems."""
from __future__ import annotations

import uuid
from decimal import Decimal

from app.services.documents.pages import drop_duplicate_pages
from app.services.documents.text_extraction import PageText
from app.services.extraction import rule_based
from app.services.reconciliation import engine as E

PAGE = """נגב חשמל קמעואות בע"מ  מדווח לצורכי מע"מ באיחוד עוסקים:  557000001  ע.מ :  516000007
סניף: אינטרנט  רחוב הדקל 5 חולון  טלפון בסניף: 0730000000
מסמך ממוחשב- מקור  חשבונית מס  400000123
לכבוד  יעד אספקה
שם:  ישראל ישראלי  עבור:  ישראל ישראלי  תאריך חשבונית: 15/11/2026  04:00
כתובת: הדקל 3  כתובת:  הדקל  מספר הקצאה:
עיר:  חולון  מס' בית:  3  מס' הזמנה:  2010000001
טלפון: 0500000000  שכונה/אזור:  תאריך הזמנה:  02/11/2026
מספר לקוח: 300000001  עיר:  חולון  סוכן:
עוסק מורשה: 200000002  מיקוד:  הזמנת לקוח:  5010000001
מס' ת.משלוח  תאריך  מק"ט  תאור מוצר  כמות  מחיר  סה"כ בש"ח
ת.משלוח
470000001  12/11/2026  375515  מקרר מקפיא עליון 400 ליטר  1.00  1,950.00 1,950.00
470000001  12/11/2026  221587  הובלה והתקנה  1.00  150.01  150.01
סה"כ חייב מע"מ  1,796.61
סה"כ הנחה ועיגול  16.94
סה"כ אחרי הנחה  1,779.67
מע"מ 18.00%  320.34
=============================
סה"כ לחיוב  2,100.01
בכבוד רב,
נגב חשמל קמעונאות בע"מ
עמוד 1 מתוך 1"""


def _ex():
    return rule_based.extract([(1, PAGE)], {"520000019"})


def test_identical_second_page_is_dropped_before_extraction():
    pages = [PageText(1, 1, 1, "native", PAGE), PageText(2, 1, 1, "native", PAGE),
             PageText(3, 1, 1, "native", "תנאים כלליים ומידע נוסף")]
    kept, dropped = drop_duplicate_pages(pages)
    assert [p.page_no for p in kept] == [1, 3] and dropped == [2]


def test_near_identical_copy_with_different_page_label_is_also_dropped():
    copy = PAGE.replace("עמוד 1 מתוך 1", "עמוד 2 מתוך 2").replace("מקור", "העתק")
    kept, dropped = drop_duplicate_pages([PageText(1, 1, 1, "native", PAGE), PageText(2, 1, 1, "native", copy)])
    assert dropped == [2]


def test_totals_with_vat_inclusive_lines_and_a_discount():
    ex = _ex()
    assert (ex.subtotal.value, ex.discount_total.value, ex.tax_amount.value, ex.total.value) == \
           ("1,796.61", "16.94", "320.34", "2,100.01")
    assert ex.tax_rate.value == "18.00%"


def test_an_id_number_on_a_line_that_mentions_vat_is_not_the_vat_amount():
    assert _ex().tax_amount.value != "516000007"


def test_invoice_date_on_a_line_shared_with_the_customer_block():
    assert _ex().invoice_date.value == "15/11/2026"


def test_supplier_tax_id_comes_from_the_header_not_the_customer_block():
    assert _ex().supplier_tax_id.value == "516000007"


def test_supplier_name_avoids_the_spelling_with_a_missing_glyph():
    assert _ex().supplier_name.value == 'נגב חשמל קמעונאות בע"מ'


def test_line_descriptions_drop_leading_delivery_columns_and_keep_numeric_sku():
    rows = [(ln.description, ln.sku, ln.quantity, ln.unit_price, ln.line_total) for ln in _ex().line_items]
    assert rows == [("מקרר מקפיא עליון 400 ליטר", "375515", "1.00", "1,950.00", "1,950.00"),
                    ("הובלה והתקנה", "221587", "1.00", "150.01", "150.01")]


def _gross_invoice(po_price: Decimal) -> tuple[E.InvoiceData, E.Context]:
    s = uuid.uuid4()
    pl = E.POLineData(uuid.uuid4(), 1, "מקרר מקפיא עליון 400 ליטר", Decimal(1), po_price, "375515")
    po = E.POData(uuid.uuid4(), "PO-9", s, "ILS", "open", [pl])
    ctx = E.Context([E.SupplierData(s, 'נגב חשמל קמעונאות בע"מ', tax_id="516000007")], [po],
                    received={pl.id: Decimal(1)}, receipt_count={po.id: 1}, previously_invoiced={}, prior_invoices=[])
    inv = E.InvoiceData(uuid.uuid4(), 'נגב חשמל קמעונאות בע"מ', "516000007", "400000123", None, "ILS", "PO-9",
                        Decimal("1652.54"), Decimal("0"), Decimal("297.46"), Decimal("1950.00"),
                        [E.InvLine(uuid.uuid4(), 1, "מקרר מקפיא עליון 400 ליטר", "375515", Decimal(1),
                                   Decimal("1950.00"), Decimal(0), Decimal("1950.00"))])
    return inv, ctx


def test_vat_inclusive_lines_do_not_raise_a_subtotal_mismatch():
    inv, ctx = _gross_invoice(Decimal("1652.54"))
    types = {f.type for f in E.reconcile(inv, ctx).findings}
    assert "SUBTOTAL_MISMATCH" not in types


def test_vat_inclusive_prices_are_compared_net_with_the_purchase_order():
    inv, ctx = _gross_invoice(Decimal("1652.54"))  # PO is net: 1950.00 / 1.18
    assert "PRICE_MISMATCH" not in {f.type for f in E.reconcile(inv, ctx).findings}
    inv, ctx = _gross_invoice(Decimal("1500.00"))  # really overpriced
    assert "PRICE_MISMATCH" in {f.type for f in E.reconcile(inv, ctx).findings}


def test_extraction_checks_accept_vat_inclusive_lines():
    from app.services.extraction.postprocess import normalize

    page = PageText(1, 1, 1, "native", PAGE)
    issues = [i.code for i in normalize(_ex(), [page], "rule_based").issues]
    assert "SUBTOTAL_MISMATCH" not in issues and "TOTAL_MISMATCH" not in issues
