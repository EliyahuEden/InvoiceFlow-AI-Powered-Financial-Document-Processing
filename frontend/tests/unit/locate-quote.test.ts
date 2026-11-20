import { describe, expect, it } from "vitest";
import { locateQuote } from "@/components/document-viewer";

const words = [
  { t: "הספק", b: [0.5, 0.1, 0.6, 0.12], l: 0 }, { t: "יחייב", b: [0.4, 0.1, 0.49, 0.12], l: 0 },
  { t: "אך", b: [0.35, 0.1, 0.39, 0.12], l: 0 }, { t: "ורק", b: [0.3, 0.1, 0.34, 0.12], l: 0 },
  { t: "תנאי", b: [0.5, 0.3, 0.6, 0.32], l: 1 }, { t: "תשלום", b: [0.4, 0.3, 0.49, 0.32], l: 1 },
];

describe("locateQuote", () => {
  it("returns one box per matching line covering the matched words", () => {
    const boxes = locateQuote(words, "הספק יחייב אך ורק בגין כמות");
    expect(boxes).toHaveLength(1);
    expect(boxes[0]).toEqual([0.3, 0.1, 0.6, 0.12]);
  });
  it("ignores lines with only stray matches", () => {
    expect(locateQuote(words, "משהו אחר לגמרי")).toEqual([]);
  });
});
