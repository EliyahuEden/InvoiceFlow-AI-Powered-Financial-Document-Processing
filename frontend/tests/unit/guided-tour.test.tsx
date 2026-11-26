import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { GuidedTour, tourDone } from "@/components/guided-tour";
import { I18nProvider } from "@/lib/i18n";

// the elements the tour points at; upload is left out, as for a user without upload permission
const TARGETS = ["needs-review", "review-next", "nav-/exceptions", "nav-/invoices", "nav-/knowledge", "copilot", "tour"];

beforeEach(() => {
  localStorage.clear();
  for (const t of TARGETS) {
    const el = document.createElement("div");
    el.dataset.tour = t;
    el.getBoundingClientRect = () => ({ top: 10, left: 10, bottom: 50, right: 110, width: 100, height: 40, x: 10, y: 10, toJSON: () => ({}) });
    el.scrollIntoView = vi.fn();
    document.body.appendChild(el);
  }
});
afterEach(() => { cleanup(); document.body.innerHTML = ""; });

const show = (onClose = vi.fn(), locale: "en" | "he" = "en") =>
  render(<I18nProvider initial={locale}><GuidedTour userId="u1" onClose={onClose} /></I18nProvider>);

describe("guided tour", () => {
  it("walks through the steps and skips ones whose element is not on the page", () => {
    show();
    expect(screen.getByRole("dialog")).toHaveTextContent("Welcome to InvoiceFlow");
    expect(screen.getByText("1 of 8")).toBeVisible(); // nine steps, minus upload
    for (let i = 0; i < 4; i++) fireEvent.click(screen.getByRole("button", { name: "Next" }));
    expect(screen.getByRole("heading")).toHaveTextContent("Every invoice");
    expect(screen.queryByText("Add invoices")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Next" }));
    expect(screen.getByRole("heading")).toHaveTextContent("Ask about your agreements"); // upload was skipped
  });

  it("finishing remembers it, so it does not open again by itself", () => {
    const onClose = vi.fn();
    show(onClose);
    for (let i = 0; i < 7; i++) fireEvent.click(screen.getByRole("button", { name: "Next" }));
    fireEvent.click(screen.getByRole("button", { name: "Finish" }));
    expect(onClose).toHaveBeenCalled();
    expect(tourDone("u1")).toBe(true);
    expect(tourDone("someone-else")).toBe(false);
  });

  it("Escape ends the tour", () => {
    const onClose = vi.fn();
    show(onClose);
    fireEvent.keyDown(window, { key: "Escape" });
    expect(onClose).toHaveBeenCalled();
    expect(tourDone("u1")).toBe(true);
  });

  it("is translated to Hebrew", () => {
    show(vi.fn(), "he");
    expect(screen.getByRole("dialog")).toHaveTextContent("ברוכים הבאים ל-InvoiceFlow");
    expect(screen.getByRole("button", { name: "הבא" })).toBeVisible();
  });
});
