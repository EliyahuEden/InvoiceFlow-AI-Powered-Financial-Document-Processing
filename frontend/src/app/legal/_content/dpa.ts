import type { LegalDoc } from "./types";

/** Data-processing agreement, accepted at sign-up together with the terms. Tokens are filled from lib/legal.ts. */
export const dpa: LegalDoc = {
  he: {
    title: "הסכם עיבוד נתונים",
    intro: "הסכם זה מסדיר את עיבוד המידע האישי שהלקוח מעלה לשירות InvoiceFlow, והוא חלק מתנאי השימוש. הלקוח הוא בעל השליטה במאגר, והמפעיל, {name}, {reg}, הוא המחזיק המעבד את המידע מטעמו.",
    sections: [
      { h: "הגדרות", p: [
        "\"מידע אישי\", \"מאגר מידע\", \"בעל שליטה\", \"מחזיק\" ו\"אירוע אבטחה\" יפורשו כמשמעותם בחוק הגנת הפרטיות, התשמ\"א-1981, ובתקנות הגנת הפרטיות (אבטחת מידע), התשע\"ז-2017. ככל שחלה על הלקוח תקנת הגנת המידע האירופית (GDPR), המונחים המקבילים בה יחולו בהתאמה.",
      ] },
      { h: "נושא העיבוד", li: [
        "מטרה: מתן השירות, כלומר קריאת חשבוניות, התאמה להזמנות ולקבלות, ניהול חריגות, אישורים, תשלומים ותיעוד.",
        "סוגי מידע: שמות ופרטי קשר של אנשי קשר אצל ספקים ובעסק, מספרי עוסק, פרטי חשבון בנק של ספקים, פרטי עובדים המשתמשים בשירות, ותוכן המסמכים שהועלו.",
        "נושאי המידע: עובדי הלקוח, ספקים ואנשי הקשר שלהם.",
        "משך: כל עוד הלקוח משתמש בשירות, ועד מחיקת סביבת העבודה.",
      ] },
      { h: "התחייבויות המפעיל", li: [
        "לעבד את המידע רק לפי הוראות הלקוח, כפי שהן באות לידי ביטוי בשימוש בשירות ובהסכם זה, ולא לכל מטרה אחרת.",
        "להגביל את הגישה למידע לאנשים שזקוקים לה לצורך מתן השירות ומחויבים בסודיות.",
        "ליישם אמצעי אבטחה ההולמים את רמת הרגישות של המידע, כמפורט בנספח א.",
        "לסייע ללקוח, במידה סבירה, לטפל בבקשות עיון, תיקון ומחיקה של נושאי מידע.",
        "לא למכור את המידע ולא להשתמש בו לפרסום או לאימון מודלים.",
      ] },
      { h: "ספקי משנה", p: [
        "הלקוח מאשר את ספקי המשנה המפורטים בנספח ב. המפעיל יעדכן את הלקוחות לפחות 14 יום לפני הוספת ספק משנה חדש, והלקוח רשאי להתנגד מטעמים סבירים ולסיים את השימוש אם ההתנגדות לא נפתרה. המפעיל יחייב כל ספק משנה בהגנה על המידע ברמה שאינה פחותה מזו שבהסכם זה.",
      ] },
      { h: "אירועי אבטחה", p: [
        "המפעיל יודיע ללקוח ללא דיחוי, ובכל מקרה תוך 72 שעות מהרגע שנודע לו, על אירוע אבטחה חמור הנוגע למידע של הלקוח. ההודעה תכלול את מה שידוע על האירוע, המידע שנפגע והצעדים שננקטו. המפעיל יסייע ללקוח בעמידה בחובות הדיווח שלו לרשות להגנת הפרטיות.",
      ] },
      { h: "העברה לחו\"ל", p: [
        "חלק מספקי המשנה פועלים מחוץ לישראל. העברת המידע אליהם נעשית בהתאם לתקנות הגנת הפרטיות (העברת מידע אל מאגרי מידע שמחוץ לגבולות המדינה), התשס\"א-2001. הלקוח יכול להפעיל את השירות במצב לא מקוון, שבו לא נשלח מידע לספקי מודלי השפה.",
      ] },
      { h: "סיום ומחיקה", p: [
        "בסיום השימוש הלקוח יכול להוריד ארכיון מלא ולמחוק את סביבת העבודה. לאחר מחיקה המידע יימחק מהמערכת הפעילה מיד, ומהגיבויים בתוך מחזור הגיבוי, אלא אם הדין מחייב לשמור אותו.",
      ] },
      { h: "ביקורת ומידע", p: [
        "המפעיל ימסור ללקוח, לפי בקשה סבירה ובכפוף לסודיות, מידע הדרוש להוכחת עמידה בהסכם זה, כולל תיאור אמצעי האבטחה.",
      ] },
      { h: "אחריות וסדר עדיפויות", p: [
        "הגבלת האחריות שבתנאי השימוש חלה גם על הסכם זה, ככל שהדין מתיר. בסתירה בין הסכם זה לתנאי השימוש בנושא הגנת מידע, הסכם זה גובר. תאריך העדכון האחרון: {updated}.",
      ] },
      { h: "נספח א: אמצעי אבטחה", li: [
        "הפרדת לקוחות בבסיס הנתונים (Row-Level Security) ובדיקות הרשאה בכל בקשה.",
        "הצפנת פרטי בנק וסודות אימות דו-שלבי (Fernet), גיבוב סיסמאות (Argon2), והצפנת תעבורה (HTTPS).",
        "אימות דו-שלבי, אפשרות לחייב אותו לכל הצוות, הגבלת ניסיונות וניתוק התחברויות.",
        "הרשאות לפי תפקיד והפרדת סמכויות: שינוי בפרטי בנק של ספק מחייב אישור של אדם אחר, והגדרה אופציונלית מונעת ממי שהעלה חשבונית להחליט עליה.",
        "יומן ביקורת שאינו ניתן לעריכה ומשורשר בגיבובים.",
        "גיבוי יומי של בסיס הנתונים, ניטור תקלות ותיעוד שינויים.",
      ] },
      { h: "נספח ב: ספקי משנה", li: [
        "אחסון ותשתית: {hosting}.",
        "שליחת דוא\"ל שירותי: Brevo (Sendinblue SAS), האיחוד האירופי.",
        "מודלי שפה: OpenAI, L.L.C., ארצות הברית; ובמקרה תקלה Groq, Inc., ארצות הברית. אינם פעילים במצב לא מקוון.",
      ] },
    ],
  },
  en: {
    title: "Data-processing agreement",
    intro: "This agreement governs the processing of personal data a customer uploads to InvoiceFlow and forms part of the terms of use. The customer controls the database; the operator, {name}, {reg}, processes the data on the customer's behalf. The Hebrew version governs.",
    sections: [
      { h: "Definitions", p: [
        "\"Personal data\", \"database\", \"controller\", \"processor\" and \"security incident\" have the meaning given in the Protection of Privacy Law, 5741-1981, and the Protection of Privacy (Data Security) Regulations, 5777-2017. Where the EU General Data Protection Regulation applies to the customer, its equivalent terms apply accordingly.",
      ] },
      { h: "Scope of processing", li: [
        "Purpose: providing the service, that is reading invoices, matching them to orders and receipts, handling exceptions, approvals, payments and records.",
        "Data: names and contact details of supplier and customer contacts, dealer numbers, supplier bank details, details of the customer's staff who use the service, and the content of uploaded documents.",
        "Data subjects: the customer's staff, suppliers and their contacts.",
        "Duration: while the customer uses the service, until the workspace is deleted.",
      ] },
      { h: "Operator obligations", li: [
        "Process the data only on the customer's instructions, as expressed through the use of the service and this agreement, and for no other purpose.",
        "Limit access to people who need it to provide the service and are bound by confidentiality.",
        "Apply security measures suited to the sensitivity of the data, as listed in Annex A.",
        "Reasonably help the customer handle access, correction and deletion requests from data subjects.",
        "Not sell the data or use it for advertising or model training.",
      ] },
      { h: "Sub-processors", p: [
        "The customer approves the sub-processors listed in Annex B. The operator will notify customers at least 14 days before adding a new one; the customer may object on reasonable grounds and stop using the service if the objection is not resolved. Every sub-processor is bound to protect the data at least as strictly as this agreement.",
      ] },
      { h: "Security incidents", p: [
        "The operator will notify the customer without delay, and in any case within 72 hours of becoming aware, of a serious security incident affecting the customer's data. The notice will describe what is known, the data affected and the steps taken. The operator will help the customer meet its own reporting duties to the Privacy Protection Authority.",
      ] },
      { h: "Transfers abroad", p: [
        "Some sub-processors operate outside Israel. Transfers follow the Protection of Privacy (Transfer of Data to Databases Abroad) Regulations, 5761-2001. The customer can run the service in offline mode, which sends nothing to the language-model providers.",
      ] },
      { h: "End and deletion", p: [
        "When the customer stops, it can download a full archive and delete the workspace. Deleted data is removed from the live system immediately and from backups within the backup cycle, unless the law requires keeping it.",
      ] },
      { h: "Audit and information", p: [
        "On reasonable request and subject to confidentiality, the operator will give the customer the information needed to show compliance with this agreement, including a description of the security measures.",
      ] },
      { h: "Liability and precedence", p: [
        "The limitation of liability in the terms of use also applies here, to the extent the law allows. If this agreement and the terms conflict on data protection, this agreement prevails. Last updated: {updated}.",
      ] },
      { h: "Annex A: security measures", li: [
        "Customer separation in the database (row-level security) and authorization checks on every request.",
        "Encryption of bank details and two-factor secrets (Fernet), password hashing (Argon2) and encrypted connections (HTTPS).",
        "Two-factor sign-in, the option to require it for the whole team, rate limits and session revocation.",
        "Role-based permissions and separation of duties: a change to supplier bank details must be confirmed by another person, and an optional setting stops whoever uploaded an invoice from deciding it.",
        "A tamper-evident, hash-chained audit log.",
        "Daily database backups, failure monitoring and change records.",
      ] },
      { h: "Annex B: sub-processors", li: [
        "Hosting and infrastructure: {hosting}.",
        "Service email delivery: Brevo (Sendinblue SAS), European Union.",
        "Language models: OpenAI, L.L.C., United States; Groq, Inc., United States, as a fallback. Not used in offline mode.",
      ] },
    ],
  },
};
