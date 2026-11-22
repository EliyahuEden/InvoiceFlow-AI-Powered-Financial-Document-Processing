import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { SeverityDot } from "@/components/domain";
import { I18nProvider } from "@/lib/i18n";

describe("accessible names", () => {
  afterEach(cleanup);
  it("a severity dot is not colour alone: it is a named image in the reader's language", () => {
    render(<I18nProvider initial="he"><SeverityDot severity="critical" /></I18nProvider>);
    expect(screen.getByRole("img", { name: "קריטי" })).toBeTruthy();
    cleanup();
    render(<I18nProvider initial="en"><SeverityDot severity="warning" /></I18nProvider>);
    expect(screen.getByRole("img", { name: "Warning" })).toBeTruthy();
  });
});
