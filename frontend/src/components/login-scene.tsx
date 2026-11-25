"use client";

import { AlertTriangle, Building2, CalendarDays, Check, ClipboardList, Coins, FileText, PackageCheck } from "lucide-react";
import { useEffect, useRef } from "react";
import { useI18n } from "@/lib/i18n";
import "./login-scene.css";
import { cx } from "./ui";

/*
  The sign-in scene: one real-looking invoice turning into structured, checked data.

  Built in CSS 3D (perspective, layered sheets, translateZ depth) rather than WebGL: it paints with the page, costs no
  extra bundle, needs no fallback and stays crisp. The stage is a size container, so every measurement is in cqw and
  the whole composition scales as one piece. Mouse parallax writes two CSS variables (--px, --py, -1..1) on the stage
  in an animation frame; nothing re-renders. Reduced motion, touch pointers and the compact (mobile) variant get the
  still composition.

  The data is one synthetic invoice from the demo set (HC-8870, Hermon Coffee Roasters) and never changes: it bills
  the espresso at 124 against 118 on the order, so the scene shows the goods receipt matching and the purchase order
  flagged, exactly what the product would report.
*/

const PARTICLES = [
  [8, 14, 2], [17, 71, 1.5], [24, 32, 1], [33, 86, 2], [41, 9, 1.5], [52, 77, 1], [59, 18, 2], [66, 92, 1.5],
  [73, 38, 1], [81, 12, 1.5], [88, 64, 2], [94, 28, 1], [12, 48, 1], [47, 55, 1.5], [70, 6, 1], [92, 84, 1.5],
] as const;

