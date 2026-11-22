import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { DocumentViewer } from "@/components/document-viewer";
import { I18nProvider } from "@/lib/i18n";

vi.mock("@/lib/api", () => ({ useApi: () => ({ data: { page_count: 2, pages: [
  { page_no: 1, method: "ocr", ocr_confidence: null, words: [] },
  { page_no: 2, method: "ocr", ocr_confidence: 0, words: [] },
] } }) }));

afterEach(cleanup);

it("distinguishes unmeasured OCR confidence from a measured zero", () => {
  render(<I18nProvider initial="en"><DocumentViewer documentId="test" pageCount={2} /></I18nProvider>);
  expect(screen.getByText(/confidence.*unknown/i)).toBeVisible();
  fireEvent.click(screen.getByRole("button", { name: "Next" }));
  expect(screen.getByText(/confidence.*0%/i)).toBeVisible();
});

it("bounds an invalid citation page and allows image retry", () => {
  render(<I18nProvider initial="en"><DocumentViewer documentId="test" pageCount={2} quotePage={99} /></I18nProvider>);
  const image = screen.getByRole("img");
  expect(image).toHaveAttribute("src", expect.stringContaining("/pages/2/image"));
  fireEvent.error(image);
  fireEvent.click(screen.getByRole("button", { name: /retry/i }));
  expect(screen.getByRole("img")).not.toBe(image);
});
