"""Operational commands.

    python -m app.cli migrate          # alembic upgrade head + LangGraph checkpoint tables
    python -m app.cli generate-docs    # regenerate synthetic PDFs into data/demo
    python -m app.cli seed [--reset]   # load the demo organization and process its documents
    python -m app.cli verify-audit     # verify the hash chain of every organization's audit log
    python -m app.cli reindex-embeddings [--all]  # embed chunks without a vector (all with --all)
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def reindex_embeddings(all_chunks: bool = False, batch: int = 64) -> int:
    """Compute and store embeddings for knowledge chunks that have none (every chunk with
    ``all_chunks``), e.g. after changing EMBEDDING_MODEL. Returns the number of chunks embedded."""
    from sqlalchemy import select

    from app.core.db import new_session, set_session_org
    from app.models import KnowledgeChunk, KnowledgeDocument, Organization
    from app.services.rag import service as rag_service
    from app.services.rag.models import get_embedder

    embedder = get_embedder()
    done = 0
    s = new_session()
    try:
        org_ids = list(s.scalars(select(Organization.id)))
    finally:
        s.close()
    for org_id in org_ids:
        s = new_session()
        try:
            set_session_org(s, org_id)
            q = (select(KnowledgeChunk, KnowledgeDocument.title)
                 .join(KnowledgeDocument, KnowledgeDocument.id == KnowledgeChunk.knowledge_document_id)
                 .where(KnowledgeChunk.organization_id == org_id))
            if not all_chunks:
                q = q.where(KnowledgeChunk.embedding.is_(None))
            rows = s.execute(q).all()
            for i in range(0, len(rows), batch):
                part = rows[i:i + batch]
                vecs = embedder.embed([f"{title}. {ch.text}" for ch, title in part])  # same text as ingestion
                for (ch, _), v in zip(part, vecs, strict=True):
                    ch.embedding = v.tolist()
            s.commit()
            done += len(rows)
            rag_service._INDEX_CACHE.pop(str(org_id), None)
        finally:
            s.close()
    return done


def migrate() -> None:
    from alembic import command
    from alembic.config import Config

    from app.core.config import get_settings
    from app.services.agent.runner import setup_checkpointer

    here = Path(__file__).resolve().parents[1]
    cfg = Config(str(here / "alembic.ini"))
    cfg.set_main_option("script_location", str(here / "alembic"))
    command.upgrade(cfg, "head")
    setup_checkpointer(get_settings().migration_database_url)
    # checkpoint tables are created by the owner; make sure the app role can use them
    from sqlalchemy import create_engine, text

    eng = create_engine(get_settings().migration_database_url)
    with eng.begin() as conn:
        conn.execute(text("GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO invoiceflow_app"))
        conn.execute(text("REVOKE UPDATE, DELETE, TRUNCATE ON audit_logs FROM invoiceflow_app"))
        conn.execute(text("REVOKE ALL ON alembic_version FROM invoiceflow_app"))
    eng.dispose()
    print("migrations applied")


def main(argv: list[str] | None = None) -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser(prog="app.cli")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("migrate")
    sub.add_parser("generate-docs")
    sp = sub.add_parser("seed")
    sp.add_argument("--reset", action="store_true", help="truncate all data first")
    sp.add_argument("--no-process", action="store_true", help="enqueue jobs but do not run them")
    sub.add_parser("verify-audit")
    rp = sub.add_parser("reindex-embeddings")
    rp.add_argument("--all", action="store_true", help="re-embed every chunk, not only those without a vector")
    args = p.parse_args(argv)

    from app.core.logging import configure_logging

    configure_logging(json_logs=False)
    if args.cmd == "migrate":
        migrate()
    elif args.cmd == "generate-docs":
        from app.demo.generate import generate

        m = generate()
        print(f"generated {len(m['invoices'])} invoices, {len(m['upload_samples'])} upload samples, "
              f"{len(m['knowledge'])} knowledge documents")
    elif args.cmd == "seed":
        from app.demo.seed import seed

        print(json.dumps(seed(reset=args.reset, process=not args.no_process), indent=2))
    elif args.cmd == "verify-audit":
        from sqlalchemy import select

        from app.core.db import session_scope
        from app.models import Organization
        from app.services.audit import verify_chain

        with session_scope() as s:
            orgs = s.scalars(select(Organization)).all()
        for org in orgs:
            with session_scope(org.id) as s:
                print(org.slug, verify_chain(s, org.id))
    elif args.cmd == "reindex-embeddings":
        print(f"embedded {reindex_embeddings(all_chunks=args.all)} chunks")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
