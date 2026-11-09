"use client";

import Link from "next/link";
import { useLanguage } from "@/components/LanguageProvider";
import { LinkIcon } from "@/components/icons";

function ChatMock() {
  const { t } = useLanguage();

  return (
    <div className="relative mx-auto w-full max-w-md lg:max-w-none">
      <div
        aria-hidden="true"
        className="absolute -inset-4 rounded-[2rem] bg-teal/10 blur-2xl"
      />
      <div className="relative rounded-2xl bg-white p-4 shadow-[0_30px_70px_-30px_rgba(2,10,20,0.85)] ring-1 ring-white/15 sm:p-5">
        <div className="mb-4 flex items-center justify-between gap-3">
          <span className="rounded-full bg-surface px-2.5 py-1 text-xs font-medium text-muted">
            {t.hero.mock.label}
          </span>
          <span aria-hidden="true" className="flex items-center gap-1.5">
            <span className="h-1.5 w-1.5 rounded-full bg-slate-200" />
            <span className="h-1.5 w-1.5 rounded-full bg-slate-200" />
            <span className="h-1.5 w-1.5 rounded-full bg-slate-200" />
          </span>
        </div>

        <div className="space-y-3">
          <p className="ms-auto max-w-[85%] rounded-2xl rounded-ee-md bg-navy px-4 py-3 text-[13px] leading-relaxed text-white sm:text-sm">
            {t.hero.mock.question}
          </p>

          <div className="me-auto max-w-[94%] rounded-2xl rounded-es-md bg-surface px-4 py-3 text-[13px] leading-relaxed text-ink ring-1 ring-slate-200/70 sm:text-sm">
            <p>{t.hero.mock.answer}</p>
            <span className="mt-3 inline-flex items-center gap-1.5 rounded-lg bg-white px-2.5 py-1.5 text-xs font-medium text-teal-deep ring-1 ring-teal/25">
              <LinkIcon className="h-3.5 w-3.5 shrink-0" />
              <span>{t.hero.mock.citation}</span>
            </span>
          </div>
        </div>
      </div>
    </div>
  );
}

export function Hero() {
  const { t } = useLanguage();

  return (
    <section className="relative overflow-hidden bg-navy text-white">
      <div
        aria-hidden="true"
        className="pointer-events-none absolute inset-0 opacity-60"
        style={{
          backgroundImage:
            "linear-gradient(to right, rgba(255,255,255,0.06) 1px, transparent 1px), linear-gradient(to bottom, rgba(255,255,255,0.06) 1px, transparent 1px)",
          backgroundSize: "72px 72px",
          maskImage:
            "radial-gradient(ellipse at center, black, transparent 78%)",
        }}
      />
      <div
        aria-hidden="true"
        className="pointer-events-none absolute -top-32 end-[-8rem] h-80 w-80 rounded-full bg-teal/20 blur-3xl"
      />
      <div
        aria-hidden="true"
        className="pointer-events-none absolute bottom-[-10rem] start-[-6rem] h-80 w-80 rounded-full bg-gold/10 blur-3xl"
      />

      <div className="relative mx-auto grid w-full max-w-[1200px] gap-12 px-5 py-14 sm:px-8 sm:py-20 lg:grid-cols-[1.05fr_0.95fr] lg:items-center lg:gap-16 lg:py-28">
        <div className="max-w-xl">
          <p className="inline-flex items-center gap-2 rounded-full border border-white/15 bg-white/5 px-3 py-1 text-xs font-medium text-white/80">
            <span aria-hidden="true" className="h-1.5 w-1.5 rounded-full bg-gold" />
            {t.hero.eyebrow}
          </p>

          <h1 className="mt-6 text-[1.75rem] font-bold leading-[1.4] sm:text-4xl sm:leading-[1.35] lg:text-5xl">
            {t.hero.title}
          </h1>

          <p className="mt-5 max-w-lg text-base leading-relaxed text-white/75 sm:text-lg">
            {t.hero.subtitle}
          </p>

          <div className="mt-8 flex flex-col gap-3 sm:flex-row sm:items-center">
            <Link
              href="/chat"
              prefetch={false}
              className="inline-flex w-full items-center justify-center rounded-xl bg-teal-deep px-6 py-3.5 text-sm font-semibold text-white transition-colors hover:bg-teal-dark sm:w-auto"
            >
              {t.hero.primary}
            </Link>
            <Link
              href="/register"
              className="inline-flex w-full items-center justify-center rounded-xl border border-white/25 px-6 py-3.5 text-sm font-semibold text-white transition-colors hover:border-white/40 hover:bg-white/10 sm:w-auto"
            >
              {t.hero.secondary}
            </Link>
          </div>
        </div>

        <ChatMock />
      </div>
    </section>
  );
}
