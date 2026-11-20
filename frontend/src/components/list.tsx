"use client";

import { ChevronLeft, ChevronRight, Search } from "lucide-react";
import { useEffect, useState } from "react";
import { useI18n } from "@/lib/i18n";
import { Button, cx, Input } from "./ui";

export type Page<T> = { items: T[]; total: number; page: number; page_size: number; pages: number };

export function SearchBox({ value, onChange, placeholder }: { value: string; onChange: (v: string) => void; placeholder?: string }) {
  const [local, setLocal] = useState(value);
  useEffect(() => setLocal(value), [value]);
  useEffect(() => {
    const id = setTimeout(() => local !== value && onChange(local), 300);
    return () => clearTimeout(id);
  }, [local, value, onChange]);
  return (
    <div className="relative w-full max-w-xs">
      <Search className="pointer-events-none absolute start-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-ink-3" aria-hidden />
      <Input value={local} onChange={(e) => setLocal(e.target.value)} placeholder={placeholder} className="ps-8" aria-label={placeholder} />
    </div>
  );
}

export function Segmented({ options, value, onChange }: {
  options: { value: string; label: string; count?: number }[]; value: string; onChange: (v: string) => void;
}) {
  return (
    <div role="tablist" className="inline-flex flex-wrap gap-1 rounded-md bg-sunken p-1">
      {options.map((o) => (
        <button key={o.value} role="tab" aria-selected={value === o.value} onClick={() => onChange(o.value)}
          className={cx("inline-flex h-7 items-center gap-1.5 rounded px-2.5 text-sm transition-colors",
            value === o.value ? "bg-surface font-medium text-ink shadow-raise" : "text-ink-2 hover:text-ink")}>
          {o.label}
          {o.count !== undefined && <span className="text-xs text-ink-3 num">{o.count}</span>}
        </button>
      ))}
    </div>
  );
}

export function Pager({ page, pages, total, onPage }: { page: number; pages: number; total: number; onPage: (p: number) => void }) {
  const { t } = useI18n();
  if (pages <= 1) return <p className="border-t border-line px-4 py-2.5 text-xs text-ink-3">{t.common.total}: <span className="num">{total}</span></p>;
  return (
    <div className="flex items-center justify-between border-t border-line px-4 py-2.5 text-sm text-ink-2">
      <span>{t.common.page} {page} {t.common.of} {pages} · <span className="num">{total}</span></span>
      <div className="flex gap-1.5">
        <Button size="sm" variant="secondary" disabled={page <= 1} onClick={() => onPage(page - 1)} aria-label={t.common.previous}>
          <ChevronRight className="h-4 w-4 ltr:rotate-180" />
        </Button>
        <Button size="sm" variant="secondary" disabled={page >= pages} onClick={() => onPage(page + 1)} aria-label={t.common.next}>
          <ChevronLeft className="h-4 w-4 ltr:rotate-180" />
        </Button>
      </div>
    </div>
  );
}

export function RowsSkeleton({ cols, rows = 8 }: { cols: number; rows?: number }) {
  return (
    <>
      {Array.from({ length: rows }).map((_, r) => (
        <tr key={r}>
          {Array.from({ length: cols }).map((__, c) => (
            <td key={c} className="border-b border-line px-3 py-3"><div className="skeleton h-3.5 w-3/4" /></td>
          ))}
        </tr>
      ))}
    </>
  );
}
