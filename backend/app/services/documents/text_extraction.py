"""Page text extraction: native PDF text first, OCR fallback per page.

Decision rule per page: use the PDF's embedded text layer when it is present and
looks sane (enough characters, few ``(cid:NN)``/replacement glyphs). Otherwise render
the page at 300 DPI and OCR it with Tesseract (``heb+eng``). Every word keeps a
normalized bounding box so extracted fields can be highlighted on the original page.
"""
from __future__ import annotations

import io
import math
import re
import shutil
from dataclasses import asdict, dataclass, field

import numpy as np
from PIL import Image, ImageFilter, ImageOps

from app.core.config import get_settings
from app.services.documents.hebrew import (
    clean_text,
    has_hebrew,
    script_counts,
    segment_direction,
    visual_to_logical,
)

OCR_DPI = 300
_CID_RE = re.compile(r"\(cid:\d+\)")


class OCRUnavailable(RuntimeError):
    """Tesseract (or its Hebrew language data) is not installed."""


class OCRFailed(RuntimeError):
    pass


@dataclass
class Word:
    t: str                      # logical-order text
    b: list[float]              # [x0, y0, x1, y1] normalized to 0..1
    l: int                      # line index on the page
    c: float | None = None      # OCR confidence 0..100 (None for native text)


@dataclass
class PageText:
    page_no: int
    width: float
    height: float
    method: str                 # native | ocr
    text: str
    words: list[Word] = field(default_factory=list)
    ocr_confidence: float | None = None

    def words_json(self) -> list[dict]:
        return [asdict(w) for w in self.words]


# ---------------------------------------------------------------- line assembly
def _group_lines(items: list[dict], y_tol: float) -> list[list[dict]]:
    """Cluster word boxes into lines by vertical center."""
    items = sorted(items, key=lambda w: ((w["top"] + w["bottom"]) / 2, w["x0"]))
    lines: list[list[dict]] = []
    for w in items:
        cy = (w["top"] + w["bottom"]) / 2
        if lines:
            last = lines[-1]
            ly = sum((x["top"] + x["bottom"]) / 2 for x in last) / len(last)
            if abs(cy - ly) <= y_tol:
                last.append(w)
                continue
        lines.append([w])
    return lines


def _assemble(items: list[dict], width: float, height: float, visual_words: bool) -> tuple[str, list[Word]]:
    """Build logical-order page text and word list from positioned words.

    ``visual_words``: True when each word's characters are already in visual
    (left→right drawn) order, as with native PDF extraction. For OCR output the word
    text is logical, so we convert it to visual first and run the same pipeline.
    """
    out_lines: list[str] = []
    words: list[Word] = []
    heights = [w["bottom"] - w["top"] for w in items] or [10.0]
    y_tol = max(2.0, float(np.median(heights)) * 0.5)
    heb, lat = script_counts(" ".join(w["text"] for w in items))
    page_dir = "R" if heb >= lat else "L"
    gap_threshold = float(np.median(heights)) * 1.5
    for li, line in enumerate(_group_lines(items, y_tol)):
        line.sort(key=lambda w: w["x0"])
        visual_tokens = []
        for w in line:
            txt = clean_text(w["text"])
            if not visual_words and has_hebrew(txt):
                txt = visual_to_logical(txt)  # logical word -> visual glyph order
            visual_tokens.append(txt)
        # Split the visual line into column segments at large horizontal gaps, so that
        # side-by-side blocks (header columns, table cells) get independent bidi runs.
        segments: list[list[str]] = [[]]
        for i, (w, vt) in enumerate(zip(line, visual_tokens, strict=True)):
            if i and w["x0"] - line[i - 1]["x1"] > gap_threshold:
                segments.append([])
            segments[-1].append(vt)
        logical_segments = []
        for seg in segments:
            visual_seg = " ".join(seg)
            logical_segments.append(visual_to_logical(visual_seg, segment_direction(visual_seg, page_dir)))
        if page_dir == "R":
            logical_segments.reverse()  # reading order of columns follows the page direction
        out_lines.append("  ".join(logical_segments))
        for w, vt in zip(line, visual_tokens, strict=True):
            words.append(
                Word(
                    t=visual_to_logical(vt),
                    b=[round(w["x0"] / width, 5), round(w["top"] / height, 5),
                       round(w["x1"] / width, 5), round(w["bottom"] / height, 5)],
                    l=li,
                    c=w.get("conf"),
                )
            )
    return "\n".join(out_lines), words


