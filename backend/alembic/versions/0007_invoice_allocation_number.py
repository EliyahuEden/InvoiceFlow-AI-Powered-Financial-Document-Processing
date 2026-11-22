"""Israel Tax Authority allocation number (מספר הקצאה) on supplier invoices.

Without a valid allocation number the buyer may not deduct the input VAT of a tax invoice above the
threshold in force on its date; reconciliation flags such invoices (MISSING_ALLOCATION_NUMBER).

Revision ID: 0007
Revises: 0006
"""
import sqlalchemy as sa
from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("invoices", sa.Column("allocation_number", sa.String(length=40), nullable=True))


def downgrade() -> None:
    op.drop_column("invoices", "allocation_number")
