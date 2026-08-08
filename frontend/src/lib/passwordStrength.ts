// ============================================================
// PASSWORD STRENGTH — pure scoring used by the register form's
// live strength meter. Kept framework-free so it is trivially
// unit-testable.
// ============================================================

export type PasswordScore = 0 | 1 | 2 | 3 | 4;

export const PASSWORD_MIN_LENGTH = 6;

/**
 * Score a password 0–4. Checks grow monotonically, so a longer password
 * always scores at least as high as its shorter prefix:
 *   +1  length >= 8
 *   +1  length >= 12
 *   +1  mixed case (upper AND lower)
 *   +1  contains a digit
 *   +1  contains a non-alphanumeric character
 */
export function scorePassword(password: string): PasswordScore {
  if (!password) return 0;
  let score = 0;
  if (password.length >= 8) score += 1;
  if (password.length >= 12) score += 1;
  if (/[a-z]/.test(password) && /[A-Z]/.test(password)) score += 1;
  if (/\d/.test(password)) score += 1;
  if (/[^A-Za-z0-9]/.test(password)) score += 1;
  return Math.min(score, 4) as PasswordScore;
}

export function passwordStrengthLabel(score: PasswordScore): string {
  switch (score) {
    case 1:
      return "Weak";
    case 2:
      return "Fair";
    case 3:
      return "Good";
    case 4:
      return "Strong";
    default:
      return "";
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
