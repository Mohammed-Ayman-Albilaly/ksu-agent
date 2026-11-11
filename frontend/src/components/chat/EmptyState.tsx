"use client";

import { useLanguage } from "@/components/LanguageProvider";
import { BrandMark } from "@/components/icons";

type EmptyStateProps = {
  firstName: string;
  onSelect: (question: string) => void;
  disabled: boolean;
};

export function EmptyState({ firstName, onSelect, disabled }: EmptyStateProps) {
  const { t } = useLanguage();
  const greeting = t.chat.empty.greeting.replace("{name}", firstName);

  return (
    <div className="mx-auto w-full max-w-xl text-center">
      <BrandMark className="mx-auto h-12 w-12" />

      <h2 className="mt-4 text-xl font-bold leading-snug text-navy sm:text-2xl">
        {greeting}
      </h2>

      <p className="mt-2 text-sm leading-relaxed text-muted">
        {t.chat.empty.note}
      </p>

      <div className="mt-6 flex flex-wrap justify-center gap-2">
        {t.chat.empty.suggestions.map((question) => (
          <button
            key={question}
            type="button"
            onClick={() => onSelect(question)}
            disabled={disabled}
            className="rounded-full border border-slate-200 bg-white px-3.5 py-2 text-start text-xs leading-relaxed text-ink transition-colors hover:border-teal/50 hover:bg-surface disabled:opacity-60"
          >
            {question}
          </button>
        ))}
      </div>
    </div>
  );
}
