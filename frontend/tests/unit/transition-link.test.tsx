import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

const push = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ push }) }));
import { TransitionLink } from "@/components/transition-link";

/** Install (or remove) a stand-in for the browser's View Transitions API. */
const setVT = (fn: unknown) => Object.defineProperty(document, "startViewTransition", { value: fn, configurable: true, writable: true });

describe("queue row → workspace transition", () => {
  afterEach(() => { cleanup(); push.mockReset(); setVT(undefined); });
  const setMotion = (reduce: boolean) => {
    window.matchMedia = ((q: string) => ({ matches: reduce && q.includes("reduce"), media: q, addEventListener() {}, removeEventListener() {} })) as never;
  };

  it("morphs the row's invoice number into the heading through a view transition", async () => {
    setMotion(false);
    let run: (() => Promise<void>) | undefined;
    setVT((cb: () => Promise<void>) => { run = cb; return {}; });
    render(<TransitionLink href="/exceptions/1"><span data-vt-source>HC-8841</span></TransitionLink>);
    const source = screen.getByText("HC-8841");
    fireEvent.click(screen.getByRole("link"));
    expect(source.style.getPropertyValue("view-transition-name")).toBe("case-title"); // named for the old snapshot
    const heading = document.createElement("h1");
    heading.setAttribute("data-vt-target", "");
    document.body.append(heading);
    await run!();
    expect(push).toHaveBeenCalledWith("/exceptions/1");
    expect(source.style.getPropertyValue("view-transition-name")).toBe(""); // and released before the new one
    heading.remove();
  });

  it("is a plain link with reduced motion, without the API, or with a modifier key", () => {
    setMotion(true);
    const start = vi.fn();
    setVT(start);
    render(<TransitionLink href="/exceptions/2">case</TransitionLink>);
    fireEvent.click(screen.getByRole("link"));
    expect(start).not.toHaveBeenCalled();
    setMotion(false);
    fireEvent.click(screen.getByRole("link"), { ctrlKey: true });
    expect(start).not.toHaveBeenCalled();
  });
});
