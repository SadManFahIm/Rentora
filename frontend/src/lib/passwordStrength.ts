// ============================================================
// PASSWORD STRENGTH — zxcvbn-ts based analysis used by the
// register form's live meter, plus a HaveIBeenPwned k-anonymity
// breach check. Pure-ish: only the breach check touches the
// network and it degrades to "unknown" instead of lying.
// ============================================================

import { ZxcvbnFactory } from "@zxcvbn-ts/core";
import * as zxcvbnCommonPackage from "@zxcvbn-ts/language-common";
import * as zxcvbnEnPackage from "@zxcvbn-ts/language-en";

const zxcvbn = new ZxcvbnFactory({
  translations: zxcvbnEnPackage.translations,
  graphs: zxcvbnCommonPackage.adjacencyGraphs,
  dictionary: {
    ...zxcvbnCommonPackage.dictionary,
    ...zxcvbnEnPackage.dictionary,
  },
});

export type PasswordScore = 0 | 1 | 2 | 3 | 4;

export const PASSWORD_MIN_LENGTH = 6;

export interface PasswordAnalysis {
  /** zxcvbn score 0–4 (0 = very guessable, 4 = very unguessable). */
  score: PasswordScore;
  label: string;
  /** log10 of estimated guesses — the real "entropy" number. */
  entropy: number;
  /** zxcvbn feedback (warning + suggestions) for the current input. */
  warnings: string[];
  /** True when the password is trivially guessable / a known common one. */
  isCommon: boolean;
}

export function passwordStrengthLabel(score: PasswordScore): string {
  switch (score) {
    case 0:
      return "Very weak";
    case 1:
      return "Weak";
    case 2:
      return "Fair";
    case 3:
      return "Good";
    default:
      return "Strong";
  }
}

/** Segment color for the meter bar (index 0..3 of the bar). */
export function passwordStrengthColor(score: PasswordScore): string {
  if (score <= 1) return "bg-red-500";
  if (score === 2) return "bg-amber-500";
  if (score === 3) return "bg-yellow-500";
  return "bg-emerald-500";
}

/** Percent width of the meter bar for a given score. */
export function passwordStrengthPercent(score: PasswordScore): number {
  return (score / 4) * 100;
}

/**
 * Analyze a password with zxcvbn-ts: real pattern-aware entropy scoring
 * (dictionary matches, sequences, repeats, keyboard patterns…) instead of
 * naive character-class counting.
 */
export function analyzePassword(password: string): PasswordAnalysis {
  if (!password) {
    return { score: 0, label: "", entropy: 0, warnings: [], isCommon: false };
  }
  const result = zxcvbn.check(password);
  const score = Math.min(Math.max(result.score, 0), 4) as PasswordScore;
  const warnings: string[] = [];
  if (result.feedback?.warning) warnings.push(result.feedback.warning);
  if (result.feedback?.suggestions) warnings.push(...result.feedback.suggestions);
  // Below ~10^8 guesses a GPU can brute-force it in minutes — treat as common.
  const isCommon = score <= 1 || result.guessesLog10 < 8;
  return {
    score,
    label: passwordStrengthLabel(score),
    entropy: Math.round(result.guessesLog10 * 10) / 10,
    warnings,
    isCommon,
  };
}

/** Backwards-compatible quick score (zxcvbn score, 0–4). */
export function scorePassword(password: string): PasswordScore {
  return analyzePassword(password).score;
}

// ---- HaveIBeenPwned k-anonymity breach check ----
// Only the first five characters of the SHA-1 hash ever leave this device;
// the suffix is matched locally against the returned range list.

async function sha1Hex(text: string): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-1", new TextEncoder().encode(text));
  return [...new Uint8Array(digest)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

/**
 * Check whether a password appears in known data breaches.
 *
 * Returns:
 *   true    — found in the breach corpus
 *   false   — not found (as far as the corpus knows)
 *   null    — could not verify (offline / API error); never claim "safe"
 *             in this case.
 */
export async function checkPasswordBreached(password: string): Promise<boolean | null> {
  try {
    const hash = await sha1Hex(password);
    const prefix = hash.slice(0, 5);
    const suffix = hash.slice(5).toUpperCase();
    const res = await fetch(`https://api.pwnedpasswords.com/range/${prefix}`, {
      headers: { "Add-Padding": "true" },
    });
    if (!res.ok) return null;
    const text = await res.text();
    return text.split(/\r?\n/).some((line) => line.split(":")[0].trim().toUpperCase() === suffix);
  } catch {
    return null;
  }
}
