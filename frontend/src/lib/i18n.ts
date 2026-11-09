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
  auth: {
    greeting: string;
    logout: string;
    pending: string;
    fields: {
      name: string;
      email: string;
      emailHint: string;
      password: string;
      confirm: string;
      agree: string;
      showPassword: string;
      hidePassword: string;
    };
    errors: {
      nameRequired: string;
      nameLength: string;
      emailRequired: string;
      emailDomain: string;
      passwordRequired: string;
      passwordLength: string;
      passwordWeak: string;
      confirmRequired: string;
      confirmMismatch: string;
      agreeRequired: string;
    };
    server: {
      emailTaken: string;
      invalidCredentials: string;
      serverUnavailable: string;
      validation: string;
    };
    login: {
      metaTitle: string;
      title: string;
      subtitle: string;
      submit: string;
      switchText: string;
      switchLink: string;
    };
    register: {
      metaTitle: string;
      title: string;
      subtitle: string;
      submit: string;
      switchText: string;
      switchLink: string;
    };
  };
  chat: {
    metaTitle: string;
    title: string;
    newChat: string;
    you: string;
    assistant: string;
    placeholder: string;
    send: string;
    stop: string;
    retry: string;
    copy: string;
    copied: string;
    sources: string;
    opensInNewTab: string;
    noSource: string;
    searching: string;
    disclaimer: string;
    newMessages: string;
    errors: {
      unavailable: string;
      invalid: string;
    };
    empty: {
      greeting: string;
      note: string;
      suggestions: [string, string, string, string];
    };
  };
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
  auth: {
    greeting: "مرحبًا،",
    logout: "تسجيل الخروج",
    pending: "جارٍ…",
    fields: {
      name: "الاسم الكامل",
      email: "البريد الجامعي",
      emailHint: "استخدم بريدك الجامعي",
      password: "كلمة المرور",
      confirm: "تأكيد كلمة المرور",
      agree: "أوافق على استخدام بياناتي لتشغيل الخدمة فقط",
      showPassword: "إظهار كلمة المرور",
      hidePassword: "إخفاء كلمة المرور",
    },
    errors: {
      nameRequired: "أدخل اسمك الكامل",
      nameLength: "يجب أن يكون الاسم بين حرفين و60 حرفًا",
      emailRequired: "أدخل بريدك الجامعي",
      emailDomain: "يجب أن ينتهي البريد بـ @student.ksu.edu.sa",
      passwordRequired: "أدخل كلمة المرور",
      passwordLength: "كلمة المرور يجب ألا تقل عن 8 أحرف",
      passwordWeak: "أضف حرفًا ورقمًا على الأقل إلى كلمة المرور",
      confirmRequired: "أعد إدخال كلمة المرور",
      confirmMismatch: "كلمتا المرور غير متطابقتين",
      agreeRequired: "يجب الموافقة على استخدام البيانات",
    },
    server: {
      emailTaken: "هذا البريد مسجل مسبقًا",
      invalidCredentials: "البريد أو كلمة المرور غير صحيحة",
      serverUnavailable: "تعذر الاتصال بالخادم، حاول لاحقًا",
      validation: "تحقق من الحقول أدناه",
    },
    login: {
      metaTitle: "تسجيل الدخول · KSU Agent",
      title: "تسجيل الدخول",
      subtitle: "أدخل بريدك الجامعي وكلمة المرور للمتابعة.",
      submit: "تسجيل الدخول",
      switchText: "ليس لديك حساب؟",
      switchLink: "إنشاء حساب",
    },
    register: {
      metaTitle: "إنشاء حساب · KSU Agent",
      title: "إنشاء حساب",
      subtitle: "أنشئ حسابك لتبدأ استخدام المساعد.",
      submit: "إنشاء حساب",
      switchText: "لديك حساب؟",
      switchLink: "تسجيل الدخول",
    },
  },
  chat: {
    metaTitle: "المحادثة · KSU Agent",
    title: "المحادثة",
    newChat: "محادثة جديدة",
    you: "أنت",
    assistant: "المساعد",
    placeholder: "اكتب سؤالك…",
    send: "إرسال",
    stop: "إيقاف",
    retry: "إعادة المحاولة",
    copy: "نسخ الإجابة",
    copied: "تم النسخ",
    sources: "المصادر",
    opensInNewTab: "يفتح في تبويب جديد",
    noSource:
      "لم يُعثر على مصدر رسمي لهذه الإجابة. للتأكد، راجع عمادة القبول والتسجيل.",
    searching: "جارٍ البحث في المصادر…",
    disclaimer: "قد يخطئ المساعد. تحقق دائمًا من المصدر.",
    newMessages: "رسائل جديدة",
    errors: {
      unavailable: "تعذر الاتصال بالخادم، حاول مرة أخرى.",
      invalid: "تعذر معالجة هذه الرسالة. جرّب صياغتها بشكل مختلف.",
    },
    empty: {
      greeting: "مرحبًا {name}، كيف أقدر أساعدك؟",
      note: "الإجابات مبنية على لائحة الدراسة والاختبارات الرسمية لجامعة الملك سعود.",
      suggestions: [
        "متى يُحرم الطالب من دخول الاختبار النهائي؟",
        "ما هو الإنذار الأكاديمي ومتى يُفصل الطالب؟",
        "كيف أعتذر عن مقرر أو عن فصل دراسي؟",
        "كيف يُحسب المعدل التراكمي؟",
      ],
    },
  },
  footer: {
    project: "KSU Agent · جامعة الملك سعود",
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
  auth: {
    greeting: "Hi,",
    logout: "Log out",
    pending: "Please wait…",
    fields: {
      name: "Full name",
      email: "University email",
      emailHint: "Use your university email",
      password: "Password",
      confirm: "Confirm password",
      agree: "I agree that my data is used only to run the service",
      showPassword: "Show password",
      hidePassword: "Hide password",
    },
    errors: {
      nameRequired: "Enter your full name",
      nameLength: "Name must be between 2 and 60 characters",
      emailRequired: "Enter your university email",
      emailDomain: "Email must end with @student.ksu.edu.sa",
      passwordRequired: "Enter your password",
      passwordLength: "Password must be at least 8 characters",
      passwordWeak: "Add at least one letter and one number",
      confirmRequired: "Re-enter your password",
      confirmMismatch: "Passwords do not match",
      agreeRequired: "You must agree to the data use",
    },
    server: {
      emailTaken: "This email is already registered",
      invalidCredentials: "Email or password is incorrect",
      serverUnavailable: "Could not reach the server, try again later",
      validation: "Check the fields below",
    },
    login: {
      metaTitle: "Log in · KSU Agent",
      title: "Log in",
      subtitle: "Enter your university email and password to continue.",
      submit: "Log in",
      switchText: "Don't have an account?",
      switchLink: "Create account",
    },
    register: {
      metaTitle: "Create account · KSU Agent",
      title: "Create account",
      subtitle: "Create your account to start using the assistant.",
      submit: "Create account",
      switchText: "Already have an account?",
      switchLink: "Log in",
    },
  },
  chat: {
    metaTitle: "Chat · KSU Agent",
    title: "Chat",
    newChat: "New chat",
    you: "You",
    assistant: "Assistant",
    placeholder: "Type your question…",
    send: "Send",
    stop: "Stop",
    retry: "Retry",
    copy: "Copy answer",
    copied: "Copied",
    sources: "Sources",
    opensInNewTab: "opens in a new tab",
    noSource:
      "No official source was found for this answer. Please confirm with the Deanship of Admission and Registration.",
    searching: "Searching the official sources…",
    disclaimer: "The assistant can make mistakes. Always check the source.",
    newMessages: "New messages",
    errors: {
      unavailable: "Could not reach the server, please try again.",
      invalid: "This message could not be processed. Try rewording it.",
    },
    empty: {
      greeting: "Hi {name}, how can I help?",
      note: "Answers come from the official KSU Study and Examination Regulations.",
      suggestions: [
        "When is a student barred from the final exam?",
        "What is an academic warning, and when is a student dismissed?",
        "How do I withdraw from a course or a semester?",
        "How is the cumulative GPA calculated?",
      ],
    },
  },
  footer: {
    project: "KSU Agent · King Saud University",
    disclaimer: "Student project — not an official KSU service.",
    copyright: "© 2026",
  },
};

export const dictionary: Record<Lang, Dictionary> = { ar, en };

