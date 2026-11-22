"""Input the database cannot store or count must be refused with a clear 4xx, never a 500 (found by
tests/test_fuzz_api.py): NUL characters in text, and page numbers past what an offset can hold."""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("url", ["/api/invoices?q=a%00b", "/api/suppliers?q=%00", "/api/purchase-orders?status=a%00",
                                 "/api/exceptions?q=x%00", "/api/audit?action=%00", "/api/review/queue?status=%00"])
def test_nul_in_query_is_refused(client, as_user, url):
    r = client.get(url, headers=as_user("admin@kinneret.example"))
    assert r.status_code == 422 and "NUL" in r.json()["detail"], (r.status_code, r.text[:200])


def test_nul_in_json_body_is_refused(client, as_user):
    h = {**as_user("admin@kinneret.example"), "X-Requested-With": "invoiceflow"}
    r = client.post("/api/suppliers", headers=h, json={"name": "a\u0000b"})
    assert r.status_code == 422 and "NUL" in r.json()["detail"]
    r = client.post("/api/copilot/ask", headers=h, json={"question": "hello\u0000there"})
    assert r.status_code == 422


def test_ordinary_text_still_passes(client, as_user):
    r = client.get("/api/invoices?q=" + "חשבונית 😀 ‮", headers=as_user("admin@kinneret.example"))
    assert r.status_code == 200


@pytest.mark.parametrize("page", [10**18, 10**7, -5, 0])
def test_page_numbers_are_bounded(client, as_user, page):
    r = client.get(f"/api/invoices?page={page}", headers=as_user("admin@kinneret.example"))
    assert r.status_code in (200, 422), r.text[:200]


def test_extracted_text_with_nul_bytes_is_cleaned():
    from app.services.documents.text_extraction import PageText, Word
    from app.services.processing import clean_pages

    pages = clean_pages([PageText(page_no=1, width=1, height=1, method="native", text="Tax\x00 Invoice",
                                  words=[Word(t="Tax\x00", b=[0, 0, 1, 1], l=0)])])
    assert pages[0].text == "Tax Invoice" and pages[0].words[0].t == "Tax"
