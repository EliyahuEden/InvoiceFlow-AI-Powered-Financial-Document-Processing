"""Bind payment-approval steps to the evidence they approved (audit FIN-01).

``basis`` is a fingerprint of the supplier, currency, PO, totals, lines and the required number of
steps. When the fingerprint changes (a correction, a new threshold), earlier steps are marked
``superseded`` and a fresh approval route is created; an unchanged rerun keeps them.

Revision ID: 0005
Revises: 0004
"""
import sqlalchemy as sa
from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("approvals", sa.Column("basis", sa.String(length=64), nullable=True))


def downgrade() -> None:
    op.drop_column("approvals", "basis")
