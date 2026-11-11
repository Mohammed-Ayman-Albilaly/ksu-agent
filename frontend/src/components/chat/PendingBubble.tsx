"use client";

import { useLanguage } from "@/components/LanguageProvider";
import { BrandMark, StopIcon } from "@/components/icons";

type PendingBubbleProps = {
  onStop: () => void;
};

export function PendingBubble({ onStop }: PendingBubbleProps) {
  const { t } = useLanguage();

  return (
    <div className="flex items-start gap-2.5">
      <BrandMark className="mt-0.5 h-7 w-7 shrink-0" />

      <div className="flex flex-wrap items-center gap-x-3 gap-y-2 rounded-2xl rounded-es-md bg-surface px-4 py-3 ring-1 ring-slate-200">
        <span aria-hidden="true" className="flex items-center gap-1">
          <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-teal [animation-delay:-300ms] motion-reduce:animate-none" />
          <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-teal [animation-delay:-150ms] motion-reduce:animate-none" />
          <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-teal motion-reduce:animate-none" />
        </span>

        <p className="text-sm text-muted">{t.chat.searching}</p>

        <button
          type="button"
          onClick={onStop}
          className="inline-flex items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-2.5 py-1.5 text-xs font-semibold text-navy transition-colors hover:bg-surface"
        >
          <StopIcon className="h-3.5 w-3.5" />
          {t.chat.stop}
        </button>
      </div>
    </div>
  );
}
