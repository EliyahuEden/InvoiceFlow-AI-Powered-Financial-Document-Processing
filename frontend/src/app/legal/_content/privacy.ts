import type { LegalDoc } from "./types";

/** Privacy policy. Tokens in {braces} are filled from OPERATOR in lib/legal.ts. */
export const privacy: LegalDoc = {
  he: {
    title: "מדיניות פרטיות",
    intro: "מדיניות זו מסבירה איזה מידע אישי נאסף בשירות InvoiceFlow, למה הוא משמש, עם מי הוא משותף, כמה זמן הוא נשמר ומה הזכויות שלך. היא נכתבה בהתאם לחוק הגנת הפרטיות, התשמ\"א-1981 (כולל תיקון 13) ולתקנות הגנת הפרטיות (אבטחת מידע), התשע\"ז-2017.",
    sections: [
      { h: "מי אחראי על המידע", p: [
        "השירות מופעל על ידי {name}, {reg}, {address} (\"המפעיל\", \"אנחנו\"). לשאלות בנושא פרטיות: {privacyEmail}.",
        "לגבי פרטי החשבון ונתוני השימוש באתר, המפעיל הוא בעל השליטה במידע. לגבי המידע העסקי שלקוח מעלה לשירות (חשבוניות, ספקים, הזמנות רכש ומסמכים), הלקוח הוא בעל השליטה במאגר והמפעיל משמש כמחזיק מטעמו, לפי הסכם עיבוד הנתונים.",
      ] },
      { h: "איזה מידע נאסף", li: [
        "פרטי חשבון: שם, כתובת דוא\"ל, שם העסק ומספר העוסק או החברה, תפקיד בצוות, שפה מועדפת.",
        "פרטי התחברות: סיסמה השמורה רק כגיבוב (Argon2), וסוד אימות דו-שלבי השמור מוצפן.",
        "מידע עסקי שהלקוח מעלה: חשבוניות ומסמכים, פרטי ספקים (כולל פרטי חשבון בנק, השמורים מוצפנים ומוצגים חלקית), הזמנות רכש, תעודות קבלה, הערות והחלטות.",
        "יומן ביקורת: מי ביצע איזו פעולה ומתי, לצורך בקרה, אבטחה ואמינות הרשומות.",
        "מידע טכני: כתובת IP וסוג דפדפן, לצורך התחברות מאובטחת, ניהול התחברויות פעילות והגבלת ניסיונות.",
      ] },
      { h: "למה המידע משמש", li: [
        "מתן השירות: קריאת חשבוניות, התאמה להזמנות ולקבלות, ניהול חריגות, אישורים ותשלומים.",
        "אבטחה: אימות משתמשים, מניעת שימוש לרעה, איתור תקלות ותיעוד פעולות.",
        "תקשורת שירותית: הזמנות לצוות, איפוס סיסמה והודעות מערכת. לא נשלח דיוור שיווקי ללא הסכמה מפורשת, בהתאם לסעיף 30א לחוק התקשורת.",
        "עמידה בדרישות החוק.",
      ] },
      { h: "שימוש בבינה מלאכותית", p: [
        "חלק מהיכולות (קריאת שדות שלא זוהו בכללים, הסברי חריגות, העוזר וחיפוש במדיניות) עשויות לשלוח קטעי טקסט רלוונטיים מהמסמכים ומהשאלות לספקי מודלי שפה: OpenAI, ובמקרה תקלה Groq. ספקים אלה פועלים מחוץ לישראל.",
        "לפי תנאי ה-API שהם מפרסמים, מידע שנשלח דרך ה-API אינו משמש לאימון המודלים שלהם כברירת מחדל. ניתן להפעיל את השירות במצב לא מקוון, שבו לא נשלח מידע לספקים אלה. תוצרי הבינה המלאכותית מסומנים כייעוץ בלבד; כל החלטה כספית מתקבלת על ידי אדם.",
      ] },
      { h: "עם מי המידע משותף", p: [
        "איננו מוכרים מידע אישי ואיננו משתפים אותו לצורכי פרסום. המידע מועבר רק לספקי משנה הדרושים להפעלת השירות: אחסון ({hosting}), שליחת דוא\"ל, וספקי מודלי השפה שלעיל. הרשימה המלאה מופיעה בנספח להסכם עיבוד הנתונים. מידע יימסר לרשויות רק כשהחוק מחייב זאת.",
      ] },
      { h: "העברת מידע לחו\"ל", p: [
        "חלק מספקי המשנה פועלים מחוץ לישראל. העברה כזו נעשית בהתאם לתקנות הגנת הפרטיות (העברת מידע אל מאגרי מידע שמחוץ לגבולות המדינה), התשס\"א-2001, ובכפוף להתחייבות הספקים להגן על המידע.",
      ] },
      { h: "עוגיות ואחסון בדפדפן", p: [
        "האתר משתמש רק בעוגיות הכרחיות: עוגיות התחברות מאובטחות (HttpOnly) ועוגיית שפה. בנוסף נשמרים בדפדפן העדפת ערכת נושא וטיוטות הערות. אין עוגיות פרסום, אין כלי מעקב ואין אנליטיקה של צד שלישי.",
      ] },
      { h: "כמה זמן המידע נשמר", p: [
        "המידע נשמר כל עוד החשבון פעיל. מנהל העסק יכול להוריד ארכיון מלא של הנתונים ולמחוק את סביבת העבודה לצמיתות מתוך ההגדרות. לאחר מחיקה, עותקים בגיבויים נמחקים בתוך מחזור הגיבוי (עד 14 יום בשרת, ובגיבוי החיצוני לפי תקופת השמירה שהוגדרה). יומן הביקורת נשמר כחלק מסביבת העבודה ונמחק יחד איתה.",
        "סביבת הדגמה שנפתחת בכפתור \"לנסות את ההדגמה\" היא עותק פרטי לכל מבקר: רק המבקר רואה אותה ואת מה שהעלה, והיא נמחקת אוטומטית, יחד עם כל המידע שבה, 24 שעות לאחר פתיחתה. אין להעלות לסביבת הדגמה מידע רגיש.",
      ] },
      { h: "אבטחת מידע", li: [
        "הפרדת לקוחות ברמת בסיס הנתונים (Row-Level Security), כך שעסק אחד אינו יכול לראות נתונים של עסק אחר.",
        "הצפנה של פרטי בנק ושל סודות אימות דו-שלבי, וגיבוב סיסמאות.",
        "אימות דו-שלבי, הגבלת ניסיונות התחברות וניתוק התחברויות.",
        "יומן ביקורת משורשר בגיבובים, שמאפשר לזהות שינוי ברשומות.",
        "גיבוי יומי, והצפנת התעבורה (HTTPS).",
      ], p: [
        "אף מערכת אינה חסינה לחלוטין. אם יתרחש אירוע אבטחה חמור, נפעל לפי תקנות אבטחת מידע, כולל דיווח לרשות להגנת הפרטיות ועדכון הלקוחות שנפגעו ללא דיחוי.",
      ] },
      { h: "הזכויות שלך", p: [
        "לפי חוק הגנת הפרטיות, זכותך לעיין במידע עליך, לבקש לתקן מידע שגוי, ולבקש למחוק מידע שאין עוד צורך בו. בקשה בנוגע לחשבון שלך אפשר לשלוח אל {privacyEmail}. בקשה בנוגע למידע שעסק אחר העלה לשירות (למשל אם הנך ספק המופיע בחשבונית) יש להפנות לאותו עסק, ונסייע לו לטפל בה.",
        "אם לא קיבלת מענה, ניתן לפנות לרשות להגנת הפרטיות במשרד המשפטים.",
      ] },
      { h: "קטינים", p: ["השירות מיועד לעסקים ולמשתמשים מגיל 18 ומעלה."] },
      { h: "שינויים במדיניות", p: [
        "נעדכן מדיניות זו מעת לעת. שינוי מהותי יפורסם באתר ויימסר למנהלי החשבונות לפני כניסתו לתוקף. תאריך העדכון האחרון: {updated}.",
      ] },
    ],
  },
  en: {
    title: "Privacy policy",
    intro: "This policy explains what personal data InvoiceFlow collects, what it is used for, who it is shared with, how long it is kept and what your rights are. It follows the Israeli Protection of Privacy Law, 5741-1981 (including Amendment 13) and the Protection of Privacy (Data Security) Regulations, 5777-2017. The Hebrew version governs.",
    sections: [
      { h: "Who is responsible", p: [
        "The service is operated by {name}, {reg}, {address} (\"the operator\", \"we\"). Privacy questions: {privacyEmail}.",
        "For account details and website use, the operator controls the data. For business data a customer uploads (invoices, suppliers, purchase orders and documents), the customer controls the database and the operator processes it on the customer's behalf under the data-processing agreement.",
      ] },
      { h: "What we collect", li: [
        "Account details: name, email address, business name and company or dealer number, team role, preferred language.",
        "Sign-in details: a password stored only as a hash (Argon2) and an encrypted two-factor secret.",
        "Business data a customer uploads: invoices and documents, supplier details (bank account details are encrypted and shown masked), purchase orders, goods receipts, notes and decisions.",
        "Audit log: who did what and when, for control, security and the integrity of records.",
        "Technical data: IP address and browser type, for secure sign-in, managing active sessions and rate limiting.",
      ] },
      { h: "What we use it for", li: [
        "Providing the service: reading invoices, matching them to orders and receipts, handling exceptions, approvals and payments.",
        "Security: authenticating users, preventing abuse, troubleshooting and recording actions.",
        "Service messages: team invitations, password resets and system notices. No marketing email is sent without explicit consent, as section 30A of the Communications Law requires.",
        "Meeting legal obligations.",
      ] },
      { h: "Artificial intelligence", p: [
        "Some features (reading fields the rules did not recognise, explaining exceptions, the assistant and policy search) may send relevant text from documents and questions to language-model providers: OpenAI, and Groq as a fallback. These providers operate outside Israel.",
        "Under their published API terms, data sent through the API is not used to train their models by default. The service can run in offline mode, which sends nothing to these providers. AI output is marked as advisory; every financial decision is made by a person.",
      ] },
      { h: "Who we share it with", p: [
        "We do not sell personal data or share it for advertising. Data goes only to sub-processors needed to run the service: hosting ({hosting}), email delivery and the language-model providers above. The full list is an annex to the data-processing agreement. Data is disclosed to authorities only when the law requires it.",
      ] },
      { h: "Transfers abroad", p: [
        "Some sub-processors operate outside Israel. Such transfers follow the Protection of Privacy (Transfer of Data to Databases Abroad) Regulations, 5761-2001, and the providers' commitments to protect the data.",
      ] },
      { h: "Cookies and browser storage", p: [
        "The site uses only strictly necessary cookies: secure (HttpOnly) sign-in cookies and a language cookie. Your theme preference and draft notes are kept in your browser. There are no advertising cookies, trackers or third-party analytics.",
      ] },
      { h: "How long we keep it", p: [
        "Data is kept while the account is active. A business administrator can download a full archive and permanently delete the workspace from Settings. After deletion, backup copies expire within the backup cycle (up to 14 days on the server, and the configured retention offsite). The audit log is part of the workspace and is deleted with it.",
        "A demo opened with \"Try the demo\" is a private copy for each visitor: only that visitor sees it and what they upload, and it is deleted automatically, with all its data, 24 hours after it opens. Do not upload sensitive data to a demo.",
      ] },
      { h: "Security", li: [
        "Customer separation in the database (row-level security), so one business cannot see another's data.",
        "Encryption of bank details and two-factor secrets, and hashed passwords.",
        "Two-factor sign-in, sign-in rate limits and session revocation.",
        "A hash-chained audit log that reveals any change to its records.",
        "Daily backups and encrypted connections (HTTPS).",
      ], p: [
        "No system is completely immune. If a serious security incident occurs, we will act under the data-security regulations, including reporting to the Privacy Protection Authority and informing affected customers without delay.",
      ] },
      { h: "Your rights", p: [
        "Under the Protection of Privacy Law you may access data about you, ask for incorrect data to be corrected, and ask for data that is no longer needed to be deleted. Requests about your account: {privacyEmail}. Requests about data another business uploaded (for example, if you are a supplier named on an invoice) should go to that business; we will help it respond.",
        "If you get no answer, you may contact the Privacy Protection Authority at the Ministry of Justice.",
      ] },
      { h: "Minors", p: ["The service is for businesses and users aged 18 or over."] },
      { h: "Changes", p: [
        "We will update this policy from time to time. A material change is published on the site and sent to account administrators before it takes effect. Last updated: {updated}.",
      ] },
    ],
  },
};
