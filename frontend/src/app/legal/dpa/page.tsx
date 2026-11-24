"use client";

import { LegalDocument } from "../_content/render";
import { dpa } from "../_content/dpa";

export default function Page() {
  return <LegalDocument doc={dpa} />;
}
