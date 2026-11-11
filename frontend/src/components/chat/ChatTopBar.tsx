"use client";

import { useLanguage } from "@/components/LanguageProvider";
import { PlusIcon } from "@/components/icons";

type ChatTopBarProps = {
  onNewChat: () => void;
  newChatDisabled: boolean;
};

export function ChatTopBar({ onNewChat, newChatDisabled }: ChatTopBarProps) {
  const { t } = useLanguage();

  return (
    <div className="shrink-0 border-b border-slate-200/80 bg-white">
      <div className="mx-auto flex w-full max-w-3xl items-center justify-between gap-3 px-4 py-3 sm:px-6">
        <h1 className="text-base font-semibold text-navy">{t.chat.title}</h1>

        <button
          type="button"
          onClick={onNewChat}
          disabled={newChatDisabled}
          className="inline-flex items-center gap-1.5 rounded-xl border border-slate-200 px-3 py-2 text-xs font-semibold text-navy transition-colors hover:bg-surface disabled:cursor-not-allowed disabled:opacity-60"
        >
          <PlusIcon className="h-4 w-4 text-teal-deep" />
          {t.chat.newChat}
        </button>
      </div>
    </div>
  );
}
