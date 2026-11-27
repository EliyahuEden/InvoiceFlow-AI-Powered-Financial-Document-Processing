"""Configurable auto-approval: one policy per organization (row-level security) and a marker on the invoice.

Nothing changes for an existing organization: it has no policy row, so no invoice is auto-approved.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None

TABLE = "auto_approval_policies"


def upgrade() -> None:
    op.create_table(
        TABLE,
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", UUID(as_uuid=True), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("max_amount", sa.Numeric(18, 4), nullable=False, server_default="0"),
        sa.Column("supplier_scope", sa.String(10), nullable=False, server_default="selected"),
        sa.Column("supplier_ids", JSONB(), nullable=False, server_default="[]"),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("updated_by", UUID(as_uuid=True), sa.ForeignKey("users.id")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("organization_id", name="uq_auto_approval_policies_org"),
        sa.CheckConstraint("max_amount >= 0", name="ck_auto_approval_max_amount"),
        sa.CheckConstraint("supplier_scope IN ('all', 'selected')", name="ck_auto_approval_scope"),
    )
    op.create_index("ix_auto_approval_policies_organization_id", TABLE, ["organization_id"])
    op.create_index("ix_auto_approval_policies_updated_by", TABLE, ["updated_by"])

    # tenant isolation, as for every other tenant table (0002): the application role sees only its own organization
    op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {TABLE} TO invoiceflow_app")
    op.execute(f"ALTER TABLE {TABLE} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {TABLE} FORCE ROW LEVEL SECURITY")
    op.execute(
        f"""CREATE POLICY tenant_isolation ON {TABLE}
            USING (organization_id = NULLIF(current_setting('app.org_id', true), '')::uuid)
            WITH CHECK (organization_id = NULLIF(current_setting('app.org_id', true), '')::uuid)"""
    )

    op.add_column("invoices", sa.Column("auto_approved_at", sa.DateTime(timezone=True)))
    op.add_column("invoices", sa.Column("auto_approval", JSONB()))
    # the dashboard counts auto-approved invoices per organization
    op.create_index("ix_invoices_org_auto_approved", "invoices", ["organization_id", "auto_approved_at"],
                    postgresql_where=sa.text("auto_approved_at IS NOT NULL"))


def downgrade() -> None:
    op.drop_index("ix_invoices_org_auto_approved", table_name="invoices")
    op.drop_column("invoices", "auto_approval")
    op.drop_column("invoices", "auto_approved_at")
    op.execute(f"DROP POLICY IF EXISTS tenant_isolation ON {TABLE}")
    op.drop_table(TABLE)
