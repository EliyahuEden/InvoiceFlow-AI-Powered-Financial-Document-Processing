"use client";

import { Slot } from "@radix-ui/react-slot";
import { cva, type VariantProps } from "class-variance-authority";
import { Loader2 } from "lucide-react";
import { forwardRef, useEffect, useRef, useState } from "react";
import { extendTailwindMerge } from "tailwind-merge";
import { clsx, type ClassValue } from "clsx";

// Our custom type sizes (tailwind.config.ts fontSize) must be known as font sizes, or tailwind-merge takes
// "text-figure" for a colour and drops it whenever a text colour is merged in.
const twMerge = extendTailwindMerge({ extend: { classGroups: { "font-size": [{ text: ["2xs", "md", "figure", "display"] }] } } });

export function cx(...v: ClassValue[]) {
  return twMerge(clsx(v));
}

/* ---------------------------------------------------------------- Button */
const buttonStyles = cva(
  "inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-[12px] font-semibold select-none " +
  "transition-[background-color,border-color,color,box-shadow,transform] duration-150 ease-out active:scale-[.98] " +
  "disabled:pointer-events-none disabled:opacity-45 [&_svg]:shrink-0",
  {
    variants: {
      variant: {
        // the single primary action of a screen: the accent fill
        primary: "bg-primary text-primary-ink shadow-[inset_0_1px_0_rgb(255_255_255/.16),0_8px_20px_-8px_rgb(var(--primary)/.55)] hover:bg-primary-hover",
        secondary: "border border-line bg-surface text-ink shadow-[0_1px_2px_rgb(34_38_92/.05)] hover:border-line-strong/70 hover:bg-sunken",
        ghost: "text-ink-2 hover:bg-accent/[.07] hover:text-ink",
        danger: "border border-danger/30 bg-surface text-danger hover:bg-danger-soft",
        // AI actions look like any other action: no special colour or sparkle; their results are labelled AI
        ai: "border border-line bg-surface text-ink shadow-[0_1px_2px_rgb(34_38_92/.05)] hover:border-line-strong/70 hover:bg-sunken",
      },
      size: { sm: "h-8 px-3 text-sm", md: "h-10 px-4 text-base", lg: "h-12 px-5 text-md", icon: "h-10 w-10" },
    },
    defaultVariants: { variant: "secondary", size: "md" },
  },
);

type ButtonProps = React.ButtonHTMLAttributes<HTMLButtonElement> &
  VariantProps<typeof buttonStyles> & { asChild?: boolean; loading?: boolean };

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, asChild, loading, children, disabled, ...props }, ref) => {
    const Comp = asChild ? Slot : "button";
    return (
      <Comp ref={ref} className={cx(buttonStyles({ variant, size }), className)} disabled={disabled || loading} {...props}>
        {asChild ? children : (<>{loading && <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden />}{children}</>)}
      </Comp>
    );
  },
);
Button.displayName = "Button";

/* ---------------------------------------------------------------- Panel */
export function Panel({ className, children, ...p }: React.HTMLAttributes<HTMLElement>) {
  return (
    <section className={cx("command-panel", className)} {...p}>
      {children}
    </section>
  );
}

export function PanelHeader({ title, sub, actions, className }: {
  title: React.ReactNode; sub?: React.ReactNode; actions?: React.ReactNode; className?: string;
}) {
  return (
    <header className={cx("flex flex-wrap items-center justify-between gap-3 border-b border-line px-5 py-4", className)}>
      <div className="min-w-0">
        <h2 className="text-lg font-bold tracking-tight text-ink">{title}</h2>
        {sub && <p className="mt-0.5 text-sm text-ink-3">{sub}</p>}
      </div>
      {actions && <div className="flex max-w-full flex-wrap items-center gap-2">{actions}</div>}
    </header>
  );
}

/* ---------------------------------------------------------------- Inputs */
const field =
  "w-full rounded-[12px] border border-line bg-surface text-base text-ink placeholder:text-ink-3 shadow-[0_1px_2px_rgb(34_38_92/.04)] " +
  "transition-[border-color,box-shadow] hover:border-line-strong/60 focus:border-accent/70 focus:outline-none focus:ring-[3px] focus:ring-accent/20 " +
  "disabled:cursor-not-allowed disabled:opacity-60 aria-[invalid=true]:border-danger/60";

