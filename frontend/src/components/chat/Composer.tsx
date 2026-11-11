"use client";

import {
  useEffect,
  type KeyboardEvent,
  type RefObject,
} from "react";
import { useLanguage } from "@/components/LanguageProvider";
import { SendIcon } from "@/components/icons";

export const MAX_MESSAGE_LENGTH = 1000;

const COUNTER_THRESHOLD = 800;
const MAX_TEXTAREA_HEIGHT = 144;

type ComposerProps = {
  value: string;
  onChange: (value: string) => void;
  onSend: () => void;
  pending: boolean;
  textareaRef: RefObject<HTMLTextAreaElement | null>;
};

export function Composer({
  value,
  onChange,
  onSend,
  pending,
  textareaRef,
}: ComposerProps) {
  const { t } = useLanguage();

  const tooLong = value.length > MAX_MESSAGE_LENGTH;
  const canSend = value.trim().length > 0 && !tooLong && !pending;
  const showCounter = value.length > COUNTER_THRESHOLD;

  useEffect(() => {
    const element = textareaRef.current;

    if (!element) {
      return;
    }

    element.style.height = "auto";
    element.style.height = `${Math.min(element.scrollHeight, MAX_TEXTAREA_HEIGHT)}px`;
    element.style.overflowY =
      element.scrollHeight > MAX_TEXTAREA_HEIGHT ? "auto" : "hidden";
  }, [value, textareaRef]);

  const handleKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key !== "Enter" || event.shiftKey) {
      return;
    }

    if (event.nativeEvent.isComposing) {
      return;
    }

    if (window.matchMedia("(pointer: coarse)").matches) {
      return;
    }

    event.preventDefault();

    if (canSend) {
      onSend();
    }
  };

  return (
    <div className="shrink-0 border-t border-slate-200/80 bg-white">
      <div className="mx-auto w-full max-w-3xl px-4 pb-3 pt-3 sm:px-6">
        <form
          onSubmit={(event) => {
            event.preventDefault();

            if (canSend) {
              onSend();
            }
          }}
          className="flex items-end gap-2 rounded-2xl border border-slate-300 bg-white px-3 py-2 transition-colors focus-within:border-teal"
        >
          <label htmlFor="chat-composer" className="sr-only">
            {t.chat.placeholder}
          </label>

          <textarea
            id="chat-composer"
            ref={textareaRef}
            rows={1}
            value={value}
            onChange={(event) => onChange(event.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={t.chat.placeholder}
            dir="auto"
            aria-describedby="chat-composer-hint"
            className="max-h-36 w-full resize-none bg-transparent py-1.5 text-sm leading-6 text-ink placeholder:text-muted/60"
          />

          <button
            type="submit"
            disabled={!canSend}
            aria-label={t.chat.send}
            className="mb-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-teal-deep text-white transition-colors hover:bg-teal-dark disabled:cursor-not-allowed disabled:bg-slate-300"
          >
            <SendIcon className="h-4 w-4" />
          </button>
        </form>

        <div className="mt-2 flex items-center justify-between gap-3">
          <p
            id="chat-composer-hint"
            className="text-[11px] leading-relaxed text-muted"
          >
            {t.chat.disclaimer}
          </p>

          {showCounter ? (
            <p
              className={
                tooLong
                  ? "shrink-0 text-[11px] font-semibold text-red-600"
                  : "shrink-0 text-[11px] text-muted"
              }
            >
              {value.length}/{MAX_MESSAGE_LENGTH}
            </p>
          ) : null}
        </div>
      </div>
    </div>
  );
}