# ---------------------------------------------------------------- native text
def native_text_is_usable(text: str, min_chars: int) -> bool:
    stripped = re.sub(r"\s", "", text)
    if len(stripped) < min_chars:
        return False
    bad = len(_CID_RE.findall(text)) + text.count("�")
    return bad / max(1, len(stripped)) < 0.05


def extract_native(page, page_no: int) -> PageText:  # noqa: ANN001  (pdfplumber.Page)
    raw = page.extract_words(x_tolerance=1.5, y_tolerance=3, keep_blank_chars=False, use_text_flow=False)
    items = [{"text": w["text"], "x0": w["x0"], "x1": w["x1"], "top": w["top"], "bottom": w["bottom"]} for w in raw]
    text, words = _assemble(items, float(page.width), float(page.height), visual_words=True)
    return PageText(page_no=page_no, width=float(page.width), height=float(page.height),
                    method="native", text=text, words=words)


# ---------------------------------------------------------------- OCR
def tesseract_available() -> bool:
    cmd = get_settings().tesseract_cmd or "tesseract"
    return shutil.which(cmd) is not None


def preprocess_for_ocr(img: Image.Image) -> Image.Image:
    """Grayscale → upscale small scans → denoise → autocontrast → Otsu binarization."""
    g = ImageOps.grayscale(img)
    if g.width < 1600:
        scale = 1600 / g.width
        g = g.resize((int(g.width * scale), int(g.height * scale)), Image.LANCZOS)
    g = g.filter(ImageFilter.MedianFilter(3))
    g = ImageOps.autocontrast(g, cutoff=1)
    arr = np.asarray(g, dtype=np.uint8)
    hist = np.bincount(arr.ravel(), minlength=256).astype(np.float64)
    total = arr.size
    sum_all = np.dot(np.arange(256), hist)
    w_b = sum_b = 0.0
    best_t, best_var = 127, -1.0
    for t in range(256):
        w_b += hist[t]
        if w_b == 0 or w_b == total:
            continue
        sum_b += t * hist[t]
        m_b = sum_b / w_b
        m_f = (sum_all - sum_b) / (total - w_b)
        var = w_b * (total - w_b) * (m_b - m_f) ** 2
        if var > best_var:
            best_var, best_t = var, t
    return Image.fromarray(np.where(arr > best_t, 255, 0).astype(np.uint8))


def _deskew_angle(image: Image.Image) -> float:
    """Find a small rotation that concentrates ink into horizontal rows."""
    preview = image.copy()
    preview.thumbnail((520, 740), Image.Resampling.LANCZOS)
    ink = np.asarray(preview) < 170
    y, x = np.nonzero(ink)
    if len(x) < 250 or ink.mean() > 0.35:
        return 0.0
    x = x - preview.width / 2

    def row_alignment(angle: float) -> float:
        # Offset the projected rows so bincount can include pixels near either edge.
        rows = np.rint(y - x * math.tan(math.radians(angle)) + preview.width).astype(np.intp)
        counts = np.bincount(rows).astype(np.float64)
        return float(counts @ counts)

    straight = row_alignment(0)
    angle = float(max(np.arange(-6, 6.5, 0.5), key=row_alignment))
    return angle if 2 <= abs(angle) < 6 and row_alignment(angle) >= straight * 1.10 else 0.0


