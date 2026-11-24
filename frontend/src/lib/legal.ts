/**
 * Legal documents: the version a new business accepts at sign-up, and the operator's details shown in them.
 *
 * LEGAL_VERSION must equal LEGAL_VERSION in backend/app/core/legal.py (a backend test checks it). Bump both, and the
 * "last updated" date below, whenever the terms, privacy policy or data-processing agreement change materially.
 *
 * OPERATOR: the operator's details. An empty value is left out of the pages (with its label); a value in [brackets]
 * is shown as a highlighted placeholder, so an unfinished document is never mistaken for a finished one.
 */
export const LEGAL_VERSION = "2026-11-24";

export const LEGAL_UPDATED = { he: "24 בנובמבר 2026", en: "24 November 2026" };

export const OPERATOR = {
  /** who runs the service: a portfolio project with no registered business yet */
  name: { he: "InvoiceFlow (פרויקט עצמאי)", en: "InvoiceFlow (independent project)" },
  /** company number (ח.פ.) or dealer number (ע.מ.); empty until a business is registered, and then hidden */
  registrationNumber: "",
  address: { he: "", en: "" },
  email: "invoiceflowe@gmail.com",
  privacyEmail: "invoiceflowe@gmail.com",
  /** accessibility coordinator (רכז/ת נגישות) required by the Israeli accessibility regulations */
  accessibility: {
    name: { he: "צוות InvoiceFlow", en: "the InvoiceFlow team" },
    phone: "",
    email: "invoiceflowe@gmail.com",
  },
  /** where the servers run (for the privacy policy and the sub-processor list) */
  hosting: { he: "Oracle Cloud, ירושלים", en: "Oracle Cloud, Jerusalem" },
} as const;

/** True for a value that still needs to be filled in. */
export const isPlaceholder = (value: string) => value.startsWith("[") && value.endsWith("]");
