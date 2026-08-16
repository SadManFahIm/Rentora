import { Languages } from "lucide-react";
import { useTranslation } from "react-i18next";
import { cn } from "../../lib/utils";
import { setStoredLanguage, type LanguageCode } from "../../i18n";

/**
 * EN ⇄ বাংলা UI toggle (Tier 3). Persists to localStorage via the i18n
 * module, so the choice survives reloads and is applied before first render
 * (no flash of the wrong language). Small enough for the navbar, with an
 * aria-pressed state for accessibility.
 */
export default function LanguageToggle({ className }: { className?: string }) {
  const { i18n } = useTranslation();
  const current = (i18n.language ?? "en").startsWith("bn") ? "bn" : "en";

  const toggle = () => {
    const next: LanguageCode = current === "en" ? "bn" : "en";
    void i18n.changeLanguage(next);
    setStoredLanguage(next);
  };

  return (
    <button
      type="button"
      onClick={toggle}
      aria-pressed={current === "bn"}
      aria-label={current === "en" ? "Switch to Bangla" : "Switch to English"}
      title={current === "en" ? "বাংলা" : "English"}
      className={cn(
        "flex items-center gap-1 rounded-full border border-gray-300 px-2.5 py-1.5 text-xs font-semibold transition-colors",
        "text-gray-700 hover:border-orange-500 hover:text-orange-600",
        "dark:border-gray-700 dark:text-gray-300 dark:hover:border-orange-400 dark:hover:text-orange-400",
        className
      )}
    >
      <Languages className="size-3.5" aria-hidden />
      {current === "en" ? "বাংলা" : "EN"}
    </button>
  );
}
