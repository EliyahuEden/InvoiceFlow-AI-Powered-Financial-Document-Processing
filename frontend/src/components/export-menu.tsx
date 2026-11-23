"use client";

import * as Menu from "@radix-ui/react-dropdown-menu";
import { Download } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";
import { useSession } from "@/components/session";
import { Button } from "@/components/ui";
import { downloadFile, qs } from "@/lib/api";
import { useI18n } from "@/lib/i18n";

const item = "flex cursor-pointer select-none items-center rounded-md px-2.5 py-2 text-sm text-ink outline-none data-[highlighted]:bg-sunken";

/** Exports the invoice list as filtered on screen, and (for finance) approved invoices for accounting. */
export function ExportMenu({ filters }: { filters: Record<string, string | undefined> }) {
  const { t, locale } = useI18n();
  const { can } = useSession();
  const m = t.exports;
  const [busy, setBusy] = useState(false);
  const save = async (path: string, name: string) => {
    setBusy(true);
    try {
      await downloadFile(path, name);
    } catch {
      toast.error(t.common.error);
    } finally {
      setBusy(false);
    }
  };
  const day = new Date().toISOString().slice(0, 10);
  const list = (fmt: "csv" | "xlsx") =>
    save(`/api/export/invoices.${fmt}${qs({ ...filters, lang: locale })}`, `invoices-${day}.${fmt}`);
  const accounting = (fmt: "csv" | "xlsx") =>
    save(`/api/export/accounting.${fmt}${qs({ lang: locale })}`, `accounting-${day}.${fmt}`);

  return (
    <Menu.Root>
      <Menu.Trigger asChild>
        <Button loading={busy}><Download className="h-4 w-4" aria-hidden />{m.open}</Button>
      </Menu.Trigger>
      <Menu.Portal>
        <Menu.Content align="end" sideOffset={6}
          className="z-50 min-w-[240px] rounded-lg border border-line bg-surface p-1 shadow-pop data-[state=open]:animate-[fade_120ms_ease-out]">
          <Menu.Label className="px-2.5 pb-1 pt-1.5 text-xs text-ink-3">{m.list}</Menu.Label>
          <Menu.Item className={item} onSelect={() => list("xlsx")}>{m.excel}</Menu.Item>
          <Menu.Item className={item} onSelect={() => list("csv")}>{m.csv}</Menu.Item>
          {can("approval:decide") && (
            <>
              <Menu.Separator className="my-1 h-px bg-line" />
              <Menu.Label className="px-2.5 pb-1 pt-1.5 text-xs text-ink-3">{m.accounting}</Menu.Label>
              <Menu.Item className={item} onSelect={() => accounting("xlsx")}>{m.excel}</Menu.Item>
              <Menu.Item className={item} onSelect={() => accounting("csv")}>{m.csv}</Menu.Item>
            </>
          )}
        </Menu.Content>
      </Menu.Portal>
    </Menu.Root>
  );
}
