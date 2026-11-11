"use client";

import type { Citation } from "@/lib/api/chat";
import { useLanguage } from "@/components/LanguageProvider";
import { LinkIcon } from "@/components/icons";

type CitationsProps = {
  citations: Citation[];
};

function safeHref(url: string): string | null {
  try {
    const parsed = new URL(url);

    if (parsed.protocol === "https:" || parsed.protocol === "http:") {
      return parsed.href;
    }

    return null;
  } catch {
    return null;
  }
}

export function Citations({ citations }: CitationsProps) {
  const { t } = useLanguage();

  if (citations.length === 0) {
    return (
      <p className="mt-3 border-t border-slate-200/80 pt-3 text-xs leading-relaxed text-muted">
        {t.chat.noSource}
      </p>
    );
  }

  return (
    <div className="mt-3 border-t border-slate-200/80 pt-3">
      <p className="text-xs font-semibold text-muted">{t.chat.sources}</p>

      <ul className="mt-2 space-y-1.5">
        {citations.map((citation, index) => {
          const href = safeHref(citation.url);
          const article = citation.article.trim();
          const showArticle = article !== "" && article !== "—";

          const content = (
            <>
              <LinkIcon className="mt-0.5 h-3.5 w-3.5 shrink-0 text-teal-deep" />
              <span className="min-w-0 text-start">
                <span className="text-ink" dir="auto">
                  {citation.title}
                </span>
                {showArticle ? (
                  <span className="text-muted" dir="auto">
                    {" · "}
                    {article}
                  </span>
                ) : null}
              </span>
            </>
          );

          return (
            <li key={`${citation.title}-${index}`}>
              {href ? (
                <a
                  href={href}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="flex items-start gap-2 rounded-xl bg-white px-3 py-2 text-xs leading-relaxed ring-1 ring-slate-200 transition-colors hover:ring-teal/50"
                >
                  {content}
                  <span className="sr-only">({t.chat.opensInNewTab})</span>
                </a>
              ) : (
                <div className="flex items-start gap-2 rounded-xl bg-white px-3 py-2 text-xs leading-relaxed ring-1 ring-slate-200">
                  {content}
                </div>
              )}
            </li>
          );
        })}
      </ul>
    </div>
  );
}
