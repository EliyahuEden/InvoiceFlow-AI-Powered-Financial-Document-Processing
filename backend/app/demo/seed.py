"""Reproducible demo initialization: organizations, users, master data, documents, processing.

    python -m app.cli seed --reset
"""
from __future__ import annotations

import json

from sqlalchemy import create_engine, select, text

from app.core.config import get_settings
from app.core.db import session_scope
from app.core.logging import get_logger
from app.core.security import hash_password
from app.demo.generate import DATA_DIR, generate
from app.demo.knowledge import KNOWLEDGE
from app.demo.spec import (
    DEMO_PASSWORD,
    INVOICES,
    ORG,
    OTHER_ORG,
    OTHER_ORG_POS,
    OTHER_ORG_SUPPLIERS,
    OTHER_USERS,
    PURCHASE_ORDERS,
    SUPPLIERS,
    USERS,
)
from app.models import (
    DEFAULT_ORG_SETTINGS,
    GoodsReceipt,
    GRLine,
    Membership,
    Organization,
    POLine,
    PurchaseOrder,
    Role,
    Supplier,
    User,
)
from app.services import audit

log = get_logger("seed")


def reset_database() -> None:
    """Truncate all application data (runs as the owner role)."""
    eng = create_engine(get_settings().migration_database_url)
    with eng.begin() as conn:
        tables = [r[0] for r in conn.execute(text(
            "SELECT tablename FROM pg_tables WHERE schemaname='public' AND tablename <> 'alembic_version'"))]
        if tables:
            conn.execute(text("TRUNCATE " + ", ".join(f'"{t}"' for t in tables) + " CASCADE"))
    eng.dispose()


def _org(session, spec: dict) -> Organization:  # noqa: ANN001
    org = session.scalars(select(Organization).where(Organization.slug == spec["slug"])).first()
    if org:
        return org
    settings = json.loads(json.dumps(DEFAULT_ORG_SETTINGS))
    settings.update({"tax_id": spec.get("tax_id"), "display_name_en": spec.get("name_en"), "auto_investigate": True})
    org = Organization(name=spec["name"], slug=spec["slug"], settings=settings)
    session.add(org)
    session.flush()
    return org


def _users(session, org: Organization, users: list[tuple]) -> dict[str, User]:  # noqa: ANN001
    out = {}
    pw = hash_password(DEMO_PASSWORD)
    for email, name, role, locale in users:
        u = session.scalars(select(User).where(User.email == email)).first()
        if not u:
            u = User(email=email, full_name=name, password_hash=pw, locale=locale)
            session.add(u)
            session.flush()
            session.add(Membership(user_id=u.id, organization_id=org.id, role=Role(role)))
        out[email] = u
    session.flush()
    return out


def _master_data(org: Organization, suppliers, pos) -> dict:  # noqa: ANN001
    with session_scope(org.id) as s:
        by_key = {}
        for sp in suppliers:
            sup = Supplier(organization_id=org.id, name=sp.name, name_en=sp.name_en, tax_id=sp.tax_id,
                           aliases=sp.aliases, email=sp.email or None, phone=sp.phone or None,
                           address=sp.address or None, default_currency=sp.currency, payment_terms=sp.payment_terms)
            s.add(sup)
            s.flush()
            by_key[sp.key] = sup.id
        for p in pos:
            po = PurchaseOrder(organization_id=org.id, supplier_id=by_key[p.supplier], po_number=p.number,
                               order_date=p.order_date, currency=p.currency, status="open")
            s.add(po)
            s.flush()
            lines = []
            for i, ln in enumerate(p.lines, start=1):
                pl = POLine(organization_id=org.id, purchase_order_id=po.id, line_no=i, sku=ln.sku,
                            description=ln.description, quantity=ln.quantity, unit_price=ln.unit_price)
                s.add(pl)
                lines.append(pl)
            s.flush()
            for gr_no, gr_date, qtys in p.receipts:
                gr = GoodsReceipt(organization_id=org.id, purchase_order_id=po.id, gr_number=gr_no, received_date=gr_date,
                                  received_by="מחסן ראשי" if org.slug == "kinneret" else "Main warehouse")
                s.add(gr)
                s.flush()
                for idx, q in qtys.items():
                    s.add(GRLine(organization_id=org.id, goods_receipt_id=gr.id, po_line_id=lines[idx].id,
                                 quantity_received=q))
                full = all(qtys.get(i, 0) >= ln.quantity for i, ln in enumerate(p.lines))
                po.status = "received" if full else "partially_received"
            if not p.receipts:
                po.status = "open"
            audit.record(s, org_id=org.id, action="purchase_order.created", entity_type="purchase_order",
                         entity_id=po.id, actor_type="system", actor_label="seed",
                         after={"po_number": po.po_number, "lines": len(lines)})
        return by_key


def seed(reset: bool = False, process: bool = True) -> dict:
    from app.services.processing import create_invoice_upload
    from app.services.rag.service import create_knowledge_upload
    from app.worker import drain

    if reset:
        reset_database()
    manifest_path = DATA_DIR / "manifest.json"
    if not manifest_path.exists():
        log.info("generating_demo_documents")
        generate()
    with session_scope() as s:
        org = _org(s, ORG)
        other = _org(s, OTHER_ORG)
        users = _users(s, org, USERS)
        _users(s, other, OTHER_USERS)
        org_id, other_id = org.id, other.id
        uploader = users["procurement@kinneret.example"]
        uploader_id = uploader.id

    with session_scope(org_id) as s:
        if s.scalars(select(Supplier).where(Supplier.organization_id == org_id)).first():
            log.info("already_seeded")
            return {"status": "already_seeded"}
    sup_ids = _master_data(_get_org(org_id), SUPPLIERS, PURCHASE_ORDERS)
    _master_data(_get_org(other_id), OTHER_ORG_SUPPLIERS, OTHER_ORG_POS)

    # Knowledge base first, so agent investigations have evidence to cite.
    for k in KNOWLEDGE:
        with session_scope(org_id) as s:
            user = s.get(User, uploader_id)
            create_knowledge_upload(s, org_id=org_id, user=user, data=(DATA_DIR / "knowledge" / f"{k.key}.pdf").read_bytes(),
                                    filename=f"{k.key}.pdf", title=k.title, doc_type=k.doc_type,
                                    supplier_id=sup_ids.get(k.supplier) if k.supplier else None,
                                    effective_date=k.effective_date, version=k.version)
    if process:
        drain()
    # Invoices in scenario order (the original must exist before its duplicate arrives).
    for inv in INVOICES:
        ext = ".png" if inv.render == "photo" else ".pdf"
        path = DATA_DIR / "invoices" / f"{inv.key}{ext}"
        with session_scope(org_id) as s:
            user = s.get(User, uploader_id)
            create_invoice_upload(s, org_id=org_id, user=user, data=path.read_bytes(), filename=path.name)
        if process:
            drain()
    log.info("seed_complete", org=str(org_id))
    return {"status": "seeded", "organization_id": str(org_id), "password": "see README (demo only)"}


def _get_org(org_id) -> Organization:  # noqa: ANN001
    with session_scope() as s:
        return s.get(Organization, org_id)
