"""Render synthetic invoices and knowledge documents to PDF / PNG.

Hebrew is written the way most real-world Hebrew PDFs are produced: logical text is
converted to *visual* glyph order (python-bidi) and drawn left-to-right. This makes
the extraction pipeline deal with the same visual-order problem real documents have.
"""
from __future__ import annotations

import io
import random
import zlib
from datetime import date
from decimal import Decimal
from pathlib import Path

from bidi import get_display
import numpy as np
from PIL import Image, ImageFilter
from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

from app.demo.spec import ORG, SUPPLIERS_BY_KEY, InvoiceSpec
from app.services.documents.hebrew import MIRROR, has_hebrew

W, H = A4
MARGIN = 40

_FONT_CANDIDATES = [
    ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
    ("C:/Windows/Fonts/arial.ttf", "C:/Windows/Fonts/arialbd.ttf"),
    ("/Library/Fonts/Arial.ttf", "/Library/Fonts/Arial Bold.ttf"),
]
_fonts_ready = False


def _ensure_fonts() -> None:
    global _fonts_ready
    if _fonts_ready:
        return
    for regular, bold in _FONT_CANDIDATES:
        if Path(regular).exists() and Path(bold).exists():
            pdfmetrics.registerFont(TTFont("Body", regular))
            pdfmetrics.registerFont(TTFont("Body-Bold", bold))
            _fonts_ready = True
            return
    raise RuntimeError("No Hebrew-capable TTF font found (install fonts-dejavu-core)")


def vis(text: str) -> str:
    """Logical → visual glyph order for an RTL paragraph, with mirrored paired brackets."""
    if not has_hebrew(text):
        return text
    return get_display(text, base_dir="R").translate(MIRROR)


def draw(c: canvas.Canvas, x: float, y: float, text: str, size: float = 10, bold: bool = False,
         align: str = "left") -> None:
    c.setFont("Body-Bold" if bold else "Body", size)
    t = vis(text)
    if align == "right":
        c.drawRightString(x, y, t)
    elif align == "center":
        c.drawCentredString(x, y, t)
    else:
        c.drawString(x, y, t)


def money(v: Decimal) -> str:
    return f"{v:,.2f}"


def qty(v: Decimal) -> str:
    return f"{v.normalize():f}" if v == v.to_integral() else f"{v:f}"


