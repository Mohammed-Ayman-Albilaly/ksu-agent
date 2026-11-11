"use client";

import { useEffect, useRef, useState } from "react";
import { useLanguage } from "@/components/LanguageProvider";
import { BrandMark, CheckIcon, CopyIcon, RefreshIcon } from "@/components/icons";
import { Citations } from "@/components/chat/Citations";
import type { ChatMessage } from "@/lib/chatStorage";

type MessageBubbleProps = {
  message: ChatMessage;
  onRetry: (messageId: string) => void;
};

export function MessageBubble({ message, onRetry }: MessageBubbleProps) {
  const { t } = useLanguage();
  const [copied, setCopied] = useState(false);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    return () => {
      if (timer.current) {
        clearTimeout(timer.current);
      }
    };
  }, []);

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(message.text);
      setCopied(true);

      if (timer.current) {
        clearTimeout(timer.current);
      }

      timer.current = setTimeout(() => setCopied(false), 2000);
    } catch {
      // Clipboard unavailable: the answer stays selectable.
    }
  };

  if (message.role === "user") {
    return (
      <div className="flex justify-end">
        <div className="max-w-[85%] rounded-2xl rounded-ee-md bg-navy px-4 py-3 text-sm leading-relaxed text-white">
          <span className="sr-only">{t.chat.you}: </span>
          <p className="whitespace-pre-wrap" dir="auto">
            {message.text}
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex items-start gap-2.5">
      <BrandMark className="mt-0.5 h-7 w-7 shrink-0" />

      <div className="min-w-0 max-w-[92%] flex-1">
        {message.status === "error" ? (
          <div className="rounded-2xl rounded-es-md bg-red-50 px-4 py-3 ring-1 ring-red-200">
            <span className="sr-only">{t.chat.assistant}: </span>
            <p className="text-sm leading-relaxed text-red-700">
              {message.errorKind === "invalid"
                ? t.chat.errors.invalid
                : t.chat.errors.unavailable}
            </p>
            <button
              type="button"
              onClick={() => onRetry(message.id)}
              className="mt-2 inline-flex items-center gap-1.5 rounded-lg border border-red-200 bg-white px-2.5 py-1.5 text-xs font-semibold text-red-700 transition-colors hover:bg-red-100"
            >
              <RefreshIcon className="h-3.5 w-3.5" />
              {t.chat.retry}
            </button>
          </div>
        ) : (
          <div className="rounded-2xl rounded-es-md bg-surface px-4 py-3 ring-1 ring-slate-200">
            <span className="sr-only">{t.chat.assistant}: </span>
            <p className="whitespace-pre-wrap text-sm leading-relaxed text-ink" dir="auto">
              {message.text}
            </p>

            <button
              type="button"
              onClick={copy}
              aria-label={copied ? t.chat.copied : t.chat.copy}
              className="mt-2 inline-flex items-center gap-1.5 rounded-lg px-2 py-1 text-xs font-medium text-muted transition-colors hover:bg-white hover:text-navy"
            >
              {copied ? (
                <CheckIcon className="h-3.5 w-3.5 text-teal-deep" />
              ) : (
                <CopyIcon className="h-3.5 w-3.5" />
              )}
              <span>{copied ? t.chat.copied : t.chat.copy}</span>
            </button>

            <Citations citations={message.citations ?? []} />
          </div>
        )}
      </div>
    </div>
  );
}
