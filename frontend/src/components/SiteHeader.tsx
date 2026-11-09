"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { useLanguage } from "@/components/LanguageProvider";
import { BrandMark, CloseIcon, LanguagesIcon, MenuIcon } from "@/components/icons";

const desktopLinkClass =
  "rounded-lg px-3 py-2 text-sm font-medium text-ink/80 transition-colors hover:bg-surface hover:text-navy";

const mobileLinkClass =
  "rounded-lg px-3 py-2.5 text-sm font-medium text-ink/80 transition-colors hover:bg-surface hover:text-navy";

export function SiteHeader() {
  const { lang, setLang, t } = useLanguage();
  const [open, setOpen] = useState(false);
  const menuButtonRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (!open) {
      return;
    }

    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setOpen(false);
        menuButtonRef.current?.focus();
      }
    };

    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [open]);

  const toggleLanguage = () => setLang(lang === "ar" ? "en" : "ar");
  const closeMenu = () => setOpen(false);
  const toggleTextLang = lang === "ar" ? "en" : "ar";

  return (
    <header className="sticky top-0 z-50 border-b border-slate-200/80 bg-white/95 shadow-[0_1px_3px_rgba(14,42,71,0.06)] backdrop-blur">
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:fixed focus:start-4 focus:top-4 focus:z-[60] focus:rounded-lg focus:bg-navy focus:px-4 focus:py-2 focus:text-sm focus:font-medium focus:text-white"
      >
        {t.skipToContent}
      </a>

      <div className="mx-auto flex h-16 w-full max-w-[1200px] items-center justify-between gap-4 px-5 sm:px-8">
        <Link
          href="/"
          className="-ms-2 flex items-center gap-2.5 rounded-xl px-2 py-1.5"
          onClick={closeMenu}
        >
          <BrandMark className="h-8 w-8 shrink-0" />
          <span className="text-lg font-semibold tracking-tight text-navy">
            {t.brand}
          </span>
        </Link>

        <nav aria-label={t.nav.label} className="hidden items-center gap-1 md:flex">
          <Link href="/chat" prefetch={false} className={desktopLinkClass}>
            {t.nav.chat}
          </Link>
          <Link href="/login" prefetch={false} className={desktopLinkClass}>
            {t.nav.login}
          </Link>
          <Link
            href="/register"
            prefetch={false}
            className="ms-2 rounded-xl bg-teal-deep px-4 py-2.5 text-sm font-semibold text-white transition-colors hover:bg-teal-dark"
          >
            {t.nav.register}
          </Link>
          <button
            type="button"
            onClick={toggleLanguage}
            aria-label={t.language.label}
            className="ms-2 flex h-9 items-center gap-1.5 rounded-lg border border-slate-200 px-3 text-xs font-semibold text-navy transition-colors hover:border-teal/40 hover:bg-surface"
          >
            <LanguagesIcon className="h-4 w-4 text-teal-deep" />
            <span lang={toggleTextLang}>{t.language.short}</span>
          </button>
        </nav>

        <button
          ref={menuButtonRef}
          type="button"
          onClick={() => setOpen((value) => !value)}
          aria-label={open ? t.nav.closeMenu : t.nav.openMenu}
          aria-expanded={open}
          aria-controls="mobile-menu"
          className="flex h-10 w-10 items-center justify-center rounded-lg border border-slate-200 text-navy transition-colors hover:bg-surface md:hidden"
        >
          {open ? (
            <CloseIcon className="h-5 w-5" />
          ) : (
            <MenuIcon className="h-5 w-5" />
          )}
        </button>
      </div>

      {open ? (
        <div id="mobile-menu" className="border-t border-slate-200/80 bg-white md:hidden">
          <nav
            aria-label={t.nav.label}
            className="mx-auto flex w-full max-w-[1200px] flex-col gap-1 px-5 py-4 sm:px-8"
          >
            <Link
              href="/chat"
              prefetch={false}
              className={mobileLinkClass}
              onClick={closeMenu}
            >
              {t.nav.chat}
            </Link>
            <Link
              href="/login"
              prefetch={false}
              className={mobileLinkClass}
              onClick={closeMenu}
            >
              {t.nav.login}
            </Link>
            <Link
              href="/register"
              prefetch={false}
              onClick={closeMenu}
              className="mt-2 rounded-xl bg-teal-deep px-4 py-3 text-center text-sm font-semibold text-white transition-colors hover:bg-teal-dark"
            >
              {t.nav.register}
            </Link>
            <button
              type="button"
              onClick={toggleLanguage}
              aria-label={t.language.label}
              className="mt-2 flex items-center justify-center gap-2 rounded-xl border border-slate-200 px-4 py-3 text-sm font-semibold text-navy transition-colors hover:bg-surface"
            >
              <LanguagesIcon className="h-4 w-4 text-teal-deep" />
              <span lang={toggleTextLang}>{t.language.short}</span>
            </button>
          </nav>
        </div>
      ) : null}
    </header>
  );
}
