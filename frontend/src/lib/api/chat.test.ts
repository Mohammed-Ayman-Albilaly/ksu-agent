import { afterEach, describe, expect, it, vi } from "vitest";

import { parseChatResponse } from "@/lib/api/chat";

const GPA = {
  cumulative_gpa: "4.21",
  scale: "5",
  earned_hours: 96,
  registered_hours: 99,
  as_of_term: "الفصل الأول 1448/1449",
};

afterEach(() => {
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
  vi.resetModules();
});

describe("a reasoning reply", () => {
  it("names its tools and the token that binds them to this question", () => {
    const result = parseChatResponse({
      type: "reason",
      tools: ["get_plan_progress", "get_gpa"],
      route_token: "signed.route-token",
    });

    expect(result).toEqual({
      ok: true,
      kind: "reason",
      tools: ["get_plan_progress", "get_gpa"],
      routeToken: "signed.route-token",
    });
  });

  it("is not a reason reply when the route token is missing or not text", () => {
    const tools = ["get_plan_progress", "get_gpa"];

    expect(parseChatResponse({ type: "reason", tools })).toBeNull();
    expect(parseChatResponse({ type: "reason", tools, route_token: "" })).toBeNull();
    expect(parseChatResponse({ type: "reason", tools, route_token: 7 })).toBeNull();
  });

  it("is not an answer when the tools are missing, empty or too many", () => {
    const token = { route_token: "signed.route-token" };

    expect(parseChatResponse({ type: "reason", ...token })).toBeNull();
    expect(parseChatResponse({ type: "reason", tools: [], ...token })).toBeNull();
    expect(
      parseChatResponse({ type: "reason", tools: ["a", "b", "c", "d"], ...token }),
    ).toBeNull();
    expect(parseChatResponse({ type: "reason", tools: [1], ...token })).toBeNull();
    expect(parseChatResponse({ type: "reason", tools: [""], ...token })).toBeNull();
  });

  it("does not change what an answer or a tool reply means", () => {
    expect(
      parseChatResponse({ type: "tool", tool: "get_gpa", args: {} }),
    ).toEqual({ ok: true, kind: "tool", tool: "get_gpa" });

    expect(
      parseChatResponse({ answer: "نص", citations: [] }),
    ).toEqual({
      ok: true,
      kind: "answer",
      answer: "نص",
      citations: [],
      basis: "regulation",
    });
  });

  it("keeps the basis the backend names, and the regulation for anything else", () => {
    expect(
      parseChatResponse({
        answer: "نص",
        citations: [],
        basis: "student_data",
      }),
    ).toEqual({
      ok: true,
      kind: "answer",
      answer: "نص",
      citations: [],
      basis: "student_data",
    });

    expect(
      parseChatResponse({ answer: "نص", citations: [], basis: "something" }),
    ).toEqual({
      ok: true,
      kind: "answer",
      answer: "نص",
      citations: [],
      basis: "regulation",
    });
  });
});

describe("sending the conversation so far", () => {
  const HISTORY = [
    { role: "user" as const, content: "كم الحد الأدنى للمعدل؟" },
    { role: "assistant" as const, content: "الحد الأدنى 2,75 من 5,00 (المادة 62)." },
  ];

  it("posts the earlier turns with the question, and parses the reply as before", async () => {
    vi.stubEnv("NEXT_PUBLIC_CHAT_MODE", "api");
    vi.stubEnv("NEXT_PUBLIC_API_URL", "https://api.example");
    vi.resetModules();

    const fetchMock = vi.fn(async () =>
      new Response(
        JSON.stringify({
          type: "answer",
          answer: "جواب",
          citations: [{ title: "لائحة", article: 62, url: "https://example" }],
        }),
        { status: 200 },
      ),
    );
    vi.stubGlobal("fetch", fetchMock);

    const { sendMessage } = await import("@/lib/api/chat");

    const result = await sendMessage({
      message: "وهل تنص على ذلك؟",
      sessionId: "s-1",
      history: HISTORY,
    });

    // The reply means exactly what it meant before history was sent.
    expect(result).toEqual({
      ok: true,
      kind: "answer",
      answer: "جواب",
      citations: [{ title: "لائحة", article: "62", url: "https://example" }],
      basis: "regulation",
    });

    const [url, init] = fetchMock.mock.calls[0] as unknown as [
      string,
      RequestInit,
    ];
    expect(url).toBe("https://api.example/chat");
    expect(JSON.parse(String(init.body))).toEqual({
      message: "وهل تنص على ذلك؟",
      session_id: "s-1",
      history: HISTORY,
    });
  });

  it("sends no turns when a caller passes none", async () => {
    vi.stubEnv("NEXT_PUBLIC_CHAT_MODE", "api");
    vi.resetModules();

    const fetchMock = vi.fn(async () =>
      new Response(JSON.stringify({ type: "tool", tool: "get_gpa" }), {
        status: 200,
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    const { sendMessage } = await import("@/lib/api/chat");

    expect(await sendMessage({ message: "ما معدلي؟", sessionId: "s-1" })).toEqual({
      ok: true,
      kind: "tool",
      tool: "get_gpa",
    });

    const [, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    expect(JSON.parse(String(init.body))).toEqual({
      message: "ما معدلي؟",
      session_id: "s-1",
      history: [],
    });
  });
});

describe("sending the approved values", () => {
  it("posts the data map to /chat/with-data", async () => {
    vi.stubEnv("NEXT_PUBLIC_CHAT_MODE", "api");
    vi.stubEnv("NEXT_PUBLIC_API_URL", "https://api.example/");
    vi.resetModules();

    const fetchMock = vi.fn(async () =>
      new Response(
        JSON.stringify({ type: "answer", answer: "جواب", citations: [] }),
        { status: 200 },
      ),
    );
    vi.stubGlobal("fetch", fetchMock);

    const { sendWithData } = await import("@/lib/api/chat");
    const data = { get_gpa: GPA };

    const result = await sendWithData({
      message: "هل أقدر أتخرج؟",
      sessionId: "s-1",
      data,
      routeToken: "signed.route-token",
    });

    expect(result).toEqual({
      ok: true,
      kind: "answer",
      answer: "جواب",
      citations: [],
      basis: "regulation",
    });
    const [url, init] = fetchMock.mock.calls[0] as unknown as [
      string,
      RequestInit,
    ];
    expect(url).toBe("https://api.example/chat/with-data");
    expect(JSON.parse(String(init.body))).toEqual({
      message: "هل أقدر أتخرج؟",
      session_id: "s-1",
      data,
      route_token: "signed.route-token",
    });
  });

  it("reports a 422 as an invalid message, not as a server outage", async () => {
    vi.stubEnv("NEXT_PUBLIC_CHAT_MODE", "api");
    vi.resetModules();

    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response("{}", { status: 422 })),
    );

    const { sendWithData } = await import("@/lib/api/chat");

    expect(
      await sendWithData({
        message: "س",
        sessionId: "s-1",
        data: { get_gpa: GPA },
        routeToken: "signed.route-token",
      }),
    ).toEqual({ ok: false, error: "invalid" });
  });

  it("reports a missing session as unauthenticated", async () => {
    vi.stubEnv("NEXT_PUBLIC_CHAT_MODE", "api");
    vi.resetModules();

    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response("{}", { status: 401 })),
    );

    const { sendWithData } = await import("@/lib/api/chat");

    expect(
      await sendWithData({
        message: "س",
        sessionId: "s-1",
        data: { get_gpa: GPA },
        routeToken: "signed.route-token",
      }),
    ).toEqual({ ok: false, error: "unauthenticated" });
  });
});