def _restore_ocr_boxes(words: list[Word], corrected: Image.Image, size: tuple[int, int], angle: float) -> None:
    """Undo the OCR rotation so highlights still refer to the uploaded page."""
    width, height = size
    sine, cosine = math.sin(math.radians(angle)), math.cos(math.radians(angle))
    for word in words:
        x0, y0, x1, y1 = word.b
        corners = []
        for nx, ny in ((x0, y0), (x0, y1), (x1, y0), (x1, y1)):
            x, y = (nx - 0.5) * corrected.width, (ny - 0.5) * corrected.height
            corners.append((0.5 + (cosine * x - sine * y) / width,
                            0.5 + (sine * x + cosine * y) / height))
        xs, ys = zip(*corners)
        word.b = [round(max(0.0, min(1.0, value)), 5) for value in (min(xs), min(ys), max(xs), max(ys))]


def ocr_image(img: Image.Image, page_no: int, page_w: float | None = None, page_h: float | None = None) -> PageText:
    s = get_settings()
    if not tesseract_available():
        raise OCRUnavailable("Tesseract OCR is not installed; scanned pages cannot be read.")
    import pytesseract

    if s.tesseract_cmd:
        pytesseract.pytesseract.tesseract_cmd = s.tesseract_cmd
    prepared = preprocess_for_ocr(img)
    angle = _deskew_angle(prepared)
    if angle:
        corrected = ImageOps.grayscale(img).rotate(angle, resample=Image.Resampling.BICUBIC, expand=True, fillcolor=255)
        prepared = preprocess_for_ocr(corrected)
    try:
        data = pytesseract.image_to_data(
            prepared, lang=s.ocr_languages, config="--psm 6 --oem 1", output_type=pytesseract.Output.DICT
        )
    except pytesseract.TesseractError as exc:
        if "Failed loading language" in str(exc):
            raise OCRUnavailable(f"Tesseract language data missing for '{s.ocr_languages}'.") from exc
        raise OCRFailed(str(exc)) from exc
    items, confs = [], []
    for i, txt in enumerate(data["text"]):
        conf = float(data["conf"][i])
        if not txt or not txt.strip() or conf < 0:
            continue
        items.append({
            "text": txt, "x0": data["left"][i], "x1": data["left"][i] + data["width"][i],
            "top": data["top"][i], "bottom": data["top"][i] + data["height"][i], "conf": conf,
        })
        confs.append(conf)
    text, words = _assemble(items, float(prepared.width), float(prepared.height), visual_words=False)
    if angle:
        _restore_ocr_boxes(words, corrected, img.size, angle)
    return PageText(
        page_no=page_no,
        width=page_w or float(img.width),
        height=page_h or float(img.height),
        method="ocr",
        text=text,
        words=words,
        ocr_confidence=round(sum(confs) / len(confs), 2) if confs else 0.0,
    )


def render_pdf_page(data: bytes, page_index: int, dpi: int = OCR_DPI) -> Image.Image:
    from app.services.documents.pdfium_safe import render_page

    return render_page(data, page_index, scale=dpi / 72)


def extract_pages(data: bytes, mime_type: str, progress=None) -> list[PageText]:  # noqa: ANN001
    """Extract text from every page. ``progress(i, n, msg)`` is called per page."""
    s = get_settings()
    pages: list[PageText] = []
    if mime_type == "application/pdf":
        import pdfplumber

        with pdfplumber.open(io.BytesIO(data)) as pdf:
            n = len(pdf.pages)
            for i, page in enumerate(pdf.pages):
                native = extract_native(page, i + 1)
                if native_text_is_usable(native.text, s.native_text_min_chars_per_page):
                    pages.append(native)
                    if progress:
                        progress(i + 1, n, f"Page {i + 1}/{n}: embedded text layer")
                    continue
                if progress:
                    progress(i + 1, n, f"Page {i + 1}/{n}: no usable text layer, running OCR")
                img = render_pdf_page(data, i)
                pages.append(ocr_image(img, i + 1, float(page.width), float(page.height)))
    else:
        if progress:
            progress(1, 1, "Image upload: running OCR")
        with Image.open(io.BytesIO(data)) as img:
            img.load()
            pages.append(ocr_image(img.convert("RGB"), 1))
    return pages
