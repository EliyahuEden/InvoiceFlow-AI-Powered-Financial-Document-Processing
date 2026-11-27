"""Organization API keys and outbound webhooks (administrators only)."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import Principal, get_db, page_params, paginated, require
from app.core.ssrf import UnsafeTarget
from app.models import ApiKey, WebhookDelivery, WebhookEndpoint
from app.services import api_keys, audit, webhooks
from app.services.rbac import Perm

router = APIRouter(prefix="/api/org", tags=["integrations"])
NO_STORE = {"Cache-Control": "no-store"}  # a response that carries a secret must never be cached


# ------------------------------------------------------------------ API keys

class ApiKeyIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    scope: str = Field(pattern="^(read|read_write)$")


@router.get("/api-keys")
def list_api_keys(p: Principal = Depends(require(Perm.ORG_MANAGE)), db: Session = Depends(get_db)) -> dict:
    rows = db.scalars(select(ApiKey).where(ApiKey.organization_id == p.org_id)
                      .order_by(ApiKey.revoked_at.is_not(None), ApiKey.created_at.desc())).all()
    return {"items": [api_keys.serialize(k) for k in rows], "scopes": list(api_keys.SCOPES)}


@router.post("/api-keys", status_code=201)
def create_api_key(body: ApiKeyIn, p: Principal = Depends(require(Perm.ORG_MANAGE)), db: Session = Depends(get_db)) -> JSONResponse:
    if not body.name.strip():
        raise HTTPException(422, "Give the key a name")
    active = db.scalar(select(func.count()).select_from(ApiKey).where(ApiKey.organization_id == p.org_id,
                                                                      ApiKey.revoked_at.is_(None)))
    if active >= api_keys.MAX_ACTIVE_KEYS:
        raise HTTPException(409, f"At most {api_keys.MAX_ACTIVE_KEYS} active API keys: revoke one first")
    key, secret = api_keys.create(db, org_id=p.org_id, name=body.name, scope=body.scope, actor_id=p.user.id,
                                  actor_label=p.user.email)
    return JSONResponse({"key": api_keys.serialize(key), "secret": secret}, status_code=201, headers=NO_STORE)


@router.delete("/api-keys/{key_id}")
def revoke_api_key(key_id: uuid.UUID, p: Principal = Depends(require(Perm.ORG_MANAGE)), db: Session = Depends(get_db)) -> dict:
    key = db.scalars(select(ApiKey).where(ApiKey.id == key_id, ApiKey.organization_id == p.org_id).with_for_update()).first()
    if key is None:
        raise HTTPException(404, "API key not found")
    api_keys.revoke(db, key, actor_id=p.user.id, actor_label=p.user.email)
    return {"key": api_keys.serialize(key)}


# ------------------------------------------------------------------ webhooks

class WebhookIn(BaseModel):
    url: str = Field(min_length=1, max_length=2000)
    events: list[str] = Field(min_length=1, max_length=10)
    description: str | None = Field(None, max_length=200)


class WebhookPatch(BaseModel):
    url: str | None = Field(None, min_length=1, max_length=2000)
    events: list[str] | None = Field(None, min_length=1, max_length=10)
    description: str | None = Field(None, max_length=200)
    active: bool | None = None


def _checked(url: str, events: list[str]) -> tuple[str, list[str]]:
    try:
        return webhooks.validate_url(url), webhooks.normalise_events(events)
    except (UnsafeTarget, ValueError) as exc:
        raise HTTPException(422, str(exc)) from exc


def _endpoint(db: Session, org_id: uuid.UUID, endpoint_id: uuid.UUID, *, lock: bool = False) -> WebhookEndpoint:
    stmt = select(WebhookEndpoint).where(WebhookEndpoint.id == endpoint_id, WebhookEndpoint.organization_id == org_id)
    endpoint = db.scalars(stmt.with_for_update() if lock else stmt).first()
    if endpoint is None:
        raise HTTPException(404, "Webhook not found")
    return endpoint


def _audit_state(e: WebhookEndpoint) -> dict:
    return {"url": e.url, "events": list(e.events or []), "description": e.description, "active": e.active}


@router.get("/webhooks")
def list_webhooks(p: Principal = Depends(require(Perm.ORG_MANAGE)), db: Session = Depends(get_db)) -> dict:
    rows = db.scalars(select(WebhookEndpoint).where(WebhookEndpoint.organization_id == p.org_id)
                      .order_by(WebhookEndpoint.created_at)).all()
    return {"items": [webhooks.serialize_endpoint(e) for e in rows], "event_types": list(webhooks.EVENT_TYPES)}


@router.post("/webhooks", status_code=201)
def create_webhook(body: WebhookIn, p: Principal = Depends(require(Perm.ORG_MANAGE)), db: Session = Depends(get_db)) -> JSONResponse:
    url, events = _checked(body.url, body.events)
    count = db.scalar(select(func.count()).select_from(WebhookEndpoint).where(WebhookEndpoint.organization_id == p.org_id))
    if count >= webhooks.MAX_ENDPOINTS:
        raise HTTPException(409, f"At most {webhooks.MAX_ENDPOINTS} webhooks: remove one first")
    secret = webhooks.new_secret()
    endpoint = WebhookEndpoint(organization_id=p.org_id, url=url, events=events, description=(body.description or "").strip() or None,
                               secret_enc=webhooks.encrypt_secret(secret), secret_hint=secret[-4:], active=True,
                               created_by=p.user.id)
    db.add(endpoint)
    db.flush()
    audit.record(db, org_id=p.org_id, action="webhook.created", entity_type="webhook_endpoint", entity_id=endpoint.id,
                 actor_id=p.user.id, actor_label=p.user.email, after=_audit_state(endpoint))
    return JSONResponse({"webhook": webhooks.serialize_endpoint(endpoint), "secret": secret}, status_code=201, headers=NO_STORE)


@router.patch("/webhooks/{webhook_id}")
def update_webhook(webhook_id: uuid.UUID, body: WebhookPatch, p: Principal = Depends(require(Perm.ORG_MANAGE)),
                   db: Session = Depends(get_db)) -> dict:
    endpoint = _endpoint(db, p.org_id, webhook_id, lock=True)
    before = _audit_state(endpoint)
    if body.url is not None or body.events is not None:
        endpoint.url, endpoint.events = _checked(body.url if body.url is not None else endpoint.url,
                                                 body.events if body.events is not None else list(endpoint.events))
    if "description" in body.model_fields_set:
        endpoint.description = (body.description or "").strip() or None
    if body.active is not None:
        endpoint.active = body.active
    db.flush()
    if _audit_state(endpoint) != before:
        audit.record(db, org_id=p.org_id, action="webhook.updated", entity_type="webhook_endpoint", entity_id=endpoint.id,
                     actor_id=p.user.id, actor_label=p.user.email, before=before, after=_audit_state(endpoint))
    return {"webhook": webhooks.serialize_endpoint(endpoint)}


@router.delete("/webhooks/{webhook_id}")
def delete_webhook(webhook_id: uuid.UUID, p: Principal = Depends(require(Perm.ORG_MANAGE)), db: Session = Depends(get_db)) -> dict:
    endpoint = _endpoint(db, p.org_id, webhook_id, lock=True)
    before = _audit_state(endpoint)
    db.delete(endpoint)
    db.flush()
    audit.record(db, org_id=p.org_id, action="webhook.deleted", entity_type="webhook_endpoint", entity_id=webhook_id,
                 actor_id=p.user.id, actor_label=p.user.email, before=before)
    return {"deleted": True}


@router.post("/webhooks/{webhook_id}/rotate-secret")
def rotate_webhook_secret(webhook_id: uuid.UUID, p: Principal = Depends(require(Perm.ORG_MANAGE)),
                          db: Session = Depends(get_db)) -> JSONResponse:
    endpoint = _endpoint(db, p.org_id, webhook_id, lock=True)
    secret = webhooks.new_secret()
    previous_hint = endpoint.secret_hint
    endpoint.secret_enc, endpoint.secret_hint = webhooks.encrypt_secret(secret), secret[-4:]
    db.flush()
    audit.record(db, org_id=p.org_id, action="webhook.secret_rotated", entity_type="webhook_endpoint", entity_id=endpoint.id,
                 actor_id=p.user.id, actor_label=p.user.email, before={"secret_hint": previous_hint},
                 after={"secret_hint": endpoint.secret_hint})
    return JSONResponse({"webhook": webhooks.serialize_endpoint(endpoint), "secret": secret}, headers=NO_STORE)


@router.post("/webhooks/{webhook_id}/test", status_code=202)
def test_webhook(webhook_id: uuid.UUID, p: Principal = Depends(require(Perm.ORG_MANAGE)), db: Session = Depends(get_db)) -> dict:
    endpoint = _endpoint(db, p.org_id, webhook_id)
    delivery = webhooks.queue_test(db, endpoint)
    audit.record(db, org_id=p.org_id, action="webhook.test_sent", entity_type="webhook_endpoint", entity_id=endpoint.id,
                 actor_id=p.user.id, actor_label=p.user.email, meta={"delivery_id": str(delivery.id)})
    return {"delivery_id": str(delivery.id), "status": delivery.status}


@router.get("/webhooks/{webhook_id}/deliveries")
def webhook_deliveries(webhook_id: uuid.UUID, status: str | None = None, pg=Depends(page_params),
                       p: Principal = Depends(require(Perm.ORG_MANAGE)), db: Session = Depends(get_db)) -> dict:
    _endpoint(db, p.org_id, webhook_id)
    page, size = pg
    stmt = select(WebhookDelivery).where(WebhookDelivery.organization_id == p.org_id, WebhookDelivery.endpoint_id == webhook_id)
    if status:
        stmt = stmt.where(WebhookDelivery.status.in_(status.split(",")))
    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    rows = db.scalars(stmt.order_by(WebhookDelivery.created_at.desc(), WebhookDelivery.id.desc())
                      .offset((page - 1) * size).limit(size)).all()
    return paginated([webhooks.serialize_delivery(d) for d in rows], total, page, size)
