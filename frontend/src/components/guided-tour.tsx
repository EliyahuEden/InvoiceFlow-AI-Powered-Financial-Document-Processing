"use client";

import { X } from "lucide-react";
import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import { Button, cx } from "@/components/ui";
import { useI18n } from "@/lib/i18n";
import type { Dictionary } from "@/lib/i18n/dictionaries";

type StepKey = keyof Dictionary["tour"]["steps"];
/** Each step points at a real element marked data-tour="…"; a step without a target is a centred card. */
const STEPS: { key: StepKey; target?: string }[] = [
  { key: "welcome" },
  { key: "needsReview", target: "needs-review" },
  { key: "reviewNext", target: "review-next" },
  { key: "exceptions", target: "nav-/exceptions" },
  { key: "inbox", target: "nav-/invoices" },
  { key: "upload", target: "nav-/invoices/upload" },
  { key: "knowledge", target: "nav-/knowledge" },
  { key: "copilot", target: "copilot" },
  { key: "finish", target: "tour" },
];

const doneKey = (userId: string) => `if_tour_done:${userId}`;

export function tourDone(userId: string): boolean {
  // automated browsers (tests, screenshots) are never interrupted; the Tour button still opens it there
  if (typeof navigator !== "undefined" && navigator.webdriver) return true;
  try { return localStorage.getItem(doneKey(userId)) === "1"; } catch { return true; } // no storage: never nag
}

function markDone(userId: string) {
  try { localStorage.setItem(doneKey(userId), "1"); } catch { /* storage unavailable */ }
}

/** The element a step points at, when it is on the page and visible (the sidebar is hidden on phones). */
function visibleTarget(target?: string): HTMLElement | null {
  if (!target) return null;
  const el = document.querySelector<HTMLElement>(`[data-tour="${CSS.escape(target)}"]`);
  if (!el) return null;
  const r = el.getBoundingClientRect();
  return r.width > 0 && r.height > 0 ? el : null;
}

/** A short guided tour over the real screen: a spotlight on one element and a card that explains it.
 *  Steps whose element is not on the page at all (no permission) are skipped; on phones, where the sidebar is
 *  hidden, the card is shown centred instead. */
export function GuidedTour({ userId, onClose }: { userId: string; onClose: () => void }) {
  const { t, dir } = useI18n();
  // drop steps whose element does not exist for this user (for example upload without permission)
  const [steps] = useState(() => STEPS.filter((s) => !s.target || document.querySelector(`[data-tour="${CSS.escape(s.target)}"]`)));
  const [index, setIndex] = useState(0);
  const [rect, setRect] = useState<DOMRect | null>(null);
  const cardRef = useRef<HTMLDivElement>(null);
  const primaryRef = useRef<HTMLButtonElement>(null);
  const step = steps[index]!;
  const copy = t.tour.steps[step.key];
  const last = index === steps.length - 1;

  const close = useCallback(() => { markDone(userId); onClose(); }, [userId, onClose]);

  // follow the target: scroll it into view, then track its box through scrolling and resizing
  useLayoutEffect(() => {
    const el = visibleTarget(step.target);
    if (el) el.scrollIntoView({ block: "center", behavior: "smooth" });
    const measure = () => setRect(visibleTarget(step.target)?.getBoundingClientRect() ?? null);
    measure();
    const timer = window.setTimeout(measure, 350); // after the smooth scroll settles
    window.addEventListener("resize", measure);
    window.addEventListener("scroll", measure, true);
    return () => { window.clearTimeout(timer); window.removeEventListener("resize", measure); window.removeEventListener("scroll", measure, true); };
  }, [step.target]);

  useEffect(() => { primaryRef.current?.focus(); }, [index]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") { e.preventDefault(); close(); }
      // keep keyboard focus inside the card while the tour is open
      if (e.key === "Tab" && cardRef.current) {
        const items = cardRef.current.querySelectorAll<HTMLElement>("button");
        const first = items[0], lastItem = items[items.length - 1];
        if (e.shiftKey && document.activeElement === first) { e.preventDefault(); lastItem?.focus(); }
        else if (!e.shiftKey && document.activeElement === lastItem) { e.preventDefault(); first?.focus(); }
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [close]);

  const pad = 8;
  const vw = typeof window === "undefined" ? 1280 : window.innerWidth;
  const vh = typeof window === "undefined" ? 800 : window.innerHeight;
  const phone = vw < 640;
  const cardWidth = Math.min(380, vw - 32);
  // place the card under the target, or above it when there is no room; centred when there is no target
  let cardStyle: React.CSSProperties;
  if (!rect || phone) {
    cardStyle = phone ? { left: 16, right: 16, bottom: 16 } : { left: (vw - cardWidth) / 2, top: Math.max(24, vh / 2 - 140), width: cardWidth };
  } else {
    const below = rect.bottom + pad + 12;
    const top = below + 230 < vh ? below : Math.max(16, rect.top - pad - 12 - 230);
    const left = Math.min(Math.max(16, rect.left + rect.width / 2 - cardWidth / 2), vw - cardWidth - 16);
    cardStyle = { top, left, width: cardWidth };
  }

  return (
    <div className="fixed inset-0 z-[60]" dir={dir}>
      {/* dim everything except the spotlight; clicking the dimmed area does nothing, so a stray click never loses the tour */}
      {rect && !phone
        ? <div aria-hidden className="pointer-events-none fixed rounded-2xl ring-2 ring-accent/70 transition-[top,left,width,height] duration-300 ease-out motion-reduce:transition-none"
            style={{ top: rect.top - pad, left: rect.left - pad, width: rect.width + pad * 2, height: rect.height + pad * 2, boxShadow: "0 0 0 9999px rgb(15 17 40 / .55)" }} />
        : <div aria-hidden className="fixed inset-0 bg-[rgb(15_17_40/.55)]" />}
      <div ref={cardRef} role="dialog" aria-modal="true" aria-labelledby="tour-title" aria-describedby="tour-body"
        className="fixed rounded-2xl border border-line bg-surface p-5 shadow-pop" style={cardStyle}>
        <div className="flex items-start justify-between gap-3">
          <p className="text-xs font-semibold text-ink-3">{t.tour.step.replace("{n}", String(index + 1)).replace("{total}", String(steps.length))}</p>
          <button type="button" onClick={close} aria-label={t.tour.skip} className="-me-1.5 -mt-1.5 grid h-8 w-8 place-items-center rounded-lg text-ink-3 hover:bg-sunken hover:text-ink">
            <X className="h-4 w-4" aria-hidden />
          </button>
        </div>
        <h2 id="tour-title" className="mt-1 text-lg font-bold leading-snug text-ink">{copy.title}</h2>
        <p id="tour-body" className="mt-1.5 text-sm leading-relaxed text-ink-2">{copy.body}</p>
        <div className="mt-4 flex items-center gap-1.5" aria-hidden>
          {steps.map((s, i) => <span key={s.key} className={cx("h-1.5 rounded-full transition-all", i === index ? "w-5 bg-accent" : "w-1.5 bg-line-strong")} />)}
        </div>
        <div className="mt-4 flex items-center justify-between gap-2">
          {index === 0
            ? <Button variant="ghost" size="sm" onClick={close}>{t.tour.skip}</Button>
            : <Button variant="ghost" size="sm" onClick={() => setIndex(index - 1)}>{t.tour.back}</Button>}
          <Button ref={primaryRef} variant="primary" size="sm" onClick={() => (last ? close() : setIndex(index + 1))}>
            {last ? t.tour.done : t.tour.next}
          </Button>
        </div>
      </div>
    </div>
  );
}
