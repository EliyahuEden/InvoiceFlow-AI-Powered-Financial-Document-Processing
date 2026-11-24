"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import type { ComponentProps, MouseEvent } from "react";

/** The shared element's name: the queue row's title in the old view, the workspace heading in the new one. */
export const CASE_TITLE_VT = "case-title";

type ViewTransitionDocument = Document & { startViewTransition?: (cb: () => Promise<void>) => unknown };

/** Resolve once an element marked as the transition target exists (the workspace heading renders after its data). */
function waitForTarget(timeoutMs = 1200): Promise<void> {
  return new Promise((resolve) => {
    const start = performance.now();
    // timers, not animation frames: frames pause in a background tab and the browser would abort the transition
    const tick = () => {
      if (document.querySelector("[data-vt-target]") || performance.now() - start > timeoutMs) resolve();
      else window.setTimeout(tick, 16);
    };
    tick();
  });
}

/**
 * A link that opens a case with a shared-element transition: the row's title (the descendant marked
 * ``data-vt-source``) morphs into the workspace heading (marked ``data-vt-target``) while the rest crossfades.
 * Uses the browser's View Transitions API; without it, with reduced motion, or with a modifier key (new tab) it is
 * an ordinary link.
 */
export function TransitionLink({ href, onClick, ...props }: ComponentProps<typeof Link> & { href: string }) {
  const router = useRouter();
  const go = (event: MouseEvent<HTMLAnchorElement>) => {
    onClick?.(event);
    const doc = document as ViewTransitionDocument;
    if (event.defaultPrevented || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey
      || !doc.startViewTransition || window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    event.preventDefault();
    const source = event.currentTarget.querySelector<HTMLElement>("[data-vt-source]") ?? event.currentTarget;
    source.style.setProperty("view-transition-name", CASE_TITLE_VT);
    doc.startViewTransition(async () => {
      source.style.removeProperty("view-transition-name");
      router.push(href);
      await waitForTarget();
    });
  };
  return <Link href={href} onClick={go} {...props} />;
}
