import type { Metadata } from "next";
import { IBM_Plex_Mono, IBM_Plex_Sans, IBM_Plex_Sans_Hebrew } from "next/font/google";
import { cookies } from "next/headers";
import { Toaster } from "sonner";
import { I18nProvider, LOCALE_COOKIE } from "@/lib/i18n";
import type { Locale } from "@/lib/i18n/dictionaries";
import "./globals.css";

const sans = IBM_Plex_Sans({ subsets: ["latin"], weight: ["400", "500", "600"], variable: "--font-sans", display: "swap" });
const hebrew = IBM_Plex_Sans_Hebrew({ subsets: ["hebrew"], weight: ["400", "500", "600"], variable: "--font-hebrew", display: "swap" });
const mono = IBM_Plex_Mono({ subsets: ["latin"], weight: ["400", "500"], variable: "--font-mono", display: "swap" });

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
      <body className={`${sans.variable} ${hebrew.variable} ${mono.variable}`}>
        <I18nProvider initial={locale}>
          {children}
          <Toaster position="bottom-center" richColors closeButton />
        </I18nProvider>
      </body>
    </html>
  );
}
