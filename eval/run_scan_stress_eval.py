"""Score 24 reproducible synthetic invoice scans using the existing rule-based evaluator.

Run inside the backend image for Tesseract Hebrew and English and the demo fonts.
"""
from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

from PIL import Image, ImageDraw

from common import write_result
from app.demo import render
from app.demo.generate import invoice_truth
from app.demo.spec import INVOICES, SUPPLIERS_BY_KEY
from app.services.documents.text_extraction import tesseract_available
from run_extraction_eval import FIELDS, run

SOURCE_KEYS = (
    "01_correct_tavor_he", "02_qty_mismatch_hermon_he", "03_price_mismatch_bluewave_en",
    "05_missing_po_arava_mixed", "06_ambiguous_desc_carmel_he", "10_missing_receipt_bluewave_en",
)
VARIANTS = ("skewed", "photo", "stamped", "low_contrast")


def write_variant(pdf: bytes, page: Image.Image, target: Path, variant: str, index: int) -> None:
    if variant == "photo":
        target.write_bytes(render.render_photo_png(pdf, seed=20261123 + index))
        return
    if variant == "skewed":
        angle = (2.0 + 0.5 * index) * (-1 if index % 2 else 1)
        page = page.rotate(angle, resample=Image.Resampling.BICUBIC, expand=True, fillcolor=255)
    elif variant == "stamped":
        page = page.convert("RGB")
        mark = ImageDraw.Draw(page, "RGBA")
        x, y = round(page.width * 0.35), round(page.height * 0.16)
        mark.rounded_rectangle((x, y, x + 270, y + 65), radius=10, outline=(150, 16, 32, 115), width=5)
        mark.text((x + 25, y + 20), "RECEIVED", fill=(150, 16, 32, 115), font_size=26)
    elif variant == "low_contrast":
        page = page.point(lambda shade: round(151 + shade * 0.23))
    page.save(target, "PNG")


def main() -> None:
    if not tesseract_available():
        raise SystemExit("Tesseract is required. Run inside the InvoiceFlow backend image.")
    invoices = {invoice.key: invoice for invoice in INVOICES}
    groups: dict[str, list[dict]] = {variant: [] for variant in VARIANTS}
    with TemporaryDirectory(prefix="invoiceflow-scan-stress-") as directory:
        dataset = Path(directory)
        for index, key in enumerate(SOURCE_KEYS):
            invoice = invoices[key]
            pdf = render.render_invoice_pdf(invoice)
            (page,) = render._render_pages(pdf, 200)
            for variant in VARIANTS:
                target = dataset / f"{key}-{variant}.png"
                write_variant(pdf, page, target, variant, index)
                groups[variant].append({"file": target.name, "render": variant, "template": invoice.template,
                                        "language": SUPPLIERS_BY_KEY[invoice.supplier].lang,
                                        "held_out_template": False, "truth": invoice_truth(invoice)})
        results = {variant: run("rule_based", rows, False, dataset_dir=dataset) for variant, rows in groups.items()}
    if any(result["documents_skipped"] for result in results.values()):
        raise SystemExit("OCR did not evaluate all generated invoices.")
    for variant, result in results.items():
        print(f"{variant}: {result['documents_evaluated']} invoices, {result['overall_field_accuracy']:.1%} field accuracy")
    path = write_result("scan_stress", {"documents": sum(map(len, groups.values())), "source_invoices": SOURCE_KEYS,
                                        "fields": FIELDS, "method": "rules only; Tesseract heb+eng",
                                        "variants": {name: {key: result[key] for key in (
                                            "documents_evaluated", "overall_field_accuracy", "per_field",
                                            "line_items", "error_examples")}
                                            for name, result in results.items()}})
    print(path)


if __name__ == "__main__":
    main()
