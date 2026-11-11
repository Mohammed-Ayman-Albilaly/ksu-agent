"use client";

import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import { useLanguage } from "@/components/LanguageProvider";
import { ArrowDownIcon } from "@/components/icons";
import { MessageBubble } from "@/components/chat/MessageBubble";
import { PendingBubble } from "@/components/chat/PendingBubble";
import type { ChatMessage } from "@/lib/chatStorage";

type MessageListProps = {
  messages: ChatMessage[];
  pending: boolean;
  onRetry: (messageId: string) => void;
  onStop: () => void;
  emptyState: ReactNode;
};

const NEAR_BOTTOM_PX = 120;

export function MessageList({
  messages,
  pending,
  onRetry,
  onStop,
  emptyState,
}: MessageListProps) {
  const { t } = useLanguage();
  const listRef = useRef<HTMLDivElement>(null);
  const stickToBottom = useRef(true);
  const [showJump, setShowJump] = useState(false);

  const scrollToBottom = useCallback((behavior: ScrollBehavior) => {
    const element = listRef.current;

    if (!element) {
      return;
    }

    element.scrollTo({ top: element.scrollHeight, behavior });
  }, []);

  const handleScroll = () => {
    const element = listRef.current;

    if (!element) {
      return;
    }

    const distance =
      element.scrollHeight - element.scrollTop - element.clientHeight;

    stickToBottom.current = distance < NEAR_BOTTOM_PX;

    if (stickToBottom.current) {
      setShowJump(false);
    }
  };

  useEffect(() => {
    if (stickToBottom.current) {
      scrollToBottom("auto");
      setShowJump(false);
      return;
    }

    setShowJump(true);
  }, [messages, pending, scrollToBottom]);

  const jump = () => {
    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

    scrollToBottom(reduced ? "auto" : "smooth");
    stickToBottom.current = true;
    setShowJump(false);
  };

  const isEmpty = messages.length === 0 && !pending;

  return (
    <div className="relative flex min-h-0 flex-1 flex-col">
      <div
        ref={listRef}
        onScroll={handleScroll}
        role="log"
        aria-live="polite"
        aria-relevant="additions text"
        className="flex-1 overflow-y-auto overscroll-contain px-4 py-5 sm:px-6"
      >
        {isEmpty ? (
          <div className="flex min-h-full items-center justify-center py-6">
            {emptyState}
          </div>
        ) : (
          <div className="mx-auto flex w-full max-w-3xl flex-col gap-4">
            {messages.map((message) => (
              <MessageBubble
                key={message.id}
                message={message}
                onRetry={onRetry}
              />
            ))}

            {pending ? <PendingBubble onStop={onStop} /> : null}
          </div>
        )}
      </div>

      {showJump ? (
        <div className="pointer-events-none absolute inset-x-0 bottom-4 flex justify-center">
          <button
            type="button"
            onClick={jump}
            className="pointer-events-auto inline-flex items-center gap-1.5 rounded-full bg-navy px-3.5 py-2 text-xs font-semibold text-white shadow-lg transition-colors hover:bg-navy/90"
          >
            <ArrowDownIcon className="h-3.5 w-3.5" />
            {t.chat.newMessages}
          </button>
        </div>
      ) : null}
    </div>
  );
}
