import { describe, expect, it, beforeEach, afterEach } from "vitest";
import { act, render, screen } from "@testing-library/react";
import { useTranslation } from "react-i18next";
import i18n, { getStoredLanguage, setStoredLanguage, SUPPORTED_LANGUAGES } from "./index";
import LanguageToggle from "../components/LanguageToggle/LanguageToggle";

function Probe({ label }: { label: string }) {
  const { t } = useTranslation();
  return <div>{t(label)}</div>;
}

describe("i18n (Tier 3 EN/BN)", () => {
  afterEach(() => {
    localStorage.clear();
  });

  it("loads both dictionaries synchronously", () => {
    expect(SUPPORTED_LANGUAGES.map((l) => l.code)).toEqual(["en", "bn"]);
    expect(i18n.hasResourceBundle("en", "translation")).toBe(true);
    expect(i18n.hasResourceBundle("bn", "translation")).toBe(true);
  });

  it("translates a nav key in Bangla after switching", () => {
    act(() => {
      void i18n.changeLanguage("bn");
    });
    render(<Probe label="nav.home" />);
    expect(screen.getByText("হোম")).toBeInTheDocument();

    act(() => {
      void i18n.changeLanguage("en");
    });
  });

  it("persists and restores the language choice", () => {
    setStoredLanguage("bn");
    expect(getStoredLanguage()).toBe("bn");
    expect(document.documentElement.lang).toBe("bn");
    localStorage.clear();
    expect(getStoredLanguage()).toBe("en");
  });

  it("falls back to English for untranslated keys", () => {
    act(() => {
      void i18n.changeLanguage("bn");
    });
    // A key that exists in en but is deliberately not in bn -> English value.
    render(<Probe label="home.searchPlaceholder" />);
    expect(screen.getByText(/Try: ১০ হাজার/)).toBeInTheDocument();
    act(() => {
      void i18n.changeLanguage("en");
    });
  });
});

describe("LanguageToggle", () => {
  const originalLang = "en";

  beforeEach(() => {
    localStorage.clear();
  });

  afterEach(() => {
    localStorage.clear();
    void i18n.changeLanguage(originalLang);
  });

  it("switches to Bangla on click and persists", async () => {
    render(<LanguageToggle />);
    const button = screen.getByRole("button", { name: "Switch to Bangla" });
    expect(button).toHaveAttribute("aria-pressed", "false");

    await act(async () => {
      button.click();
    });
    expect(button).toHaveAttribute("aria-pressed", "true");
    expect(getStoredLanguage()).toBe("bn");
  });
});
