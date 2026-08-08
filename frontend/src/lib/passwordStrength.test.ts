import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  analyzePassword,
  checkPasswordBreached,
  passwordStrengthColor,
  passwordStrengthLabel,
  passwordStrengthPercent,
  scorePassword,
} from "./passwordStrength";

const sha1Hex = async (text: string) => {
  const digest = await crypto.subtle.digest("SHA-1", new TextEncoder().encode(text));
  return [...new Uint8Array(digest)].map((b) => b.toString(16).padStart(2, "0")).join("");
};

describe("analyzePassword (zxcvbn)", () => {
  it("scores empty input neutrally", () => {
    const a = analyzePassword("");
    expect(a.score).toBe(0);
    expect(a.label).toBe("");
    expect(a.entropy).toBe(0);
    expect(a.isCommon).toBe(false);
  });

  it("flags common passwords as weak and common", () => {
    const a = analyzePassword("password");
    expect(a.score).toBeLessThanOrEqual(1);
    expect(a.isCommon).toBe(true);
    expect(a.label).toBe("Very weak");
  });

  it("flags simple numeric sequences as very weak", () => {
    const a = analyzePassword("123456");
    expect(a.score).toBeLessThanOrEqual(1);
  });

  it("scores a long varied password highly with real entropy", () => {
    const a = analyzePassword("Xk9!qW2#vL7$zP5@mN3");
    expect(a.score).toBeGreaterThanOrEqual(3);
    expect(a.entropy).toBeGreaterThan(15); // ~10^15+ guesses (zxcvbn is conservative)
    expect(a.isCommon).toBe(false);
  });

  it("exposes zxcvbn feedback warnings", () => {
    const a = analyzePassword("qwerty123");
    expect(Array.isArray(a.warnings)).toBe(true);
    expect(a.warnings.length).toBeGreaterThan(0);
  });

  it("never downgrades a longer varied password", () => {
    const weak = analyzePassword("monkey").score;
    const strong = analyzePassword("monkey-biscuit!9Xz").score;
    expect(strong).toBeGreaterThanOrEqual(weak);
  });
});

describe("scorePassword (back-compat wrapper)", () => {
  it("returns the zxcvbn score in 0..4", () => {
    expect(scorePassword("")).toBe(0);
    expect([0, 1, 2, 3, 4]).toContain(scorePassword("Xk9!qW2#vL7$zP5@mN3"));
  });
});

describe("passwordStrengthLabel / Color / Percent", () => {
  it("maps each score to a label", () => {
    expect(passwordStrengthLabel(0)).toBe("Very weak");
    expect(passwordStrengthLabel(1)).toBe("Weak");
    expect(passwordStrengthLabel(2)).toBe("Fair");
    expect(passwordStrengthLabel(3)).toBe("Good");
    expect(passwordStrengthLabel(4)).toBe("Strong");
  });

  it("provides a tailwind class per score band", () => {
    expect(passwordStrengthColor(0)).toBe("bg-red-500");
    expect(passwordStrengthColor(1)).toBe("bg-red-500");
    expect(passwordStrengthColor(2)).toBe("bg-amber-500");
    expect(passwordStrengthColor(3)).toBe("bg-yellow-500");
    expect(passwordStrengthColor(4)).toBe("bg-emerald-500");
  });

  it("maps score to a 0–100 percentage", () => {
    expect(passwordStrengthPercent(0)).toBe(0);
    expect(passwordStrengthPercent(2)).toBe(50);
    expect(passwordStrengthPercent(4)).toBe(100);
  });
});

describe("checkPasswordBreached (HIBP k-anonymity)", () => {
  beforeEach(() => vi.stubGlobal("fetch", vi.fn()));
  afterEach(() => vi.unstubAllGlobals());

  it("returns true when the hash suffix is in the range response", async () => {
    const pw = "P@ssw0rd123!";
    const hash = await sha1Hex(pw);
    const prefix = hash.slice(0, 5);
    const suffix = hash.slice(5).toUpperCase();
    (globalThis.fetch as ReturnType<typeof vi.fn>).mockResolvedValue({
      ok: true,
      text: async () => `00000000:1\n${suffix}:42\nFFFFFF:3\n`,
    });
    await expect(checkPasswordBreached(pw)).resolves.toBe(true);
    // Only the 5-char prefix ever leaves the device.
    expect(globalThis.fetch).toHaveBeenCalledWith(
      `https://api.pwnedpasswords.com/range/${prefix}`,
      expect.any(Object)
    );
  });

  it("returns false when the suffix is absent", async () => {
    (globalThis.fetch as ReturnType<typeof vi.fn>).mockResolvedValue({
      ok: true,
      text: async () => "00000000:1\nFFFFFF:3\n",
    });
    await expect(checkPasswordBreached("random-unique-pw-9x")).resolves.toBe(false);
  });

  it("returns null on network errors", async () => {
    (globalThis.fetch as ReturnType<typeof vi.fn>).mockRejectedValue(new Error("offline"));
    await expect(checkPasswordBreached("any")).resolves.toBeNull();
  });

  it("returns null on a non-OK response (never claims safe)", async () => {
    (globalThis.fetch as ReturnType<typeof vi.fn>).mockResolvedValue({ ok: false, status: 429 });
    await expect(checkPasswordBreached("any")).resolves.toBeNull();
  });
});
