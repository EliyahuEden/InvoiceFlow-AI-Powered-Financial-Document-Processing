"""multilingual-e5-large is the default dense model: 1024-d vectors, its own calibrated abstention
floor when no reranker is used, and a command to re-embed stored chunks after a model change."""
from __future__ import annotations

import pytest
from sqlalchemy import create_engine, text

from app.core.config import Settings, get_settings
from app.services.rag.answer import dense_floor


def test_e5_large_is_the_default_dense_model():
    s = Settings()
    assert s.embedding_model == "intfloat/multilingual-e5-large"
    assert s.embedding_dim == 1024


def test_dense_abstention_floor_is_calibrated_per_model():
    assert dense_floor("fastembed", "intfloat/multilingual-e5-large") == 0.906
    assert dense_floor("fastembed", "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2") == 0.35
    assert dense_floor("hash", "intfloat/multilingual-e5-large") == 0.35  # the test embedder is not e5


@pytest.mark.integration
def test_vector_column_matches_the_configured_dimension(migrated):
    eng = create_engine(get_settings().migration_database_url)
    with eng.connect() as conn:
        dim = conn.execute(text("SELECT atttypmod FROM pg_attribute WHERE attrelid = 'knowledge_chunks'::regclass "
                                "AND attname = 'embedding'")).scalar()
    eng.dispose()
    assert dim == get_settings().embedding_dim


@pytest.mark.integration
def test_reindex_embeds_chunks_without_a_vector(world):
    from app.cli import reindex_embeddings

    eng = create_engine(get_settings().migration_database_url)
    with eng.begin() as conn:
        n = conn.execute(text("SELECT count(*) FROM knowledge_chunks")).scalar()
        assert n > 0
        conn.execute(text("UPDATE knowledge_chunks SET embedding = NULL"))
    assert reindex_embeddings() == n
    with eng.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM knowledge_chunks WHERE embedding IS NULL")).scalar() == 0
        assert conn.execute(text("SELECT vector_dims(embedding) FROM knowledge_chunks LIMIT 1")).scalar() == 1024
    eng.dispose()
