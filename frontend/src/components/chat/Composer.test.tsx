import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { Composer } from "@/components/chat/Composer";
import { dictionary } from "@/lib/i18n";

vi.mock("@/components/LanguageProvider", () => ({
  useLanguage: () => ({ lang: "ar", setLang: vi.fn(), t: dictionary.ar }),
}));

const t = dictionary.ar;

function renderComposer(overrides: Partial<Parameters<typeof Composer>[0]> = {}) {
  const props = {
    value: "سؤال",
    onChange: vi.fn(),
    onSend: vi.fn(),
    onStop: vi.fn(),
    pending: false,
    textareaRef: { current: null },
    ...overrides,
  };

  render(<Composer {...props} />);

  return props;
}

describe("Composer", () => {
  it("shows the send button and no stop button when idle", () => {
    renderComposer();

    expect(screen.getByLabelText(t.chat.send)).toBeDefined();
    expect(screen.queryByLabelText(t.chat.stop)).toBeNull();
  });

  it("replaces the send button with the stop button while a reply is pending", () => {
    renderComposer({ pending: true });

    expect(screen.queryByLabelText(t.chat.send)).toBeNull();
    expect(screen.getByLabelText(t.chat.stop)).toBeDefined();
  });

  it("calls onStop when the stop button is pressed", () => {
    const props = renderComposer({ pending: true });

    fireEvent.click(screen.getByLabelText(t.chat.stop));

    expect(props.onStop).toHaveBeenCalledTimes(1);
    expect(props.onSend).not.toHaveBeenCalled();
  });
});
