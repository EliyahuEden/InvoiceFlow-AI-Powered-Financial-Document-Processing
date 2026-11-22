// A keyboard key, e.g. Ctrl K. Its own module so importing it never pulls in the command palette (cmdk).
export function Kbd({ children }: { children: React.ReactNode }) {
  return <kbd className="inline-flex min-w-[1.5rem] items-center justify-center rounded-md border border-line bg-surface px-1.5 py-0.5 font-sans text-[0.7rem] font-semibold text-ink-2 shadow-[0_1px_0_rgb(var(--line))]">{children}</kbd>;
}
