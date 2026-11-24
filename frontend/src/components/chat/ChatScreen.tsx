"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import { useAuth } from "@/components/AuthProvider";
import { useLanguage } from "@/components/LanguageProvider";
import { ChatTopBar } from "@/components/chat/ChatTopBar";
import { Composer, MAX_MESSAGE_LENGTH } from "@/components/chat/Composer";
import { ConsentCard } from "@/components/chat/ConsentCard";
import { EmptyState } from "@/components/chat/EmptyState";
import { MessageList } from "@/components/chat/MessageList";
import {
  MAX_HISTORY_TURNS,
  sendMessage,
  sendWithData,
  type ChatHistoryTurn,
} from "@/lib/api/chat";
import {
  MAX_STORED_MESSAGES,
  readChat,
  writeChat,
  type ChatMessage,
} from "@/lib/chatStorage";
import { readForConsent, type ConsentRequest } from "@/lib/consent";
import { runTool } from "@/lib/extension";
import {
  consentAnswers,
  personalAnswer,
  toolErrorText,
} from "@/lib/personalAnswers";

/**
 * The turns sent with a question: the last six of the conversation, user and assistant only.
 *
 * A turn with no text is the pending placeholder or a failed answer, so it carries nothing. A
 * personal answer was built in the browser from values the server must never see (ADR 0001, rules 2
 * and 4), so it stays on the device with the consent card it came from.
 */