export function LoginScene({ compact = false, className }: { compact?: boolean; className?: string }) {
  const { t, dir } = useI18n();
  const s = t.login.scene;
  const stage = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const el = stage.current;
    if (!el || compact || typeof window.matchMedia !== "function") return; // no media queries: keep the still scene
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches || !window.matchMedia("(pointer: fine)").matches) return;
    let frame = 0;
    const host = el.parentElement ?? el;
    const move = (e: PointerEvent) => {
      const r = host.getBoundingClientRect();
      const px = Math.max(-1, Math.min(1, ((e.clientX - r.left) / r.width) * 2 - 1));
      const py = Math.max(-1, Math.min(1, ((e.clientY - r.top) / r.height) * 2 - 1));
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(() => { el.style.setProperty("--px", px.toFixed(3)); el.style.setProperty("--py", py.toFixed(3)); });
    };
    const leave = () => { cancelAnimationFrame(frame); el.style.setProperty("--px", "0"); el.style.setProperty("--py", "0"); };
    host.addEventListener("pointermove", move);
    host.addEventListener("pointerleave", leave);
    return () => { cancelAnimationFrame(frame); host.removeEventListener("pointermove", move); host.removeEventListener("pointerleave", leave); };
  }, [compact]);

  return (
    <div className={cx("login-scene relative isolate flex flex-col overflow-hidden", className)}>
      {/* atmosphere: two slow aurora glows, a light wave and a few still particles */}
      <div aria-hidden className="pointer-events-none absolute inset-0">
      <div className="login-glow login-glow-a" />
      <div className="login-glow login-glow-b" />
      <svg className="pointer-events-none absolute inset-x-0 bottom-0 h-[38%] w-full" viewBox="0 0 800 240" preserveAspectRatio="none">
        <defs>
          <linearGradient id="ls-wave" x1="0" x2="1">
            <stop offset="0" stopColor="#8580F7" stopOpacity="0" /><stop offset=".45" stopColor="#8580F7" stopOpacity=".55" />
            <stop offset=".8" stopColor="#67C7EA" stopOpacity=".55" /><stop offset="1" stopColor="#67C7EA" stopOpacity="0" />
          </linearGradient>
        </defs>
        <path d="M0 170 C 170 110, 330 230, 520 160 S 760 120, 800 140" fill="none" stroke="url(#ls-wave)" strokeWidth="1.4" />
        <path d="M0 196 C 190 150, 350 240, 540 186 S 770 160, 800 176" fill="none" stroke="url(#ls-wave)" strokeWidth=".8" opacity=".6" />
      </svg>
      {!compact && PARTICLES.map(([x, y, size], i) => (
        <span key={i} className="login-particle" style={{ insetInlineStart: `${x}%`, top: `${y}%`, width: size * 2, height: size * 2, animationDelay: `${(i % 6) * 0.9}s` }} />
      ))}
      </div>

      {/* the stage: decorative, scales with its width */}
      <div className="relative flex flex-1 items-center justify-center px-[4%]">
      <div ref={stage} aria-hidden dir="ltr" className={cx("login-stage relative", compact ? "login-stage-compact" : "")}>
        {!compact && (
          <svg className="absolute inset-0 h-full w-full overflow-visible" viewBox="0 0 680 440" preserveAspectRatio="none">
            <defs>
              <linearGradient id="ls-link" x1="0" x2="1">
                <stop offset="0" stopColor="#67C7EA" stopOpacity=".15" /><stop offset=".5" stopColor="#A9A6FF" stopOpacity=".9" />
                <stop offset="1" stopColor="#67C7EA" stopOpacity=".15" />
              </linearGradient>
            </defs>
            {/* invoice → extracted fields (right), invoice → order and receipt (left) */}
            {["M446 130 C 468 130, 458 110, 482 110", "M446 210 C 468 210, 458 205, 482 205", "M446 290 C 468 290, 458 300, 482 300",
              "M236 175 C 214 175, 222 150, 198 150", "M236 255 C 214 255, 222 272, 198 272"].map((d) => (
              <g key={d}>
                <path d={d} fill="none" stroke="url(#ls-link)" strokeWidth="1.6" vectorEffect="non-scaling-stroke" />
                <path d={d} fill="none" stroke="#E7E5FF" strokeWidth="2.2" strokeLinecap="round" vectorEffect="non-scaling-stroke"
                  className="login-link-pulse" pathLength={100} />
              </g>
            ))}
          </svg>
        )}

        {/* the documents, in 3D */}
        <div className="login-docs">
          <div className="login-sheet login-sheet-3" />
          <div className="login-sheet login-sheet-2" />
          <div className="login-sheet login-invoice">
            <div className="flex items-start justify-between" dir="rtl">
              <div>
                <p className="login-doc-title">{s.invoiceTitle}</p>
                <p className="login-doc-meta">{s.number} <span dir="ltr" className="login-hl login-hl-1">HC-8870</span></p>
                <p className="login-doc-meta">תאריך: <span dir="ltr" className="login-hl login-hl-2">25.10.2026</span></p>
              </div>
              <span className="login-doc-badge"><FileText strokeWidth={2} /></span>
            </div>
            <p className="login-doc-supplier login-hl login-hl-3" dir="rtl">חרמון קלייה בע״מ</p>
            <div className="login-doc-table" dir="rtl">
              {[["אספרסו בלנד הבית 1 ק״ג", "4,960.00"], ["נטול קפאין 1 ק״ג", "1,056.00"], ["מע״מ 18%", "1,082.88"]].map(([item, amount]) => (
                <div key={item} className="login-doc-row"><span>{item}</span><span dir="ltr">₪{amount}</span></div>
              ))}
            </div>
            <div className="login-doc-total" dir="rtl"><span>{s.total}</span><span dir="ltr" className="login-hl login-hl-4">₪7,098.88</span></div>
            {!compact && <span className="login-scan" />}
          </div>
          <span className="login-bracket login-bracket-tl" /><span className="login-bracket login-bracket-tr" />
          <span className="login-bracket login-bracket-bl" /><span className="login-bracket login-bracket-br" />
        </div>

        {/* extracted fields */}
        <Card className="login-card-amount" icon={Coins} label={s.amount} value="₪7,098.88" ltr />
        {!compact && <Card className="login-card-date" icon={CalendarDays} label={s.date} value="25.10.2026" ltr />}
        <Card className="login-card-supplier" icon={Building2} label={s.supplier} value="חרמון קלייה" />
        {/* matching against the order and the receipt: one passes, one is flagged */}
        {!compact && <Card className="login-card-po" icon={ClipboardList} label={s.po} value="PO-2026-1011" ltr status="flag" note={s.priceFlag} />}
        {!compact && <Card className="login-card-gr" icon={PackageCheck} label={s.gr} value="GR-5011" ltr status="ok" />}

        {!compact && (
          <ol className="login-steps" dir={dir}>
            {[s.extract, s.match, s.verify].map((step, i) => (
              <li key={step} className="login-step" style={{ animationDelay: `${i * 1.1}s` }}>{step}</li>
            ))}
          </ol>
        )}
      </div>
      </div>

      {!compact && (
        <div className="relative px-[7%] pb-[6%] text-center">
          <h2 className="text-[clamp(2.25rem,3.6vw,3.6rem)] font-extrabold leading-[1.05] tracking-[-0.03em] text-white">
            {s.headline.replace(/\.$/, "")}<span className="text-[#8FD8F2]">.</span>
          </h2>
          <p className="mx-auto mt-3 max-w-[34rem] text-[clamp(1rem,1.25vw,1.25rem)] leading-relaxed text-[#D3D0F7]">{s.sub}</p>
        </div>
      )}
    </div>
  );
}

function Card({ className, icon: Icon, label, value, ltr, status, note }: {
  className: string; icon: React.ElementType; label: string; value: string; ltr?: boolean; status?: "ok" | "flag"; note?: string;
}) {
  return (
    <div className={cx("login-card", className)} dir="rtl">
      <span className="login-card-icon"><Icon strokeWidth={1.8} /></span>
      <span className="min-w-0">
        <span className="login-card-label">{label}</span>
        <span className="login-card-value" dir={ltr ? "ltr" : "rtl"}>{value}</span>
        {note && <span className="login-card-note">{note}</span>}
      </span>
      {status === "ok" && <span className="login-card-status login-card-ok"><Check strokeWidth={3} /></span>}
      {status === "flag" && <span className="login-card-status login-card-flag"><AlertTriangle strokeWidth={2.4} /></span>}
    </div>
  );
}
