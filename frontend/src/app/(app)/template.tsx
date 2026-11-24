/** A short, calm entrance for every page (re-mounted on navigation by the App Router).
 *  Pure CSS, so the server and client render the same markup; the global reduced-motion rule turns it off. */
export default function PageTransition({ children }: { children: React.ReactNode }) {
  return <div className="animate-[rise_180ms_cubic-bezier(0.16,1,0.3,1)_backwards]">{children}</div>;
}
