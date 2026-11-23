"""Two-factor sign-in: an encrypted TOTP secret, when it was turned on, the last code step used (replay guard) and
SHA-256 hashes of the unused recovery codes. Users are not tenant data, so no RLS.

Revision ID: 0010
Revises: 0009
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("totp_secret_enc", sa.Text(), nullable=True))
    op.add_column("users", sa.Column("totp_enabled_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("users", sa.Column("totp_last_step", sa.BigInteger(), nullable=True))
    op.add_column("users", sa.Column("recovery_codes", postgresql.JSONB(), nullable=False, server_default="[]"))


def downgrade() -> None:
    for col in ("recovery_codes", "totp_last_step", "totp_enabled_at", "totp_secret_enc"):
        op.drop_column("users", col)
