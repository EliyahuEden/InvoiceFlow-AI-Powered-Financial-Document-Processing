"""Field highlighting: a verified value gets a word-level box even when OCR words are not
in reading order or one value is split across OCR line groups."""
from __future__ import annotations

from app.services.documents.text_extraction import PageText, Word
from app.services.extraction.postprocess import _locate


def _page(text: str, words: list[Word]) -> list[PageText]:
    return [PageText(page_no=1, width=1, height=1, method="ocr", text=text, words=words)]


def test_rtl_words_listed_in_visual_order_still_get_a_box():
    # logical text "סה"כ לתשלום 1,180.00" but the OCR line lists words right-to-left visually reversed
    words = [Word("1,180.00", [0.1, 0.8, 0.2, 0.82], 5), Word("לתשלום", [0.6, 0.8, 0.7, 0.82], 5),
             Word('סה"כ', [0.72, 0.8, 0.8, 0.82], 5)]
    src = _locate("סה\"כ לתשלום", _page('סה"כ לתשלום 1,180.00', words), 1)
    assert src and src.bbox == [0.6, 0.8, 0.8, 0.82]


def test_value_split_across_ocr_line_groups_gets_a_union_box():
    # Tesseract put the two halves of an invoice number on different line indices
    words = [Word("Invoice", [0.1, 0.1, 0.2, 0.12], 0), Word("No.", [0.21, 0.1, 0.25, 0.12], 0),
             Word("AW-", [0.26, 0.1, 0.3, 0.12], 0), Word("48213", [0.3, 0.101, 0.36, 0.121], 1)]
    src = _locate("AW-48213", _page("Invoice No. AW-48213", words), 1)
    assert src and src.bbox == [0.26, 0.1, 0.36, 0.121]


def test_value_with_an_ocr_glitch_in_one_word_gets_a_box_on_the_best_line():
    # "Kinneret Hospitality Ltd" with one word misread; still mostly on one line
    words = [Word("Kinneret", [0.1, 0.3, 0.2, 0.32], 2), Word("Hospita1ity", [0.21, 0.3, 0.33, 0.32], 2),
             Word("Ltd", [0.34, 0.3, 0.38, 0.32], 2), Word("Total", [0.1, 0.9, 0.2, 0.92], 9)]
    src = _locate("Kinneret Hospitality Ltd", _page("Kinneret Hospitality Ltd\nTotal", words), 1)
    assert src is None or src.bbox is None  # value is not verbatim in the text: no false provenance
    src = _locate("Kinneret", _page("Kinneret Hospita1ity Ltd\nTotal", words), 1)
    assert src and src.bbox == [0.1, 0.3, 0.2, 0.32]


def test_line_item_falls_back_to_its_description_for_the_box():
    from app.services.extraction.postprocess import normalize
    from app.services.extraction.schema import ExtractedLine, InvoiceExtraction

    # OCR split the row's numbers into another line group, so the full row cannot be boxed
    words = [Word("Hex", [0.1, 0.5, 0.15, 0.52], 4), Word("nut", [0.16, 0.5, 0.2, 0.52], 4),
             Word("0.40", [0.7, 0.5, 0.75, 0.52], 7), Word("10", [0.6, 0.5, 0.62, 0.52], 3),
             Word("4.00", [0.8, 0.5, 0.85, 0.52], 7)]
    ex = InvoiceExtraction(line_items=[ExtractedLine(description="Hex nut", quantity="10", unit_price="0.40",
                                                     line_total="4.00", source_text="Hex nut 10 0.40 4.00", page=1)])
    n = normalize(ex, _page("Hex nut 10 0.40 4.00", words), "rule_based")
    assert n.lines[0].source.bbox == [0.1, 0.5, 0.2, 0.52]


def test_mixed_direction_description_is_boxed_by_its_tokens_on_one_line():
    # visual order of an RTL line with an LTR run: "מקורי HP 26A טונר" (the LTR run keeps its order)
    words = [Word("6", [0.3, 0.4, 0.32, 0.42], 3), Word("מקורי", [0.4, 0.4, 0.46, 0.42], 3),
             Word("HP", [0.47, 0.4, 0.5, 0.42], 3), Word("26A", [0.51, 0.4, 0.55, 0.42], 3),
             Word("טונר", [0.56, 0.4, 0.62, 0.42], 3), Word("טונר", [0.56, 0.9, 0.62, 0.92], 8)]
    src = _locate("טונר HP 26A מקורי", _page("טונר HP 26A מקורי  6", words), 1)
    assert src and src.bbox == [0.4, 0.4, 0.62, 0.42]
