"""Inbound email: a forwarding address per organization, a log of received messages, and where each invoice came from.

* organizations.inbox_token: the secret part of the organization's forwarding address. It is deliberately *outside*
  row-level security: a message is mapped to its organization by this token before any tenant is known. Existing
  organizations get a random token here.
* inbound_emails: one row per message (tenant table, forced RLS). Unique (organization_id, message_id) is the dedupe.
* invoices.source / invoices.inbound_email_id: "upload" or "email", and the message an emailed invoice came from.

Revision ID: 0017
Revises: 0016
"""
import secrets

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("organizations", sa.Column("inbox_token", sa.String(40), nullable=True))
    conn = op.get_bind()
    for (org_id,) in conn.execute(sa.text("SELECT id FROM organizations")).all():
        conn.execute(sa.text("UPDATE organizations SET inbox_token = :t WHERE id = :i"),
                     {"t": secrets.token_hex(10), "i": org_id})
    op.alter_column("organizations", "inbox_token", nullable=False)
    op.create_unique_constraint("uq_organizations_inbox_token", "organizations", ["inbox_token"])

    op.create_table(
        "inbound_emails",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("organization_id", sa.UUID(), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("message_id", sa.String(300), nullable=False),
        sa.Column("source", sa.String(10), nullable=False),
        sa.Column("sender", sa.String(320)),
        sa.Column("subject", sa.String(500)),
        sa.Column("recipient", sa.String(320), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True)),
        sa.Column("status", sa.String(10), nullable=False, server_default="rejected"),
        sa.Column("attachments_total", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("attachments_accepted", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("details", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("organization_id", "message_id", name="uq_inbound_emails_org_message"),
    )
    op.create_index("ix_inbound_emails_organization_id", "inbound_emails", ["organization_id"])
    op.create_index("ix_inbound_emails_org_received", "inbound_emails", ["organization_id", "created_at"])
    op.execute("ALTER TABLE inbound_emails ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE inbound_emails FORCE ROW LEVEL SECURITY")
    op.execute(
        """CREATE POLICY tenant_isolation ON inbound_emails
            USING (organization_id = NULLIF(current_setting('app.org_id', true), '')::uuid)
            WITH CHECK (organization_id = NULLIF(current_setting('app.org_id', true), '')::uuid)"""
    )

    op.add_column("invoices", sa.Column("source", sa.String(10), nullable=False, server_default="upload"))
    op.add_column("invoices", sa.Column("inbound_email_id", sa.UUID(), nullable=True))
    op.create_foreign_key("fk_invoices_inbound_email", "invoices", "inbound_emails", ["inbound_email_id"], ["id"],
                          ondelete="SET NULL")
    op.create_index("ix_invoices_inbound_email_id", "invoices", ["inbound_email_id"])


def downgrade() -> None:
    op.drop_index("ix_invoices_inbound_email_id", table_name="invoices")
    op.drop_constraint("fk_invoices_inbound_email", "invoices", type_="foreignkey")
    op.drop_column("invoices", "inbound_email_id")
    op.drop_column("invoices", "source")
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON inbound_emails")
    op.drop_table("inbound_emails")
    op.drop_constraint("uq_organizations_inbox_token", "organizations", type_="unique")
    op.drop_column("organizations", "inbox_token")
