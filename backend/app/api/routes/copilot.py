"""AP Copilot endpoint: read-only questions about the queue, invoices, suppliers and policies."""
from __future__ import annotations

import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field, StringConstraints
from sqlalchemy.orm import Session

from app.api.deps import Principal, get_db, require
from app.core.config import get_settings
from app.services import copilot
from app.services.ratelimit import check_rate_limit
from app.services.rbac import Perm

router = APIRouter(prefix="/api/copilot", tags=["copilot"])


class Turn(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(..., max_length=2000)


class PageContext(BaseModel):
    invoice_id: uuid.UUID | None = None
    exception_id: uuid.UUID | None = None


class AskIn(BaseModel):
    question: Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=1000)]
    history: list[Turn] = Field(default_factory=list, max_length=10)
    context: PageContext = Field(default_factory=PageContext)


@router.post("/ask")
def ask(body: AskIn, p: Principal = Depends(require(Perm.INVOICE_READ)), db: Session = Depends(get_db)) -> dict:
    check_rate_limit(f"copilot:{p.user.id}", get_settings().rate_limit_ai_per_minute)
    ctx = {k: str(v) for k, v in body.context.model_dump().items() if v}
    return copilot.ask(db, p.org_id, p.user.id, p.role.value, body.question,
                       history=[t.model_dump() for t in body.history], context=ctx)
