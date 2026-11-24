import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import type { Mock } from "vitest";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ChatScreen } from "@/components/chat/ChatScreen";
import { dictionary } from "@/lib/i18n";
import { sendMessage, sendWithData } from "@/lib/api/chat";
import { runTool } from "@/lib/extension";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: vi.fn(), push: vi.fn() }),
}));

vi.mock("@/components/AuthProvider", () => ({
  useAuth: () => ({
    user: { id: "u-1", full_name: "نورة العتيبي", email: "444100001@student.ksu.edu.sa" },
    status: "authenticated",
    logout: vi.fn(),
  }),
}));

vi.mock("@/components/LanguageProvider", () => ({
  useLanguage: () => ({
    lang: "ar",
    setLang: vi.fn(),
    t: dictionary.ar,
  }),
}));

// The functions are mocked; the module's own constants stay real.
vi.mock("@/lib/api/chat", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api/chat")>();

  return { ...actual, sendMessage: vi.fn(), sendWithData: vi.fn() };
});

vi.mock("@/lib/extension", async () => {
  const actual =
    await vi.importActual<typeof import("@/lib/extension")>("@/lib/extension");

  return { ...actual, runTool: vi.fn() };
});

const t = dictionary.ar;
const QUESTION = "هل أقدر أتخرج الفصل القادم؟";

const GPA = {
  cumulative_gpa: "4.21",
  scale: "5",
  earned_hours: 96,
  registered_hours: 987654,
  as_of_term: "الفصل الأول 1448/1449",
};

const PLAN = {
  completed_hours: 96,
  remaining_hours: 6,
  remaining_courses: [],
};

const DATA = { get_gpa: GPA, get_plan_progress: PLAN };

async function ask() {
  fireEvent.change(screen.getByRole("textbox"), {
    target: { value: QUESTION },
  });
  fireEvent.click(screen.getByRole("button", { name: t.chat.send }));
}

async function askQuestion(question: string) {
  // The answer settles inside act, so the next question starts from a settled screen.
  await act(async () => {
    fireEvent.change(screen.getByRole("textbox"), {
      target: { value: question },
    });
    fireEvent.click(screen.getByRole("button", { name: t.chat.send }));
  });
}

/** A plain answer to one question, as the API would return it. */
function answerWith(question: string) {
  return {
    ok: true as const,
    kind: "answer" as const,
    answer: `جواب ${question}`,
    citations: [],
    basis: "regulation" as const,
  };
}

/** The earlier turns the request at that index carried. */
function sentHistory(index: number) {
  const [sent] = (sendMessage as Mock).mock.calls[index] as [
    { history: { role: string; content: string }[] },
  ];

  return sent.history;
}

function storedText(): string {
  const stored: Record<string, string> = {};

  for (let index = 0; index < window.sessionStorage.length; index += 1) {
    const key = window.sessionStorage.key(index);
    stored[String(key)] = window.sessionStorage.getItem(String(key)) ?? "";
  }

  for (let index = 0; index < window.localStorage.length; index += 1) {
    const key = window.localStorage.key(index);
    stored[`local:${String(key)}`] =
      window.localStorage.getItem(String(key)) ?? "";
  }

  return JSON.stringify(stored);
}

beforeEach(() => {
  (sendMessage as Mock).mockResolvedValue({
    ok: true,
    kind: "reason",
    tools: ["get_gpa", "get_plan_progress"],
    routeToken: "signed.route-token",
  });

  (runTool as Mock).mockImplementation(async (tool: string) => ({
    ok: true,
    data: DATA[tool as keyof typeof DATA],
    readAt: "2026-11-20T10:00:00+03:00",
  }));
});

