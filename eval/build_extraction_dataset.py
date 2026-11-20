"""Build the labelled extraction dataset (synthetic, seeded, reproducible).

    backend/.venv/Scripts/python eval/build_extraction_dataset.py

Writes eval/datasets/extraction/docs/* and labels.jsonl. Labels are the structured
specifications the documents were rendered from, so they are exact by construction;
a sample was additionally checked by eye against the rendered PDFs.
"""
from __future__ import annotations

import json
import random
from datetime import date, timedelta
from decimal import Decimal

from common import ROOT

from app.demo import render
from app.demo.generate import invoice_truth
from app.demo.spec import INVOICES, PURCHASE_ORDERS, SUPPLIERS_BY_KEY, InvoiceSpec, LineSpec

OUT = ROOT / "eval" / "datasets" / "extraction"
SEED = 20261120
N_GENERATED = 44


def catalog() -> dict[str, list[LineSpec]]:
    cat: dict[str, list[LineSpec]] = {}
    for po in PURCHASE_ORDERS:
        cat.setdefault(po.supplier, []).extend(po.lines)
    return cat


def build() -> None:
    rng = random.Random(SEED)
    cat = catalog()
    (OUT / "docs").mkdir(parents=True, exist_ok=True)
    rows = []
    specs: list[tuple[InvoiceSpec, str]] = [(inv, "demo") for inv in INVOICES]
    suppliers = list(cat)
    for i in range(N_GENERATED):
        sup = suppliers[i % len(suppliers)]
        lang = SUPPLIERS_BY_KEY[sup].lang
        seen = ["he_classic", "he_boxed", "he_compact"] if lang == "he" else ["en_classic", "en_modern"] if lang == "en" \
            else ["he_classic", "en_classic", "he_boxed"]
        held = ["he_receipt"] if lang == "he" else ["en_minimal"] if lang == "en" else ["he_receipt", "en_minimal"]
        template = rng.choice(held) if i % 5 == 4 else rng.choice(seen)  # 20% held-out layouts
        render_mode = "scanned" if i % 5 == 1 else "photo" if i % 11 == 3 else "native"
        lines = []
        for ln in rng.sample(cat[sup], k=min(len(cat[sup]), rng.randint(1, 5))):
            q = Decimal(rng.choice([1, 2, 3, 4, 5, 6, 8, 10, 12, 20, 24, 40, 50]))
            disc = Decimal("0")
            lines.append(LineSpec(ln.sku if rng.random() > 0.15 else None, ln.description, q, ln.unit_price, disc))
        inv = InvoiceSpec(
            key=f"gen_{i:03d}_{sup}_{template}_{render_mode}", scenario="generated", supplier=sup,
            number=f"{sup[:2].upper()}-{rng.randint(10000, 99999)}", invoice_date=date(2026, 1, 1) + timedelta(days=rng.randint(0, 300)),
            lines=lines, po_reference=f"PO-2026-{rng.randint(2000, 2999)}" if rng.random() > 0.2 else None,
            payment_terms=SUPPLIERS_BY_KEY[sup].payment_terms if rng.random() > 0.3 else None,
            template=template, render=render_mode, show_tax_id=rng.random() > 0.1,
        )
        specs.append((inv, "generated"))
    for inv, origin in specs:
        data, ext = render.render_invoice(inv)
        name = f"{inv.key}{ext}"
        (OUT / "docs" / name).write_bytes(data)
        lang = SUPPLIERS_BY_KEY[inv.supplier].lang
        rows.append({"file": f"docs/{name}", "origin": origin, "template": inv.template,
                     "held_out_template": inv.template in render.HELD_OUT_TEMPLATES, "render": inv.render,
                     "language": "mixed" if lang == "mixed" else ("he" if inv.template.startswith("he") else "en"),
                     "truth": invoice_truth(inv) | {"currency": inv.currency if inv.template != "he_compact" else None}})
    (OUT / "labels.jsonl").write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n", encoding="utf-8")
    print(f"wrote {len(rows)} documents to {OUT}")


if __name__ == "__main__":
    build()
