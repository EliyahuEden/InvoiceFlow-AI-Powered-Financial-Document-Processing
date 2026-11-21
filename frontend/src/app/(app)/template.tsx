"use client";

import { LazyMotion, domAnimation, m, useReducedMotion } from "motion/react";

/** A short, calm entrance for every page (re-mounted on navigation by the App Router).
 *  Figures are never animated; reduced-motion users get no movement at all. */
export default function PageTransition({ children }: { children: React.ReactNode }) {
  const reduce = useReducedMotion();
  return (
    <LazyMotion features={domAnimation} strict>
      <m.div
        initial={reduce ? false : { opacity: 0, y: 6 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.18, ease: [0.16, 1, 0.3, 1] }}
      >
        {children}
      </m.div>
    </LazyMotion>
  );
}
