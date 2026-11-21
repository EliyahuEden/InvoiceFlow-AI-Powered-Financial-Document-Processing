"""Layout patterns seen on real Israeli invoices and receipts (titles that carry the number,
two-row headers, dates on the customer line, branch-numbered supplier names, placeholder tax
IDs, VAT-free receipts). Every company, person and number here is invented."""
from __future__ import annotations

import pytest

from app.services.extraction import rule_based
from app.services.extraction.rule_based import israeli_id_valid


def _x(text: str):
    return rule_based.extract([(1, text)], {"520000019"})


@pytest.mark.parametrize("title,number", [
    ("חשבונית מס קבלה 65326 (מקור)", "65326"),
    ("חשבונית מס/קבלה 2000720", "2000720"),
    ("חשבונית מס/קבלה: 51-52392", "51-52392"),
    ("חשבונית מס קבלה מספר 216024249  מקור", "216024249"),
    ("חשבונית מס-קבלה #4417", "4417"),
])
def test_invoice_number_printed_after_the_document_title(title, number):
    ex = _x(f'גל שירותים בע"מ\nח.פ 514720135\nלכבוד: ישראל ישראלי\n{title}\nסה"כ לתשלום  ₪100.00\n')
    assert ex.invoice_number.value == number


def test_two_row_header_values_sit_under_their_labels():
    ex = _x('חשבונית מס קבלה\nמס\' עוסק מורשה: 514720135\nמספר חשבונית מס  תאריך\n6824159  18/03/25\nמקור\n')
    assert ex.invoice_number.value == "6824159"
    assert ex.invoice_date.value == "18/03/25"


def test_date_on_the_customer_line_is_read():
    ex = _x('גל שירותים בע"מ\nח.פ 514720135\nלכבוד:  06/11/2026\nישראל ישראלי\nחשבונית מס קבלה 120\n')
    assert ex.invoice_date.value == "06/11/2026"


def test_supplier_name_skips_document_titles_and_finds_the_company_lower_down():
    ex = _x('מסמך ממוחשב\nחשבונית מס קבלה 65326 (מקור)\nעוסק מורשה/ח.פ.:  514720135\nגל ספורט בע"מ  תאריך:  11/03/2025\n')
    assert ex.supplier_name.value == 'גל ספורט בע"מ'


def test_supplier_name_drops_a_leading_branch_number_and_stray_punctuation():
    assert _x('57 גל אקספרס בע"מ\nלכבוד: ישראל ישראלי\n').supplier_name.value == 'גל אקספרס בע"מ'
    assert _x('.Orbit Labs Ltd\nלכבוד: ישראל ישראלי\n').supplier_name.value == "Orbit Labs Ltd"


def test_registered_nonprofit_suffix_counts_as_a_company():
    assert _x('המרכז הקהילתי גל ע"ר  מספר ע"ר\n580123453\n').supplier_name.value == 'המרכז הקהילתי גל ע"ר'


def test_israeli_id_check_digit():
    assert israeli_id_valid("514720135") and israeli_id_valid("516900214")
    assert not israeli_id_valid("097495777") and not israeli_id_valid("000000000")


def test_placeholder_tax_id_is_skipped():
    ex = _x('גל אקספרס בע"מ\nח.פ  000000000  ח.פ./ע.מ.:  513884205\n')
    assert ex.supplier_tax_id.value == "513884205"


def test_a_valid_company_number_is_preferred_over_other_nine_digit_numbers():
    ex = _x('חניון גל\n097495777\nחברה בע"מ 516900214\nלכבוד: ישראל ישראלי\n')
    assert ex.supplier_tax_id.value == "516900214"


def test_amounts_followed_by_a_currency_word_and_taxable_subtotal_label():
    ex = _x('גל הפצה בע"מ\nח.פ 514720135\nחשבונית מס # 1015796 - מקור\n'
            'סכום חייב במע"מ  254.07 ש"ח\n18% מע"מ  45.73 ש"ח\nסה"כ  299.80 ש"ח\n')
    assert (ex.subtotal.value, ex.tax_amount.value, ex.total.value) == ("254.07", "45.73", "299.80")


def test_receipt_without_vat_uses_its_only_total():
    ex = _x('המרכז הקהילתי גל ע"ר\nקבלה  1 / 407895  מקור  31/10/2025\nסה"כ  10,552.00\n')
    assert ex.total.value == "10,552.00" and ex.tax_amount.value is None


def test_single_quantity_rows_without_a_unit_price_column():
    ex = _x('גל שירותים בע"מ\nח.פ 514720135\nמוצר/שירות  כמות  סה"כ\nהתקנת מוצר על ידי טכנאי מוסמך  1  ₪211.87\n'
            'סה"כ ללא מע"מ  ₪211.87\n18% מע"מ  ₪38.14\nסה"כ לתשלום  ₪250.01\n')
    rows = [(ln.description, ln.quantity, ln.unit_price, ln.line_total) for ln in ex.line_items]
    assert rows == [("התקנת מוצר על ידי טכנאי מוסמך", "1", "211.87", "211.87")]


def test_a_two_line_table_header_does_not_end_the_table():
    ex = _x('גל אקספרס בע"מ\n#  תיאור  כמות  מחיר  סה"כ\nמע"מ\n1  ערכת בנייה לילדים  2  ₪ 50.00  ₪ 100.00\n'
            'סה"כ לפני מע"מ  ₪ 100.00\nמע"מ 18%  ₪ 18.00\nסה"כ לתשלום  ₪ 118.00\n')
    assert [(ln.quantity, ln.unit_price, ln.line_total) for ln in ex.line_items] == [("2", "50.00", "100.00")]


def test_total_with_one_decimal_is_found_by_arithmetic():
    ex = _x('גל הפצה בע"מ\nח.פ 514720135\n#  תיאור  כמות  מחיר  סה"כ\n1  אבקה  1.00  237.2  237.2\n'
            'סכום חייב במע"מ  237.20 ש"ח\n18% מע"מ  42.70 ש"ח\nסה"כ  279.9 ש"ח\n')
    assert ex.total.value == "279.9"


def test_totals_found_even_when_line_items_are_unreadable():
    ex = _x('Orbit Labs Ltd\nחברה בע"מ 514720135\nקוד  תאור  כמות  מחיר  סה"כ\n210  סדרת טיפולים  300.00 10.00  ₪3,000.00\n'
            'סה"כ ₪3,000.00\nחייב במע"מ ₪2,542.37\nמע"מ נגבה 18.00% ₪457.63\nסה"כ שקל ₪3,000.00\n')
    assert (ex.subtotal.value, ex.tax_amount.value, ex.total.value) == ("₪2,542.37".lstrip("₪"), "457.63", "3,000.00")


def test_a_customers_personal_id_is_not_the_supplier_tax_id():
    ex = _x('אישור הזמנה ממלון גל\nשם פרטי: ישראל  שם משפחה: ישראלי\nתעודת זהות: 513884205\n')
    assert ex.supplier_tax_id.value is None


def test_supplier_name_sharing_the_line_with_the_document_title():
    assert _x('גל שירותים  חשבונית מס\nרחוב הדקל 5, חיפה  חשבונית מס GL-0091\nלקוח: ישראל ישראלי\n').supplier_name.value == "גל שירותים"
