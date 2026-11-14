export type Citation = {
  title: string;
  article: string;
  url: string;
};

export type ChatErrorKind =
  | "unauthenticated"
  | "invalid"
  | "server_unavailable"
  | "aborted";

export type SendMessageResult =
  | { ok: true; answer: string; citations: Citation[] }
  | { ok: false; error: ChatErrorKind };

export type SendMessageInput = {
  message: string;
  sessionId: string;
  signal?: AbortSignal;
};

const MODE = process.env.NEXT_PUBLIC_CHAT_MODE === "api" ? "api" : "mock";
const BASE_URL = (process.env.NEXT_PUBLIC_API_URL ?? "").replace(/\/+$/, "");
const TIMEOUT_MS = 30_000;

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function parseCitations(value: unknown): Citation[] | null {
  if (!Array.isArray(value)) {
    return null;
  }

  const citations: Citation[] = [];

  for (const entry of value) {
    if (!isRecord(entry)) {
      return null;
    }

    const { title, article, url } = entry;

    if (typeof title !== "string" || typeof url !== "string") {
      return null;
    }

    // The backend sends the article number as an integer, or null for chunks
    // without one (the annex). Keep it as text for display and storage.
    let articleText: string;

    if (typeof article === "string") {
      articleText = article;
    } else if (typeof article === "number" && Number.isFinite(article)) {
      articleText = String(article);
    } else if (article === null || article === undefined) {
      articleText = "";
    } else {
      return null;
    }

    citations.push({
      title,
      article: articleText,
      url,
    });
  }

  return citations;
}

function parseAnswer(body: unknown): SendMessageResult | null {
  if (!isRecord(body)) {
    return null;
  }

  const { answer, citations } = body;

  if (typeof answer !== "string" || !answer.trim()) {
    return null;
  }

  const parsedCitations = parseCitations(citations);

  if (!parsedCitations) {
    return null;
  }

  return { ok: true, answer, citations: parsedCitations };
}

export async function sendMessage({
  message,
  sessionId,
  signal,
}: SendMessageInput): Promise<SendMessageResult> {
  if (MODE === "mock") {
    const { mockSendMessage } = await import("./chatMock");
    return mockSendMessage({ message, sessionId, signal });
  }

  if (signal?.aborted) {
    return { ok: false, error: "aborted" };
  }

  const controller = new AbortController();
  let timedOut = false;

  const timer = setTimeout(() => {
    timedOut = true;
    controller.abort();
  }, TIMEOUT_MS);

  const forwardAbort = () => controller.abort();
  signal?.addEventListener("abort", forwardAbort, { once: true });

  try {
    const response = await fetch(`${BASE_URL}/chat`, {
      method: "POST",
      credentials: "include",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message, session_id: sessionId }),
      signal: controller.signal,
    });

    if (response.status === 200) {
      let body: unknown = null;

      try {
        body = await response.json();
      } catch {
        return { ok: false, error: "server_unavailable" };
      }

      return parseAnswer(body) ?? { ok: false, error: "server_unavailable" };
    }

    if (response.status === 401) {
      return { ok: false, error: "unauthenticated" };
    }

    if (response.status === 422) {
      return { ok: false, error: "invalid" };
    }

    return { ok: false, error: "server_unavailable" };
  } catch {
    if (signal?.aborted) {
      return { ok: false, error: "aborted" };
    }

    if (timedOut) {
      return { ok: false, error: "server_unavailable" };
    }

    return { ok: false, error: "server_unavailable" };
  } finally {
    clearTimeout(timer);
    signal?.removeEventListener("abort", forwardAbort);
  }
}
