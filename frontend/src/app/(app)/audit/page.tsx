"use client";

import { ArrowRight, ChevronDown, Link2, ShieldCheck, ShieldX } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { toast } from "sonner";
import { ACTOR_ICON, actorTone, AuditDiff, auditHref, auditLabel, type AuditEntry } from "@/components/audit-list";
import { Pager, type Page } from "@/components/list";
import { CountBadge, DetailPanel, DetailSection, FilterBar, FilterSelect, PageHeader, useWideLayout } from "@/components/page-kit";
import { Button, cx, EmptyState, ErrorState, Panel, Skeleton } from "@/components/ui";
import { api, qs, useApi } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { label } from "@/lib/i18n/label";

// the event-type filter: each group is a set of action prefixes the API matches
const GROUPS = {
  groupInvoices: "invoice.", groupDecisions: "exception.,approval.", groupAgent: "agent.",
  groupRecords: "purchase_order.,goods_receipt.,supplier.", groupKnowledge: "knowledge.",
  groupAccess: "auth.,member.,legal.", groupWorkspace: "org.,sandbox.,export.,import.",
} as const;
const ENTITIES = ["invoice", "exception", "purchase_order", "agent_run", "knowledge_document", "user", "organization", "export"];

const dayKey = (iso: string) => { const d = new Date(iso); return `${d.getFullYear()}-${d.getMonth()}-${d.getDate()}`; };

