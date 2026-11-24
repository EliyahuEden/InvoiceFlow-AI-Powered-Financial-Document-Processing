/** A legal document in both languages. Text may contain {tokens} filled from OPERATOR in lib/legal.ts. */
export type LegalSection = { h: string; p?: string[]; li?: string[] };
export type LegalText = { title: string; intro: string; sections: LegalSection[] };
export type LegalDoc = { he: LegalText; en: LegalText };
