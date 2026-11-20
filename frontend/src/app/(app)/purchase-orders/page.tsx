"use client";

import { ShoppingCart } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useState } from "react";
import { StatusPill } from "@/components/domain";
import { Pager, RowsSkeleton, SearchBox, Segmented, type Page } from "@/components/list";
import { PageHeader } from "@/components/shell";
import { EmptyState, Panel, Table, Td, Th } from "@/components/ui";
import { qs, useApi } from "@/lib/api";
import { date, money } from "@/lib/format";
import { useI18n } from "@/lib/i18n";

type PO = { id: string; po_number: string; supplier_name: string; supplier_name_en: string | null; order_date: string; currency: string;
  status: string; line_count: number; total: string };

export default function POsPage() {
  const { t, locale } = useI18n();
  const router = useRouter();
  const [q, setQ] = useState("");
  const [status, setStatus] = useState("");
  const [page, setPage] = useState(1);
  const { data, isLoading } = useApi<Page<PO>>(`/api/purchase-orders${qs({ q, status, page, page_size: 25 })}`);
  const onQ = useCallback((v: string) => { setQ(v); setPage(1); }, []);
  return (
    <div>
      <PageHeader title={t.pos.title} />
      <Panel>
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-line p-3">
          <Segmented value={status} onChange={(v) => { setStatus(v); setPage(1); }}
            options={["", "open", "partially_received", "received"].map((s) => ({ value: s, label: s ? (t.status as Record<string, string>)[s] : t.common.all }))} />
          <SearchBox value={q} onChange={onQ} placeholder={`${t.common.search}: ${t.pos.number}, ${t.common.supplier}`} />
        </div>
        <Table>
          <thead><tr><Th>{t.pos.number}</Th><Th>{t.common.supplier}</Th><Th>{t.common.date}</Th><Th className="text-end">{t.pos.lines}</Th>
            <Th className="text-end">{t.common.total}</Th><Th>{t.common.status}</Th></tr></thead>
          <tbody>
            {isLoading && !data ? <RowsSkeleton cols={6} /> : data?.items.map((p) => (
              <tr key={p.id} className="cursor-pointer hover:bg-sunken/70" onClick={() => router.push(`/purchase-orders/${p.id}`)}>
                <Td><Link href={`/purchase-orders/${p.id}`} className="ltr font-mono text-sm font-medium hover:text-accent" onClick={(e) => e.stopPropagation()}>{p.po_number}</Link></Td>
                <Td dir="auto">{locale === "en" && p.supplier_name_en ? p.supplier_name_en : p.supplier_name}</Td>
                <Td className="text-ink-2">{date(p.order_date, locale)}</Td>
                <Td className="text-end num">{p.line_count}</Td>
                <Td className="text-end font-medium"><span className="ltr">{money(p.total, p.currency)}</span></Td>
                <Td><StatusPill status={p.status} /></Td>
              </tr>
            ))}
          </tbody>
        </Table>
        {data && data.items.length === 0 && <EmptyState icon={<ShoppingCart className="h-8 w-8" />} title={t.common.noResults} />}
        {data && <Pager page={data.page} pages={data.pages} total={data.total} onPage={setPage} />}
      </Panel>
    </div>
  );
}
