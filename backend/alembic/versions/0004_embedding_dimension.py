"""Resize knowledge_chunks.embedding to the configured embedding dimension.

The default model changed from MiniLM (384) to multilingual-e5-large (1024). Vectors of another
size cannot be converted, so they are cleared and must be recomputed with
`python -m app.cli reindex-embeddings` (retrieval also embeds missing vectors in memory meanwhile).

Revision ID: 0004
Revises: 0003
"""
import sqlalchemy as sa
from alembic import op

from app.core.config import get_settings

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def _resize(dim: int) -> None:
    current = op.get_bind().execute(sa.text(
        "SELECT atttypmod FROM pg_attribute WHERE attrelid = 'knowledge_chunks'::regclass AND attname = 'embedding'"
    )).scalar()
    if current != dim:
        op.execute(f"ALTER TABLE knowledge_chunks ALTER COLUMN embedding TYPE vector({int(dim)}) USING NULL")


def upgrade() -> None:
    _resize(get_settings().embedding_dim)


def downgrade() -> None:
    _resize(384)
