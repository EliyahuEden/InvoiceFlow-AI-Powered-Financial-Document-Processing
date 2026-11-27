"""Organization API keys and outbound webhooks, with tenant row-level security.

api_keys also gets a narrow SELECT policy that matches one row by the hash of the presented secret
(the transaction-local setting app.api_key_hash): a request that carries only a key does not know its
organization yet, so that single lookup cannot be tenant-bound.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None

TABLES = ["api_keys", "webhook_endpoints", "webhook_deliveries"]


def _base() -> list[sa.Column]:
    return [
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", pg.UUID(as_uuid=True), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    ]


def upgrade() -> None:
    op.create_table(
        "api_keys", *_base(),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("scope", sa.String(12), nullable=False),
        sa.Column("prefix", sa.String(16), nullable=False),
        sa.Column("key_hash", sa.String(64), nullable=False),
        sa.Column("created_by", pg.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("last_used_at", sa.DateTime(timezone=True)),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.Column("revoked_by", pg.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.CheckConstraint("scope IN ('read', 'read_write')", name="ck_api_keys_scope"),
        sa.UniqueConstraint("key_hash", name="uq_api_keys_key_hash"),
    )
    op.create_index("ix_api_keys_organization_id", "api_keys", ["organization_id"])
    op.create_index("ix_api_keys_created_by", "api_keys", ["created_by"])
    op.create_index("ix_api_keys_revoked_by", "api_keys", ["revoked_by"])

    op.create_table(
        "webhook_endpoints", *_base(),
        sa.Column("url", sa.String(2000), nullable=False),
        sa.Column("description", sa.String(200)),
        sa.Column("events", pg.JSONB, nullable=False, server_default="[]"),
        sa.Column("secret_enc", sa.Text, nullable=False),
        sa.Column("secret_hint", sa.String(12), nullable=False),
        sa.Column("active", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("created_by", pg.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL")),
    )
    op.create_index("ix_webhook_endpoints_organization_id", "webhook_endpoints", ["organization_id"])
    op.create_index("ix_webhook_endpoints_created_by", "webhook_endpoints", ["created_by"])

    op.create_table(
        "webhook_deliveries", *_base(),
        sa.Column("endpoint_id", pg.UUID(as_uuid=True), sa.ForeignKey("webhook_endpoints.id", ondelete="CASCADE"), nullable=False),
        sa.Column("event_type", sa.String(60), nullable=False),
        sa.Column("payload", pg.JSONB, nullable=False),
        sa.Column("is_test", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("status", sa.String(12), nullable=False, server_default="pending"),
        sa.Column("attempts", sa.Integer, nullable=False, server_default="0"),
        sa.Column("last_status_code", sa.Integer),
        sa.Column("last_error", sa.String(500)),
        sa.Column("last_attempt_at", sa.DateTime(timezone=True)),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True)),
        sa.Column("delivered_at", sa.DateTime(timezone=True)),
        sa.Column("attempt_log", pg.JSONB, nullable=False, server_default="[]"),
        sa.CheckConstraint("status IN ('pending', 'retrying', 'succeeded', 'failed')", name="ck_webhook_deliveries_status"),
    )
    op.create_index("ix_webhook_deliveries_organization_id", "webhook_deliveries", ["organization_id"])
    op.create_index("ix_webhook_deliveries_endpoint_created", "webhook_deliveries", ["endpoint_id", sa.text("created_at DESC")])

    for table in TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"""CREATE POLICY tenant_isolation ON {table}
                USING (organization_id = NULLIF(current_setting('app.org_id', true), '')::uuid)
                WITH CHECK (organization_id = NULLIF(current_setting('app.org_id', true), '')::uuid)"""
        )
    op.execute(
        """CREATE POLICY api_key_lookup ON api_keys FOR SELECT
           USING (key_hash = NULLIF(current_setting('app.api_key_hash', true), ''))"""
    )
    # tables created by the owner inherit the application role's grants (0002); this is a no-op safety net
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON api_keys, webhook_endpoints, webhook_deliveries TO invoiceflow_app")


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS api_key_lookup ON api_keys")
    for table in reversed(TABLES):
        op.drop_table(table)
