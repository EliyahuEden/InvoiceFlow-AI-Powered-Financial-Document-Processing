"""Group knowledge policy revisions across title changes.

Revision ID: 0006
Revises: 0005
"""
import sqlalchemy as sa
from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("knowledge_documents", sa.Column("policy_key", sa.String(length=80), nullable=True))
    documents = sa.table("knowledge_documents", sa.column("doc_type"), sa.column("title"), sa.column("policy_key"))
    op.execute(documents.update().where(documents.c.doc_type == "purchasing_policy", documents.c.title.in_((
        "נוהל רכש והתקשרויות - כנרת אירוח (גרסה 3.0)", "נוהל רכש - גרסה 2.1 (2023)",
    ))).values(policy_key="purchasing-policy"))


def downgrade() -> None:
    op.drop_column("knowledge_documents", "policy_key")