# ------------------------------------------------------------------ invoice layouts
TEMPLATES = {
    "he_classic": dict(
        rtl=True, title="חשבונית מס", number="חשבונית מס מספר: {n}", date="תאריך: {d}", datefmt="%d/%m/%Y",
        po="מס' הזמנה: {po}", terms="תנאי תשלום: {t}", taxid="ח.פ. {id}", billto="לכבוד: {org}  ח.פ. {orgid}",
        cols=["מק\"ט", "תיאור", "כמות", "מחיר יחידה", "סה\"כ"], sub="סה\"כ לפני מע\"מ", vat="מע\"מ {r}%",
        total="סה\"כ לתשלום", cur_prefix="₪ ",
    ),
    "he_boxed": dict(
        rtl=True, title="חשבונית מס / קבלה", number="מספר חשבונית {n}", date="תאריך הפקה {d}", datefmt="%d.%m.%Y",
        po="הזמנת רכש {po}", terms="תנאי תשלום {t}", taxid="עוסק מורשה {id}", billto="עבור: {org}",
        cols=["מק\"ט", "פריט", "כמות", "מחיר", "סכום"], sub="סכום ביניים", vat="מע\"מ ({r}%)",
        total="סה\"כ כולל מע\"מ", cur_prefix="₪",
    ),
    "he_compact": dict(
        rtl=True, title="חשבונית מס", number="חשבונית מס {n}", date="תאריך {d}", datefmt="%d/%m/%y",
        po="הזמנה: {po}", terms="תשלום: {t}", taxid="ע.מ. {id}", billto="לקוח: {org}",
        cols=["מק\"ט", "תיאור", "כמות", "מחיר", "סה\"כ"], sub="סה\"כ", vat="מע\"מ {r}%", total="לתשלום",
        cur_prefix="",
    ),
    "en_classic": dict(
        rtl=False, title="TAX INVOICE", number="Invoice No: {n}", date="Invoice Date: {d}", datefmt="%d %b %Y",
        po="PO Number: {po}", terms="Payment Terms: {t}", taxid="Company No. {id}",
        billto="Bill to: {org_en}, Company No. {orgid}",
        cols=["SKU", "Description", "Qty", "Unit Price", "Discount", "Amount"], sub="Subtotal", vat="VAT {r}%",
        total="Total Due", cur_prefix="",
    ),
    "en_modern": dict(
        rtl=False, title="Invoice", number="Invoice # {n}", date="Date: {d}", datefmt="%Y-%m-%d",
        po="Your reference: {po}", terms="Terms: {t}", taxid="VAT No. {id}", billto="Customer: {org_en}",
        cols=["Item", "Description", "Qty", "Price", "Amount"], sub="Net amount", vat="Tax ({r}%)",
        total="Amount due ({cur})", cur_prefix="",
    ),
    # --- held-out templates: never used while developing the rule-based extractor.
    "he_receipt": dict(
        rtl=True, title="קבלה / חשבונית מס", number="מסמך מס' {n}", date="תאריך מסמך: {d}", datefmt="%d/%m/%Y",
        po="אסמכתא: {po}", terms="אופן תשלום: {t}", taxid="מספר עוסק {id}", billto="שם הלקוח: {org}",
        cols=["תיאור", "מק\"ט", "מחיר ליח'", "כמות", "סכום"], order=["description", "sku", "price", "qty", "total"],
        sub="סכום לפני מע\"מ", vat="מע\"מ בשיעור {r}%", total="סכום כולל", cur_prefix="₪",
    ),
    "en_minimal": dict(
        rtl=False, title="BILL", number="Bill No. {n}", date="Issued {d}", datefmt="%B %d, %Y",
        po="Order ref {po}", terms="Due: {t}", taxid="Reg. {id}", billto="To: {org_en}",
        cols=["Qty", "Code", "Item", "Rate", "Total"], order=["qty", "sku", "description", "price", "total"],
        sub="Sub Total", vat="VAT @ {r}%", total="TOTAL PAYABLE", cur_prefix="",
    ),
    # --- held-out set v2: written before the layout-tolerant extractor changes and scored once
    # afterwards. The v1 templates above were inspected while making those changes, so their
    # score is reported as development data from then on (docs/EVALUATION_PLAN.md).
    "he_service": dict(
        rtl=True, title="חשבון עסקה / חשבונית מס", number="מס' חשבונית: {n}", date="נוצר בתאריך {d}", datefmt="%d-%m-%Y",
        po="מספר רכש: {po}", terms="תנאים: {t}", taxid="ח\"פ {id}", billto="מזמין: {org}",
        cols=["פריט", "כמות", "תיאור", "מחיר ליחידה", "סה\"כ שורה"], order=["sku", "qty", "description", "price", "total"],
        sub="סה\"כ חייב במע\"מ", vat="מס ערך מוסף {r}%", total="סה\"כ לתשלום כולל מע\"מ", cur_prefix="₪",
    ),
    "en_statement": dict(
        rtl=False, title="Commercial Invoice", number="Document No. {n}", date="Dated {d}", datefmt="%d/%m/%Y",
        po="P.O. {po}", terms="Payment: {t}", taxid="Tax Reg. No. {id}", billto="Invoice to: {org_en}",
        cols=["Description", "Unit Cost", "Units", "Line Total", "Ref"], order=["description", "price", "qty", "total", "sku"],
        sub="Total before tax", vat="V.A.T. {r}%", total="Amount Payable", cur_prefix="",
    ),
}
HELD_OUT_V1 = {"he_receipt", "en_minimal"}
HELD_OUT_V2 = {"he_service", "en_statement"}
HELD_OUT_TEMPLATES = HELD_OUT_V1 | HELD_OUT_V2
ROWS_PER_PAGE = 16


