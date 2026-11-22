"""Index every foreign key, and give the invoice list an index in its own sort order.

Measured on 100,000 invoices in one business (with RLS, as the application role): the first page of the invoice
list went from 35 ms (fetch and sort every row) to 0.04 ms, and the status-filtered list from 19 ms to 0.06 ms.
Foreign keys without an index make joins and cascading deletes scan the whole table.

Built CONCURRENTLY so a large production table stays writable while the indexes are created.

Revision ID: 0009
Revises: 0008
"""
from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None

FK_INDEXES = [
    ("ix_documents_uploaded_by", "documents", "uploaded_by"),
    ("ix_purchase_orders_created_by", "purchase_orders", "created_by"),
    ("ix_invoices_reviewed_by", "invoices", "reviewed_by"),
    ("ix_agent_runs_started_by", "agent_runs", "started_by"),
    ("ix_approvals_decided_by", "approvals", "decided_by"),
    ("ix_exceptions_decided_by", "exceptions", "decided_by"),
    ("ix_exception_comments_author_id", "exception_comments", "author_id"),
    ("ix_auth_sessions_organization_id", "auth_sessions", "organization_id"),
    ("ix_auth_tokens_organization_id", "auth_tokens", "organization_id"),
]


def upgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute("CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_invoices_org_created "
                   "ON invoices (organization_id, created_at DESC NULLS LAST)")
        for name, table, column in FK_INDEXES:
            op.execute(f"CREATE INDEX CONCURRENTLY IF NOT EXISTS {name} ON {table} ({column})")


def downgrade() -> None:
    with op.get_context().autocommit_block():
        for name, _, _ in FK_INDEXES:
            op.execute(f"DROP INDEX CONCURRENTLY IF EXISTS {name}")
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS ix_invoices_org_created")
