import type { Metadata } from "next";
import { Assistant, JetBrains_Mono } from "next/font/google";
import { cookies } from "next/headers";
import { Toaster } from "sonner";
import { I18nProvider } from "@/lib/i18n";
import { LOCALE_COOKIE } from "@/lib/i18n/constants";
import type { Locale } from "@/lib/i18n/dictionaries";
import "./globals.css";

// One workhorse family for Hebrew and Latin (precise humanist forms, tabular figures);
// a mono only for codes and hashes, never as decoration.
const sans = Assistant({ subsets: ["latin", "hebrew"], weight: ["400", "500", "600", "700"], variable: "--font-sans", display: "swap" });
const mono = JetBrains_Mono({ subsets: ["latin"], weight: ["400", "500"], variable: "--font-mono", display: "swap" });

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
      <body className={`${sans.variable} ${mono.variable}`}>
        <I18nProvider initial={locale}>
          {children}
          <Toaster position="bottom-center" closeButton toastOptions={{ className: "if-toast" }} />
        </I18nProvider>
      </body>
    </html>
  );
}
