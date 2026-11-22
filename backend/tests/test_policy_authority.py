from datetime import date

from app.core.db import session_scope
from app.models import Document, KnowledgeChunk, KnowledgeDocument
from app.services.rag import service


def add_policy(session, org_id, key, text, effective_date):
    original = Document(organization_id=org_id, purpose="knowledge", filename=f"{key}.pdf",
                        mime_type="application/pdf", size_bytes=1, sha256=key, storage_key=key)
    policy = KnowledgeDocument(organization_id=org_id, title="Versioned freight policy", doc_type="purchasing_policy",
                               effective_date=effective_date, status="indexed", document_id=None)
    session.add(original)
    session.flush()
    policy.document_id = original.id
    session.add(policy)
    session.flush()
    chunk = KnowledgeChunk(organization_id=org_id, knowledge_document_id=policy.id, chunk_index=0,
                           page=1, text=text, search_text=text, char_start=0, char_end=len(text), strategy="clause")
    session.add(chunk)
    session.flush()
    return chunk


def test_policy_search_excludes_superseded_and_future_revisions(world):
    org_id = world["org_id"]
    with session_scope(org_id) as session:
        old = add_policy(session, org_id, "old", "Freight threshold was 100.", date(2025, 1, 1))
        current = add_policy(session, org_id, "current", "Freight threshold is 200.", date(2026, 1, 1))
        conflicting = add_policy(session, org_id, "same-date", "Freight threshold is 250.", date(2026, 1, 1))
        future = add_policy(session, org_id, "future", "Freight threshold will be 300.", date(2027, 1, 1))
        ids = {str(c.id) for c in (old, current, conflicting, future)}
        expected = {str(current.id), str(conflicting.id)}
        historical = str(old.id)
    with session_scope(org_id) as session:
        def retrieve(at):
            return {hit.chunk.id for hit in service.search(session, org_id, "freight threshold", mode="bm25",
                                                           as_of=at, k=20)} & ids

        assert retrieve(date(2026, 6, 1)) == expected
        assert retrieve(date(2025, 6, 1)) == {historical}
        answer = service.ask(session, org_id, "What is the freight threshold?", mode="bm25", as_of=date(2026, 6, 1))
        assert answer["abstained"] and answer["conflict_detected"]
        assert {citation["chunk_id"] for citation in answer["citations"]} == expected


def test_policy_index_refreshes_after_same_count_content_and_metadata_edits(world):
    org_id = world["org_id"]
    with session_scope(org_id) as session:
        chunk_id = add_policy(session, org_id, "editable", "Freight threshold is 200.", date(2026, 1, 1)).id
    with session_scope(org_id) as session:
        assert any(c.text == "Freight threshold is 200." for c in service.get_index(session, org_id).chunks)
    with session_scope(org_id) as session:
        chunk = session.get(KnowledgeChunk, chunk_id)
        chunk.text = "Freight threshold is 275."
        chunk.knowledge_document.effective_date = date(2026, 3, 1)
    with session_scope(org_id) as session:
        current = next(c for c in service.get_index(session, org_id).chunks if c.id == str(chunk_id))
        assert current.text == "Freight threshold is 275."
        assert current.effective_date == "2026-03-01"


def test_demo_purchasing_policy_excludes_superseded_version_with_a_different_title(world):
    org_id = world["org_id"]
    with session_scope(org_id) as session:
        def versions(at):
            hits = service.search(session, org_id, "סטיית מחיר", mode="bm25", k=20,
                                  doc_types=["purchasing_policy"], as_of=at)
            return {hit.chunk.version for hit in hits}

        assert versions(date(2026, 6, 1)) == {"3.0"}
        assert versions(date(2024, 6, 1)) == {"2.1"}