export const Input = forwardRef<HTMLInputElement, React.InputHTMLAttributes<HTMLInputElement>>(
  ({ className, ...p }, ref) => <input ref={ref} className={cx(field, "h-10 px-3.5", className)} {...p} />,
);
Input.displayName = "Input";

export const Textarea = forwardRef<HTMLTextAreaElement, React.TextareaHTMLAttributes<HTMLTextAreaElement>>(
  ({ className, ...p }, ref) => <textarea ref={ref} className={cx(field, "min-h-20 px-3 py-2", className)} {...p} />,
);
Textarea.displayName = "Textarea";

export function Select({ className, children, ...p }: React.SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <select className={cx(field, "h-10 w-auto pe-8 ps-3.5", className)} {...p}>
      {children}
    </select>
  );
}

export function Field({ label, hint, children, htmlFor }: { label: string; hint?: string; children: React.ReactNode; htmlFor?: string }) {
  return (
    <div className="space-y-1.5">
      <label htmlFor={htmlFor} className="block text-sm font-medium text-ink-2">{label}</label>
      {children}
      {hint && <p className="text-xs text-ink-3">{hint}</p>}
    </div>
  );
}

/* ---------------------------------------------------------------- Feedback */
export function Skeleton({ className }: { className?: string }) {
  return <div className={cx("skeleton h-4", className)} aria-hidden />;
}

export function EmptyState({ icon, title, body, action }: {
  icon?: React.ReactNode; title: string; body?: string; action?: React.ReactNode;
}) {
  return (
    <div className="flex flex-col items-center justify-center px-6 py-12 text-center">
      {icon && <div className="mb-3 grid h-12 w-12 place-items-center rounded-2xl border border-line bg-accent-soft text-accent [&_svg]:h-6 [&_svg]:w-6">{icon}</div>}
      <p className="text-base font-medium text-ink">{title}</p>
      {body && <p className="mt-1 max-w-md text-sm text-ink-3">{body}</p>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}

export function ErrorState({ message, onRetry, retryLabel = "Retry" }: { message: string; onRetry?: () => void; retryLabel?: string }) {
  return (
    <div role="alert" className="flex items-center justify-between gap-3 rounded-lg border border-danger/30 bg-danger-soft px-4 py-2.5 text-sm text-danger">
      <span>{message}</span>
      {onRetry && <Button size="sm" variant="danger" onClick={onRetry}>{retryLabel}</Button>}
    </div>
  );
}

/* ---------------------------------------------------------------- Table */
export function Table({ className, children }: { className?: string; children: React.ReactNode }) {
  // a table that scrolls sideways must be reachable by keyboard (WCAG 2.1.1); one that fits needs no extra tab stop
  const ref = useRef<HTMLDivElement>(null);
  const [scrolls, setScrolls] = useState(false);
  useEffect(() => {
    const el = ref.current;
    if (!el || typeof ResizeObserver === "undefined") return;
    const check = () => setScrolls(el.scrollWidth > el.clientWidth + 1);
    check();
    const ro = new ResizeObserver(check);
    ro.observe(el);
    return () => ro.disconnect();
  }, []);
  return (
    <div ref={ref} className={cx("command-table", className)} tabIndex={scrolls ? 0 : undefined}>
      <table className="w-full border-collapse text-start text-base">{children}</table>
    </div>
  );
}
export function Th({ className, children, ...p }: React.ThHTMLAttributes<HTMLTableCellElement>) {
  return (
    <th className={cx("sticky top-0 z-[1] h-10 whitespace-nowrap border-b border-line bg-sunken px-4 text-start text-sm font-semibold text-ink-3", className)} {...p}>
      {children}
    </th>
  );
}
export function Td({ className, children, ...p }: React.TdHTMLAttributes<HTMLTableCellElement>) {
  return <td className={cx("h-12 border-b border-line px-4 py-2 align-middle", className)} {...p}>{children}</td>;
}

/* ---------------------------------------------------------------- Key/value */
export function KV({ label, children, className }: { label: string; children: React.ReactNode; className?: string }) {
  return (
    <div className={cx("min-w-0", className)}>
      <dt className="text-xs text-ink-3">{label}</dt>
      <dd className="mt-0.5 truncate text-base text-ink">{children}</dd>
    </div>
  );
}