export function historyFrom(messages: ChatMessage[]): ChatHistoryTurn[] {
  return messages
    .filter((message) => message.personal !== true && message.text.trim() !== "")
    .map(({ role, text }) => ({ role, content: text }))
    .slice(-MAX_HISTORY_TURNS);
}

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
  const { t, lang } = useLanguage();
  const { user, status, logout } = useAuth();
  const router = useRouter();

  const [sessionId, setSessionId] = useState(createId);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [hydrated, setHydrated] = useState(false);
  const [pending, setPending] = useState(false);
  const [text, setText] = useState("");
  // The consent step's values live here and nowhere else: not in the message list, not in
  // storage, not in the URL. Approving or cancelling drops them (ADR 0001, rule 5).
  const [consent, setConsent] = useState<{
    request: ConsentRequest;
    messageId: string;
  } | null>(null);

  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const abortRef = useRef<AbortController | null>(null);
  const requestRef = useRef(0);
  const mountedRef = useRef(true);

  const userId = user?.id ?? null;

  useEffect(() => {
    if (status === "guest") {
      router.replace("/login?next=/chat");
    }
  }, [status, router]);

  useEffect(() => {
    mountedRef.current = true;

    return () => {
      mountedRef.current = false;
      abortRef.current?.abort();
      abortRef.current = null;
    };
  }, []);

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

  // A tool runs in the student's browser: the answer is built here from the values the
  // extension read, and those values are never sent back to the server.
  const answerWithTool = useCallback(
    async (tool: string, requestId: number) => {
      const outcome = await runTool(tool);

      if (!mountedRef.current || requestRef.current !== requestId) {
        return;
      }

      abortRef.current = null;
      setPending(false);

      if (outcome.ok) {
        const answer = personalAnswer(tool, outcome.data, lang);

        appendMessage({
          id: createId(),
          role: "assistant",
          text: answer ?? toolErrorText(t, "page_unreadable", tool),
          note: t.chat.personalNote,
          personal: true,
          status: "ok",
        });
        return;
      }

      appendMessage({
        id: createId(),
        role: "assistant",
        text: toolErrorText(t, outcome.error, tool),
        personal: true,
        status: "ok",
      });
    },
    [appendMessage, lang, t],
  );

  const run = useCallback(
    async (
      question: string,
      userMessageId: string,
      history: ChatHistoryTurn[],
    ) => {
      const requestId = requestRef.current + 1;
      requestRef.current = requestId;

      const controller = new AbortController();
      abortRef.current = controller;
      setPending(true);

      // The earlier turns go with the question: the server keeps no conversation of its own.
      const result = await sendMessage({
        message: question,
        sessionId,
        history,
        signal: controller.signal,
      });

      if (!mountedRef.current || requestRef.current !== requestId) {
        return;
      }

      if (result.ok && result.kind === "tool") {
        await answerWithTool(result.tool, requestId);
        return;
      }

      // A reasoning question needs values compared, so every tool runs first, then the
      // student sees one card and decides for this question only.
      if (result.ok && result.kind === "reason") {
        const outcome = await readForConsent(question, result, t, runTool);

        if (!mountedRef.current || requestRef.current !== requestId) {
          return;
        }

        abortRef.current = null;
        setPending(false);

        if (!outcome.ok) {
          appendMessage({
            id: createId(),
            role: "assistant",
            text: toolErrorText(t, outcome.error, outcome.tool),
            personal: true,
            status: "ok",
          });
          return;
        }

        setConsent({ request: outcome.request, messageId: userMessageId });
        return;
      }

      abortRef.current = null;
      setPending(false);

      if (result.ok && result.kind === "answer") {
        appendMessage({
          id: createId(),
          role: "assistant",
          text: result.answer,
          citations: result.citations,
          basis: result.basis,
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
        errorKind: result.ok ? "server_unavailable" : result.error,
      });
    },
    [answerWithTool, appendMessage, logout, router, sessionId, t],
  );

  const send = useCallback(
    (question: string) => {
      const trimmed = question.trim();

      if (!trimmed || trimmed.length > MAX_MESSAGE_LENGTH || abortRef.current) {
        return;
      }

      const userMessageId = createId();

      // A new question replaces the previous card, and drops its values with it.
      setConsent(null);
      appendMessage({
        id: userMessageId,
        role: "user",
        text: trimmed,
        status: "ok",
      });
      setText("");
      textareaRef.current?.focus();
      // Built before this question joins the list: the conversation so far, not the question itself.
      void run(trimmed, userMessageId, historyFrom(messages));
    },
    [appendMessage, messages, run],
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
          // Only the turns before the question being retried travel with it again.
          const earlier = historyFrom(messages.slice(0, cursor));
          void run(candidate.text, candidate.id, earlier);
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
    setConsent(null);
    setSessionId(createId());
    setMessages([]);
    setText("");
    textareaRef.current?.focus();
  }, []);

  // Approving sends the values the card showed, once, for this question. The card is gone
  // before the request starts, so it cannot be approved a second time.
  const approveConsent = useCallback(async () => {
    if (!consent) {
      return;
    }

    const { request, messageId } = consent;
    setConsent(null);
    setPending(true);

    const controller = new AbortController();
    abortRef.current = controller;

    const result = await sendWithData({
      message: request.question,
      sessionId,
      data: request.data,
      routeToken: request.routeToken,
      signal: controller.signal,
    });

    if (!mountedRef.current) {
      return;
    }

    abortRef.current = null;
    setPending(false);

    if (result.ok && result.kind === "answer") {
      appendMessage({
        id: createId(),
        role: "assistant",
        text: result.answer,
        citations: result.citations,
        basis: result.basis,
        status: "ok",
      });
      return;
    }

    if (!result.ok && result.error === "aborted") {
      setMessages((current) =>
        current.filter((message) => message.id !== messageId),
      );
      setText(request.question);
      textareaRef.current?.focus();
      return;
    }

    if (!result.ok && result.error === "unauthenticated") {
      await logout();
      router.replace("/login?next=/chat");
      return;
    }

    appendMessage({
      id: createId(),
      role: "assistant",
      text: "",
      status: "error",
      errorKind:
        !result.ok && result.error === "invalid" ? "invalid" : "server_unavailable",
    });
  }, [appendMessage, consent, logout, router, sessionId]);

  // Cancelling sends nothing: the values already read answer from the templates instead.
  const cancelConsent = useCallback(() => {
    if (!consent) {
      return;
    }

    const { request } = consent;
    setConsent(null);
    appendMessage({
      id: createId(),
      role: "assistant",
      text: consentAnswers(
        request.tools.map(({ tool, payload }) => ({ tool, data: payload })),
        lang,
      ),
      note: t.chat.consent.notSent,
      personal: true,
      status: "ok",
    });
  }, [appendMessage, consent, lang, t]);

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
        emptyState={
          <EmptyState firstName={firstName} onSelect={send} disabled={pending} />
        }
        consent={
          consent ? (
            <ConsentCard
              request={consent.request}
              busy={pending}
              onApprove={() => void approveConsent()}
              onCancel={cancelConsent}
            />
          ) : null
        }
      />

      <Composer
        value={text}
        onChange={setText}
        onSend={() => send(text)}
        onStop={stop}
        pending={pending}
        textareaRef={textareaRef}
      />
    </div>
  );
}