export default function AuditPage() {
  const { t, locale } = useI18n();
  const wide = useWideLayout();
  const [actor, setActor] = useState("");
  const [group, setGroup] = useState("");
  const [entity, setEntity] = useState("");
  const [page, setPage] = useState(1);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [openId, setOpenId] = useState<string | null>(null);
  const [verify, setVerify] = useState<{ valid: boolean; checked: number } | null>(null);
  const [checking, setChecking] = useState(false);
  const action = group ? GROUPS[group as keyof typeof GROUPS] : "";
  const { data, error, mutate } = useApi<Page<AuditEntry>>(`/api/audit${qs({ actor_type: actor, action: action || undefined, entity_type: entity || undefined, page, page_size: 30 })}`);
  const selected = data?.items.find((a) => a.id === selectedId) ?? data?.items[0] ?? null;
  const active = [actor, group, entity].filter(Boolean).length;
  const reset = (fn: () => void) => { fn(); setPage(1); };
  const day = new Intl.DateTimeFormat(locale === "he" ? "he-IL" : "en-GB", { weekday: "long", day: "numeric", month: "long", year: "numeric" });
  const time = new Intl.DateTimeFormat(locale === "he" ? "he-IL" : "en-GB", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
  const dayLabel = (iso: string) => {
    const k = dayKey(iso);
    const today = new Date(); const yesterday = new Date(Date.now() - 86_400_000);
    return k === dayKey(today.toISOString()) ? t.audit.today : k === dayKey(yesterday.toISOString()) ? t.audit.yesterday : day.format(new Date(iso));
  };
  // the page's events, grouped by local day, in the order the API returns them (newest first)
  const days: { key: string; label: string; items: AuditEntry[] }[] = [];
  for (const a of data?.items ?? []) {
    const k = dayKey(a.created_at);
    const last = days[days.length - 1];
    if (last?.key === k) last.items.push(a); else days.push({ key: k, label: dayLabel(a.created_at), items: [a] });
  }

  return (
    <div className="min-w-0 space-y-5">
      <PageHeader title={t.audit.title} sub={t.audit.subtitle} actions={<>
        {verify && (verify.valid
          ? <span role="status" className="inline-flex items-center gap-1.5 rounded-full bg-ok-soft px-3 py-1.5 text-sm font-semibold text-ok"><ShieldCheck className="h-4 w-4" aria-hidden />{t.audit.valid} · {t.audit.checked.replace("{n}", String(verify.checked))}</span>
          : <span role="status" className="inline-flex items-center gap-1.5 rounded-full bg-danger-soft px-3 py-1.5 text-sm font-semibold text-danger"><ShieldX className="h-4 w-4" aria-hidden />{t.audit.broken}</span>)}
        <Button loading={checking} onClick={async () => {
          setChecking(true);
          try { setVerify(await api.get("/api/audit/verify")); }
          catch { setVerify(null); toast.error(t.common.error); } finally { setChecking(false); }
        }}><Link2 className="h-4 w-4" aria-hidden />{t.audit.verify}</Button>
      </>} />

      <div className="grid min-w-0 items-start gap-4 min-[1440px]:grid-cols-[minmax(0,1fr)_24rem]">
        <Panel className="min-w-0">
          <div className="flex flex-wrap items-center justify-between gap-3 px-5 pb-3 pt-4">
            <h2 className="flex items-center gap-2 text-lg font-bold tracking-tight text-ink">{t.audit.title}{data && <CountBadge>{data.total}</CountBadge>}</h2>
          </div>
          <FilterBar className="border-b border-line px-5 pb-4" active={active} onClear={active ? () => reset(() => { setActor(""); setGroup(""); setEntity(""); }) : undefined}
>
            <FilterSelect label={t.audit.eventType} value={group} onChange={(v) => reset(() => setGroup(v))}>
              <option value="">{t.common.all}</option>{Object.keys(GROUPS).map((g) => <option key={g} value={g}>{t.audit[g as keyof typeof GROUPS]}</option>)}
            </FilterSelect>
            <FilterSelect label={t.audit.actorType} value={actor} onChange={(v) => reset(() => setActor(v))}>
              <option value="">{t.common.all}</option><option value="user">{t.audit.actorUser}</option><option value="agent">{t.audit.actorAgent}</option><option value="system">{t.audit.actorSystem}</option>
            </FilterSelect>
            <FilterSelect label={t.audit.recordType} value={entity} onChange={(v) => reset(() => setEntity(v))}>
              <option value="">{t.common.all}</option>{ENTITIES.map((e) => <option key={e} value={e}>{label(t.auditEntities, e)}</option>)}
            </FilterSelect>
          </FilterBar>

          {error ? <div className="p-4"><ErrorState onRetry={() => mutate()} retryLabel={t.common.retry} message={error.status === 403 ? t.audit.noAccess : t.common.error} /></div>
            : !data ? <div className="space-y-3 p-5">{[0, 1, 2, 3, 4].map((i) => <Skeleton key={i} className="h-11 w-full" />)}</div>
            : data.items.length === 0 ? <EmptyState title={t.audit.empty} />
            : <div>{days.map((d) => <section key={d.key} aria-label={d.label}>
              <h3 className="sticky top-16 z-[2] flex items-center gap-2 border-y border-line bg-sunken/95 px-5 py-2 text-sm font-bold text-ink-2 backdrop-blur">
                {d.label}<span className="text-xs font-semibold text-ink-3">· {t.audit.eventsN.replace("{n}", String(d.items.length))}</span></h3>
              <ol className="divide-y divide-line">{d.items.map((a) => {
                const Icon = ACTOR_ICON[a.actor_type as keyof typeof ACTOR_ICON] ?? ACTOR_ICON.user;
                const href = auditHref(a);
                const isSelected = wide && selected?.id === a.id;
                const open = !wide && openId === a.id;
                return <li key={a.id} className={cx("transition-colors", isSelected ? "bg-accent/[.085]" : "hover:bg-accent/[.045]")}>
                  <button type="button" aria-pressed={wide ? isSelected : undefined} aria-expanded={wide ? undefined : open}
                    onClick={() => (wide ? setSelectedId(a.id) : setOpenId(open ? null : a.id))}
                    className="grid w-full grid-cols-[auto_minmax(0,1fr)_auto] items-center gap-x-3 gap-y-0.5 px-5 py-3 text-start sm:grid-cols-[auto_minmax(0,1.3fr)_minmax(0,1fr)_auto]">
                    <span className={cx("grid h-8 w-8 shrink-0 place-items-center rounded-full", actorTone(a.actor_type))}><Icon className="h-4 w-4" aria-hidden /></span>
                    <span className="min-w-0">
                      <span className="block truncate text-sm font-semibold text-ink">{auditLabel(t, a.action)}</span>
                      <span className="block truncate text-xs text-ink-3"><bdi>{a.actor_label ?? label({ user: t.audit.actorUser, agent: t.audit.actorAgent, system: t.audit.actorSystem }, a.actor_type)}</bdi></span>
                    </span>
                    <span className="col-span-2 col-start-2 row-start-2 min-w-0 truncate text-xs text-ink-2 sm:col-span-1 sm:col-start-auto sm:row-start-auto">{label(t.auditEntities, a.entity_type)}{href && <span className="text-ink-3"> · <bdi className="font-mono" dir="ltr">{(a.entity_id ?? String(a.meta?.invoice_id ?? "")).slice(0, 8)}</bdi></span>}</span>
                    <span className="col-start-3 row-start-1 flex items-center gap-2 justify-self-end text-xs text-ink-3 num sm:col-start-auto sm:row-start-auto">
                      <time dateTime={a.created_at}>{time.format(new Date(a.created_at))}</time>
                      {!wide && <ChevronDown className={cx("h-4 w-4 transition-transform", open && "rotate-180")} aria-hidden />}
                    </span>
                  </button>
                  {open && <div className="space-y-3 border-t border-line bg-sunken/40 px-5 py-4"><EventBody a={a} /></div>}
                </li>;
              })}</ol>
            </section>)}</div>}
          {data && data.items.length > 0 && <Pager page={data.page} pages={data.pages} total={data.total} onPage={setPage} />}
        </Panel>
        {wide && selected && <aside className="min-w-0 min-[1440px]:sticky min-[1440px]:top-20">
          <DetailPanel title={auditLabel(t, selected.action)}
            meta={<span className="inline-flex items-center gap-2 text-sm text-ink-2"><span className={cx("grid h-6 w-6 place-items-center rounded-full", actorTone(selected.actor_type))}>
              {(() => { const I = ACTOR_ICON[selected.actor_type as keyof typeof ACTOR_ICON] ?? ACTOR_ICON.user; return <I className="h-3 w-3" aria-hidden />; })()}</span>
              <bdi>{selected.actor_label ?? selected.actor_type}</bdi></span>}
            footer={auditHref(selected) ? <Button variant="secondary" className="w-full" asChild><Link href={auditHref(selected)!}>{label(t.auditEntities, selected.entity_type)}<ArrowRight className="h-4 w-4 rtl:rotate-180" aria-hidden /></Link></Button> : undefined}>
            <EventBody a={selected} />
          </DetailPanel>
        </aside>}
      </div>
    </div>
  );
}

/** What one event recorded: when (local and UTC), the record, the field changes, other details, and its place in the hash chain. */
function EventBody({ a }: { a: AuditEntry }) {
  const { t, locale } = useI18n();
  const at = new Date(a.created_at);
  const local = at.toLocaleString(locale === "he" ? "he-IL" : "en-GB", { dateStyle: "medium", timeStyle: "medium" });
  const href = auditHref(a);
  const details = Object.entries(a.meta ?? {});
  const row = (k: string, v: React.ReactNode) => <div className="flex items-baseline justify-between gap-3 py-1.5">
    <dt className="shrink-0 text-sm text-ink-3">{k}</dt><dd className="min-w-0 break-words text-end text-sm font-medium text-ink">{v}</dd></div>;
  return <>
    <dl className="divide-y divide-line">
      {row(t.audit.when, <time dateTime={a.created_at}>{local}</time>)}
      {row(t.audit.whenUtc, <bdi className="font-mono text-xs" dir="ltr">{a.created_at.replace("T", " ").slice(0, 19)}</bdi>)}
      {row(t.audit.record, href ? <Link href={href} className="text-accent hover:underline">{label(t.auditEntities, a.entity_type)}</Link> : label(t.auditEntities, a.entity_type))}
      {row(t.audit.action, <bdi className="font-mono text-xs" dir="ltr">{a.action}</bdi>)}
    </dl>
    <DetailSection title={t.audit.changes}><AuditDiff before={a.before} after={a.after} /></DetailSection>
    {details.length > 0 && <DetailSection title={t.audit.details}>
      <dl className="divide-y divide-line rounded-xl border border-line px-3">
        {details.map(([k, v]) => <div key={k} className="flex items-baseline justify-between gap-3 py-1.5 text-xs">
          <dt className="shrink-0 font-mono text-ink-3" dir="ltr">{k}</dt>
          <dd className="min-w-0 break-all text-end text-ink"><bdi dir="auto">{v !== null && typeof v === "object" ? JSON.stringify(v) : String(v)}</bdi></dd>
        </div>)}
      </dl>
    </DetailSection>}
    <DetailSection title={t.audit.chain}>
      <dl className="space-y-1.5 text-xs">
        <div><dt className="text-ink-3">{t.audit.hash}</dt><dd className="break-all font-mono text-ink-2" dir="ltr">{a.hash}</dd></div>
        <div><dt className="text-ink-3">{t.audit.prevHash}</dt><dd className="break-all font-mono text-ink-2" dir="ltr">{a.prev_hash ?? t.audit.genesis}</dd></div>
      </dl>
    </DetailSection>
  </>;
}
