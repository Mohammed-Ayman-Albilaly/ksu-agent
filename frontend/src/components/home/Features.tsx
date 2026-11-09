"use client";

import { useLanguage } from "@/components/LanguageProvider";
import { CapIcon, CitedIcon, HonestIcon, LanguagesIcon } from "@/components/icons";

const features = [
  { key: "cited", Icon: CitedIcon },
  { key: "bilingual", Icon: LanguagesIcon },
  { key: "honest", Icon: HonestIcon },
  { key: "ccis", Icon: CapIcon },
] as const;

export function Features() {
  const { t } = useLanguage();

  return (
    <section className="bg-white">
      <div className="mx-auto w-full max-w-[1200px] px-5 py-16 sm:px-8 sm:py-20 lg:py-24">
        <div className="max-w-2xl">
          <h2 className="text-2xl font-bold text-navy sm:text-3xl sm:leading-[1.35]">
            {t.features.title}
          </h2>
          <p className="mt-3 text-base leading-relaxed text-muted">
            {t.features.subtitle}
          </p>
        </div>

        <ul className="mt-10 grid gap-4 sm:grid-cols-2 sm:gap-5 lg:grid-cols-4">
          {features.map(({ key, Icon }) => {
            const item = t.features.items[key];

            return (
              <li
                key={key}
                className="rounded-2xl border border-slate-200/80 bg-white p-6 shadow-[0_1px_2px_rgba(14,42,71,0.04)]"
              >
                <span className="flex h-11 w-11 items-center justify-center rounded-full bg-teal/10 text-teal-deep ring-1 ring-teal/15">
                  <Icon className="h-5 w-5" />
                </span>
                <h3 className="mt-5 text-base font-semibold text-navy">
                  {item.title}
                </h3>
                <p className="mt-2 text-sm leading-relaxed text-muted">
                  {item.body}
                </p>
              </li>
            );
          })}
        </ul>
      </div>
    </section>
  );
}
