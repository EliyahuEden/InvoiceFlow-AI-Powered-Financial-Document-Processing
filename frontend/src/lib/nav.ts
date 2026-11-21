"use client";

import {
  Activity, BookOpenText, Bot, Building2, ClipboardCheck, FlaskConical, Gauge, Inbox, ScrollText, Settings, ShoppingCart, Upload,
} from "lucide-react";
import { useSession } from "@/components/session";
import { useI18n } from "@/lib/i18n";

export type NavItem = { href: string; label: string; icon: React.ElementType; perm?: string; key?: string };
export type NavGroup = { group: string; items: NavItem[] };

/** Every destination, filtered by the backend-provided permissions. `key` is the "g <key>" shortcut. */
export function useNav(): NavGroup[] {
  const { t } = useI18n();
  const { can } = useSession();
  const groups: NavGroup[] = [
    { group: t.nav.work, items: [
      { href: "/", label: t.nav.overview, icon: Gauge, key: "d" },
      { href: "/exceptions", label: t.nav.exceptions, icon: ClipboardCheck, key: "q" },
      { href: "/invoices", label: t.nav.inbox, icon: Inbox, key: "i" },
      { href: "/invoices/upload", label: t.nav.upload, icon: Upload, perm: "invoice:upload", key: "u" },
      { href: "/investigations", label: t.nav.investigations, icon: Bot },
    ]},
    { group: t.nav.records, items: [
      { href: "/suppliers", label: t.nav.suppliers, icon: Building2, key: "s" },
      { href: "/purchase-orders", label: t.nav.purchaseOrders, icon: ShoppingCart, key: "p" },
      { href: "/knowledge", label: t.nav.knowledge, icon: BookOpenText, key: "k" },
    ]},
    { group: t.nav.quality, items: [
      { href: "/evaluation", label: t.nav.evaluation, icon: FlaskConical },
      { href: "/observability", label: t.nav.observability, icon: Activity },
      { href: "/audit", label: t.nav.audit, icon: ScrollText, perm: "audit:read" },
    ]},
    { group: t.nav.admin, items: [{ href: "/settings", label: t.nav.settings, icon: Settings }] },
  ];
  return groups.map((g) => ({ ...g, items: g.items.filter((i) => !i.perm || can(i.perm)) })).filter((g) => g.items.length);
}

export function isActive(path: string, href: string) {
  if (href === "/") return path === "/";
  if (href === "/invoices") return path === "/invoices" || (path.startsWith("/invoices/") && !path.startsWith("/invoices/upload"));
  return path === href || path.startsWith(href + "/");
}

/** True while the user is typing, so single-key shortcuts never hijack text entry. */
export function isTyping(target: EventTarget | null): boolean {
  const el = target as HTMLElement | null;
  if (!el) return false;
  return el.isContentEditable || ["INPUT", "TEXTAREA", "SELECT"].includes(el.tagName);
}
