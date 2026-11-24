"use client";

import { useLanguage } from "@/components/LanguageProvider";
import { BrandMark } from "@/components/icons";

/**
 * The waiting bubble. It carries no control of its own: stopping a reply is the
 * composer's job, where the send button stands, so there is one place to look.
 */
export function PendingBubble() {
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
      </div>
    </div>
  );
}
