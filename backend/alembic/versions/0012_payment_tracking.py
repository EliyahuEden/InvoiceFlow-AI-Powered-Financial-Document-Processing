"""Record scheduled dates and externally completed payments on invoices."""

import sqlalchemy as sa
from alembic import op

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("invoices", sa.Column("payment_scheduled_for", sa.Date()))
    op.add_column("invoices", sa.Column("payment_paid_on", sa.Date()))
    op.add_column("invoices", sa.Column("payment_reference", sa.String(120)))
    op.create_check_constraint("ck_invoices_payment_record", "invoices",
                               "(payment_paid_on IS NULL) = (payment_reference IS NULL)")


def downgrade() -> None:
    op.drop_constraint("ck_invoices_payment_record", "invoices", type_="check")
    for column in ("payment_reference", "payment_paid_on", "payment_scheduled_for"):
        op.drop_column("invoices", column)
