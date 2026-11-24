// A keyboard key, e.g. Ctrl K. Its own module so importing it never pulls in the command palette (cmdk).
export function Kbd({ children }: { children: React.ReactNode }) {
  return <kbd className="inline-flex h-5 min-w-[1.25rem] items-center justify-center rounded border border-line bg-sunken px-1 font-mono text-2xs text-ink-3">{children}</kbd>;
}
