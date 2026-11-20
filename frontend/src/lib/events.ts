"use client";

import { useEffect } from "react";
import { useSWRConfig } from "swr";

export type LiveEvent = { event: string; data: Record<string, unknown> };

const REFRESH_PREFIXES = ["/api/invoices", "/api/exceptions", "/api/dashboard", "/api/agent", "/api/knowledge"];

/**
 * Subscribe to server-sent events for the organization. Every event is re-broadcast
 * on `window` as `if:event` (for progress UIs) and relevant SWR caches are revalidated.
 * If the stream is unavailable the UI keeps working through normal fetches/polling.
 */
export function useLiveEvents() {
  const { mutate } = useSWRConfig();
  useEffect(() => {
    let es: EventSource | null = null;
    let timer: ReturnType<typeof setTimeout> | undefined;
    let debounce: ReturnType<typeof setTimeout> | undefined;
    const connect = () => {
      es = new EventSource("/api/events", { withCredentials: true });
      const handler = (ev: MessageEvent, name: string) => {
        let data: Record<string, unknown> = {};
        try { data = JSON.parse(ev.data); } catch { /* ignore */ }
        window.dispatchEvent(new CustomEvent<LiveEvent>("if:event", { detail: { event: name, data } }));
        if (name !== "job.progress" && name !== "ping" && name !== "ready") {
          clearTimeout(debounce);
          debounce = setTimeout(() => {
            mutate((key) => typeof key === "string" && REFRESH_PREFIXES.some((p) => key.startsWith(p)));
          }, 300);
        }
      };
      for (const name of ["ready", "job.progress", "job.completed", "job.failed", "job.retrying", "invoice.updated",
        "exception.updated", "agent.updated"]) {
        es.addEventListener(name, (ev) => handler(ev as MessageEvent, name));
      }
      es.onerror = () => {
        es?.close();
        timer = setTimeout(connect, 5000);
      };
    };
    connect();
    return () => { es?.close(); clearTimeout(timer); clearTimeout(debounce); };
  }, [mutate]);
}

export function onLiveEvent(cb: (e: LiveEvent) => void): () => void {
  const h = (ev: Event) => cb((ev as CustomEvent<LiveEvent>).detail);
  window.addEventListener("if:event", h);
  return () => window.removeEventListener("if:event", h);
}
