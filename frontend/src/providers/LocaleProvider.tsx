import { createContext, useContext, useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";
import { copy, CopyKey, Locale } from "../copy";

type LocaleContextValue = { locale: Locale; setLocale: (locale: Locale) => void; toggleLocale: () => void; t: (key: CopyKey) => string };
const LocaleContext = createContext<LocaleContextValue | null>(null);
const initialLocale = (): Locale => localStorage.getItem("dashanbing-locale") === "en" ? "en" : "zh";

export function LocaleProvider({ children }: { children: ReactNode }) {
  const [locale, setLocale] = useState<Locale>(initialLocale);
  useEffect(() => {
    localStorage.setItem("dashanbing-locale", locale);
    document.documentElement.lang = locale === "zh" ? "zh-CN" : "en";
    document.title = copy[locale].metaTitle;
    let description = document.querySelector<HTMLMetaElement>('meta[name="description"]');
    if (!description) {
      description = document.createElement("meta");
      description.name = "description";
      document.head.append(description);
    }
    description.content = copy[locale].metaDescription;
  }, [locale]);
  const value = useMemo<LocaleContextValue>(() => ({
    locale, setLocale, toggleLocale: () => setLocale((current) => current === "zh" ? "en" : "zh"), t: (key) => copy[locale][key],
  }), [locale]);
  return <LocaleContext.Provider value={value}>{children}</LocaleContext.Provider>;
}

export function useLocale() {
  const value = useContext(LocaleContext);
  if (!value) throw new Error("useLocale must be used inside LocaleProvider");
  return value;
}
