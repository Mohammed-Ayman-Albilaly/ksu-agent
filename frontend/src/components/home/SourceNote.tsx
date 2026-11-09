"use client";

import { useLanguage } from "@/components/LanguageProvider";
import { InfoIcon } from "@/components/icons";

export function SourceNote() {
  const { t } = useLanguage();

  return (
    <section className="bg-white">
      <div className="mx-auto w-full max-w-[1200px] px-5 pb-16 sm:px-8">
        <div className="flex gap-3 border-t border-slate-200/80 pt-8">
          <InfoIcon className="mt-0.5 h-5 w-5 shrink-0 text-muted" />
          <p className="max-w-3xl text-sm leading-relaxed text-muted">
            {t.note}
          </p>
        </div>
      </div>
    </section>
  );
}
