import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { CopilotPanel } from "@/components/copilot";
import { I18nProvider } from "@/lib/i18n";
import { at } from "../support/at";

const post = vi.fn();
let path = "/invoices/inv-9";
vi.mock("next/navigation", () => ({ usePathname: () => path, useRouter: () => ({ push: vi.fn() }) }));
vi.mock("@/lib/api", () => ({ api: { post: (p: string, b: unknown) => post(p, b) } }));
afterEach(() => { cleanup(); post.mockReset(); path = "/invoices/inv-9"; });

const reply = (over: Record<string, unknown> = {}) => ({
  answer: "Start with the Hermon invoice: billed 60 but only 50 received.",
  citations: [{ kind: "invoice", id: "inv-2", label: "HC-2026-0388", href: "/invoices/inv-2" }],
  follow_ups: ["Show the goods receipt"], steps: [{ tool: "review_queue", status: "ok", latency_ms: 12 }],
  mode: "llm:openai/gpt-oss-120b", language: "en", verified: true, ...over,
});

const panel = (locale: "en" | "he" = "en") =>
  render(<I18nProvider initial={locale}><CopilotPanel open onOpenChange={() => {}} /></I18nProvider>);

const askVia = (text: string) => {
  const box = screen.getByRole("textbox", { name: /Ask/ });
  fireEvent.change(box, { target: { value: text } });
  fireEvent.keyDown(box, { key: "Enter" });
};

describe("AP Copilot panel", () => {
  it("sends the question with the page context and shows the cited answer", async () => {
    post.mockResolvedValue(reply());
    panel();
    askVia("Why is this blocked?");
    await waitFor(() => expect(screen.getByText(/billed 60 but only 50 received/)).toBeVisible());
    expect(post).toHaveBeenCalledWith("/api/copilot/ask", expect.objectContaining({
      question: "Why is this blocked?", context: { invoice_id: "inv-9" }, history: [] }));
    expect(screen.getByRole("link", { name: /HC-2026-0388/ })).toHaveAttribute("href", "/invoices/inv-2");
  });

  it("shows which read-only tools ran", async () => {
    post.mockResolvedValue(reply());
    panel();
    askVia("What should I review first?");
    const steps = await screen.findByText(/Steps \(1\)/);
    fireEvent.click(steps);
    expect(within(steps.closest("details")!).getByText("review_queue")).toBeInTheDocument();
  });

  it("sends earlier turns as history and offers follow-ups", async () => {
    post.mockResolvedValue(reply());
    panel();
    askVia("What should I review first?");
    fireEvent.click(await screen.findByRole("button", { name: "Show the goods receipt" }));
    await waitFor(() => expect(post).toHaveBeenCalledTimes(2));
    expect(at(post.mock.calls, 1)[1].history).toEqual([
      { role: "user", content: "What should I review first?" },
      { role: "assistant", content: reply().answer }]);
  });

  it("starts from suggested questions and passes the case on an exception page", async () => {
    path = "/exceptions/exc-4";
    post.mockResolvedValue(reply());
    panel();
    fireEvent.click(screen.getByRole("button", { name: "What should I review first?" }));
    await waitFor(() => expect(post).toHaveBeenCalledWith("/api/copilot/ask", expect.objectContaining({
      context: { exception_id: "exc-4" } })));
  });

  it("marks an answer whose figures could not be verified", async () => {
    post.mockResolvedValue(reply({ verified: false, answer: "I could not write an answer whose figures all match the data." }));
    panel();
    askVia("How much is at risk?");
    expect(await screen.findByText("Not verified")).toBeVisible();
  });

  it("says it is read-only and is translated", () => {
    panel("he");
    expect(screen.getByText(/קריאה בלבד/)).toBeVisible();
  });

  it("reports a failed request without losing the question", async () => {
    post.mockRejectedValue(new Error("boom"));
    panel();
    askVia("What should I review first?");
    expect(await screen.findByRole("alert")).toBeVisible();
    expect(screen.getByText("What should I review first?")).toBeVisible();
  });
});
