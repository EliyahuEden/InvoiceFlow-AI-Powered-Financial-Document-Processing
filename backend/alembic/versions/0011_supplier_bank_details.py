"""Store confirmed and pending supplier payment details and the payment hold."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("suppliers", sa.Column("bank_account", JSONB(none_as_null=True)))
    op.add_column("suppliers", sa.Column("pending_bank_account", JSONB(none_as_null=True)))
    op.add_column("suppliers", sa.Column("bank_hold_until", sa.DateTime(timezone=True)))


def downgrade() -> None:
    op.drop_column("suppliers", "bank_hold_until")
    op.drop_column("suppliers", "pending_bank_account")
    op.drop_column("suppliers", "bank_account")
