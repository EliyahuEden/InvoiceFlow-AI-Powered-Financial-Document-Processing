"use client";

import { Slot } from "@radix-ui/react-slot";
import { cva, type VariantProps } from "class-variance-authority";
import { Loader2 } from "lucide-react";
import { forwardRef } from "react";
import { twMerge } from "tailwind-merge";
import { clsx, type ClassValue } from "clsx";

export function cx(...v: ClassValue[]) {
  return twMerge(clsx(v));
}

/* ---------------------------------------------------------------- Button */
const buttonStyles = cva(
  "inline-flex items-center justify-center gap-1.5 whitespace-nowrap rounded-md font-medium select-none " +
  "transition-[background-color,border-color,color,box-shadow,transform] duration-150 ease-out active:scale-[.98] " +
  "disabled:pointer-events-none disabled:opacity-45 [&_svg]:shrink-0",
  {
    variants: {
      variant: {
        // the single primary action of a screen: the accent fill
        primary: "bg-primary text-primary-ink shadow-[inset_0_1px_0_rgb(255_255_255/.14),0_1px_2px_rgb(0_0_0/.25)] hover:bg-primary-hover",
        secondary: "border border-line bg-raised text-ink hover:border-line-strong/70 hover:bg-sunken",
        ghost: "text-ink-2 hover:bg-ink/[.06] hover:text-ink",
        danger: "border border-danger/35 bg-raised text-danger hover:bg-danger-soft",
        // AI actions look like any other action: no special colour or sparkle; their results are labelled AI
        ai: "border border-line bg-raised text-ink hover:border-line-strong/70 hover:bg-sunken",
      },
      size: { sm: "h-7 px-2.5 text-sm", md: "h-8 px-3 text-base", lg: "h-10 px-4 text-md", icon: "h-8 w-8" },
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
    <header className={cx("flex flex-wrap items-center justify-between gap-3 border-b border-line px-4 py-3", className)}>
      <div className="min-w-0">
        <h2 className="text-md font-medium tracking-tight text-ink">{title}</h2>
        {sub && <p className="mt-0.5 text-sm text-ink-3">{sub}</p>}
      </div>
      {actions && <div className="flex max-w-full flex-wrap items-center gap-2">{actions}</div>}
    </header>
  );
}

/* ---------------------------------------------------------------- Inputs */
const field =
  "w-full rounded-md border border-line bg-bg/60 text-base text-ink placeholder:text-ink-3 shadow-[inset_0_1px_0_rgb(0_0_0/.12)] " +
  "transition-[border-color,box-shadow] hover:border-line-strong/60 focus:border-accent/70 focus:outline-none focus:ring-[3px] focus:ring-accent/20 " +
  "disabled:cursor-not-allowed disabled:opacity-60 aria-[invalid=true]:border-danger/60";

export const Input = forwardRef<HTMLInputElement, React.InputHTMLAttributes<HTMLInputElement>>(
  ({ className, ...p }, ref) => <input ref={ref} className={cx(field, "h-9 px-3", className)} {...p} />,
);
Input.displayName = "Input";

export const Textarea = forwardRef<HTMLTextAreaElement, React.TextareaHTMLAttributes<HTMLTextAreaElement>>(
  ({ className, ...p }, ref) => <textarea ref={ref} className={cx(field, "min-h-20 px-3 py-2", className)} {...p} />,
);
Textarea.displayName = "Textarea";

export function Select({ className, children, ...p }: React.SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <select className={cx(field, "h-9 w-auto pe-8 ps-3", className)} {...p}>
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
      {icon && <div className="mb-3 grid h-10 w-10 place-items-center rounded-lg border border-line bg-raised text-ink-3 [&_svg]:h-5 [&_svg]:w-5">{icon}</div>}
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
  return (
    <div className={cx("command-table", className)}>
      <table className="w-full border-collapse text-start text-base">{children}</table>
    </div>
  );
}
export function Th({ className, children, ...p }: React.ThHTMLAttributes<HTMLTableCellElement>) {
  return (
    <th className={cx("sticky top-0 z-[1] h-9 whitespace-nowrap border-b border-line bg-surface px-4 text-start text-xs font-medium text-ink-3", className)} {...p}>
      {children}
    </th>
  );
}
export function Td({ className, children, ...p }: React.TdHTMLAttributes<HTMLTableCellElement>) {
  return <td className={cx("h-11 border-b border-line px-4 py-2 align-middle", className)} {...p}>{children}</td>;
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
