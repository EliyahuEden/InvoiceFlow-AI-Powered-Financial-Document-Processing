import type { Metadata } from "next";
// Fonts ship with the app (@fontsource), so building never depends on a network call to Google Fonts
// (next/font/google failed intermittently in Docker and CI). Each file covers Latin and Hebrew via unicode-range.
import "@fontsource/assistant/400.css";
import "@fontsource/assistant/500.css";
import "@fontsource/assistant/600.css";
import "@fontsource/assistant/700.css";
import "@fontsource/jetbrains-mono/400.css";
import "@fontsource/jetbrains-mono/500.css";
import { cookies } from "next/headers";
import { Toaster } from "sonner";
import { I18nProvider } from "@/lib/i18n";
import { LOCALE_COOKIE } from "@/lib/i18n/constants";
import type { Locale } from "@/lib/i18n/dictionaries";
import "./globals.css";


export const metadata: Metadata = {
  title: { default: "InvoiceFlow", template: "%s · InvoiceFlow" },
  description: "AI-assisted supplier invoice processing with deterministic reconciliation.",
};

export default async function RootLayout({ children }: { children: React.ReactNode }) {
  const store = await cookies();
  const locale: Locale = store.get(LOCALE_COOKIE)?.value === "en" ? "en" : "he";
  return (
    <html lang={locale} dir={locale === "he" ? "rtl" : "ltr"} suppressHydrationWarning>
      <head>
        <script
          dangerouslySetInnerHTML={{
            __html: `try{var t=localStorage.getItem('if_theme');if(t)document.documentElement.dataset.theme=t}catch(e){}`,
          }}
        />
      </head>
      <body>
        <I18nProvider initial={locale}>
          {children}
          <Toaster position="bottom-center" closeButton toastOptions={{ className: "if-toast" }} />
        </I18nProvider>
      </body>
    </html>
  );
}