def _fmt_rate(r: Decimal) -> str:
    return f"{r:.1f}" if r != r.to_integral() else f"{int(r)}"


def render_invoice_pdf(inv: InvoiceSpec) -> bytes:
    _ensure_fonts()
    t = TEMPLATES[inv.template]
    sup = SUPPLIERS_BY_KEY[inv.supplier]
    rtl = t["rtl"]
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    c.setTitle(f"Invoice {inv.number}")
    c.setAuthor("InvoiceFlow synthetic data generator")
    pages = [inv.lines[i:i + ROWS_PER_PAGE] for i in range(0, len(inv.lines), ROWS_PER_PAGE)] or [[]]
    cur = inv.currency
    prefix = t["cur_prefix"] if cur == "ILS" else ("$" if cur == "USD" else "")
    supplier_name = inv.supplier_display_name or (sup.name if rtl else sup.name_en)

    for pi, rows in enumerate(pages):
        x_start, x_end = (W - MARGIN, MARGIN) if rtl else (MARGIN, W - MARGIN)
        a_start, a_end = ("right", "left") if rtl else ("left", "right")
        # --- header: supplier block
        y = H - MARGIN - 10
        draw(c, x_start, y, supplier_name, 16, True, a_start)
        draw(c, x_start, y - 16, sup.address if rtl else sup.address, 9, False, a_start)
        draw(c, x_start, y - 28, f"{sup.phone}  |  {sup.email}", 9, False, a_start)
        if inv.show_tax_id:
            draw(c, x_start, y - 40, t["taxid"].format(id=sup.tax_id), 9, False, a_start)
        # --- title block
        draw(c, x_end, y, t["title"], 18, True, a_end)
        draw(c, x_end, y - 20, t["number"].format(n=inv.number), 10, True, a_end)
        draw(c, x_end, y - 33, t["date"].format(d=inv.invoice_date.strftime(t["datefmt"])), 10, False, a_end)
        if inv.po_reference:
            draw(c, x_end, y - 46, t["po"].format(po=inv.po_reference), 10, False, a_end)
        if inv.payment_terms:
            draw(c, x_end, y - 59, t["terms"].format(t=inv.payment_terms), 10, False, a_end)
        if inv.template == "he_boxed":
            c.setLineWidth(0.8)
            c.rect(MARGIN - 6, y - 66, 210, 86)
        c.setLineWidth(0.5)
        c.line(MARGIN, y - 72, W - MARGIN, y - 72)
        draw(c, x_start, y - 88, t["billto"].format(org=ORG["name"], org_en="Kinneret Hospitality Ltd",
                                                     orgid=ORG["tax_id"]), 10, False, a_start)
        if pi > 0:
            draw(c, x_end, y - 88, "המשך" if rtl else "(continued)", 9, False, a_end)

        # --- table
        ty = y - 120
        cols = t["cols"]
        has_disc = len(cols) == 6
        widths = [80, 225, 45, 70, 55, 70] if has_disc else [85, 265, 45, 70, 70]
        if t.get("order"):
            base = {"sku": 85, "description": 265, "qty": 45, "price": 70, "total": 70}
            widths = [base[k] for k in t["order"]]
        scale = (W - 2 * MARGIN) / sum(widths)
        widths = [w * scale for w in widths]
        xs = []  # column anchor x (start edge in reading direction)
        acc = 0.0
        for w in widths:
            xs.append((W - MARGIN - acc) if rtl else (MARGIN + acc))
            acc += w
        c.setFillGray(0.92)
        c.rect(MARGIN, ty - 4, W - 2 * MARGIN, 16, stroke=0, fill=1)
        c.setFillGray(0)
        for i, name in enumerate(cols):
            pad = 4
            draw(c, xs[i] - pad if rtl else xs[i] + pad, ty, name, 9, True, "right" if rtl else "left")
        ry = ty - 18
        for ln in rows:
            values = {"sku": ln.sku or "", "description": ln.description, "qty": qty(ln.quantity),
                      "price": money(ln.unit_price), "discount": money(ln.discount), "total": money(ln.total)}
            order = t.get("order") or (["sku", "description", "qty", "price"] + (["discount"] if has_disc else []) + ["total"])
            cells = [values[k] for k in order]
            for i, val in enumerate(cells):
                pad = 4
                numeric = order[i] not in ("sku", "description")
                if numeric:  # numbers aligned to the column end
                    x_num = (xs[i] - widths[i] + pad) if rtl else (xs[i] + widths[i] - pad)
                    draw(c, x_num, ry, val, 9, False, "left" if rtl else "right")
                else:
                    draw(c, xs[i] - pad if rtl else xs[i] + pad, ry, val, 9, False, "right" if rtl else "left")
            c.setStrokeGray(0.85)
            c.line(MARGIN, ry - 5, W - MARGIN, ry - 5)
            c.setStrokeGray(0)
            ry -= 18

        last = pi == len(pages) - 1
        if last:
            # --- totals block (bottom, end side)
            by = min(ry - 20, 230)
            label_x = (MARGIN + 190) if rtl else (W - MARGIN - 190)
            val_x = MARGIN if rtl else W - MARGIN
            rows_tot = [
                (t["sub"], money(inv.subtotal), False),
                (t["vat"].format(r=_fmt_rate(inv.vat_rate)), money(inv.vat), False),
                (t["total"].format(cur=cur), f"{prefix}{money(inv.total)}" + ("" if rtl or prefix else f" {cur}"), True),
            ]
            for label, val, bold in rows_tot:
                draw(c, label_x, by, label, 10, bold, "right" if rtl else "left")
                draw(c, val_x, by, val, 10, bold, "left" if rtl else "right")
                by -= 16
            ny = 140
            for note in inv.notes:
                c.setFont("Body", 7)
                c.setFillGray(0.35)
                words, line = note.split(), ""
                for wd in words:  # simple wrap
                    if pdfmetrics.stringWidth(line + " " + wd, "Body", 7) > W - 2 * MARGIN:
                        c.drawString(MARGIN, ny, line.strip())
                        ny -= 9
                        line = ""
                    line += " " + wd
                c.drawString(MARGIN, ny, line.strip())
                ny -= 12
                c.setFillGray(0)
        footer = "מסמך ממוחשב" if rtl else "Computer-generated document"
        draw(c, W / 2, 40, f"{footer}  ·  {pi + 1}/{len(pages)}", 8, False, "center")
        c.showPage()
    c.save()
    return buf.getvalue()


