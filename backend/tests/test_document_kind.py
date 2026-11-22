"""Telling supplier invoices apart from other documents that reach accounts payable.
All texts are invented look-alikes; no real document is used."""
from __future__ import annotations

import pytest

from app.services.documents.classify import classify_document


@pytest.mark.parametrize("text", [
    "חשבונית מס 1042\nכרמל שירותי ניקיון בע\"מ\nע.מ 514000005",
    "חשבונית מס קבלה מספר 88\nמכולת השכונה",
    "חשבונית מס/קבלה 77",
    "TAX INVOICE\nBlueWave IT Solutions Ltd\nInvoice No. BW-2026-0412",
    "Invoice\nStatement of services for August\nArava Packaging",  # an invoice styled as a statement
    "ACME Ltd\nInvoice # 5521\nBill to: Kinneret Hospitality",
    "חשבונית מס 3001\nהזמנה מספר 4410",  # invoices often print the order number too
])
def test_invoices_are_invoices(text):
    assert classify_document(text) is None


@pytest.mark.parametrize(("text", "kind", "phrase"), [
    ("אישור הזמנה\nמלון חוף הים\nתאריך הגעה 12/08/2026", "order_confirmation", "אישור הזמנה"),
    ("Booking Confirmation\nSeaside Hotel\nCheck-in: 12 Aug 2026", "order_confirmation", "Booking Confirmation"),
    ("Order confirmation #A-7731\nThank you for your order", "order_confirmation", "Order confirmation"),
    # an online-store order printout: an order number and no invoice title anywhere in the header
    ("חנות אלקטרוניקה בע\"מ\nהזמנה מספר - מס' 2010001234  העתק\nתאריך הזמנה 02/11/2026", "order_confirmation",
     "הזמנה מספר"),
    ("הצעת מחיר מס' 301\nתוקף ההצעה 30 יום", "quote", "הצעת מחיר"),
    ("QUOTATION\nValid for 30 days", "quote", "QUOTATION"),
    ("חשבון עסקה 2210\nלתשלום עד 30/09/2026", "proforma", "חשבון עסקה"),
    ("קבלה מס' 555\nהתקבל תשלום במזומן", "receipt", "קבלה"),
    ("RECEIPT\nPayment received, thank you", "receipt", "RECEIPT"),
    ("חשבונית זיכוי 19\nזיכוי בגין החזרה", "credit_note", "חשבונית זיכוי"),
    ("CREDIT NOTE CN-44\nRefund for returned goods", "credit_note", "CREDIT NOTE"),
    ("תעודת משלוח 9001\nנמסר ל: מחסן ראשי", "delivery_note", "תעודת משלוח"),
    ("רשימון יבוא\nמכס אשדוד", "customs_declaration", "רשימון"),
    ("כרטסת הנהלת חשבונות\nיתרה לתשלום", "statement", "כרטסת"),
])
def test_other_documents_are_recognised(text, kind, phrase):
    assert classify_document(text) == (kind, phrase)


def test_only_the_header_decides():
    body = "\n".join(f"שורה {i}" for i in range(30))
    assert classify_document("חשבונית מס 5\n" + body + "\nהצעת מחיר קודמת בוטלה") is None


def test_empty_text_is_unknown_not_flagged():
    assert classify_document("") is None
