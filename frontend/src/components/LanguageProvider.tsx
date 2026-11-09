"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { dictionary, type Dictionary, type Lang } from "@/lib/i18n";

const STORAGE_KEY = "ksu-agent-lang";

type LanguageContextValue = {
  lang: Lang;
  setLang: (lang: Lang) => void;
  t: Dictionary;
};

const LanguageContext = createContext<LanguageContextValue | null>(null);

function isLang(value: string | null): value is Lang {
  return value === "ar" || value === "en";
}

export function LanguageProvider({ children }: { children: ReactNode }) {
  const [lang, setLangState] = useState<Lang>("ar");

  useEffect(() => {
    let stored: string | null = null;

    try {
      stored = window.localStorage.getItem(STORAGE_KEY);
    } catch {
      stored = null;
    }

    if (isLang(stored)) {
      setLangState(stored);
    }
  }, []);

  useEffect(() => {
    document.documentElement.lang = lang;
    document.documentElement.dir = lang === "ar" ? "rtl" : "ltr";
  }, [lang]);

  const setLang = useCallback((next: Lang) => {
    setLangState(next);

    try {
      window.localStorage.setItem(STORAGE_KEY, next);
    } catch {
      // Storage unavailable (private mode, blocked cookies): the session choice still applies.
    }
  }, []);

  const value = useMemo<LanguageContextValue>(
    () => ({ lang, setLang, t: dictionary[lang] }),
    [lang, setLang],
  );

  return (
    <LanguageContext.Provider value={value}>{children}</LanguageContext.Provider>
  );
}

export function useLanguage(): LanguageContextValue {
  const context = useContext(LanguageContext);

  if (!context) {
    throw new Error("useLanguage must be used inside a LanguageProvider");
  }

  return context;
}
