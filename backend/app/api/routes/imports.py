"""Bulk import endpoints: preview (commit=false) and import (commit=true) of a CSV or Excel file, plus templates."""
from __future__ import annotations

import csv
import io

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import JSONResponse, Response
from sqlalchemy.orm import Session

from app.api.deps import Principal, get_db, require
from app.services import audit
from app.services import bulk_import as bi
from app.services.rbac import Perm

router = APIRouter(prefix="/api/import", tags=["import"])
KINDS = ("suppliers", "purchase-orders", "goods-receipts")


@router.get("/{kind}/template.csv")
def template(kind: str, _: Principal = Depends(require(Perm.MASTERDATA_WRITE))) -> Response:
    if kind not in KINDS:
        raise HTTPException(404, "Unknown import type")
    header, example = bi.TEMPLATES[kind]
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(header)
    writer.writerow(example)
    # a BOM, so Excel opens the Hebrew example correctly
    return Response("﻿" + buf.getvalue(), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="{kind}-template.csv"'})


@router.post("/{kind}")
async def run_import(kind: str, commit: bool = False, file: UploadFile = File(...),
                     p: Principal = Depends(require(Perm.MASTERDATA_WRITE)), db: Session = Depends(get_db)) -> JSONResponse:
    if kind not in KINDS:
        raise HTTPException(404, "Unknown import type")
    data = await file.read(bi.MAX_BYTES + 1)
    try:
        table = bi.read_table(data, file.filename or "")
    except bi.ImportError_ as exc:
        raise HTTPException(422, str(exc)) from exc
    plan = bi.PLANNERS[kind](db, p.org_id, table)
    if not commit:
        return JSONResponse(plan.response())
    if plan.errors:  # all or nothing: fix the file and import it again
        return JSONResponse({**plan.response(), "detail": "The file has errors; nothing was imported."}, status_code=422)
    if kind == "suppliers":
        bi.apply_suppliers(db, p.org_id, plan)
    elif kind == "purchase-orders":
        bi.apply_purchase_orders(db, p.org_id, p.user.id, plan)
    else:
        bi.apply_goods_receipts(db, p.org_id, plan)
    audit.record(db, org_id=p.org_id, action=f"import.{kind.replace('-', '_')}", entity_type="import", entity_id=None,
                 actor_id=p.user.id, actor_label=p.user.email,
                 meta={**plan.summary, "file": (file.filename or "")[:200],
                       "keys": [i["key"] for i in plan.items if i["action"] != "skip"][:500]})
    return JSONResponse(plan.response())
