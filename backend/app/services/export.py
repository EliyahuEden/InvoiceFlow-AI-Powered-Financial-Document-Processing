"""Writes tables to CSV or Excel.

CSV gets a UTF-8 BOM so Excel shows Hebrew. Text cells that a spreadsheet would run as a formula (they start with
= + - @ or a tab or carriage return) get a leading apostrophe: invoice text comes from supplier documents, which are
untrusted. Numbers and dates stay real numbers and dates in Excel.
"""
from __future__ import annotations

import csv
import io
from collections.abc import Iterable, Sequence
from datetime import date, datetime
from decimal import Decimal

FORMULA_START = ("=", "+", "-", "@", "\t", "\r")
MAX_ROWS = 50_000

Cell = str | int | float | Decimal | date | datetime | None


def safe_text(value: str) -> str:
    return "'" + value if value.startswith(FORMULA_START) else value


def _csv_cell(v: Cell) -> str:
    if v is None:
        return ""
    if isinstance(v, datetime):
        return v.date().isoformat()
    if isinstance(v, date):
        return v.isoformat()
    if isinstance(v, Decimal):
        return f"{v:.2f}"
    if isinstance(v, (int, float)):
        return str(v)
    return safe_text(str(v))


def to_csv(header: Sequence[str], rows: Iterable[Sequence[Cell]]) -> bytes:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(header)
    for row in rows:
        writer.writerow([_csv_cell(v) for v in row])
    return ("﻿" + buf.getvalue()).encode("utf-8")


def to_xlsx(header: Sequence[str], rows: Iterable[Sequence[Cell]], *, sheet: str, rtl: bool = False) -> bytes:
    from openpyxl import Workbook
    from openpyxl.styles import Font

    wb = Workbook(write_only=False)
    ws = wb.active
    ws.title = sheet[:31]
    ws.sheet_view.rightToLeft = rtl
    ws.append(list(header))
    for cell in ws[1]:
        cell.font = Font(bold=True)
    for row in rows:
        out: list = []
        for v in row:
            if isinstance(v, datetime):
                out.append(v.replace(tzinfo=None))
            elif isinstance(v, Decimal):
                out.append(float(v))
            elif isinstance(v, str):
                out.append(safe_text(v))
            else:
                out.append(v)
        ws.append(out)
    for i, name in enumerate(header):
        letter = ws.cell(row=1, column=i + 1).column_letter
        ws.column_dimensions[letter].width = max(12, min(40, len(name) + 4))
        for cell in ws[letter][1:]:
            if isinstance(cell.value, float):
                cell.number_format = "#,##0.00"
            elif isinstance(cell.value, (date, datetime)):
                cell.number_format = "dd/mm/yyyy"
    ws.freeze_panes = "A2"
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
