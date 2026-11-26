"""Schema guards: every foreign key is indexed (joins and cascading deletes must not scan whole tables), and the
invoice list reads its first page straight from an index. Measured on 100,000 invoices in one business:
35 ms -> 0.04 ms for the first page (docs/quality.md)."""
from __future__ import annotations

from sqlalchemy import create_engine, text

from app.core.config import get_settings


def _rows(sql: str) -> list[tuple]:
    eng = create_engine(get_settings().migration_database_url)
    try:
        with eng.connect() as conn:
            return [tuple(r) for r in conn.execute(text(sql))]
    finally:
        eng.dispose()


def test_every_foreign_key_has_an_index(migrated):
    unindexed = _rows("""
        select c.conrelid::regclass::text, a.attname
        from pg_constraint c
        join pg_attribute a on a.attrelid = c.conrelid and a.attnum = c.conkey[1]
        where c.contype = 'f' and c.connamespace = 'public'::regnamespace
          and not exists (select 1 from pg_index i where i.indrelid = c.conrelid and i.indkey[0] = c.conkey[1])
          and c.conrelid::regclass::text not like 'checkpoint%'
        order by 1, 2""")
    assert unindexed == []


def test_the_invoice_list_order_has_a_matching_index(migrated):
    defs = [r[0] for r in _rows("select indexdef from pg_indexes where tablename = 'invoices'")]
    assert any("(organization_id, created_at DESC NULLS LAST)" in d for d in defs), defs
