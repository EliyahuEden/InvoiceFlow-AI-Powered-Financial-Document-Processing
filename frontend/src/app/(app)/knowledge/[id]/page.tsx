"use client";

import { useParams } from "next/navigation";
import { useState } from "react";
import { StatusPill } from "@/components/domain";
import { DocumentViewer } from "@/components/document-viewer";
import { PageHeader } from "@/components/shell";
import { cx, ErrorState, Panel, PanelHeader, Skeleton } from "@/components/ui";
import { useApi } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { label } from "@/lib/i18n/label";

type KD = { status: string; language: string | null; id: string; title: string; doc_type: string; document_id: string; version: string | null; effective_date: string | null;
  chunks: { id: string; index: number; page: number; section: string | null; text: string; strategy: string }[] };

export default function KnowledgeDoc() {
  const { t } = useI18n();
  const { id } = useParams<{ id: string }>();
  const { data: d, error, mutate } = useApi<KD>(`/api/knowledge/documents/${id}`);
  const { data: pages } = useApi<{ page_count: number }>(d ? `/api/documents/${d.document_id}/pages` : null);
  const [active, setActive] = useState<string | null>(null);
  if (error) return <ErrorState message={t.common.error} retryLabel={t.common.retry} onRetry={() => mutate()} />;
  if (!d) return <Skeleton className="h-96 w-full" />;
  const chunk = d.chunks.find((c) => c.id === active);
  return (
    <div className="space-y-4">
      <PageHeader back={{ href: "/knowledge", label: t.knowledge.title }} title={<span dir="auto">{d.title}</span>}
        actions={<StatusPill status={d.status} />}
        sub={`${label(t.knowledge.type, d.doc_type)} · ${t.knowledge.version} ${d.version ?? "—"} · ${t.knowledge.effective} ${d.effective_date ?? "—"}`} />
      <div className="grid grid-cols-1 gap-5 xl:grid-cols-2">
        <DocumentViewer className="h-[52svh] min-h-72 xl:h-[calc(100vh-14rem)] xl:min-h-96" documentId={d.document_id} pageCount={pages?.page_count ?? 1}
          filename={d.title} quote={chunk?.text.split("\n").slice(1).join(" ") || chunk?.text} quotePage={chunk?.page}
          page={chunk?.page} />
        <Panel className="min-w-0 self-start">
          <PanelHeader title={`${t.knowledge.chunks} (${d.chunks.length})`} sub={[d.chunks[0]?.strategy, d.language?.toUpperCase()].filter(Boolean).join(" · ")} />
          <ol className="max-h-[calc(100vh-16rem)] divide-y divide-line overflow-y-auto">
            {d.chunks.map((c) => (
              <li key={c.id}>
                <button aria-pressed={active === c.id} onClick={() => setActive(c.id)} className={cx("w-full px-4 py-3 text-start hover:bg-sunken/60", active === c.id && "bg-accent-soft")}>
                  <p className="text-xs text-ink-3">#{c.index} · {t.common.page_short} {c.page}{c.section && ` · ${c.section}`}</p>
                  <p className="mt-1 line-clamp-3 whitespace-pre-line text-sm text-ink" dir="auto">{c.text}</p>
                </button>
              </li>
            ))}
          </ol>
        </Panel>
      </div>
    </div>
  );
}
