"""Row-level security, least-privilege grants, append-only audit log, vector index.

Revision ID: 0002
Revises: 0001
"""
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

APP_ROLE = "invoiceflow_app"

RLS_TABLES = [
    "suppliers", "purchase_orders", "po_lines", "goods_receipts", "gr_lines",
    "documents", "document_pages", "invoices", "invoice_lines",
    "reconciliation_runs", "discrepancies", "exceptions", "exception_comments", "approvals",
    "knowledge_documents", "knowledge_chunks", "agent_runs", "ai_calls", "audit_logs",
]


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute(
        f"""DO $$ BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{APP_ROLE}') THEN
              CREATE ROLE {APP_ROLE} LOGIN PASSWORD 'invoiceflow_app_dev';
            END IF; END $$;"""
    )
    op.execute(f"GRANT USAGE ON SCHEMA public TO {APP_ROLE}")
    op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO {APP_ROLE}")
    op.execute(f"GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO {APP_ROLE}")
    # Tables created later by the owner (e.g. LangGraph checkpoint tables) inherit grants.
    op.execute(f"ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO {APP_ROLE}")
    op.execute(f"ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT USAGE, SELECT ON SEQUENCES TO {APP_ROLE}")
    # The audit trail is append-only for the application role.
    op.execute(f"REVOKE UPDATE, DELETE, TRUNCATE ON audit_logs FROM {APP_ROLE}")
    op.execute(f"REVOKE ALL ON alembic_version FROM {APP_ROLE}")

    for table in RLS_TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"""CREATE POLICY tenant_isolation ON {table}
                USING (organization_id = NULLIF(current_setting('app.org_id', true), '')::uuid)
                WITH CHECK (organization_id = NULLIF(current_setting('app.org_id', true), '')::uuid)"""
        )

    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_knowledge_chunks_embedding_hnsw "
        "ON knowledge_chunks USING hnsw (embedding vector_cosine_ops)"
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_jobs_claim ON jobs (status, run_after, created_at)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_jobs_claim")
    op.execute("DROP INDEX IF EXISTS ix_knowledge_chunks_embedding_hnsw")
    for table in RLS_TABLES:
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation ON {table}")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
