"use client";

import { useEffect, useState } from "react";
import { createPortal } from "react-dom";

type Line = { x1: number; y1: number; x2: number; y2: number };

/**
 * The evidence connector: a thin line from the evidence-trace row the reviewer picked to the highlighted box on the
 * source document, so a value is visibly traced to where it was read. It appears only on the three-column layout
 * (≥1280px), only while both ends are on screen and the box is inside the document's scroll region, and it follows
 * scrolling and resizing. Purely visual (aria-hidden, no pointer events): the row and the highlight carry the meaning.
 */
export function TraceConnector({ activeId }: { activeId: string | null }) {
  const [line, setLine] = useState<Line | null>(null);

  useEffect(() => {
    if (!activeId) { setLine(null); return; }
    let frame = 0;
    const measure = () => {
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(() => {
        const row = document.querySelector<HTMLElement>(`[data-trace-source="${CSS.escape(activeId)}"]`);
        const box = document.querySelector<HTMLElement>('[role="region"] [data-active="true"]');
        const region = box?.closest<HTMLElement>('[role="region"]');
        if (!row || !box || !region || !window.matchMedia("(min-width: 1280px)").matches) { setLine(null); return; }
        const a = row.getBoundingClientRect(), b = box.getBoundingClientRect(), r = region.getBoundingClientRect();
        const boxVisible = b.top >= r.top && b.bottom <= r.bottom && b.left >= r.left - 1 && b.right <= r.right + 1;
        const rowVisible = a.bottom > 0 && a.top < window.innerHeight;
        if (!boxVisible || !rowVisible) { setLine(null); return; }
        // leave the row from the side that faces the document, enter the box on its near side
        const docIsRight = b.left > a.right;
        setLine({
          x1: docIsRight ? a.right : a.left, y1: a.top + a.height / 2,
          x2: docIsRight ? b.left : b.right, y2: b.top + b.height / 2,
        });
      });
    };
    measure();
    // the box is placed after the document zooms and scrolls; measure again once that has settled
    const settle = window.setTimeout(measure, 300);
    window.addEventListener("scroll", measure, true);
    window.addEventListener("resize", measure);
    return () => {
      cancelAnimationFrame(frame);
      window.clearTimeout(settle);
      window.removeEventListener("scroll", measure, true);
      window.removeEventListener("resize", measure);
    };
  }, [activeId]);

  if (!line) return null;
  const mid = (line.x1 + line.x2) / 2;
  const d = `M ${line.x1} ${line.y1} C ${mid} ${line.y1}, ${mid} ${line.y2}, ${line.x2} ${line.y2}`;
  // portalled to <body>: any transformed ancestor would otherwise become the fixed box's containing block
  return createPortal(
    <svg aria-hidden className="pointer-events-none fixed inset-0 z-30 h-full w-full overflow-visible">
      <path d={d} className="fill-none stroke-accent" strokeWidth={1.5} strokeDasharray="4 4" strokeLinecap="round" />
      <circle cx={line.x1} cy={line.y1} r={3.5} className="fill-accent" />
      <circle cx={line.x2} cy={line.y2} r={3.5} className="fill-surface stroke-accent" strokeWidth={1.5} />
    </svg>,
    document.body,
  );
}
