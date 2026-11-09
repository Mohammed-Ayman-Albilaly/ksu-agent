// DEVELOPMENT ONLY.
import type { SendMessageInput, SendMessageResult } from "./chat";

const DELAY_MS = 1200;

const CITATION = {
  title:
    "KSU Regulations of Study and Examinations — undergraduate, with executive rules (v2)",
  article: "—",
  url: "https://dar.ksu.edu.sa/sites/dar.ksu.edu.sa/files/users/user980/excutive_regulations_2.pdf",
};

const ANSWERS = {
  ar: {
    withSource:
      "[وضع تجريبي] هذه إجابة تجريبية تُعرض أثناء التطوير فقط، وليست إجابة من المساعد الحقيقي. عند تشغيل الخادم تأتي الإجابة من مستندات جامعة الملك سعود الرسمية مع اسم المستند ورقم المادة ورابطها. للتأكد من أي شرط أو حكم، راجع لائحة الدراسة والاختبارات الرسمية أو عمادة القبول والتسجيل.",
    withoutSource:
      "[وضع تجريبي] هذه إجابة تجريبية تُعرض أثناء التطوير فقط. في هذه الحالة لا يوجد مصدر رسمي مرتبط بالإجابة، ولن يخمّن المساعد الحقيقي عند غياب المصدر.",
  },
  en: {
    withSource:
      "[Demo mode] This is a demo answer shown during development only, not an answer from the real assistant. With the server running, answers come from official King Saud University documents with the document name, article number and link. To confirm any rule, check the official Study and Examination Regulations or the Deanship of Admission and Registration.",
    withoutSource:
      "[Demo mode] This is a demo answer shown during development only. In this case no official source is attached to the answer, and the real assistant will not guess when no source is found.",
  },
};

function delay(ms: number, signal?: AbortSignal): Promise<boolean> {
  return new Promise((resolve) => {
    if (signal?.aborted) {
      resolve(false);
      return;
    }

    const finish = (completed: boolean) => {
      clearTimeout(timer);
      signal?.removeEventListener("abort", onAbort);
      resolve(completed);
    };

    const onAbort = () => finish(false);

    const timer = setTimeout(() => finish(true), ms);

    signal?.addEventListener("abort", onAbort, { once: true });
  });
}

export async function mockSendMessage({
  message,
  signal,
}: SendMessageInput): Promise<SendMessageResult> {
  const completed = await delay(DELAY_MS, signal);

  if (!completed) {
    return { ok: false, error: "aborted" };
  }

  if (message.includes("#error")) {
    return { ok: false, error: "server_unavailable" };
  }

  const isEnglish = /[A-Za-z]/.test(message);
  const text = isEnglish ? ANSWERS.en : ANSWERS.ar;

  if (message.includes("#nosource")) {
    return { ok: true, answer: text.withoutSource, citations: [] };
  }

  return {
    ok: true,
    answer: text.withSource,
    citations: [{ ...CITATION }],
  };
}
