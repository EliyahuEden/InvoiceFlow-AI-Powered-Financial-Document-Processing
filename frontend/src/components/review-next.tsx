"use client";

import { ArrowLeft } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import type { NextResp } from "@/lib/types";
import { Button } from "./ui";

/** Opens the highest-priority invoice the backend says this user can act on now. */
export function ReviewNextButton({ size = "md", after, className, variant = "primary" }: { size?: "sm" | "md" | "lg"; after?: string; className?: string; variant?: "primary" | "secondary" }) {
  const { t } = useI18n();
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const go = async () => {
    setBusy(true);
    try {
      const r = await api.get<NextResp>(`/api/review/next${after ? `?after=${after}` : ""}`);
      if (r.item) router.push(`/exceptions/${r.item.exception_id}`);
      else toast.success(t.review.clearTitle, { description: t.review.clearBody });
    } catch {
      toast.error(t.common.error);
    } finally {
      setBusy(false);
    }
  };
  return (
    <Button variant={variant} size={size} loading={busy} onClick={go} className={className} data-testid="review-next">
      {t.review.reviewNext}
      <ArrowLeft className="h-4 w-4 ltr:rotate-180" aria-hidden />
    </Button>
  );
}
