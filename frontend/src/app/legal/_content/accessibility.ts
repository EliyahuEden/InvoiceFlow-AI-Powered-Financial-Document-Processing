import type { LegalDoc } from "./types";

/**
 * Accessibility statement (הצהרת נגישות), required by the Equal Rights for Persons with Disabilities (Service
 * Accessibility Adjustments) Regulations, 5773-2013, regulation 35. Keep the facts true to the build: the axe scan in
 * frontend/tests/e2e/a11y.spec.ts runs on the core screens in both languages and themes.
 */
export const accessibility: LegalDoc = {
  he: {
    title: "הצהרת נגישות",
    intro: "אנו רואים חשיבות בכך שהשירות יהיה נגיש לכל המשתמשים, כולל אנשים עם מוגבלות, ופועלים לשם כך בהתאם לחוק שוויון זכויות לאנשים עם מוגבלות, התשנ\"ח-1998, ולתקנות שוויון זכויות לאנשים עם מוגבלות (התאמות נגישות לשירות), התשע\"ג-2013.",
    sections: [
      { h: "רמת הנגישות", p: [
        "האתר והשירות הותאמו לדרישות התקן הישראלי ת\"י 5568, המבוסס על הנחיות WCAG ברמה AA. אנו בודקים את המסכים המרכזיים בעברית ובאנגלית, במצב בהיר ובמצב כהה, בכלי בדיקה אוטומטיים (axe) כחלק מכל שינוי, ומטפלים בכל ממצא חמור.",
      ] },
      { h: "מה הותאם", li: [
        "ניווט מלא במקלדת, קישור \"דילוג לתוכן\" וסימון ברור של הרכיב הממוקד.",
        "תמיכה בקוראי מסך: כותרות מסודרות, תוויות לשדות ולכפתורים, הכרזה על שינויים ועל שגיאות.",
        "ניגודיות צבעים לפי רמה AA בשני מצבי התצוגה, ומידע שאינו מועבר בצבע בלבד.",
        "תמיכה מלאה בעברית מימין לשמאל ובאנגלית, ותצוגה מותאמת לטלפון.",
        "כיבוד העדפת \"הפחתת תנועה\" של מערכת ההפעלה.",
      ] },
      { h: "מגבלות ידועות", li: [
        "מסמכים שמשתמשים מעלים (קובצי PDF וסריקות) מוצגים כפי שהם, וייתכן שאינם נגישים. הטקסט שזוהה בהם מוצג גם כשדות טקסט נגישים.",
        "בדיקה ידנית מלאה עם קוראי מסך ובהגדלה של 200% טרם הושלמה בכל המסכים, והיא מתוכננת.",
      ] },
      { h: "פנייה בנושא נגישות", p: [
        "נתקלת בבעיית נגישות? נשמח לשמוע ולתקן. רכז/ת הנגישות: {a11yName}, {a11yPhone}דוא\"ל {a11yEmail}. נא לציין את הדף ואת הבעיה, ונחזור אליך בהקדם.",
      ] },
      { h: "עדכון ההצהרה", p: ["ההצהרה עודכנה לאחרונה ב-{updated}."] },
    ],
  },
  en: {
    title: "Accessibility statement",
    intro: "We want the service to be usable by everyone, including people with disabilities, and work to that end under the Equal Rights for Persons with Disabilities Law, 5758-1998, and the Service Accessibility Adjustments Regulations, 5773-2013.",
    sections: [
      { h: "Accessibility level", p: [
        "The site and service are built to Israeli Standard 5568, based on WCAG level AA. The core screens are checked in Hebrew and English, light and dark, with automated tools (axe) on every change, and every serious finding is fixed.",
      ] },
      { h: "What has been adapted", li: [
        "Full keyboard navigation, a \"skip to content\" link and a clear focus indicator.",
        "Screen-reader support: ordered headings, labels for fields and buttons, announced changes and errors.",
        "Colour contrast at level AA in both themes, and no information conveyed by colour alone.",
        "Full Hebrew right-to-left and English support, and a phone-friendly layout.",
        "Respect for the operating system's \"reduce motion\" preference.",
      ] },
      { h: "Known limitations", li: [
        "Documents users upload (PDFs and scans) are shown as they are and may not be accessible. The text read from them is also shown as accessible text fields.",
        "A full manual pass with screen readers and at 200% zoom has not yet covered every screen; it is planned.",
      ] },
      { h: "Contact about accessibility", p: [
        "Found an accessibility problem? We want to hear and fix it. Accessibility coordinator: {a11yName}, {a11yPhone}email {a11yEmail}. Please name the page and the problem, and we will get back to you soon.",
      ] },
      { h: "Updates", p: ["This statement was last updated on {updated}."] },
    ],
  },
};
