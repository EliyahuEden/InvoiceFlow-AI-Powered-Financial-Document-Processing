import type { LegalDoc } from "./types";

/** Terms of use. Tokens in {braces} are filled from OPERATOR in lib/legal.ts. */
export const terms: LegalDoc = {
  he: {
    title: "תנאי שימוש",
    intro: "תנאים אלה חלים על השימוש בשירות InvoiceFlow. בהרשמה לשירות או בשימוש בו את/ה מסכים/ה להם בשם העסק שלך. אם אינך מסכים/ה, אין להשתמש בשירות.",
    sections: [
      { h: "הצדדים", p: [
        "השירות מופעל על ידי {name}, {reg}, {address} (\"המפעיל\"). \"הלקוח\" הוא העסק שנרשם לשירות, ו\"משתמש\" הוא כל אדם שהלקוח הזמין לסביבת העבודה שלו.",
      ] },
      { h: "השירות", p: [
        "InvoiceFlow מסייע לקרוא חשבוניות ספקים, להתאים אותן להזמנות רכש ולתעודות קבלה, לנהל חריגות ואישורים ולתעד החלטות. השירות הוא כלי עזר. האחריות על ההחלטות העסקיות, החשבונאיות והמיסויות, ועל ביצוע התשלומים, היא של הלקוח.",
      ] },
      { h: "הרשמה וחשבון", li: [
        "השירות מיועד לעסקים ולמשתמשים מגיל 18 ומעלה. הנרשם מצהיר שהוא מוסמך לפעול בשם העסק.",
        "יש למסור פרטים נכונים ולשמור על סודיות הסיסמה. מומלץ להפעיל אימות דו-שלבי.",
        "הלקוח אחראי לפעולות שמבוצעות בחשבונו, ולמי שהוא מזמין לצוות ולהרשאות שהוא נותן.",
      ] },
      { h: "שימוש מותר", p: ["אסור להשתמש בשירות כדי:"], li: [
        "להעלות תוכן בלתי חוקי, או מידע שאין ללקוח זכות לעבד.",
        "לפגוע באבטחת השירות, לנסות לגשת לנתונים של לקוחות אחרים או לעקוף מגבלות.",
        "להעמיס על השירות באופן חריג, להפעיל אותו בכלים אוטומטיים שלא אושרו, או להנדס אותו לאחור.",
        "להטעות, להונות או לבצע פעולה כספית בניגוד לדין.",
      ] },
      { h: "המידע של הלקוח", p: [
        "המידע שהלקוח מעלה שייך ללקוח. הלקוח מעניק למפעיל רשות לעבד אותו רק לצורך מתן השירות, לפי מדיניות הפרטיות והסכם עיבוד הנתונים, המהווים חלק מתנאים אלה.",
        "הלקוח אחראי לכך שיש לו בסיס חוקי להעלאת המידע, כולל מידע אישי על ספקים ועובדים.",
        "בכל עת ניתן להוריד ארכיון של הנתונים ולמחוק את סביבת העבודה מתוך ההגדרות.",
      ] },
      { h: "בינה מלאכותית", p: [
        "חלק מהיכולות מבוססות על מודלי שפה. התוצרים שלהן (סיכומים, הסברים, תשובות והצעות) מסומנים כייעוץ בלבד, עלולים להיות שגויים ואינם ייעוץ משפטי, חשבונאי, מיסויי או פיננסי. יש לבדוק אותם לפני הסתמכות. סכומים והתאמות מחושבים בכללים קבועים, וכל החלטה מתקבלת על ידי אדם.",
      ] },
      { h: "זמינות ושינויים", p: [
        "המפעיל ישתדל שהשירות יהיה זמין ותקין, אך אינו מתחייב לזמינות רציפה או ללא תקלות. השירות עשוי להשתנות, להתעדכן או להיות מושבת לתחזוקה. שינוי מהותי לרעה יימסר מראש ככל האפשר.",
      ] },
      { h: "תשלום", p: [
        "השירות ניתן כרגע ללא תשלום. אם יוצעו תוכניות בתשלום, המחירים והתנאים יפורסמו מראש, ולא ייגבה תשלום ללא הסכמה מפורשת.",
      ] },
      { h: "קניין רוחני", p: [
        "כל הזכויות בשירות, בקוד, בעיצוב ובסימנים שייכות למפעיל. אין להעתיק, להפיץ או ליצור יצירות נגזרות מהשירות ללא רשות בכתב, למעט ככל שהדין מתיר.",
      ] },
      { h: "הגבלת אחריות", p: [
        "השירות ניתן כמות שהוא (AS IS). ככל שהדין מתיר, המפעיל לא יישא באחריות לנזק עקיף, תוצאתי או לאובדן רווחים, נתונים או מוניטין, ובכל מקרה האחריות הכוללת שלו מוגבלת לסכום ששולם לו בעד השירות ב-12 החודשים שקדמו לאירוע. אין באמור כדי לגרוע מאחריות שלא ניתן להגביל לפי דין.",
      ] },
      { h: "שיפוי", p: [
        "הלקוח ישפה את המפעיל על נזק או הוצאה סבירים שנגרמו עקב שימוש בניגוד לתנאים אלה או לדין, או עקב מידע שהלקוח העלה ללא זכות, לאחר שהמפעיל הודיע לו על הדרישה ואפשר לו להתגונן.",
      ] },
      { h: "סיום", p: [
        "הלקוח רשאי להפסיק את השימוש ולמחוק את סביבת העבודה בכל עת. המפעיל רשאי להשעות או לסיים חשבון שמפר תנאים אלה, ובמקרים אחרים בהודעה מוקדמת סבירה שתאפשר להוריד את הנתונים.",
      ] },
      { h: "שינוי התנאים", p: [
        "המפעיל רשאי לעדכן תנאים אלה. שינוי מהותי יפורסם באתר ויימסר למנהלי החשבונות לפחות 14 יום לפני כניסתו לתוקף. המשך שימוש לאחר מכן מהווה הסכמה. תאריך העדכון האחרון: {updated}.",
      ] },
      { h: "דין ושיפוט", p: [
        "על תנאים אלה חלים דיני מדינת ישראל בלבד. סמכות השיפוט הייחודית נתונה לבתי המשפט המוסמכים במחוז תל אביב-יפו.",
      ] },
      { h: "יצירת קשר", p: ["לשאלות על תנאים אלה: {email}."] },
    ],
  },
  en: {
    title: "Terms of use",
    intro: "These terms apply to the use of InvoiceFlow. By signing up or using the service you accept them on behalf of your business. If you do not accept them, do not use the service. The Hebrew version governs.",
    sections: [
      { h: "The parties", p: [
        "The service is operated by {name}, {reg}, {address} (\"the operator\"). \"The customer\" is the business that signs up, and a \"user\" is anyone the customer invites to its workspace.",
      ] },
      { h: "The service", p: [
        "InvoiceFlow helps read supplier invoices, match them to purchase orders and goods receipts, handle exceptions and approvals, and record decisions. It is a tool. The customer remains responsible for its business, accounting and tax decisions, and for making payments.",
      ] },
      { h: "Sign-up and accounts", li: [
        "The service is for businesses and users aged 18 or over. Whoever signs up confirms they may act for the business.",
        "Give accurate details and keep your password secret. Turning on two-factor sign-in is recommended.",
        "The customer is responsible for activity in its account, for whom it invites to its team and for the permissions it grants.",
      ] },
      { h: "Acceptable use", p: ["Do not use the service to:"], li: [
        "upload unlawful content, or data the customer has no right to process;",
        "harm the service's security, try to reach other customers' data or bypass limits;",
        "place abnormal load on the service, drive it with unapproved automation, or reverse-engineer it;",
        "mislead, defraud or carry out an unlawful financial action.",
      ] },
      { h: "Customer data", p: [
        "Data the customer uploads belongs to the customer. The customer lets the operator process it only to provide the service, under the privacy policy and the data-processing agreement, which form part of these terms.",
        "The customer is responsible for having a lawful basis to upload the data, including personal data about suppliers and staff.",
        "A full archive can be downloaded and the workspace deleted at any time from Settings.",
      ] },
      { h: "Artificial intelligence", p: [
        "Some features use language models. Their output (summaries, explanations, answers and suggestions) is marked as advisory, may be wrong, and is not legal, accounting, tax or financial advice. Check it before relying on it. Amounts and matches are computed by fixed rules, and every decision is made by a person.",
      ] },
      { h: "Availability and changes", p: [
        "The operator will try to keep the service available and working, but does not promise uninterrupted or error-free operation. The service may change, update or go offline for maintenance. A material change for the worse will be announced in advance where possible.",
      ] },
      { h: "Payment", p: [
        "The service is currently free. If paid plans are offered, prices and terms will be published in advance, and nothing will be charged without explicit consent.",
      ] },
      { h: "Intellectual property", p: [
        "All rights in the service, its code, design and marks belong to the operator. Do not copy, distribute or create derivative works without written permission, except as the law allows.",
      ] },
      { h: "Limitation of liability", p: [
        "The service is provided as is. To the extent the law allows, the operator is not liable for indirect or consequential damage or for lost profits, data or goodwill, and its total liability is limited to the amount paid to it for the service in the 12 months before the event. Nothing here limits liability that cannot be limited by law.",
      ] },
      { h: "Indemnity", p: [
        "The customer will indemnify the operator for reasonable damage or costs caused by use in breach of these terms or the law, or by data the customer uploaded without the right to do so, after the operator has notified the customer of the claim and let it defend.",
      ] },
      { h: "Termination", p: [
        "The customer may stop using the service and delete its workspace at any time. The operator may suspend or close an account that breaches these terms, and otherwise only with reasonable notice that allows the data to be downloaded.",
      ] },
      { h: "Changes to these terms", p: [
        "The operator may update these terms. A material change is published on the site and sent to account administrators at least 14 days before it takes effect. Continued use afterwards means acceptance. Last updated: {updated}.",
      ] },
      { h: "Law and jurisdiction", p: [
        "These terms are governed solely by the laws of the State of Israel. The competent courts of the Tel Aviv-Jaffa district have exclusive jurisdiction.",
      ] },
      { h: "Contact", p: ["Questions about these terms: {email}."] },
    ],
  },
};
