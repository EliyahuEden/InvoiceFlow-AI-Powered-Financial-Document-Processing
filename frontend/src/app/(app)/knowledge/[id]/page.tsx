"use client";

import { useParams } from "next/navigation";
import { useState } from "react";
import { DocumentViewer } from "@/components/document-viewer";
import { PageHeader } from "@/components/shell";
import { cx, Panel, PanelHeader, Skeleton } from "@/components/ui";
import { useApi } from "@/lib/api";
import { useI18n } from "@/lib/i18n";

type KD = { id: string; title: string; doc_type: string; document_id: string; version: string | null; effective_date: string | null;
  chunks: { id: string; index: number; page: number; section: string | null; text: string; strategy: string }[] };

export default function KnowledgeDoc() {
  const { t } = useI18n();
  const { id } = useParams<{ id: string }>();
  const { data: d } = useApi<KD>(`/api/knowledge/documents/${id}`);
  const { data: pages } = useApi<{ page_count: number }>(d ? `/api/documents/${d.document_id}/pages` : null);
  const [active, setActive] = useState<string | null>(null);
  if (!d) return <Skeleton className="h-96 w-full" />;
  const chunk = d.chunks.find((c) => c.id === active);
  return (
    <div>
      <PageHeader back={{ href: "/knowledge", label: t.knowledge.title }} title={<span dir="auto">{d.title}</span>}
        sub={`${(t.knowledge.type as Record<string, string>)[d.doc_type]} · ${t.knowledge.version} ${d.version ?? "—"} · ${t.knowledge.effective} ${d.effective_date ?? "—"}`} />
      <div className="grid gap-5 xl:grid-cols-2">
        <DocumentViewer className="h-[calc(100vh-12rem)] min-h-[520px]" documentId={d.document_id} pageCount={pages?.page_count ?? 1}
          filename={d.title} quote={chunk?.text.split("\n").slice(1).join(" ") || chunk?.text} quotePage={chunk?.page}
          page={chunk?.page} />
        <Panel>
          <PanelHeader title={`${t.knowledge.chunks} (${d.chunks.length})`} sub={d.chunks[0]?.strategy} />
          <ol className="max-h-[calc(100vh-16rem)] divide-y divide-line overflow-y-auto">
            {d.chunks.map((c) => (
              <li key={c.id}>
                <button onClick={() => setActive(c.id)} className={cx("w-full px-4 py-3 text-start hover:bg-sunken/60", active === c.id && "bg-ai-soft/50")}>
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
