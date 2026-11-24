import { useId } from "react";

/** The InvoiceFlow mark: two slanted ledger bars in the Aurora indigo-to-violet, drawn as geometry (no raster). */
export function LogoMark({ className = "h-7 w-7" }: { className?: string }) {
  const id = useId();
  return (
    <svg viewBox="0 0 32 32" className={className} aria-hidden focusable="false">
      <defs>
        <linearGradient id={`${id}-a`} x1="0" y1="1" x2="1" y2="0">
          <stop offset="0" stopColor="#6a5ae0" />
          <stop offset="1" stopColor="#a78bfa" />
        </linearGradient>
        <linearGradient id={`${id}-b`} x1="0" y1="1" x2="1" y2="0">
          <stop offset="0" stopColor="#4f46e5" />
          <stop offset="1" stopColor="#818cf8" />
        </linearGradient>
      </defs>
      <path d="M9.5 27 L15.5 5 H21 L15 27 Z" fill={`url(#${id}-b)`} />
      <path d="M17.5 27 L23.5 5 H29 L23 27 Z" fill={`url(#${id}-a)`} opacity=".85" />
      <path d="M3 27 L6.6 14 H12 L8.4 27 Z" fill={`url(#${id}-a)`} opacity=".55" />
    </svg>
  );
}
