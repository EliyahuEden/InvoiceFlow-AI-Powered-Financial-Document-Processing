import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { DecisionPanel } from "@/components/decision-panel";
import { I18nProvider } from "@/lib/i18n";

const base = {
  proposedAction: "accept_variance", allowedActions: ["accept_variance"], note: "", override: "", target: "",
  onNote: vi.fn(), onOverride: vi.fn(), onTarget: vi.fn(), onDecide: vi.fn(),
  busy: null, canDecide: true, canRequestInfo: true, restricted: false,
};
function show(props: Partial<typeof base> = {}) {
  return render(<I18nProvider initial="en"><DecisionPanel {...base} {...props} /></I18nProvider>);
}
afterEach(cleanup);
beforeEach(() => vi.clearAllMocks());
describe("review decision requirements", () => {
  it("requires a reviewer note for rejection and escalation", () => {
    show();
    expect(screen.getByRole("button", { name: /Reject/ })).toBeDisabled();
    expect(screen.getByRole("button", { name: /Escalate/ })).toBeDisabled();
    expect(screen.getByRole("button", { name: /Approve/ })).toBeEnabled();
  });
  it("requires both a note and a clarification target", () => {
    const { rerender } = show({ note: "Please confirm receipt" });
    expect(screen.getByRole("button", { name: /Request information/ })).toBeDisabled();
    rerender(<I18nProvider initial="en"><DecisionPanel {...base} note="Please confirm receipt" target="procurement" /></I18nProvider>);
    fireEvent.click(screen.getByRole("button", { name: /Request information/ }));
    expect(base.onDecide).toHaveBeenCalledWith("request_info");
  });
  it("does not offer approval of an escalation to its author or a finance reviewer", () => {
    show({ restricted: true, note: "Reviewed", target: "supplier" });
    expect(screen.queryByRole("button", { name: /Approve/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Reject/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Request information/ })).not.toBeInTheDocument();
  });
});