describe("a reasoning question", () => {
  it("shows one card for the question, after reading every tool", async () => {
    render(<ChatScreen />);

    await ask();

    const card = await screen.findByRole("group", { name: t.chat.consent.title });

    expect((runTool as Mock).mock.calls.map(([tool]) => tool)).toEqual([
      "get_gpa",
      "get_plan_progress",
    ]);
    expect(within(card).getAllByRole("listitem")).toHaveLength(2);
    expect(sendWithData).not.toHaveBeenCalled();
  });

  it("posts exactly the values the card shows, once, when the student approves", async () => {
    (sendWithData as Mock).mockResolvedValue({
      ok: true,
      kind: "answer",
      answer: "تستطيع التخرج بعد 6 ساعات (المادة 62).",
      citations: [],
      basis: "regulation",
    });

    render(<ChatScreen />);
    await ask();

    const card = await screen.findByRole("group", { name: t.chat.consent.title });

    fireEvent.click(
      within(card).getByRole("button", { name: t.chat.consent.showJson }),
    );
    const shown = within(card).getByText(/"cumulative_gpa"/).textContent;

    fireEvent.click(
      within(card).getByRole("button", { name: t.chat.consent.approve }),
    );

    await waitFor(() => expect(sendWithData).toHaveBeenCalledTimes(1));

    const [sent] = (sendWithData as Mock).mock.calls[0] as [
      { message: string; data: unknown; routeToken: string },
    ];

    expect(sent.message).toBe(QUESTION);
    expect(sent.data).toEqual(DATA);
    // The token /chat issued for this question goes back with it, unchanged.
    expect(sent.routeToken).toBe("signed.route-token");
    expect(shown).toBe(JSON.stringify(sent.data, null, 2));

    expect(
      await screen.findByText("تستطيع التخرج بعد 6 ساعات (المادة 62)."),
    ).toBeTruthy();

    // Single use: the card is gone, so a second approval is impossible.
    expect(screen.queryByRole("group", { name: t.chat.consent.title })).toBeNull();
  });

  it("marks an answer that rests on the student's own data, not the regulation", async () => {
    (sendWithData as Mock).mockResolvedValue({
      ok: true,
      kind: "answer",
      answer: "لديك تعارض بين اختبارين يوم الأحد.",
      citations: [],
      basis: "student_data",
    });

    render(<ChatScreen />);
    await ask();

    const card = await screen.findByRole("group", { name: t.chat.consent.title });

    fireEvent.click(
      within(card).getByRole("button", { name: t.chat.consent.approve }),
    );

    expect(await screen.findByText(t.chat.notFromRegulation)).toBeTruthy();
    expect(screen.queryByText(t.chat.noSource)).toBeNull();
  });

  it("sends nothing when the student cancels, and answers from the values instead", async () => {
    render(<ChatScreen />);
    await ask();

    const card = await screen.findByRole("group", { name: t.chat.consent.title });

    fireEvent.click(
      within(card).getByRole("button", { name: t.chat.consent.cancel }),
    );

    await waitFor(() =>
      expect(screen.queryByRole("group", { name: t.chat.consent.title })).toBeNull(),
    );

    expect(sendWithData).not.toHaveBeenCalled();
    expect(screen.getByText(t.chat.consent.notSent)).toBeTruthy();
    expect(screen.getByText(/4\.21/)).toBeTruthy();
  });

  it("never writes the values to web storage", async () => {
    render(<ChatScreen />);
    await ask();

    const card = await screen.findByRole("group", { name: t.chat.consent.title });

    fireEvent.click(
      within(card).getByRole("button", { name: t.chat.consent.cancel }),
    );

    await waitFor(() =>
      expect(screen.queryByRole("group", { name: t.chat.consent.title })).toBeNull(),
    );

    const stored = storedText();

    expect(stored).not.toContain("987654");
    expect(stored).not.toContain("cumulative_gpa");
  });

  it("sends the last six turns with the question, and never the question being asked", async () => {
    (sendMessage as Mock).mockImplementation(
      async ({ message }: { message: string }) => answerWith(message),
    );

    render(<ChatScreen />);

    for (const question of ["سؤال ١", "سؤال ٢", "سؤال ٣", "سؤال ٤"]) {
      await askQuestion(question);
      await screen.findByText(`جواب ${question}`);
    }

    // The first question had nothing before it; the fourth had the three exchanges before it.
    expect(sentHistory(0)).toEqual([]);
    expect(sentHistory(3)).toEqual([
      { role: "user", content: "سؤال ١" },
      { role: "assistant", content: "جواب سؤال ١" },
      { role: "user", content: "سؤال ٢" },
      { role: "assistant", content: "جواب سؤال ٢" },
      { role: "user", content: "سؤال ٣" },
      { role: "assistant", content: "جواب سؤال ٣" },
    ]);
  });

  it("leaves out a turn that carries no text", async () => {
    (sendMessage as Mock).mockResolvedValueOnce({
      ok: false,
      error: "server_unavailable",
    });
    (sendMessage as Mock).mockImplementation(
      async ({ message }: { message: string }) => answerWith(message),
    );

    render(<ChatScreen />);

    await askQuestion("سؤال ١");
    await waitFor(() => expect(sendMessage).toHaveBeenCalledTimes(1));

    await askQuestion("سؤال ٢");
    await screen.findByText("جواب سؤال ٢");

    // The failed answer is a bubble with no text, so only the question travels.
    expect(sentHistory(1)).toEqual([{ role: "user", content: "سؤال ١" }]);
  });

  it("reports the site to open when the extension cannot read a page", async () => {
    (runTool as Mock).mockResolvedValue({ ok: false, error: "not_logged_in" });

    render(<ChatScreen />);
    await ask();

    expect(
      await screen.findByText(
        t.chat.errors.notSignedInFor.replace("{source}", t.chat.toolSources.edugate),
      ),
    ).toBeTruthy();
    expect(
      screen.queryByRole("group", { name: t.chat.consent.title }),
    ).toBeNull();
  });
});
