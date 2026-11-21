import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { RulesFirstReport } from "@/components/rules-first";
import { I18nProvider } from "@/lib/i18n";

const router = { documents: 73, sent_to_llm: 12, with_errors: 29, errors_sent: 12, clean_sent: 0,
  share_sent_to_llm: 0.164, error_recall: 0.414, gap_counts: { total: 8, subtotal: 7, invoice_date: 4 } };
const measured = {
  llm: { model: "openai/gpt-oss-20b", provider: "openai", endpoint: "api.groq.com", max_output_tokens: 3000 },
  systems: {
    rule_based: { overall_field_accuracy: 0.92, rules_first_router: router, line_items: { f1: 0.944 } },
    rules_first: { overall_field_accuracy: 0.924, llm_calls: 12, llm_errors: 1, line_items: { f1: 0.94 },
      tokens: { input: 11535, output: 9079, per_call: 1718 } },
  },
};

const show = (r: unknown, locale: "en" | "he" = "en") =>
  render(<I18nProvider initial={locale}><RulesFirstReport r={r} /></I18nProvider>);

describe("rules-first report", () => {
  afterEach(cleanup);

  it("shows how many invoices reached the model and how many of those the rules had wrong", () => {
    show(measured);
    expect(screen.getByText("12 / 73")).toBeVisible();
    expect(screen.getByText("12 / 12")).toBeVisible();
    expect(screen.getByText("16.4%", { exact: false })).toBeVisible();
  });

  it("compares measured accuracy and names the model, endpoint, tokens and failed calls", () => {
    show(measured);
    expect(screen.getByText("92.0% → 92.4%")).toBeVisible();
    expect(screen.getByText(/openai\/gpt-oss-20b/)).toBeVisible();
    expect(screen.getByText(/api\.groq\.com/)).toBeVisible();
    expect(screen.getByText("1,718")).toBeVisible();
    expect(screen.getByText(/1 failed/)).toBeVisible();
  });

  it("lists why invoices were sent", () => {
    show(measured);
    expect(screen.getByText("total")).toBeVisible();
    expect(screen.getByText("invoice_date")).toBeVisible();
  });

  it("says the model run is pending instead of inventing numbers", () => {
    show({ systems: { rule_based: measured.systems.rule_based, rules_first: { skipped: "not requested" } } });
    expect(screen.getByText("12 / 73")).toBeVisible();
    expect(screen.queryByText(/→/)).toBeNull();
    expect(screen.getByText(/Not measured with a model yet/)).toBeVisible();
  });

  it("renders nothing for an older report without router data", () => {
    const { container } = show({ systems: { rule_based: { overall_field_accuracy: 0.9 } } });
    expect(container).toBeEmptyDOMElement();
  });

  it("is translated to Hebrew", () => {
    show(measured, "he");
    expect(screen.getByText("קודם כללים, מודל רק כשצריך")).toBeVisible();
  });
});
