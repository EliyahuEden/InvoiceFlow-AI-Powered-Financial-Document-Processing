"""Preserve archived invoices and link explicitly classified credit notes."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("invoices", sa.Column("archived_at", sa.DateTime(timezone=True)))
    op.add_column("invoices", sa.Column("credit_for_invoice_id", UUID(as_uuid=True)))
    op.create_foreign_key("fk_invoices_credit_for", "invoices", "invoices", ["credit_for_invoice_id"], ["id"], ondelete="SET NULL")
    op.create_index("ix_invoices_credit_for_invoice_id", "invoices", ["credit_for_invoice_id"])


def downgrade() -> None:
    op.drop_index("ix_invoices_credit_for_invoice_id", table_name="invoices")
    op.drop_constraint("fk_invoices_credit_for", "invoices", type_="foreignkey")
    op.drop_column("invoices", "credit_for_invoice_id")
    op.drop_column("invoices", "archived_at")
