"use client";

import { useEffect, useRef } from "react";

/** Protect the current draft across links, browser history, reload and controlled navigation. */
export function useUnsavedWork(dirty: boolean, message: string) {
  const state = useRef({ dirty, message, allowed: false });
  state.current.dirty = dirty;
  state.current.message = message;
  useEffect(() => {
    const currentUrl = window.location.href;
    const currentHistory = window.history.state;
    const needsPrompt = () => state.current.dirty && !state.current.allowed;
    const beforeUnload = (event: BeforeUnloadEvent) => {
      if (needsPrompt()) { event.preventDefault(); event.returnValue = ""; }
    };
    const onClick = (event: MouseEvent) => {
      if (event.defaultPrevented || event.button !== 0 || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
      const target = event.target as Element;
      const link = target.closest?.("a[href]") as HTMLAnchorElement | null;
      const nextButton = target.closest?.('[data-testid="review-next"]');
      if (!nextButton && (!link || link.target === "_blank" || link.hasAttribute("download") || link.href === window.location.href)) return;
      if (needsPrompt() && !window.confirm(state.current.message)) {
        event.preventDefault(); event.stopPropagation();
      }
    };
    const onPopState = (event: PopStateEvent) => {
      if (needsPrompt() && !window.confirm(state.current.message)) {
        event.stopImmediatePropagation();
        window.history.pushState(currentHistory, "", currentUrl);
      }
    };
    window.addEventListener("beforeunload", beforeUnload);
    document.addEventListener("click", onClick, true);
    window.addEventListener("popstate", onPopState, true);
    return () => {
      window.removeEventListener("beforeunload", beforeUnload);
      document.removeEventListener("click", onClick, true);
      window.removeEventListener("popstate", onPopState, true);
    };
  }, []);
  return {
    confirmNavigation: () => !state.current.dirty || state.current.allowed || window.confirm(state.current.message),
    allowNavigation: () => { state.current.allowed = true; },
  };
}
