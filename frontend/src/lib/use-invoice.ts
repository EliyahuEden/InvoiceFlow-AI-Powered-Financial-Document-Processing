"use client";

import { useParams } from "next/navigation";
import { useApi } from "@/lib/api";
import type { InvoiceDetail } from "@/lib/types";

export function useInvoice() {
  const { id } = useParams<{ id: string }>();
  return useApi<InvoiceDetail>(`/api/invoices/${id}`, {
    refreshInterval: (d) => (d?.status === "processing" || d?.agent_runs.some((r) => ["queued", "running"].includes(r.status)) ? 2500 : 0),
  });
}
