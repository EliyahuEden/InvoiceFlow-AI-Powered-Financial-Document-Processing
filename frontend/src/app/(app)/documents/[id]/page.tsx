"use client";

import { useParams, useRouter, useSearchParams } from "next/navigation";
import { Suspense } from "react";
import { DocumentViewer } from "@/components/document-viewer";
import { PageHeader } from "@/components/shell";
import { Skeleton } from "@/components/ui";
import { useApi } from "@/lib/api";
import { useI18n } from "@/lib/i18n";

/** Source viewer opened from an AI citation: jumps to the page and highlights the quoted passage. */
function Viewer() {
  const { t } = useI18n();
  const { id } = useParams<{ id: string }>();
  const params = useSearchParams();
  const router = useRouter();
  const page = Number(params.get("page") ?? 1);
  const quote = params.get("q");
  const title = params.get("title");
  const { data } = useApi<{ page_count: number; filename: string }>(`/api/documents/${id}/pages`);
  return (
    <div>
      <PageHeader title={<span dir="auto" className="break-all">{title ?? data?.filename ?? "…"}</span>}
        sub={quote ? <span dir="auto" className="text-ai">“{quote}”</span> : undefined}
        actions={<button className="text-sm text-ink-3 hover:text-accent" onClick={() => router.back()}>{t.common.back}</button>} />
      {!data ? <Skeleton className="h-[70vh] w-full" /> : (
        <DocumentViewer className="h-[calc(100vh-13rem)] min-h-[520px]" documentId={id} pageCount={data.page_count}
          filename={data.filename} quote={quote} quotePage={page} />
      )}
    </div>
  );
}

export default function DocumentPage() {
  return <Suspense><Viewer /></Suspense>;
}