# ------------------------------------------------------------------ degradations
def _render_pages(pdf_bytes: bytes, dpi: int) -> list[Image.Image]:
    import pypdfium2 as pdfium

    pdf = pdfium.PdfDocument(pdf_bytes)
    try:
        return [pdf[i].render(scale=dpi / 72).to_pil().convert("L") for i in range(len(pdf))]
    finally:
        pdf.close()


def _degrade(img: Image.Image, rng: random.Random, angle: float, noise: int, blur: float) -> Image.Image:
    img = img.rotate(angle, resample=Image.BICUBIC, expand=False, fillcolor=255)
    if blur:
        img = img.filter(ImageFilter.GaussianBlur(blur))
    px = img.load()
    w, h = img.size
    for _ in range(int(w * h * noise / 10000)):
        x, y = rng.randrange(w), rng.randrange(h)
        px[x, y] = rng.choice((0, 90, 200, 255))
    return img


def render_scanned_pdf(pdf_bytes: bytes, seed: int = 7) -> bytes:
    """Image-only PDF imitating a office scanner: 200 DPI, skew, speckle noise, JPEG."""
    rng = random.Random(seed)
    pages = [_degrade(p, rng, angle=rng.uniform(-0.8, 0.8), noise=4, blur=0.4) for p in _render_pages(pdf_bytes, 200)]
    out = io.BytesIO()
    jpgs = []
    for p in pages:
        b = io.BytesIO()
        p.save(b, "JPEG", quality=70)
        jpgs.append(Image.open(io.BytesIO(b.getvalue())))
    jpgs[0].save(out, "PDF", resolution=200, save_all=True, append_images=jpgs[1:])
    return out.getvalue()


