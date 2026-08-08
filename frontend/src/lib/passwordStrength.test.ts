import { describe, expect, it } from "vitest";
import {
  scorePassword,
  passwordStrengthLabel,
  passwordStrengthColor,
  passwordStrengthPercent,
} from "./passwordStrength";

describe("scorePassword", () => {
  it("scores empty input as 0", () => {
    expect(scorePassword("")).toBe(0);
  });

  it("scores a short password low", () => {
    expect(scorePassword("abc123")).toBe(1); // only digit, len < 8
  });

  it("rewards length", () => {
    // len 8+ => +1; digit => +1 => 2
    expect(scorePassword("abcdefg1")).toBe(2);
    // len 12+ => +2; digit => +1; mixed case => +1 => 4
    expect(scorePassword("abcdefghijk1A")).toBe(4);
  });

  it("rewards mixed case", () => {
    expect(scorePassword("abcdefgH1")).toBe(3); // len 8+ + mixed + digit
  });

  it("rewards special characters", () => {
    expect(scorePassword("Abcdefg1!")).toBe(4); // all five checks
  });

  it("caps at 4", () => {
    expect(scorePassword("Abcdefghijklm1!@#")).toBe(4);
  });

  it("is monotonic — longer never scores lower", () => {
    const short = scorePassword("abc");
    const longer = scorePassword("abcxyz1234");
    expect(longer).toBeGreaterThanOrEqual(short);
  });
});

describe("passwordStrengthLabel", () => {
  it("maps each score to a label", () => {
    expect(passwordStrengthLabel(0)).toBe("");
    expect(passwordStrengthLabel(1)).toBe("Weak");
    expect(passwordStrengthLabel(2)).toBe("Fair");
    expect(passwordStrengthLabel(3)).toBe("Good");
    expect(passwordStrengthLabel(4)).toBe("Strong");
  });
});

describe("passwordStrengthColor / Percent", () => {
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
