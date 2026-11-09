export type Lang = "ar" | "en";

export type Dictionary = {
  meta: {
    description: string;
  };
  skipToContent: string;
  brand: string;
  nav: {
    label: string;
    chat: string;
    login: string;
    register: string;
    openMenu: string;
    closeMenu: string;
  };
  language: {
    label: string;
    short: string;
  };
  hero: {
    eyebrow: string;
    title: string;
    subtitle: string;
    primary: string;
    secondary: string;
    mock: {
      label: string;
      question: string;
      answer: string;
      citation: string;
    };
  };
  features: {
    title: string;
    subtitle: string;
    items: {
      cited: { title: string; body: string };
      bilingual: { title: string; body: string };
      honest: { title: string; body: string };
      ccis: { title: string; body: string };
    };
  };
  how: {
    title: string;
    subtitle: string;
    steps: {
      ask: { title: string; body: string };
      search: { title: string; body: string };
      answer: { title: string; body: string };
    };
  };
  note: string;
  footer: {
    project: string;
    disclaimer: string;
    copyright: string;
  };
};

const ar: Dictionary = {
  meta: {
    description:
      "مساعد ذكي لطلاب كلية علوم الحاسب والمعلومات في جامعة الملك سعود، يجيب عن الأنظمة والخطط الدراسية والتقويم الأكاديمي مع ذكر المصدر الرسمي.",
  },
  skipToContent: "تخطي إلى المحتوى",
  brand: "KSU Agent",
  nav: {
    label: "التنقل الرئيسي",
    chat: "المحادثة",
    login: "تسجيل الدخول",
    register: "إنشاء حساب",
    openMenu: "فتح القائمة",
    closeMenu: "إغلاق القائمة",
  },
  language: {
    label: "التبديل إلى الإنجليزية",
    short: "EN",
  },
  hero: {
    eyebrow: "مساعد أكاديمي لطلاب كلية علوم الحاسب والمعلومات",
    title: "اسأل عن أنظمة الجامعة واحصل على إجابة موثّقة",
    subtitle:
      "مساعد ذكي لطلاب كلية علوم الحاسب والمعلومات، يجيب بالعربية أو الإنجليزية ويذكر المادة والرابط الرسمي مع كل إجابة.",
    primary: "ابدأ المحادثة",
    secondary: "إنشاء حساب",
    mock: {
      label: "مثال توضيحي",
      question: "متى يُحرم الطالب من دخول الاختبار النهائي؟",
      answer:
        "يوضح المساعد الشرط كما ورد في اللائحة، مع ذكر رقم المادة ورابط المستند الرسمي للتحقق منه.",
      citation: "لائحة الدراسة والاختبارات · الإصدار 2",
    },
  },
  features: {
    title: "لماذا KSU Agent؟",
    subtitle: "كل إجابة مبنية على مستند رسمي، لا على تخمين.",
    items: {
      cited: {
        title: "إجابات موثّقة",
        body: "كل إجابة تعرض نص المادة ورابط المستند الرسمي الذي استُند إليه.",
      },
      bilingual: {
        title: "عربي وإنجليزي",
        body: "اكتب سؤالك بالعربية أو الإنجليزية، ويجيبك المساعد باللغة نفسها.",
      },
      honest: {
        title: "صريح عند عدم التأكد",
        body: "إذا لم يجد مصدرًا واضحًا يقول ذلك، ويرشدك إلى المكتب المختص بدلًا من التخمين.",
      },
      ccis: {
        title: "مخصص لطلاب الكلية",
        body: "يغطي لوائح كلية علوم الحاسب والمعلومات والخطط الدراسية والتقويم الأكاديمي لطلبة البكالوريوس.",
      },
    },
  },
  how: {
    title: "كيف يعمل؟",
    subtitle: "من سؤالك إلى إجابة يمكنك التحقق منها.",
    steps: {
      ask: {
        title: "اكتب سؤالك",
        body: "اسأل عن أي شيء يخص اللوائح أو الخطة الدراسية أو التقويم الأكاديمي.",
      },
      search: {
        title: "نبحث في المصادر الرسمية",
        body: "يبحث المساعد داخل المستندات الرسمية للجامعة للعثور على المادة المتعلقة بسؤالك.",
      },
      answer: {
        title: "تحصل على إجابة مع المصدر",
        body: "تأتيك الإجابة مع اسم المستند ورقم المادة ورابطها الرسمي للتحقق.",
      },
    },
  },
  note: "الإجابات مبنية على المستندات الرسمية لجامعة الملك سعود. للقرارات الرسمية، تأكد دائمًا من عمادة القبول والتسجيل.",
  footer: {
    project: "KSU Agent · مشروع مقرر SWE 444 · جامعة الملك سعود",
    disclaimer: "مشروع طلابي، وليس خدمة رسمية من جامعة الملك سعود.",
    copyright: "© 2026",
  },
};

const en: Dictionary = {
  meta: {
    description:
      "An AI assistant for CCIS students at King Saud University that answers questions about regulations, study plans and the academic calendar, citing the official source every time.",
  },
  skipToContent: "Skip to content",
  brand: "KSU Agent",
  nav: {
    label: "Main navigation",
    chat: "Chat",
    login: "Log in",
    register: "Create account",
    openMenu: "Open menu",
    closeMenu: "Close menu",
  },
  language: {
    label: "Switch to Arabic",
    short: "عربي",
  },
  hero: {
    eyebrow: "An academic assistant for CCIS students",
    title: "Ask about KSU regulations. Get answers you can trust.",
    subtitle:
      "An AI assistant for CCIS students that answers in Arabic or English and cites the official article and link with every answer.",
    primary: "Start chatting",
    secondary: "Create account",
    mock: {
      label: "Example",
      question: "When is a student barred from the final exam?",
      answer:
        "The assistant explains the rule exactly as the regulation states it, with the article number and a link to the official document.",
      citation: "Study and Examination Regulations · v2",
    },
  },
  features: {
    title: "Why KSU Agent?",
    subtitle: "Every answer is grounded in an official document, not a guess.",
    items: {
      cited: {
        title: "Cited answers",
        body: "Every answer shows the article and a link to the official document it came from.",
      },
      bilingual: {
        title: "Arabic & English",
        body: "Ask in either language and get the answer in the language you used.",
      },
      honest: {
        title: "Honest when unsure",
        body: "When no clear source is found, it says so and points you to the right office instead of guessing.",
      },
      ccis: {
        title: "Built for CCIS",
        body: "Covers CCIS regulations, study plans and the academic calendar for undergraduate students.",
      },
    },
  },
  how: {
    title: "How it works",
    subtitle: "From your question to an answer you can check.",
    steps: {
      ask: {
        title: "Ask your question",
        body: "Ask anything about regulations, your study plan or the academic calendar.",
      },
      search: {
        title: "We search the official KSU documents",
        body: "The assistant looks through official university documents for the article that answers your question.",
      },
      answer: {
        title: "Get an answer with its source",
        body: "The answer arrives with the document name, article number and official link so you can verify it.",
      },
    },
  },
 
  note: "Answers are based on official King Saud University documents. For official decisions, always confirm with the Deanship of Admission and Registration.",
  footer: {
    project: "KSU Agent · King Saud University",
    disclaimer: "Student project — not an official KSU service.",
    copyright: "© 2026",
  },
};

export const dictionary: Record<Lang, Dictionary> = { ar, en };

