/**
 * TwoFactorCard — account security: enable/disable email-OTP 2FA
 * (two-step: password → emailed code → one-time recovery codes)
 * and manage WebAuthn passkeys.
 */

import { useState } from "react";
import { KeyRound, Loader2, ShieldCheck } from "lucide-react";
import { startRegistration } from "@simplewebauthn/browser";
import { useApp } from "../../context/AppContext";
import { authService } from "../../services/authService";
import { getApiErrorMessage } from "../../services/errors";
import { Button } from "../../components/ui/button";
import { Input } from "../../components/ui/input";
import { toast } from "sonner";
import type { PasskeyInfo } from "../../types";
import { cn } from "../../lib/utils";

export default function TwoFactorCard() {
  const { user, setUser } = useApp();
  const [step, setStep] = useState<"idle" | "password" | "email" | "codes">("idle");
  const [password, setPassword] = useState("");
  const [code, setCode] = useState("");
  const [challenge, setChallenge] = useState("");
  const [destination, setDestination] = useState("");
  const [recoveryCodes, setRecoveryCodes] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const [copied, setCopied] = useState(false);
  const [registeringPasskey, setRegisteringPasskey] = useState(false);

  const enabled = user?.otpEnabled === true;
  const passkeys = user?.passkeys ?? [];

  const beginEnable = async () => {
    setBusy(true);
    try {
      const result = await authService.toggle2fa(true, password);
      if (result.pendingEnable && result.challenge) {
        setChallenge(result.challenge);
        setDestination(result.destinationMasked ?? "your inbox");
        setStep("email");
      } else {
        setUser({ ...user!, otpEnabled: result.otpEnabled });
        setStep("idle");
        setPassword("");
      }
    } catch (error) {
      toast.error(getApiErrorMessage(error, "Could not enable 2FA. Check your current password."));
    } finally {
      setBusy(false);
    }
  };

  const confirmEnable = async () => {
    setBusy(true);
    try {
      const result = await authService.confirmEnable2fa(challenge, code.trim());
      setUser({ ...user!, otpEnabled: result.otpEnabled });
      setRecoveryCodes(result.recoveryCodes);
      setStep("codes");
      setCode("");
    } catch (error) {
      toast.error(getApiErrorMessage(error, "That code was not accepted. Try again."));
    } finally {
      setBusy(false);
    }
  };

  const disable = async () => {
    setBusy(true);
    try {
      const result = await authService.toggle2fa(false);
      setUser({ ...user!, otpEnabled: result.otpEnabled });
      setStep("idle");
      toast.success("Two-factor authentication disabled.");
    } catch {
      toast.error("Could not disable 2FA right now.");
    } finally {
      setBusy(false);
    }
  };

  const copyCodes = async () => {
    try {
      await navigator.clipboard.writeText(recoveryCodes.join("\n"));
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      /* clipboard unavailable */
    }
  };

  const registerPasskey = async () => {
    setRegisteringPasskey(true);
    try {
      const options = await authService.passkeyRegisterBegin();
      const { challenge_id: _challengeId, ...publicKeyOptions } = options as Record<
        string,
        unknown
      >;
      const credential = await startRegistration({
        optionsJSON: publicKeyOptions as never,
      });
      await authService.passkeyRegisterComplete(
        credential as unknown as Record<string, unknown>,
        "Browser"
      );
      toast.success("Passkey saved — you can now sign in with it.");
      const fresh = await authService.getProfile();
      setUser({ ...user!, passkeys: fresh.passkeys });
    } catch (error) {
      toast.error(getApiErrorMessage(error, "Could not register this passkey."));
    } finally {
      setRegisteringPasskey(false);
    }
  };

  return (
    <div className="rounded-2xl border border-gray-200 bg-card p-5 dark:border-gray-800">
      {/* ---- 2FA row ---- */}
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-start gap-3">
          <span
            className={cn(
              "inline-flex size-10 shrink-0 items-center justify-center rounded-xl",
              enabled
                ? "bg-emerald-500/10 text-emerald-500"
                : "bg-gray-100 text-gray-500 dark:bg-gray-800"
            )}
          >
            <KeyRound className="size-5" />
          </span>
          <div>
            <h3 className="font-display text-sm font-bold text-foreground">
              Two-Factor Authentication
            </h3>
            <p className="mt-0.5 max-w-md text-sm text-gray-600 dark:text-gray-400">
              {enabled
                ? "On — signing in also requires a one-time code emailed to you (or a backup recovery code)."
                : "Off — add a second step: after your password, a code emailed to you is required to sign in."}
            </p>
            {enabled && (
              <span className="mt-2 inline-flex items-center gap-1 rounded-full bg-emerald-500/10 px-2.5 py-0.5 text-xs font-semibold text-emerald-500">
                <ShieldCheck className="size-3" /> Enabled
              </span>
            )}
          </div>
        </div>

        <div className="shrink-0">
          {step === "password" && (
            <div className="flex items-center gap-2">
              <Input
                type="password"
                placeholder="Current password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && beginEnable()}
                className="w-44"
                autoComplete="current-password"
                aria-label="Current password"
              />
              <Button size="sm" onClick={beginEnable} disabled={busy || !password}>
                {busy ? <Loader2 className="size-3.5 animate-spin" /> : "Confirm"}
              </Button>
              <Button size="sm" variant="ghost" onClick={() => setStep("idle")} disabled={busy}>
                Cancel
              </Button>
            </div>
          )}
          {step === "email" && (
            <div className="flex items-center gap-2">
              <Input
                value={code}
                onChange={(e) => setCode(e.target.value.replace(/\D/g, "").slice(0, 6))}
                placeholder="Email code"
                className="w-32 text-center tracking-widest"
                aria-label="Email verification code"
              />
              <Button size="sm" onClick={confirmEnable} disabled={busy || code.length < 6}>
                {busy ? <Loader2 className="size-3.5 animate-spin" /> : "Verify"}
              </Button>
              <Button size="sm" variant="ghost" onClick={() => setStep("password")} disabled={busy}>
                Back
              </Button>
            </div>
          )}
          {step === "codes" && (
            <Button size="sm" variant="outline" onClick={() => setStep("idle")}>
              Done
            </Button>
          )}
          {step === "idle" &&
            (enabled ? (
              <Button variant="outline" size="sm" onClick={disable} disabled={busy}>
                {busy ? <Loader2 className="size-3.5 animate-spin" /> : "Disable"}
              </Button>
            ) : (
              <Button
                size="sm"
                className="bg-orange-600 text-white hover:bg-orange-700"
                onClick={() => setStep("password")}
              >
                Enable 2FA
              </Button>
            ))}
        </div>
      </div>

      {step === "email" && (
        <p className="mt-3 rounded-lg bg-gray-50 px-3 py-2 text-xs text-gray-600 dark:bg-gray-800/60 dark:text-gray-400">
          🔐 We emailed a 6-digit verification code to <strong>{destination}</strong>. Enter it to
          finish enabling two-factor authentication.
        </p>
      )}

      {/* ---- One-time recovery codes (shown exactly once) ---- */}
      {step === "codes" && (
        <div className="mt-4 rounded-xl border border-amber-200 bg-amber-50 p-4 dark:border-amber-500/30 dark:bg-amber-950/30">
          <h4 className="font-display text-sm font-bold text-amber-800 dark:text-amber-300">
            ⚠️ Save your recovery codes — shown only once
          </h4>
          <p className="mt-1 text-xs text-amber-700 dark:text-amber-300/80">
            If you lose access to your email, any one of these codes signs you in. Each works once.
          </p>
          <div className="mt-3 grid grid-cols-1 gap-1.5 sm:grid-cols-2">
            {recoveryCodes.map((codeItem) => (
              <code
                key={codeItem}
                className="rounded-md bg-white px-3 py-1.5 font-mono text-sm font-semibold tracking-wide text-amber-900 dark:bg-gray-900 dark:text-amber-200"
              >
                {codeItem}
              </code>
            ))}
          </div>
          <Button size="sm" variant="outline" className="mt-3" onClick={copyCodes}>
            {copied ? "✓ Copied" : "Copy all codes"}
          </Button>
        </div>
      )}

      {/* ---- Passkeys ---- */}
      <div className="mt-4 border-t border-gray-100 pt-4 dark:border-gray-800">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex items-start gap-3">
            <span className="inline-flex size-10 shrink-0 items-center justify-center rounded-xl bg-emerald-500/10 text-emerald-500">
              <KeyRound className="size-5" />
            </span>
            <div>
              <h4 className="font-display text-sm font-bold text-foreground">Passkeys</h4>
              <p className="mt-0.5 max-w-md text-sm text-gray-600 dark:text-gray-400">
                Sign in with a fingerprint, face, or device PIN — no password needed.
              </p>
              {passkeys.length > 0 && (
                <div className="mt-2 flex flex-wrap gap-1.5">
                  {passkeys.map((pk: PasskeyInfo) => (
                    <span
                      key={pk.id}
                      className="inline-flex items-center gap-1 rounded-full bg-gray-100 px-2.5 py-0.5 text-xs font-medium text-gray-600 dark:bg-gray-800 dark:text-gray-400"
                    >
                      {pk.name}
                    </span>
                  ))}
                </div>
              )}
            </div>
          </div>
          <Button
            size="sm"
            variant="outline"
            onClick={registerPasskey}
            disabled={registeringPasskey}
          >
            {registeringPasskey ? (
              <Loader2 className="size-3.5 animate-spin" />
            ) : (
              "+ Register a passkey"
            )}
          </Button>
        </div>
      </div>
    </div>
  );
}
