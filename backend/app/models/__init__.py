from app.models.base import Base
from app.models.documents import Document, DocumentPage, Invoice, InvoiceLine
from app.models.knowledge import KnowledgeChunk, KnowledgeDocument
from app.models.procurement import GoodsReceipt, GRLine, POLine, PurchaseOrder, Supplier
from app.models.tenancy import DEFAULT_ORG_SETTINGS, Membership, Organization, Role, User
from app.models.workflow import (
    AgentRun,
    AICall,
    Approval,
    AuditLog,
    Discrepancy,
    ExceptionCase,
    ExceptionComment,
    Job,
    ReconciliationRun,
)

# Tables protected by PostgreSQL row-level security (tenant isolation, layer 2).
RLS_TABLES = [
    "suppliers", "purchase_orders", "po_lines", "goods_receipts", "gr_lines",
    "documents", "document_pages", "invoices", "invoice_lines",
    "reconciliation_runs", "discrepancies", "exceptions", "exception_comments", "approvals",
    "knowledge_documents", "knowledge_chunks", "agent_runs", "ai_calls", "audit_logs",
]

__all__ = [
    "Base", "Organization", "User", "Membership", "Role", "DEFAULT_ORG_SETTINGS",
    "Supplier", "PurchaseOrder", "POLine", "GoodsReceipt", "GRLine",
    "Document", "DocumentPage", "Invoice", "InvoiceLine",
    "KnowledgeDocument", "KnowledgeChunk",
    "ReconciliationRun", "Discrepancy", "ExceptionCase", "ExceptionComment", "Approval",
    "AgentRun", "AICall", "Job", "AuditLog", "RLS_TABLES",
]
