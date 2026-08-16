/**
 * Rentora i18n (Tier 3) — full English ⇄ Bangla UI toggle.
 *
 * Loaded once in `main.tsx` (and in `src/test/setup.ts` for tests) with
 * `initImmediate: false` so the dictionaries are available synchronously —
 * the very first render is already in the right language, no flash of
 * untranslated keys.
 *
 * Language is persisted in localStorage and mirrored on
 * `document.documentElement.lang` for accessibility. Every translation key
 * has an English value, so an untranslated key degrades to English instead
 * of a raw key string (graceful fallback, never broken UI).
 */
import i18n from "i18next";
import { initReactI18next } from "react-i18next";

import en from "./en.json";
import bn from "./bn.json";

export const SUPPORTED_LANGUAGES = [
  { code: "en", label: "English" },
  { code: "bn", label: "বাংলা" },
] as const;

export type LanguageCode = (typeof SUPPORTED_LANGUAGES)[number]["code"];

const STORAGE_KEY = "rentora_language";

export function getStoredLanguage(): LanguageCode {
  try {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (stored === "en" || stored === "bn") return stored;
  } catch {
    /* localStorage unavailable (private mode) — default to English */
  }
  return "en";
}

export function setStoredLanguage(lang: LanguageCode) {
  try {
    localStorage.setItem(STORAGE_KEY, lang);
  } catch {
    /* best-effort persistence */
  }
  document.documentElement.lang = lang;
}

i18n.use(initReactI18next).init({
  resources: {
    en: { translation: en },
    bn: { translation: bn },
  },
  lng: getStoredLanguage(),
  fallbackLng: "en",
  interpolation: { escapeValue: false },
  returnEmptyString: false,
});

document.documentElement.lang = i18n.language;

export default i18n;
