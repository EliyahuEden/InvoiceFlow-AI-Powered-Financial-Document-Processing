import { cleanup, fireEvent, render, renderHook, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { useUnsavedWork } from "@/lib/use-unsaved-work";

afterEach(() => { cleanup(); vi.restoreAllMocks(); });
describe("unsaved reviewer work", () => {
  it("cancels link navigation when the reviewer keeps editing", () => {
    vi.spyOn(window, "confirm").mockReturnValue(false);
    function Editor() { useUnsavedWork(true, "Leave unsaved work?"); return <a href="https://example.com/queue">Queue</a>; }
    render(<Editor />);
    expect(fireEvent.click(screen.getByRole("link", { name: "Queue" }))).toBe(false);
    expect(window.confirm).toHaveBeenCalledWith("Leave unsaved work?");
  });
  it("warns on reload only while dirty, and bypasses after a recorded decision", () => {
    const { result } = renderHook(() => useUnsavedWork(true, "Leave?"));
    const dirtyEvent = new Event("beforeunload", { cancelable: true });
    window.dispatchEvent(dirtyEvent);
    expect(dirtyEvent.defaultPrevented).toBe(true);
    result.current.allowNavigation();
    const savedEvent = new Event("beforeunload", { cancelable: true });
    window.dispatchEvent(savedEvent);
    expect(savedEvent.defaultPrevented).toBe(false);
  });
  it("guards the shell's programmatic Review next action", () => {
    const go = vi.fn();
    vi.spyOn(window, "confirm").mockReturnValue(false);
    function Editor() { useUnsavedWork(true, "Leave?"); return <button data-testid="review-next" onClick={go}>Next</button>; }
    render(<Editor />);
    fireEvent.click(screen.getByRole("button", { name: "Next" }));
    expect(go).not.toHaveBeenCalled();
    expect(window.confirm).toHaveBeenCalledWith("Leave?");
  });
  it("restores the editor URL when browser-back navigation is cancelled", () => {
    const current = window.location.href;
    vi.spyOn(window, "confirm").mockReturnValue(false);
    renderHook(() => useUnsavedWork(true, "Leave?"));
    window.history.pushState({}, "", "/exceptions");
    window.dispatchEvent(new PopStateEvent("popstate"));
    expect(window.location.href).toBe(current);
    expect(window.confirm).toHaveBeenCalledWith("Leave?");
  });
});
