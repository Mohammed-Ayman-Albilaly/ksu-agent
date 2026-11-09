"use client";

import { useLanguage } from "@/components/LanguageProvider";

export function SiteFooter() {
  const { t } = useLanguage();

  return (
    <footer className="border-t border-white/10 bg-navy text-white">
      <div className="mx-auto w-full max-w-[1200px] px-5 py-10 sm:px-8">
        <p className="text-sm font-medium">{t.footer.project}</p>
        <p className="mt-2 text-sm text-white/70">{t.footer.disclaimer}</p>
        <p className="mt-4 text-xs text-white/60">{t.footer.copyright}</p>
      </div>
    </footer>
  );
}
