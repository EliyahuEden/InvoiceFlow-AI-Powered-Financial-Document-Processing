"""Operational commands.

    python -m app.cli migrate          # alembic upgrade head + LangGraph checkpoint tables
    python -m app.cli generate-docs    # regenerate synthetic PDFs into data/demo
    python -m app.cli seed [--reset]   # load the demo organization and process its documents
    python -m app.cli verify-audit     # verify the hash chain of every organization's audit log
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


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
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
