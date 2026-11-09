"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import { useAuth } from "@/components/AuthProvider";
import { useLanguage } from "@/components/LanguageProvider";
import { ChatTopBar } from "@/components/chat/ChatTopBar";
import { Composer, MAX_MESSAGE_LENGTH } from "@/components/chat/Composer";
import { EmptyState } from "@/components/chat/EmptyState";
import { MessageList } from "@/components/chat/MessageList";
import { sendMessage } from "@/lib/api/chat";
import {
  MAX_STORED_MESSAGES,
  readChat,
  writeChat,
  type ChatMessage,
} from "@/lib/chatStorage";

function createId(): string {
  try {
    if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
      return crypto.randomUUID();
    }
  } catch {
    // Fall through to the timestamp based id.
  }

  return `id-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;
}

export function ChatScreen() {
  const { t } = useLanguage();
  const { user, status, logout } = useAuth();
  const router = useRouter();

  const [sessionId, setSessionId] = useState(createId);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [hydrated, setHydrated] = useState(false);
  const [pending, setPending] = useState(false);
  const [text, setText] = useState("");

  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const abortRef = useRef<AbortController | null>(null);
  const requestRef = useRef(0);

  const userId = user?.id ?? null;

  useEffect(() => {
    if (status === "guest") {
      router.replace("/login?next=/chat");
    }
  }, [status, router]);

  useEffect(() => {
    if (!userId) {
      return;
    }

    const stored = readChat(userId);

    if (stored) {
      setSessionId(stored.session_id);
      setMessages(stored.messages);
    }

    setHydrated(true);
  }, [userId]);

  useEffect(() => {
    if (!hydrated || !userId) {
      return;
    }

    writeChat(userId, { session_id: sessionId, messages });
  }, [hydrated, userId, sessionId, messages]);

  const appendMessage = useCallback((message: ChatMessage) => {
    setMessages((current) =>
      [...current, message].slice(-MAX_STORED_MESSAGES),
    );
  }, []);

  const run = useCallback(
    async (question: string, userMessageId: string) => {
      const requestId = requestRef.current + 1;
      requestRef.current = requestId;

      const controller = new AbortController();
      abortRef.current = controller;
      setPending(true);

      const result = await sendMessage({
        message: question,
        sessionId,
        signal: controller.signal,
      });

      if (requestRef.current !== requestId) {
        return;
      }

      abortRef.current = null;
      setPending(false);

      if (result.ok) {
        appendMessage({
          id: createId(),
          role: "assistant",
          text: result.answer,
          citations: result.citations,
          status: "ok",
        });
        return;
      }

      if (result.error === "aborted") {
        setMessages((current) =>
          current.filter((message) => message.id !== userMessageId),
        );
        setText(question);
        textareaRef.current?.focus();
        return;
      }

      if (result.error === "unauthenticated") {
        await logout();
        router.replace("/login?next=/chat");
        return;
      }

      appendMessage({
        id: createId(),
        role: "assistant",
        text: "",
        status: "error",
        errorKind: result.error,
      });
    },
    [appendMessage, logout, router, sessionId],
  );

  const send = useCallback(
    (question: string) => {
      const trimmed = question.trim();

      if (!trimmed || trimmed.length > MAX_MESSAGE_LENGTH || abortRef.current) {
        return;
      }

      const userMessageId = createId();

      appendMessage({
        id: userMessageId,
        role: "user",
        text: trimmed,
        status: "ok",
      });
      setText("");
      textareaRef.current?.focus();
      void run(trimmed, userMessageId);
    },
    [appendMessage, run],
  );

  const stop = useCallback(() => {
    abortRef.current?.abort();
  }, []);

  const retry = useCallback(
    (messageId: string) => {
      if (abortRef.current) {
        return;
      }

      const index = messages.findIndex((message) => message.id === messageId);

      if (index < 1) {
        return;
      }

      for (let cursor = index - 1; cursor >= 0; cursor -= 1) {
        const candidate = messages[cursor];

        if (candidate.role === "user" && candidate.text) {
          setMessages((current) =>
            current.filter((message) => message.id !== messageId),
          );
          void run(candidate.text, candidate.id);
          return;
        }
      }
    },
    [messages, run],
  );

  const newChat = useCallback(() => {
    if (abortRef.current) {
      return;
    }

    requestRef.current += 1;
    setSessionId(createId());
    setMessages([]);
    setText("");
    textareaRef.current?.focus();
  }, []);

  if (status !== "authenticated" || !user || !hydrated) {
    return (
      <div className="flex flex-1 items-center justify-center">
        <span
          role="status"
          aria-label={t.auth.pending}
          className="h-6 w-6 animate-spin rounded-full border-2 border-slate-300 border-t-teal motion-reduce:animate-none"
        />
      </div>
    );
  }

  const firstName = user.full_name.trim().split(/\s+/)[0] ?? "";

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <ChatTopBar onNewChat={newChat} newChatDisabled={pending} />

      <MessageList
        messages={messages}
        pending={pending}
        onRetry={retry}
        onStop={stop}
        emptyState={
          <EmptyState firstName={firstName} onSelect={send} disabled={pending} />
        }
      />

      <Composer
        value={text}
        onChange={setText}
        onSend={() => send(text)}
        pending={pending}
        textareaRef={textareaRef}
      />
    </div>
  );
}
