import type { Metadata } from "next";
import { IBM_Plex_Sans_Arabic } from "next/font/google";
import { LanguageProvider } from "@/components/LanguageProvider";
import { dictionary } from "@/lib/i18n";
import "./globals.css";

const ibmPlexSansArabic = IBM_Plex_Sans_Arabic({
  variable: "--font-ibm-plex-sans-arabic",
  subsets: ["arabic", "latin"],
  weight: ["400", "500", "700"],
  display: "swap",
});

export const metadata: Metadata = {
  title: "KSU Agent",
  description: dictionary.ar.meta.description,
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="ar" dir="rtl">
      <body className={`${ibmPlexSansArabic.variable} font-sans antialiased`}>
        <LanguageProvider>{children}</LanguageProvider>
      </body>
    </html>
  );
}
