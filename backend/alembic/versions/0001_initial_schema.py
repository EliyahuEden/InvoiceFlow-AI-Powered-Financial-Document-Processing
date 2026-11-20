"""initial schema

Revision ID: 0001
Revises: 
Create Date: 2026-11-20 11:58:24.338279
"""
from alembic import op
import sqlalchemy as sa
import pgvector.sqlalchemy
from sqlalchemy.dialects import postgresql

revision = '0001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.create_table('jobs',
    sa.Column('organization_id', sa.UUID(), nullable=False),
    sa.Column('type', sa.String(length=50), nullable=False),
    sa.Column('payload', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('idempotency_key', sa.String(length=200), nullable=True),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('attempts', sa.Integer(), nullable=False),
    sa.Column('max_attempts', sa.Integer(), nullable=False),
    sa.Column('run_after', sa.DateTime(timezone=True), nullable=True),
    sa.Column('locked_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('locked_by', sa.String(length=100), nullable=True),
    sa.Column('progress', sa.Integer(), nullable=False),
    sa.Column('progress_message', sa.String(length=300), nullable=True),
    sa.Column('last_error', sa.Text(), nullable=True),
    sa.Column('result', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('entity_id', sa.UUID(), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('idempotency_key')
    )
    op.create_index(op.f('ix_jobs_entity_id'), 'jobs', ['entity_id'], unique=False)
    op.create_index(op.f('ix_jobs_organization_id'), 'jobs', ['organization_id'], unique=False)
    op.create_index(op.f('ix_jobs_status'), 'jobs', ['status'], unique=False)
    op.create_table('organizations',
    sa.Column('name', sa.String(length=200), nullable=False),
    sa.Column('slug', sa.String(length=80), nullable=False),
    sa.Column('settings', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('slug')
    )
    op.create_table('users',
    sa.Column('email', sa.String(length=320), nullable=False),
    sa.Column('full_name', sa.String(length=200), nullable=False),
    sa.Column('password_hash', sa.String(length=255), nullable=False),
    sa.Column('locale', sa.String(length=5), nullable=False),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_users_email'), 'users', ['email'], unique=True)
    op.create_table('ai_calls',
    sa.Column('kind', sa.String(length=30), nullable=False),
    sa.Column('provider', sa.String(length=30), nullable=False),
    sa.Column('model', sa.String(length=100), nullable=False),
    sa.Column('prompt_version', sa.String(length=20), nullable=True),
    sa.Column('workflow', sa.String(length=50), nullable=True),
    sa.Column('latency_ms', sa.Integer(), nullable=False),
    sa.Column('input_tokens', sa.Integer(), nullable=True),
    sa.Column('output_tokens', sa.Integer(), nullable=True),
    sa.Column('cost_usd', sa.Float(), nullable=True),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('retries', sa.Integer(), nullable=False),
    sa.Column('error', sa.Text(), nullable=True),
    sa.Column('invoice_id', sa.UUID(), nullable=True),
    sa.Column('agent_run_id', sa.UUID(), nullable=True),
    sa.Column('meta', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('organization_id', sa.UUID(), nullable=False),
    sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_ai_calls_agent_run_id'), 'ai_calls', ['agent_run_id'], unique=False)
    op.create_index(op.f('ix_ai_calls_invoice_id'), 'ai_calls', ['invoice_id'], unique=False)
    op.create_index(op.f('ix_ai_calls_kind'), 'ai_calls', ['kind'], unique=False)
    op.create_index(op.f('ix_ai_calls_organization_id'), 'ai_calls', ['organization_id'], unique=False)
    op.create_table('audit_logs',
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('actor_type', sa.String(length=10), nullable=False),
    sa.Column('actor_id', sa.UUID(), nullable=True),
    sa.Column('actor_label', sa.String(length=200), nullable=True),
    sa.Column('action', sa.String(length=80), nullable=False),
    sa.Column('entity_type', sa.String(length=40), nullable=False),
    sa.Column('entity_id', sa.UUID(), nullable=True),
    sa.Column('before', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('after', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('meta', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('prev_hash', sa.String(length=64), nullable=True),
    sa.Column('hash', sa.String(length=64), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('organization_id', sa.UUID(), nullable=False),
    sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_audit_logs_action'), 'audit_logs', ['action'], unique=False)
    op.create_index(op.f('ix_audit_logs_created_at'), 'audit_logs', ['created_at'], unique=False)
    op.create_index(op.f('ix_audit_logs_entity_id'), 'audit_logs', ['entity_id'], unique=False)
    op.create_index(op.f('ix_audit_logs_entity_type'), 'audit_logs', ['entity_type'], unique=False)
    op.create_index(op.f('ix_audit_logs_organization_id'), 'audit_logs', ['organization_id'], unique=False)
    op.create_table('documents',
    sa.Column('purpose', sa.String(length=20), nullable=False),
    sa.Column('filename', sa.String(length=255), nullable=False),
    sa.Column('mime_type', sa.String(length=100), nullable=False),
    sa.Column('size_bytes', sa.Integer(), nullable=False),
    sa.Column('sha256', sa.String(length=64), nullable=False),
    sa.Column('storage_key', sa.String(length=500), nullable=False),
    sa.Column('page_count', sa.Integer(), nullable=True),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('text_method', sa.String(length=20), nullable=True),
    sa.Column('language', sa.String(length=10), nullable=True),
    sa.Column('error', sa.Text(), nullable=True),
    sa.Column('uploaded_by', sa.UUID(), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('organization_id', sa.UUID(), nullable=False),
    sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['uploaded_by'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('organization_id', 'sha256', 'purpose')
    )
    op.create_index(op.f('ix_documents_organization_id'), 'documents', ['organization_id'], unique=False)
    op.create_index(op.f('ix_documents_sha256'), 'documents', ['sha256'], unique=False)
    op.create_table('memberships',
    sa.Column('user_id', sa.UUID(), nullable=False),
    sa.Column('organization_id', sa.UUID(), nullable=False),
    sa.Column('role', sa.Enum('admin', 'procurement_manager', 'finance_reviewer', 'read_only', name='role'), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('user_id', 'organization_id')
    )
    op.create_index(op.f('ix_memberships_organization_id'), 'memberships', ['organization_id'], unique=False)
    op.create_table('suppliers',
    sa.Column('name', sa.String(length=300), nullable=False),
    sa.Column('name_en', sa.String(length=300), nullable=True),
    sa.Column('aliases', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('tax_id', sa.String(length=32), nullable=True),
    sa.Column('email', sa.String(length=320), nullable=True),
    sa.Column('phone', sa.String(length=50), nullable=True),
    sa.Column('address', sa.Text(), nullable=True),
    sa.Column('default_currency', sa.String(length=3), nullable=False),
    sa.Column('payment_terms', sa.String(length=100), nullable=True),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('organization_id', sa.UUID(), nullable=False),
    sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('organization_id', 'tax_id')
    )
    op.create_index(op.f('ix_suppliers_organization_id'), 'suppliers', ['organization_id'], unique=False)
    op.create_table('document_pages',
    sa.Column('document_id', sa.UUID(), nullable=False),
    sa.Column('page_no', sa.Integer(), nullable=False),
    sa.Column('width', sa.Float(), nullable=False),
    sa.Column('height', sa.Float(), nullable=False),
    sa.Column('method', sa.String(length=10), nullable=False),
    sa.Column('text', sa.Text(), nullable=False),
    sa.Column('ocr_confidence', sa.Float(), nullable=True),
    sa.Column('words', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('organization_id', sa.UUID(), nullable=False),
    sa.ForeignKeyConstraint(['document_id'], ['documents.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('document_id', 'page_no')
    )
    op.create_index(op.f('ix_document_pages_document_id'), 'document_pages', ['document_id'], unique=False)
    op.create_index(op.f('ix_document_pages_organization_id'), 'document_pages', ['organization_id'], unique=False)
    op.create_table('knowledge_documents',
    sa.Column('document_id', sa.UUID(), nullable=False),
    sa.Column('title', sa.String(length=300), nullable=False),
    sa.Column('doc_type', sa.String(length=30), nullable=False),
    sa.Column('supplier_id', sa.UUID(), nullable=True),
    sa.Column('language', sa.String(length=10), nullable=True),
    sa.Column('effective_date', sa.Date(), nullable=True),
    sa.Column('version', sa.String(length=20), nullable=True),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('chunk_count', sa.Integer(), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('organization_id', sa.UUID(), nullable=False),
    sa.ForeignKeyConstraint(['document_id'], ['documents.id'], ),
    sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['supplier_id'], ['suppliers.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_knowledge_documents_document_id'), 'knowledge_documents', ['document_id'], unique=False)
    op.create_index(op.f('ix_knowledge_documents_organization_id'), 'knowledge_documents', ['organization_id'], unique=False)
    op.create_index(op.f('ix_knowledge_documents_supplier_id'), 'knowledge_documents', ['supplier_id'], unique=False)
    op.create_table('purchase_orders',
    sa.Column('supplier_id', sa.UUID(), nullable=False),
    sa.Column('po_number', sa.String(length=50), nullable=False),
    sa.Column('order_date', sa.Date(), nullable=False),
    sa.Column('currency', sa.String(length=3), nullable=False),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.Column('created_by', sa.UUID(), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('organization_id', sa.UUID(), nullable=False),
    sa.ForeignKeyConstraint(['created_by'], ['users.id'], ),
    sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['supplier_id'], ['suppliers.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('organization_id', 'po_number')
    )
    op.create_index(op.f('ix_purchase_orders_organization_id'), 'purchase_orders', ['organization_id'], unique=False)
    op.create_index(op.f('ix_purchase_orders_supplier_id'), 'purchase_orders', ['supplier_id'], unique=False)
    op.create_table('goods_receipts',
    sa.Column('purchase_order_id', sa.UUID(), nullable=False),
    sa.Column('gr_number', sa.String(length=50), nullable=False),
    sa.Column('received_date', sa.Date(), nullable=False),
    sa.Column('received_by', sa.String(length=200), nullable=True),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('organization_id', sa.UUID(), nullable=False),
    sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['purchase_order_id'], ['purchase_orders.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('organization_id', 'gr_number')
    )
    op.create_index(op.f('ix_goods_receipts_organization_id'), 'goods_receipts', ['organization_id'], unique=False)
    op.create_index(op.f('ix_goods_receipts_purchase_order_id'), 'goods_receipts', ['purchase_order_id'], unique=False)
    op.create_table('invoices',
    sa.Column('document_id', sa.UUID(), nullable=True),
    sa.Column('supplier_id', sa.UUID(), nullable=True),
    sa.Column('purchase_order_id', sa.UUID(), nullable=True),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('supplier_name_raw', sa.String(length=300), nullable=True),
    sa.Column('supplier_tax_id_raw', sa.String(length=32), nullable=True),
    sa.Column('invoice_number', sa.String(length=80), nullable=True),
    sa.Column('invoice_date', sa.Date(), nullable=True),
    sa.Column('due_date', sa.Date(), nullable=True),
    sa.Column('currency', sa.String(length=3), nullable=True),
    sa.Column('po_reference', sa.String(length=50), nullable=True),
    sa.Column('payment_terms', sa.String(length=200), nullable=True),
    sa.Column('subtotal', sa.Numeric(precision=18, scale=4), nullable=True),
    sa.Column('discount_total', sa.Numeric(precision=18, scale=4), nullable=True),
    sa.Column('tax_total', sa.Numeric(precision=18, scale=4), nullable=True),
    sa.Column('tax_rate', sa.Numeric(precision=18, scale=4), nullable=True),
    sa.Column('total', sa.Numeric(precision=18, scale=4), nullable=True),
    sa.Column('field_sources', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('missing_fields', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('validation_warnings', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('extraction_method', sa.String(length=40), nullable=True),
    sa.Column('extraction_raw', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('language', sa.String(length=10), nullable=True),
    sa.Column('reviewed_by', sa.UUID(), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('organization_id', sa.UUID(), nullable=False),
    sa.ForeignKeyConstraint(['document_id'], ['documents.id'], ),
    sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['purchase_order_id'], ['purchase_orders.id'], ),
    sa.ForeignKeyConstraint(['reviewed_by'], ['users.id'], ),
    sa.ForeignKeyConstraint(['supplier_id'], ['suppliers.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_invoices_document_id'), 'invoices', ['document_id'], unique=False)
    op.create_index(op.f('ix_invoices_invoice_number'), 'invoices', ['invoice_number'], unique=False)
    op.create_index(op.f('ix_invoices_organization_id'), 'invoices', ['organization_id'], unique=False)
    op.create_index(op.f('ix_invoices_purchase_order_id'), 'invoices', ['purchase_order_id'], unique=False)
    op.create_index(op.f('ix_invoices_status'), 'invoices', ['status'], unique=False)
    op.create_index(op.f('ix_invoices_supplier_id'), 'invoices', ['supplier_id'], unique=False)
    op.create_table('knowledge_chunks',
    sa.Column('knowledge_document_id', sa.UUID(), nullable=False),
    sa.Column('chunk_index', sa.Integer(), nullable=False),
    sa.Column('page', sa.Integer(), nullable=False),
    sa.Column('section', sa.String(length=300), nullable=True),
    sa.Column('text', sa.Text(), nullable=False),
    sa.Column('search_text', sa.Text(), nullable=False),
    sa.Column('char_start', sa.Integer(), nullable=False),
    sa.Column('char_end', sa.Integer(), nullable=False),
    sa.Column('strategy', sa.String(length=20), nullable=False),
    sa.Column('embedding', pgvector.sqlalchemy.vector.VECTOR(dim=384), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('organization_id', sa.UUID(), nullable=False),
    sa.ForeignKeyConstraint(['knowledge_document_id'], ['knowledge_documents.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_knowledge_chunks_knowledge_document_id'), 'knowledge_chunks', ['knowledge_document_id'], unique=False)
    op.create_index(op.f('ix_knowledge_chunks_organization_id'), 'knowledge_chunks', ['organization_id'], unique=False)
    op.create_table('po_lines',
    sa.Column('purchase_order_id', sa.UUID(), nullable=False),
    sa.Column('line_no', sa.Integer(), nullable=False),
    sa.Column('sku', sa.String(length=80), nullable=True),
    sa.Column('description', sa.Text(), nullable=False),
    sa.Column('quantity', sa.Numeric(precision=18, scale=3), nullable=False),
    sa.Column('unit_price', sa.Numeric(precision=18, scale=4), nullable=False),
    sa.Column('unit', sa.String(length=20), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('organization_id', sa.UUID(), nullable=False),
    sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['purchase_order_id'], ['purchase_orders.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_po_lines_organization_id'), 'po_lines', ['organization_id'], unique=False)
    op.create_index(op.f('ix_po_lines_purchase_order_id'), 'po_lines', ['purchase_order_id'], unique=False)
    op.create_table('agent_runs',
    sa.Column('invoice_id', sa.UUID(), nullable=False),
    sa.Column('thread_id', sa.String(length=100), nullable=False),
    sa.Column('status', sa.String(length=30), nullable=False),
    sa.Column('mode', sa.String(length=40), nullable=False),
    sa.Column('prompt_version', sa.String(length=20), nullable=False),
    sa.Column('steps', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('result', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('error', sa.Text(), nullable=True),
    sa.Column('started_by', sa.UUID(), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('organization_id', sa.UUID(), nullable=False),
    sa.ForeignKeyConstraint(['invoice_id'], ['invoices.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['started_by'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('thread_id')
    )
    op.create_index(op.f('ix_agent_runs_invoice_id'), 'agent_runs', ['invoice_id'], unique=False)
    op.create_index(op.f('ix_agent_runs_organization_id'), 'agent_runs', ['organization_id'], unique=False)
    op.create_table('approvals',
    sa.Column('invoice_id', sa.UUID(), nullable=False),
    sa.Column('step', sa.Integer(), nullable=False),
    sa.Column('required_role', sa.String(length=40), nullable=False),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('decided_by', sa.UUID(), nullable=True),
    sa.Column('decided_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('comment', sa.Text(), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('organization_id', sa.UUID(), nullable=False),
    sa.ForeignKeyConstraint(['decided_by'], ['users.id'], ),
    sa.ForeignKeyConstraint(['invoice_id'], ['invoices.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_approvals_invoice_id'), 'approvals', ['invoice_id'], unique=False)
    op.create_index(op.f('ix_approvals_organization_id'), 'approvals', ['organization_id'], unique=False)
    op.create_table('exceptions',
    sa.Column('invoice_id', sa.UUID(), nullable=False),
    sa.Column('title', sa.String(length=300), nullable=False),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('priority', sa.String(length=10), nullable=False),
    sa.Column('discrepancy_types', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('proposed_action', sa.String(length=60), nullable=True),
    sa.Column('proposed_action_detail', sa.Text(), nullable=True),
    sa.Column('ai_summary', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('created_by_agent', sa.Boolean(), nullable=False),
    sa.Column('agent_run_id', sa.UUID(), nullable=True),
    sa.Column('decision', sa.String(length=20), nullable=True),
    sa.Column('decision_note', sa.Text(), nullable=True),
    sa.Column('decided_by', sa.UUID(), nullable=True),
    sa.Column('decided_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('organization_id', sa.UUID(), nullable=False),
    sa.ForeignKeyConstraint(['decided_by'], ['users.id'], ),
    sa.ForeignKeyConstraint(['invoice_id'], ['invoices.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_exceptions_invoice_id'), 'exceptions', ['invoice_id'], unique=False)
    op.create_index(op.f('ix_exceptions_organization_id'), 'exceptions', ['organization_id'], unique=False)
    op.create_index(op.f('ix_exceptions_status'), 'exceptions', ['status'], unique=False)
    op.create_table('gr_lines',
    sa.Column('goods_receipt_id', sa.UUID(), nullable=False),
    sa.Column('po_line_id', sa.UUID(), nullable=False),
    sa.Column('quantity_received', sa.Numeric(precision=18, scale=3), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('organization_id', sa.UUID(), nullable=False),
    sa.ForeignKeyConstraint(['goods_receipt_id'], ['goods_receipts.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['po_line_id'], ['po_lines.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_gr_lines_goods_receipt_id'), 'gr_lines', ['goods_receipt_id'], unique=False)
    op.create_index(op.f('ix_gr_lines_organization_id'), 'gr_lines', ['organization_id'], unique=False)
    op.create_index(op.f('ix_gr_lines_po_line_id'), 'gr_lines', ['po_line_id'], unique=False)
    op.create_table('invoice_lines',
    sa.Column('invoice_id', sa.UUID(), nullable=False),
    sa.Column('line_no', sa.Integer(), nullable=False),
    sa.Column('sku', sa.String(length=80), nullable=True),
    sa.Column('description', sa.Text(), nullable=False),
    sa.Column('quantity', sa.Numeric(precision=18, scale=3), nullable=True),
    sa.Column('unit_price', sa.Numeric(precision=18, scale=4), nullable=True),
    sa.Column('discount', sa.Numeric(precision=18, scale=4), nullable=True),
    sa.Column('line_total', sa.Numeric(precision=18, scale=4), nullable=True),
    sa.Column('source', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('organization_id', sa.UUID(), nullable=False),
    sa.ForeignKeyConstraint(['invoice_id'], ['invoices.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_invoice_lines_invoice_id'), 'invoice_lines', ['invoice_id'], unique=False)
    op.create_index(op.f('ix_invoice_lines_organization_id'), 'invoice_lines', ['organization_id'], unique=False)
    op.create_table('reconciliation_runs',
    sa.Column('invoice_id', sa.UUID(), nullable=False),
    sa.Column('mode', sa.String(length=10), nullable=False),
    sa.Column('engine_version', sa.String(length=20), nullable=False),
    sa.Column('outcome', sa.String(length=20), nullable=False),
    sa.Column('tolerances', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('result', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('triggered_by', sa.String(length=20), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('organization_id', sa.UUID(), nullable=False),
    sa.ForeignKeyConstraint(['invoice_id'], ['invoices.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_reconciliation_runs_invoice_id'), 'reconciliation_runs', ['invoice_id'], unique=False)
    op.create_index(op.f('ix_reconciliation_runs_organization_id'), 'reconciliation_runs', ['organization_id'], unique=False)
    op.create_table('discrepancies',
    sa.Column('invoice_id', sa.UUID(), nullable=False),
    sa.Column('run_id', sa.UUID(), nullable=False),
    sa.Column('type', sa.String(length=40), nullable=False),
    sa.Column('severity', sa.String(length=10), nullable=False),
    sa.Column('invoice_line_id', sa.UUID(), nullable=True),
    sa.Column('po_line_id', sa.UUID(), nullable=True),
    sa.Column('expected', sa.String(length=100), nullable=True),
    sa.Column('actual', sa.String(length=100), nullable=True),
    sa.Column('difference', sa.String(length=100), nullable=True),
    sa.Column('message', sa.Text(), nullable=False),
    sa.Column('evidence', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('organization_id', sa.UUID(), nullable=False),
    sa.ForeignKeyConstraint(['invoice_id'], ['invoices.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['run_id'], ['reconciliation_runs.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_discrepancies_invoice_id'), 'discrepancies', ['invoice_id'], unique=False)
    op.create_index(op.f('ix_discrepancies_organization_id'), 'discrepancies', ['organization_id'], unique=False)
    op.create_index(op.f('ix_discrepancies_run_id'), 'discrepancies', ['run_id'], unique=False)
    op.create_index(op.f('ix_discrepancies_type'), 'discrepancies', ['type'], unique=False)
    op.create_table('exception_comments',
    sa.Column('exception_id', sa.UUID(), nullable=False),
    sa.Column('author_id', sa.UUID(), nullable=False),
    sa.Column('body', sa.Text(), nullable=False),
    sa.Column('kind', sa.String(length=20), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('organization_id', sa.UUID(), nullable=False),
    sa.ForeignKeyConstraint(['author_id'], ['users.id'], ),
    sa.ForeignKeyConstraint(['exception_id'], ['exceptions.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_exception_comments_exception_id'), 'exception_comments', ['exception_id'], unique=False)
    op.create_index(op.f('ix_exception_comments_organization_id'), 'exception_comments', ['organization_id'], unique=False)



def downgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.drop_index(op.f('ix_exception_comments_organization_id'), table_name='exception_comments')
    op.drop_index(op.f('ix_exception_comments_exception_id'), table_name='exception_comments')
    op.drop_table('exception_comments')
    op.drop_index(op.f('ix_discrepancies_type'), table_name='discrepancies')
    op.drop_index(op.f('ix_discrepancies_run_id'), table_name='discrepancies')
    op.drop_index(op.f('ix_discrepancies_organization_id'), table_name='discrepancies')
    op.drop_index(op.f('ix_discrepancies_invoice_id'), table_name='discrepancies')
    op.drop_table('discrepancies')
    op.drop_index(op.f('ix_reconciliation_runs_organization_id'), table_name='reconciliation_runs')
    op.drop_index(op.f('ix_reconciliation_runs_invoice_id'), table_name='reconciliation_runs')
    op.drop_table('reconciliation_runs')
    op.drop_index(op.f('ix_invoice_lines_organization_id'), table_name='invoice_lines')
    op.drop_index(op.f('ix_invoice_lines_invoice_id'), table_name='invoice_lines')
    op.drop_table('invoice_lines')
    op.drop_index(op.f('ix_gr_lines_po_line_id'), table_name='gr_lines')
    op.drop_index(op.f('ix_gr_lines_organization_id'), table_name='gr_lines')
    op.drop_index(op.f('ix_gr_lines_goods_receipt_id'), table_name='gr_lines')
    op.drop_table('gr_lines')
    op.drop_index(op.f('ix_exceptions_status'), table_name='exceptions')
    op.drop_index(op.f('ix_exceptions_organization_id'), table_name='exceptions')
    op.drop_index(op.f('ix_exceptions_invoice_id'), table_name='exceptions')
    op.drop_table('exceptions')
    op.drop_index(op.f('ix_approvals_organization_id'), table_name='approvals')
    op.drop_index(op.f('ix_approvals_invoice_id'), table_name='approvals')
    op.drop_table('approvals')
    op.drop_index(op.f('ix_agent_runs_organization_id'), table_name='agent_runs')
    op.drop_index(op.f('ix_agent_runs_invoice_id'), table_name='agent_runs')
    op.drop_table('agent_runs')
    op.drop_index(op.f('ix_po_lines_purchase_order_id'), table_name='po_lines')
    op.drop_index(op.f('ix_po_lines_organization_id'), table_name='po_lines')
    op.drop_table('po_lines')
    op.drop_index(op.f('ix_knowledge_chunks_organization_id'), table_name='knowledge_chunks')
    op.drop_index(op.f('ix_knowledge_chunks_knowledge_document_id'), table_name='knowledge_chunks')
    op.drop_table('knowledge_chunks')
    op.drop_index(op.f('ix_invoices_supplier_id'), table_name='invoices')
    op.drop_index(op.f('ix_invoices_status'), table_name='invoices')
    op.drop_index(op.f('ix_invoices_purchase_order_id'), table_name='invoices')
    op.drop_index(op.f('ix_invoices_organization_id'), table_name='invoices')
    op.drop_index(op.f('ix_invoices_invoice_number'), table_name='invoices')
    op.drop_index(op.f('ix_invoices_document_id'), table_name='invoices')
    op.drop_table('invoices')
    op.drop_index(op.f('ix_goods_receipts_purchase_order_id'), table_name='goods_receipts')
    op.drop_index(op.f('ix_goods_receipts_organization_id'), table_name='goods_receipts')
    op.drop_table('goods_receipts')
    op.drop_index(op.f('ix_purchase_orders_supplier_id'), table_name='purchase_orders')
    op.drop_index(op.f('ix_purchase_orders_organization_id'), table_name='purchase_orders')
    op.drop_table('purchase_orders')
    op.drop_index(op.f('ix_knowledge_documents_supplier_id'), table_name='knowledge_documents')
    op.drop_index(op.f('ix_knowledge_documents_organization_id'), table_name='knowledge_documents')
    op.drop_index(op.f('ix_knowledge_documents_document_id'), table_name='knowledge_documents')
    op.drop_table('knowledge_documents')
    op.drop_index(op.f('ix_document_pages_organization_id'), table_name='document_pages')
    op.drop_index(op.f('ix_document_pages_document_id'), table_name='document_pages')
    op.drop_table('document_pages')
    op.drop_index(op.f('ix_suppliers_organization_id'), table_name='suppliers')
    op.drop_table('suppliers')
    op.drop_index(op.f('ix_memberships_organization_id'), table_name='memberships')
    op.drop_table('memberships')
    op.drop_index(op.f('ix_documents_sha256'), table_name='documents')
    op.drop_index(op.f('ix_documents_organization_id'), table_name='documents')
    op.drop_table('documents')
    op.drop_index(op.f('ix_audit_logs_organization_id'), table_name='audit_logs')
    op.drop_index(op.f('ix_audit_logs_entity_type'), table_name='audit_logs')
    op.drop_index(op.f('ix_audit_logs_entity_id'), table_name='audit_logs')
    op.drop_index(op.f('ix_audit_logs_created_at'), table_name='audit_logs')
    op.drop_index(op.f('ix_audit_logs_action'), table_name='audit_logs')
    op.drop_table('audit_logs')
    op.drop_index(op.f('ix_ai_calls_organization_id'), table_name='ai_calls')
    op.drop_index(op.f('ix_ai_calls_kind'), table_name='ai_calls')
    op.drop_index(op.f('ix_ai_calls_invoice_id'), table_name='ai_calls')
    op.drop_index(op.f('ix_ai_calls_agent_run_id'), table_name='ai_calls')
    op.drop_table('ai_calls')
    op.drop_index(op.f('ix_users_email'), table_name='users')
    op.drop_table('users')
    op.drop_table('organizations')
    op.drop_index(op.f('ix_jobs_status'), table_name='jobs')
    op.drop_index(op.f('ix_jobs_organization_id'), table_name='jobs')
    op.drop_index(op.f('ix_jobs_entity_id'), table_name='jobs')
    op.drop_table('jobs')