def render_photo_png(pdf_bytes: bytes, seed: int = 11) -> bytes:
    """PNG imitating a phone capture: uneven lighting, rotation, mild blur, speckle."""
    rng = random.Random(seed)
    page = _render_pages(pdf_bytes, 170)[0]
    page = _degrade(page, rng, angle=rng.uniform(-1.5, 1.5), noise=2, blur=0.6)
    arr = np.asarray(page, dtype=np.int16)
    gradient = np.linspace(0, 40, arr.shape[1], dtype=np.int16)[None, :]  # left-to-right shadow
    lit = Image.fromarray(np.clip(arr - gradient, 0, 255).astype(np.uint8))
    out = io.BytesIO()
    lit.save(out, "PNG", optimize=True)
    return out.getvalue()


def render_invoice(inv: InvoiceSpec) -> tuple[bytes, str]:
    pdf = render_invoice_pdf(inv)
    if inv.render == "scanned":
        return render_scanned_pdf(pdf, seed=zlib.crc32(inv.key.encode()) % 1000), ".pdf"
    if inv.render == "photo":
        return render_photo_png(pdf), ".png"
    return pdf, ".pdf"


# ------------------------------------------------------------------ text documents
def render_text_document(title: str, blocks: list[tuple[str, str]], rtl: bool, meta: list[str] | None = None) -> bytes:
    """Render a policy / agreement. blocks: [("h", heading) | ("p", paragraph)]."""
    _ensure_fonts()
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    c.setTitle(title)
    width = W - 2 * MARGIN
    y = H - MARGIN - 10
    page_no = 1

    def new_page() -> None:
        nonlocal y, page_no
        draw(c, W / 2, 30, f"{page_no}", 8, False, "center")
        c.showPage()
        page_no += 1
        y = H - MARGIN - 10

    def line_out(text: str, size: float, bold: bool, para_rtl: bool) -> None:
        nonlocal y
        if y < MARGIN + 30:
            new_page()
        draw(c, (W - MARGIN) if para_rtl else MARGIN, y, text, size, bold, "right" if para_rtl else "left")
        y -= size * 1.45

    def wrap(text: str, size: float, bold: bool) -> list[str]:
        font = "Body-Bold" if bold else "Body"
        lines, cur = [], ""
        for wd in text.split():
            cand = f"{cur} {wd}".strip()
            if pdfmetrics.stringWidth(vis(cand), font, size) > width and cur:
                lines.append(cur)
                cur = wd
            else:
                cur = cand
        if cur:
            lines.append(cur)
        return lines

    for ln in wrap(title, 16, True):
        line_out(ln, 16, True, rtl)
    for m in meta or []:
        line_out(m, 9, False, rtl or has_hebrew(m))
    y -= 8
    for kind, text in blocks:
        para_rtl = has_hebrew(text) if text.strip() else rtl
        if kind == "h":
            y -= 6
            for ln in wrap(text, 11.5, True):
                line_out(ln, 11.5, True, para_rtl)
        else:
            for ln in wrap(text, 10, False):
                line_out(ln, 10, False, para_rtl)
            y -= 4
    draw(c, W / 2, 30, f"{page_no}", 8, False, "center")
    c.showPage()
    c.save()
    return buf.getvalue()


def write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def iso(d: date) -> str:
    return d.isoformat()
