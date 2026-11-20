import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { AiBlock, StatusPill } from "@/components/domain";
import { I18nProvider } from "@/lib/i18n";

describe("domain components", () => {
  afterEach(cleanup);
  it("keeps workflow states distinct from critical risk and AI output", () => {
    render(<I18nProvider initial="en"><StatusPill status="open" /><StatusPill status="reconciled" /><StatusPill status="awaiting_approval" /></I18nProvider>);
    expect(screen.getByText("Open")).not.toHaveClass("text-danger");
    expect(screen.getByText("Ready for approval")).toHaveClass("text-ok");
    expect(screen.getByText("Awaiting decision")).not.toHaveClass("text-ai");
  });
  it("renders localized status labels (never colour alone)", () => {
    render(<I18nProvider initial="he"><StatusPill status="exception" /></I18nProvider>);
    expect(screen.getByText("חריגה")).toBeInTheDocument();
  });
  it("labels AI output and its offline mode", () => {
    render(<I18nProvider initial="en"><AiBlock mode="offline-template">text</AiBlock></I18nProvider>);
    expect(screen.getByText("AI-generated")).toBeInTheDocument();
    expect(screen.getByText("Template (offline)")).toBeInTheDocument();
    expect(screen.getByText(/Advisory only/)).toBeInTheDocument();
  });
});
