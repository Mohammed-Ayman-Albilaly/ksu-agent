import type { Citation } from "@/lib/api/chat";

export const CHAT_STORAGE_PREFIX = "ksu-agent-chat:";
export const MAX_STORED_MESSAGES = 50;

export type ChatMessage = {
  id: string;
  role: "user" | "assistant";
  text: string;
  citations?: Citation[];
  status: "ok" | "error";
  errorKind?: "invalid" | "server_unavailable";
};

export type StoredChat = {
  session_id: string;
  messages: ChatMessage[];
};

function storageKey(userId: string): string {
  return `${CHAT_STORAGE_PREFIX}${userId}`;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function parseCitations(value: unknown): Citation[] | undefined {
  if (!Array.isArray(value)) {
    return undefined;
  }

  const citations: Citation[] = [];

  for (const entry of value) {
    if (!isRecord(entry)) {
      continue;
    }

    const { title, article, url } = entry;

    if (
      typeof title === "string" &&
      typeof url === "string" &&
      typeof article === "string"
    ) {
      citations.push({ title, article, url });
    }
  }

  return citations;
}

function parseMessage(value: unknown): ChatMessage | null {
  if (!isRecord(value)) {
    return null;
  }

  const { id, role, text, status, errorKind } = value;

  if (typeof id !== "string" || typeof text !== "string") {
    return null;
  }

  if (role !== "user" && role !== "assistant") {
    return null;
  }

  if (status !== "ok" && status !== "error") {
    return null;
  }

  const message: ChatMessage = { id, role, text, status };

  if (errorKind === "invalid" || errorKind === "server_unavailable") {
    message.errorKind = errorKind;
  }

  const citations = parseCitations(value.citations);

  if (citations && citations.length > 0) {
    message.citations = citations;
  }

  return message;
}

export function readChat(userId: string): StoredChat | null {
  try {
    const raw = window.sessionStorage.getItem(storageKey(userId));

    if (!raw) {
      return null;
    }

    const parsed: unknown = JSON.parse(raw);

    if (!isRecord(parsed)) {
      return null;
    }

    const sessionId = parsed.session_id;

    if (typeof sessionId !== "string" || !sessionId) {
      return null;
    }

    if (!Array.isArray(parsed.messages)) {
      return null;
    }

    const messages: ChatMessage[] = [];

    for (const entry of parsed.messages) {
      const message = parseMessage(entry);

      if (message) {
        messages.push(message);
      }
    }

    return { session_id: sessionId, messages: messages.slice(-MAX_STORED_MESSAGES) };
  } catch {
    return null;
  }
}

export function writeChat(userId: string, chat: StoredChat): void {
  try {
    window.sessionStorage.setItem(
      storageKey(userId),
      JSON.stringify({
        session_id: chat.session_id,
        messages: chat.messages.slice(-MAX_STORED_MESSAGES),
      }),
    );
  } catch {
    // Storage unavailable or full: the conversation stays in memory.
  }
}

export function clearChatSessions(): void {
  try {
    for (let index = window.sessionStorage.length - 1; index >= 0; index -= 1) {
      const key = window.sessionStorage.key(index);

      if (key && key.startsWith(CHAT_STORAGE_PREFIX)) {
        window.sessionStorage.removeItem(key);
      }
    }
  } catch {
    // Storage unavailable: nothing to clear.
  }
}
