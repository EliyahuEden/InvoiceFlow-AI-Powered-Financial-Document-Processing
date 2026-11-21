"use client";

import * as Dialog from "@radix-ui/react-dialog";
import { X } from "lucide-react";
import { useI18n } from "@/lib/i18n";
import { Kbd } from "./command-palette";
import { Button } from "./ui";

/** "?" overlay listing every shortcut. Financial decisions never have a single-key shortcut. */
export function ShortcutsDialog({ open, onOpenChange }: { open: boolean; onOpenChange: (open: boolean) => void }) {
  const { t } = useI18n();
  const mod = typeof navigator !== "undefined" && /Mac|iPhone|iPad/.test(navigator.platform) ? "⌘" : "Ctrl";
  const groups: [string, [string[], string][]][] = [
    [t.shortcuts.general, [[[mod, "K"], t.shortcuts.open], [["?"], t.shortcuts.help]]],
    [t.shortcuts.navigation, [[["G", "D"], t.shortcuts.gotoDashboard], [["G", "Q"], t.shortcuts.gotoQueue], [["G", "I"], t.shortcuts.gotoInbox],
      [["G", "S"], t.nav.suppliers], [["G", "P"], t.nav.purchaseOrders], [["G", "K"], t.nav.knowledge]]],
    [t.shortcuts.workspace, [[["N"], t.shortcuts.nextItem], [["E"], t.shortcuts.evidence], [["D"], t.shortcuts.decision]]],
  ];
  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-50 bg-ink/30 backdrop-blur-[3px]" />
        <Dialog.Content aria-label={t.shortcuts.title} aria-describedby={undefined}
          className="fixed inset-x-3 top-[10vh] z-50 mx-auto max-h-[80vh] max-w-[560px] overflow-y-auto rounded-xl border border-line bg-surface p-6 shadow-pop data-[state=open]:animate-[palette-in_180ms_cubic-bezier(.16,1,.3,1)]">
          <div className="mb-4 flex items-center justify-between">
            <Dialog.Title className="text-xl font-semibold tracking-tight text-ink">{t.shortcuts.title}</Dialog.Title>
            <Dialog.Close asChild><Button variant="ghost" size="icon" aria-label={t.common.close}><X className="h-5 w-5" /></Button></Dialog.Close>
          </div>
          <div className="space-y-5">
            {groups.map(([heading, rows]) => (
              <section key={heading}>
                <h3 className="mb-2 text-xs font-semibold text-ink-3">{heading}</h3>
                <ul className="divide-y divide-line rounded-2xl border border-line">
                  {rows.map(([keys, label]) => (
                    <li key={label} className="flex items-center justify-between gap-4 px-4 py-2.5 text-sm text-ink-2">
                      <span>{label}</span>
                      <span className="flex shrink-0 items-center gap-1" dir="ltr">{keys.map((k) => <Kbd key={k}>{k}</Kbd>)}</span>
                    </li>
                  ))}
                </ul>
              </section>
            ))}
          </div>
          <p className="mt-4 text-xs text-ink-3">{t.shortcuts.safety}</p>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
