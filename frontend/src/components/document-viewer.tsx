"use client";

import { ChevronLeft, ChevronRight, Download, FileScan, Minus, Plus } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { useApi } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { Button, cx } from "./ui";

export type Highlight = { id: string; page: number; bbox: number[]; tone?: "field" | "active" | "finding" | "citation"; label?: string };

type Word = { t: string; b: number[]; l: number; c?: number | null };
type PagesResp = { page_count: number; pages: { page_no: number; method: string; ocr_confidence: number | null; words: Word[] }[] };

const norm = (s: string) => s.normalize("NFKC").replace(/[״"“”]/g, '"').replace(/[׳'’]/g, "'").replace(/\s+/g, "").toLowerCase();

/** Locate a quote on a page: group matching words by line and return one box per line. */
export function locateQuote(words: Word[], quote: string): number[][] {
  const tokens = new Set(quote.split(/\s+/).map(norm).filter((x) => x.length > 1));
  const byLine = new Map<number, Word[]>();
  for (const w of words) if (tokens.has(norm(w.t))) byLine.set(w.l, [...(byLine.get(w.l) ?? []), w]);
  // keep lines where a meaningful share of the line matched (avoid stray common words)
  const boxes: number[][] = [];
  for (const [line, ws] of byLine) {
    const lineWords = words.filter((w) => w.l === line).length;
    if (ws.length >= Math.min(3, tokens.size) || ws.length / lineWords > 0.5) {
      boxes.push([Math.min(...ws.map((w) => w.b[0])), Math.min(...ws.map((w) => w.b[1])),
        Math.max(...ws.map((w) => w.b[2])), Math.max(...ws.map((w) => w.b[3]))]);
    }
  }
  return boxes;
}

export function DocumentViewer({ documentId, pageCount = 1, highlights = [], activeId, page: controlledPage, onPage,
  quote, quotePage, filename, className }: {
  documentId: string; pageCount?: number; highlights?: Highlight[]; activeId?: string | null; page?: number;
  onPage?: (p: number) => void; quote?: string | null; quotePage?: number; filename?: string; className?: string;
}) {
  const { t } = useI18n();
  const [localPage, setLocalPage] = useState(quotePage ?? 1);
  const page = controlledPage ?? localPage;
  const setPage = (p: number) => { setLocalPage(p); onPage?.(p); };
  const [zoom, setZoom] = useState(1);
  const [loaded, setLoaded] = useState(false);
  const { data: pages } = useApi<PagesResp>(quote || pageCount > 0 ? `/api/documents/${documentId}/pages` : null);
  const pageInfo = pages?.pages.find((p) => p.page_no === page);

  const active = highlights.find((h) => h.id === activeId);
  // jump to the page of the hovered/focused field (only when the active highlight changes)
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { if (active && active.page !== page) setPage(active.page); }, [activeId]);
  useEffect(() => setLoaded(false), [page, documentId]);

  const quoteBoxes = useMemo(() => (quote && pageInfo ? locateQuote(pageInfo.words, quote) : []), [quote, pageInfo]);
  const shown = highlights.filter((h) => h.page === page && h.bbox?.length === 4);

  return (
    <div className={cx("flex flex-col overflow-hidden rounded-lg border border-line bg-sunken", className)}>
      <div className="flex items-center gap-2 border-b border-line bg-surface px-3 py-2">
        <span className="min-w-0 flex-1 truncate font-mono text-xs text-ink-2" dir="ltr">{filename}</span>
        {pageInfo && (
          <span className="inline-flex items-center gap-1 text-xs text-ink-3">
            <FileScan className="h-3.5 w-3.5" aria-hidden />
            {pageInfo.method === "ocr" ? `${t.invoice.ocr} · ${t.invoice.ocrConfidence} ${Math.round(pageInfo.ocr_confidence ?? 0)}%` : t.invoice.nativeText}
          </span>
        )}
        <div className="flex items-center gap-0.5">
          <Button size="icon" variant="ghost" onClick={() => setZoom((z) => Math.max(0.6, z - 0.2))} aria-label="Zoom out"><Minus className="h-4 w-4" /></Button>
          <span className="w-10 text-center text-xs text-ink-3 num">{Math.round(zoom * 100)}%</span>
          <Button size="icon" variant="ghost" onClick={() => setZoom((z) => Math.min(2.2, z + 0.2))} aria-label="Zoom in"><Plus className="h-4 w-4" /></Button>
        </div>
        {pageCount > 1 && (
          <div className="flex items-center gap-0.5 border-s border-line ps-2">
            <Button size="icon" variant="ghost" disabled={page <= 1} onClick={() => setPage(page - 1)} aria-label={t.common.previous}>
              <ChevronRight className="h-4 w-4 ltr:rotate-180" />
            </Button>
            <span className="text-xs text-ink-2 num">{page}/{pageCount}</span>
            <Button size="icon" variant="ghost" disabled={page >= pageCount} onClick={() => setPage(page + 1)} aria-label={t.common.next}>
              <ChevronLeft className="h-4 w-4 ltr:rotate-180" />
            </Button>
          </div>
        )}
        <Button asChild size="icon" variant="ghost" aria-label="Download original">
          <a href={`/api/documents/${documentId}/file`} target="_blank" rel="noreferrer"><Download className="h-4 w-4" /></a>
        </Button>
      </div>
      <div className="flex-1 overflow-auto p-4">
        <div className="relative mx-auto bg-surface shadow-raise" style={{ width: `${zoom * 100}%`, maxWidth: zoom > 1 ? "none" : "100%" }}>
          {!loaded && <div className="skeleton aspect-[1/1.414] w-full" />}
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            src={`/api/documents/${documentId}/pages/${page}/image?width=1200`}
            alt={`${filename ?? "document"} — ${t.invoice.page} ${page}`}
            className={cx("block w-full select-none", !loaded && "absolute inset-0 opacity-0")}
            onLoad={() => setLoaded(true)}
            draggable={false}
          />
          {loaded && shown.map((h) => (
            <div key={h.id} title={h.label}
              className={cx("pointer-events-none absolute rounded-[2px] transition-all duration-150",
                h.id === activeId ? "bg-hl/35 ring-2 ring-hl" :
                h.tone === "finding" ? "bg-danger/10 ring-1 ring-danger/50" : "bg-accent/[0.06] ring-1 ring-accent/25")}
              style={pad(h.bbox)} />
          ))}
          {loaded && quoteBoxes.map((b, i) => (
            <div key={i} className="pointer-events-none absolute rounded-[2px] bg-ai/15 ring-2 ring-ai/60" style={pad(b)} />
          ))}
        </div>
      </div>
    </div>
  );
}

function pad(b: number[]): React.CSSProperties {
  const p = 0.004;
  return { left: `${(b[0] - p) * 100}%`, top: `${(b[1] - p) * 100}%`, width: `${(b[2] - b[0] + 2 * p) * 100}%`, height: `${(b[3] - b[1] + 2 * p) * 100}%` };
}
