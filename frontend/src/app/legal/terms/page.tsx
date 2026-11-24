"use client";

import { LegalDocument } from "../_content/render";
import { terms } from "../_content/terms";

export default function Page() {
  return <LegalDocument doc={terms} />;
}
