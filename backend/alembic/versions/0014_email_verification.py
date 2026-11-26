"""Email verification for self-service sign-up. Every existing account counts as verified, so nobody is locked out."""

import sqlalchemy as sa
from alembic import op

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # server default now(): existing rows (and accounts created by invitation, seed or demo) are verified;
    # only a self-service sign-up on an installation that sends email starts out unverified
    op.add_column("users", sa.Column("email_verified_at", sa.DateTime(timezone=True), server_default=sa.func.now()))


def downgrade() -> None:
    op.drop_column("users", "email_verified_at")
