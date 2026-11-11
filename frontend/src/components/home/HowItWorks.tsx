"use client";

import { useLanguage } from "@/components/LanguageProvider";

const steps = ["ask", "search", "answer"] as const;

export function HowItWorks() {
  const { t } = useLanguage();

  return (
    <section className="border-y border-slate-200/70 bg-surface">
      <div className="mx-auto w-full max-w-[1200px] px-5 py-16 sm:px-8 sm:py-20 lg:py-24">
        <div className="mx-auto max-w-2xl text-center">
          <h2 className="text-2xl font-bold text-navy sm:text-3xl sm:leading-[1.35]">
            {t.how.title}
          </h2>
          <p className="mt-3 text-base leading-relaxed text-muted">
            {t.how.subtitle}
          </p>
        </div>

        <div className="relative mt-12">
          <div
            aria-hidden="true"
            className="absolute inset-x-[16.667%] top-6 hidden border-t border-dashed border-slate-300 md:block"
          />

          <ol className="grid gap-8 md:grid-cols-3 md:gap-0">
            {steps.map((key, index) => {
              const step = t.how.steps[key];

              return (
                <li
                  key={key}
                  className="relative flex gap-4 md:flex-col md:items-center md:gap-5 md:px-6 md:text-center"
                >
                  <span
                    aria-hidden="true"
                    className="relative z-10 flex h-12 w-12 shrink-0 items-center justify-center rounded-full bg-navy text-sm font-bold text-white ring-4 ring-surface"
                  >
                    {index + 1}
                  </span>
                  <div>
                    <h3 className="text-base font-semibold text-navy">
                      {step.title}
                    </h3>
                    <p className="mt-2 text-sm leading-relaxed text-muted">
                      {step.body}
                    </p>
                  </div>
                </li>
              );
            })}
          </ol>
        </div>
      </div>
    </section>
  );
}
