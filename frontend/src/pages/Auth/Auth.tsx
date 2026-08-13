import { useEffect, useMemo, useState } from "react";
import { Navigate, useNavigate, useSearchParams } from "react-router-dom";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { toast } from "sonner";
import { motion, AnimatePresence } from "motion/react";
import {
  startAuthentication,
  type PublicKeyCredentialRequestOptionsJSON,
} from "@simplewebauthn/browser";
import { ArrowLeft, Home, KeyRound, Loader2 } from "lucide-react";
import { useApp } from "../../context/AppContext";
import { useLogin, usePasskeyLogin, useRegister, useVerifyOtp } from "../../hooks/useAuth";
import { authService } from "../../services/authService";
import { getApiErrorMessage } from "../../services/errors";
import { isOtpPending, type OtpPending } from "../../types";
import { Dialog, DialogContent, DialogTitle } from "../../components/ui/dialog";
import { Button } from "../../components/ui/button";
import { Input } from "../../components/ui/input";
import { VisuallyHidden } from "../../components/ui/visually-hidden";
import { cn } from "../../lib/utils";
import {
  analyzePassword,
  checkPasswordBreached,
  passwordStrengthColor,
} from "../../lib/passwordStrength";

interface AuthFormValues {
  name: string;
  email: string;
  password: string;
  confirmPassword: string;
}

/** Small ease-in-out helper matching the Dribbble-style gentle motion. */
const spring = { type: "spring", stiffness: 260, damping: 24 } as const;

/** Floating decorative shape — one of the animated background elements. */
function FloatShape({
  className,
  delay = 0,
  duration = 9,
}: {
  className: string;
  delay?: number;
  duration?: number;
}) {
  return (
    <motion.span
      aria-hidden
      className={cn("pointer-events-none absolute rounded-full blur-2xl", className)}
      initial={{ opacity: 0, scale: 0.7 }}
      animate={{
        opacity: [0.35, 0.7, 0.4],
        scale: [0.8, 1.15, 0.85],
        y: [0, -26, 6, 0],
        x: [0, 18, -12, 0],
      }}
      transition={{
        duration,
        delay,
        repeat: Infinity,
        ease: "easeInOut",
      }}
    />
  );
}

export default function Auth() {
  const navigate = useNavigate();
  const { user, authLoading } = useApp();
  const [searchParams] = useSearchParams();
  const [isLogin, setIsLogin] = useState(true);
  const login = useLogin();
  const register = useRegister();
  const verifyOtp = useVerifyOtp();
  // Referral program: the inviter's ?ref= code travels through the URL on
  // the shared signup link straight into the register payload.
  const refCode = searchParams.get("ref") ?? undefined;

  // When login reports a pending email-OTP challenge (2FA account), the
  // form is replaced by a verification-code step.
  const [otpStep, setOtpStep] = useState<OtpPending | null>(null);
  const [otpCode, setOtpCode] = useState("");
  const [resending, setResending] = useState(false);
  const [useRecovery, setUseRecovery] = useState(false);
  const passkeyLogin = usePasskeyLogin();

  /** Shared handling for a completed passkey assertion. */
  const finishPasskey = (result: Awaited<ReturnType<typeof authService.passkeyLoginComplete>>) => {
    if (isOtpPending(result)) {
      setOtpStep(result);
      setOtpCode("");
      setUseRecovery(false);
      return;
    }
    toast.success(`Welcome back, ${result.user.name}!`);
    navigate("/dashboard");
  };

  /** Run the browser WebAuthn ceremony (optionally as conditional autofill). */
  const runPasskeyFlow = async (conditional = false) => {
    try {
      const options = await authService.passkeyLoginBegin();
      const { challenge_id: challengeId, ...publicKeyOptions } = options;
      const credential = await startAuthentication({
        optionsJSON: publicKeyOptions as unknown as PublicKeyCredentialRequestOptionsJSON,
        useBrowserAutofill: conditional,
      });
      if (!credential) return;
      passkeyLogin.mutate(
        {
          challengeId,
          response: credential as unknown as Record<string, unknown>,
        },
        {
          onSuccess: finishPasskey,
          onError: (error) =>
            toast.error(getApiErrorMessage(error, "Passkey sign-in did not complete.")),
        }
      );
    } catch {
      // Conditional autofill aborts silently when no passkey is available or
      // the user ignores it — the password form remains the fallback.
      if (!conditional) {
        toast.error("Passkey sign-in is not available right now. Use your password instead.");
      }
    }
  };

  // Conditional UI: arm a silent passkey autofill while the login form is
  // shown. When the browser offers the passkey and the user picks it, the
  // ceremony completes without touching the password fields.
  useEffect(() => {
    if (!isLogin || otpStep) return;
    let cancelled = false;
    const timer = setTimeout(() => {
      if (cancelled) return;
      void runPasskeyFlow(true);
    }, 600);
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- options are fetched inside
  }, [isLogin, otpStep]);

  // Single schema whose rules depend on the current mode:
  //  - Login:    email/username (non-empty) + password (min 6)
  //  - Register: name (required) + email (valid format) + password
  //              + confirmPassword (match)
  const schema = useMemo(
    () =>
      z
        .object({
          // `.catch("")` keeps fields that aren't rendered in the current
          // mode (name/confirmPassword while logging in) from surfacing the
          // opaque Zod v4 "Invalid input: expected string, received
          // undefined" error — they simply resolve to empty strings. Only
          // the conditional fields need this; email/password keep their
          // real validation messages.
          name: z.string().catch(""),
          email: z.string().min(1, "Email or username is required"),
          password: z
            .string()
            .min(1, "Password is required")
            .min(6, "Password must be at least 6 characters"),
          confirmPassword: z.string().catch(""),
        })
        .superRefine((data, ctx) => {
          // Register mode enforces a valid email address; login mode
          // accepts either the email address or the username (demo users
          // sign in with e.g. `rahim.hossain`).
          if (!isLogin && !/^\S+@\S+\.\S+$/.test(data.email)) {
            ctx.addIssue({
              code: z.ZodIssueCode.custom,
              path: ["email"],
              message: "Enter a valid email address",
            });
          }
          if (!isLogin) {
            if (!data.name.trim()) {
              ctx.addIssue({
                code: z.ZodIssueCode.custom,
                path: ["name"],
                message: "Name is required",
              });
            }
            if (data.confirmPassword !== data.password) {
              ctx.addIssue({
                code: z.ZodIssueCode.custom,
                path: ["confirmPassword"],
                message: "Passwords do not match",
              });
            }
          }
        }),
    [isLogin]
  );

  const {
    register: field,
    handleSubmit,
    reset,
    watch,
    formState: { errors, isSubmitting },
  } = useForm<AuthFormValues>({
    resolver: zodResolver(schema),
    defaultValues: { name: "", email: "", password: "", confirmPassword: "" },
    // Keep hidden-mode fields registered so they stay "" instead of
    // undefined on submit (see schema note above).
    shouldUnregister: false,
    mode: "onTouched",
  });

  // Live values for the register-mode strength meter + match indicator.
  const passwordValue = watch("password") ?? "";
  const confirmValue = watch("confirmPassword") ?? "";
  const analysis = analyzePassword(passwordValue);
  const passwordsMatch = confirmValue.length > 0 && confirmValue === passwordValue;

  // Debounced HaveIBeenPwned breach check (register mode only).
  const [breach, setBreach] = useState<"idle" | "checking" | "safe" | "breached">("idle");
  useEffect(() => {
    if (isLogin || passwordValue.length < 8) {
      setBreach("idle");
      return;
    }
    let cancelled = false;
    setBreach("checking");
    const timer = setTimeout(async () => {
      const found = await checkPasswordBreached(passwordValue);
      if (cancelled) return;
      setBreach(found === true ? "breached" : found === false ? "safe" : "idle");
    }, 700);
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [passwordValue, isLogin]);

  const rootError = login.isError || register.isError;
  const isBusy = isSubmitting || login.isPending || register.isPending;

  const submitOtp = () => {
    if (!otpStep || otpCode.trim().length === 0) return;
    verifyOtp.mutate(
      useRecovery
        ? { challenge: otpStep.challenge, recoveryCode: otpCode.trim() }
        : { challenge: otpStep.challenge, code: otpCode.trim() },
      {
        onSuccess: (user) => {
          toast.success(`Welcome back, ${user.name}!`);
          navigate("/dashboard");
        },
        onError: (error) =>
          toast.error(getApiErrorMessage(error, "That code was not accepted. Try again.")),
      }
    );
  };

  const resendOtp = async () => {
    if (!otpStep) return;
    setResending(true);
    try {
      await authService.resendOtp(otpStep.challenge);
      toast.success("A new code has been sent to your email.");
    } catch (error) {
      toast.error(getApiErrorMessage(error, "Could not resend the code yet."));
    } finally {
      setResending(false);
    }
  };

  const backToLogin = () => {
    setOtpStep(null);
    setOtpCode("");
    setUseRecovery(false);
    login.reset();
  };

  const toggleRecoveryMode = () => {
    setUseRecovery((v) => !v);
    setOtpCode("");
  };

  const onSubmit = handleSubmit((values) => {
    if (isLogin) {
      login.mutate(
        { email: values.email, password: values.password },
        {
          onSuccess: (result) => {
            if (isOtpPending(result)) {
              // 2FA enabled — collect the emailed code before any tokens.
              setOtpStep(result);
              setOtpCode("");
              return;
            }
            toast.success(`Welcome back, ${result.user.name}!`);
            navigate("/dashboard");
          },
          onError: (error) => toast.error(getApiErrorMessage(error, "Invalid email or password.")),
        }
      );
    } else {
      register.mutate(
        {
          name: values.name,
          email: values.email,
          password: values.password,
          ref: refCode,
        },
        {
          onSuccess: (user) => {
            toast.success(`Welcome to Rentora, ${user.name}!`);
            navigate("/dashboard");
          },
          onError: (error) =>
            toast.error(getApiErrorMessage(error, "Could not create your account.")),
        }
      );
    }
  });

  const switchMode = () => {
    setIsLogin((v) => !v);
    reset();
    login.reset();
    register.reset();
  };

  const fadeUp = {
    initial: { opacity: 0, y: 18 },
    animate: { opacity: 1, y: 0 },
    exit: { opacity: 0, y: -12 },
  };

  // Already signed in? Send the user straight to their dashboard instead of
  // showing the auth dialog. While the session is still restoring (tokens
  // present, profile fetch in flight) render nothing to avoid a flash.
  // (Placed after every hook so the hook order stays stable.)
  if (authLoading) return null;
  if (user) return <Navigate to="/dashboard" replace />;

  return (
    <Dialog open onOpenChange={(open) => !open && navigate("/")}>
      <DialogContent className="max-w-md gap-0 overflow-hidden p-0" showCloseButton>
        {/* ---------- Animated header (Dribbble "Login Web Animation" style) ---------- */}
        <div className="relative isolate overflow-hidden bg-gradient-to-br from-indigo-950 via-violet-950 to-slate-950 px-8 pb-9 pt-8">
          {/* drifting color blobs */}
          <FloatShape className="-left-10 -top-12 size-36 bg-fuchsia-500/50" delay={0} />
          <FloatShape className="right-[-3rem] top-[-2rem] size-44 bg-orange-500/50" delay={1.4} />
          <FloatShape className="bottom-[-3.5rem] left-1/3 size-32 bg-sky-400/50" delay={2.6} />
          {/* static concentric rings */}
          <motion.span
            aria-hidden
            className="pointer-events-none absolute right-6 top-6 size-24 rounded-full border border-white/15"
            animate={{ scale: [1, 1.18, 1], rotate: [0, 18, 0] }}
            transition={{ duration: 14, repeat: Infinity, ease: "easeInOut" }}
          />
          <motion.span
            aria-hidden
            className="pointer-events-none absolute right-14 top-14 size-10 rounded-full border border-white/20"
            animate={{ scale: [1, 1.4, 1], rotate: [0, -24, 0] }}
            transition={{ duration: 10, repeat: Infinity, ease: "easeInOut" }}
          />

          <div className="relative">
            <motion.div
              initial={{ opacity: 0, scale: 0.8, rotate: -8 }}
              animate={{ opacity: 1, scale: 1, rotate: 0 }}
              transition={spring}
              className="mb-4 inline-flex size-12 items-center justify-center rounded-2xl bg-gradient-to-br from-orange-500 to-orange-600 shadow-lg shadow-orange-900/40"
            >
              <Home className="size-6 text-white" />
            </motion.div>

            <AnimatePresence mode="wait">
              <motion.h2
                key={`title-${isLogin}`}
                {...fadeUp}
                transition={spring}
                className="font-display text-2xl font-extrabold tracking-tight text-white"
              >
                {isLogin ? "Welcome Back!" : "Create Account"}
              </motion.h2>
            </AnimatePresence>

            <AnimatePresence mode="wait">
              <motion.p
                key={`sub-${isLogin}`}
                {...fadeUp}
                transition={{ ...spring, delay: 0.06 }}
                className="mt-1.5 text-sm text-indigo-200/80"
              >
                {isLogin
                  ? "Sign in to access your dashboard, messages, and bookings."
                  : "Join Rentora and find your perfect room."}
              </motion.p>
            </AnimatePresence>
          </div>
        </div>

        {/* ---------- Form body (frosted panel) ---------- */}
        <div className="relative bg-background px-8 pb-8 pt-6">
          <VisuallyHidden>
            <DialogTitle>
              {otpStep ? "Two-step verification" : isLogin ? "Welcome Back!" : "Create Account"}
            </DialogTitle>
          </VisuallyHidden>

          {otpStep && (
            <div className="flex flex-col gap-4">
              <motion.div
                initial={{ opacity: 0, y: 14 }}
                animate={{ opacity: 1, y: 0 }}
                transition={spring}
                className="flex flex-col items-center text-center"
              >
                <span className="mb-3 inline-flex size-12 items-center justify-center rounded-2xl bg-gradient-to-br from-emerald-500 to-teal-600 text-2xl shadow-lg shadow-emerald-900/30">
                  🔐
                </span>
                <h3 className="font-display text-lg font-extrabold tracking-tight text-foreground">
                  Two-step verification
                </h3>
                <p className="mt-1.5 max-w-xs text-sm text-muted-foreground">
                  We emailed a 6-digit code to{" "}
                  <span className="font-semibold text-foreground">{otpStep.destinationMasked}</span>
                  . Enter it below to finish signing in.
                </p>
              </motion.div>

              <label className="text-sm font-semibold text-muted-foreground">
                {useRecovery ? "Recovery code" : "Verification code"}
              </label>
              <Input
                value={otpCode}
                onChange={(e) =>
                  setOtpCode(
                    useRecovery
                      ? e.target.value.toUpperCase().slice(0, 14)
                      : e.target.value.replace(/\D/g, "").slice(0, 6)
                  )
                }
                onKeyDown={(e) => e.key === "Enter" && submitOtp()}
                inputMode={useRecovery ? undefined : "numeric"}
                autoFocus
                maxLength={useRecovery ? 14 : 6}
                placeholder={useRecovery ? "XXXX-XXXX-XXXX" : "••••••"}
                className={
                  useRecovery
                    ? "text-center font-display text-xl tracking-widest"
                    : "text-center font-display text-2xl tracking-[0.5em]"
                }
                aria-label={useRecovery ? "Recovery code" : "6-digit verification code"}
              />
              <p className="text-center text-xs text-muted-foreground">
                {useRecovery ? (
                  <>
                    A recovery code works once. Request a new batch by disabling and re-enabling
                    2FA.
                  </>
                ) : (
                  <>
                    Lost your email?{" "}
                    <button
                      type="button"
                      onClick={toggleRecoveryMode}
                      className="font-semibold text-brand hover:underline"
                    >
                      Use a recovery code
                    </button>
                  </>
                )}
              </p>

              {verifyOtp.isPending && (
                <p className="flex items-center justify-center gap-2 text-sm text-muted-foreground">
                  <Loader2 className="size-4 animate-spin" /> Verifying…
                </p>
              )}

              <Button
                type="button"
                variant="brand"
                size="lg"
                className="w-full rounded-xl bg-gradient-to-r from-emerald-600 to-teal-500 font-semibold text-white shadow-lg shadow-emerald-600/25"
                onClick={submitOtp}
                disabled={verifyOtp.isPending || otpCode.length < 6}
              >
                {verifyOtp.isPending ? "Verifying…" : "Verify & Sign In"}
              </Button>

              <div className="flex items-center justify-between text-sm">
                <button
                  type="button"
                  onClick={backToLogin}
                  className="flex items-center gap-1 font-medium text-muted-foreground transition-colors hover:text-foreground"
                >
                  <ArrowLeft className="size-3.5" /> Use another account
                </button>
                {useRecovery ? (
                  <button
                    type="button"
                    onClick={toggleRecoveryMode}
                    className="font-semibold text-brand hover:underline"
                  >
                    Use emailed code
                  </button>
                ) : (
                  <button
                    type="button"
                    onClick={resendOtp}
                    disabled={resending}
                    className="font-semibold text-brand hover:underline disabled:opacity-50"
                  >
                    {resending ? "Sending…" : "Resend code"}
                  </button>
                )}
              </div>
            </div>
          )}

          <form onSubmit={onSubmit} noValidate className="flex flex-col gap-3.5">
            {!otpStep && (
              <>
                {rootError && (
                  <motion.div
                    initial={{ opacity: 0, height: 0 }}
                    animate={{ opacity: 1, height: "auto" }}
                    className="overflow-hidden rounded-lg border border-red-200 bg-red-50 px-3.5 py-2.5 text-sm text-red-700 dark:border-red-500/30 dark:bg-red-950/40 dark:text-red-400"
                  >
                    Something went wrong. Please check your details and try again.
                  </motion.div>
                )}

                <AnimatePresence initial={false} mode="popLayout">
                  {!isLogin && (
                    <motion.div
                      key="name"
                      initial={{ opacity: 0, height: 0, marginBottom: 0 }}
                      animate={{ opacity: 1, height: "auto", marginBottom: 14 }}
                      exit={{ opacity: 0, height: 0, marginBottom: 0 }}
                      transition={{ duration: 0.22 }}
                      className="overflow-hidden"
                    >
                      <label className="mb-1.5 block text-sm font-semibold text-muted-foreground">
                        Full Name
                      </label>
                      <Input
                        placeholder="Your name"
                        aria-invalid={!!errors.name}
                        {...field("name")}
                      />
                      {errors.name && (
                        <span className="mt-1.5 block text-xs font-medium text-red-600">
                          {errors.name.message}
                        </span>
                      )}
                    </motion.div>
                  )}
                </AnimatePresence>

                <div>
                  <label className="mb-1.5 block text-sm font-semibold text-muted-foreground">
                    {isLogin ? "Email or Username" : "Email Address"}
                  </label>
                  <Input
                    type="text"
                    inputMode="email"
                    placeholder={isLogin ? "you@email.com or rahim.hossain" : "you@email.com"}
                    autoComplete="username"
                    aria-invalid={!!errors.email}
                    {...field("email")}
                  />
                  {errors.email && (
                    <span className="mt-1.5 block text-xs font-medium text-red-600">
                      {errors.email.message}
                    </span>
                  )}
                </div>

                <div>
                  <label className="mb-1.5 block text-sm font-semibold text-muted-foreground">
                    Password
                  </label>
                  <Input
                    type="password"
                    placeholder="••••••••"
                    aria-invalid={!!errors.password}
                    {...field("password")}
                  />
                  {errors.password && (
                    <span className="mt-1.5 block text-xs font-medium text-red-600">
                      {errors.password.message}
                    </span>
                  )}
                  {/* Live strength meter (register mode only) */}
                  {!isLogin && passwordValue.length > 0 && (
                    <div className="mt-2" aria-live="polite">
                      <div className="flex items-center justify-between text-[11px] font-medium">
                        <span
                          className={cn(
                            "transition-colors",
                            analysis.score >= 3
                              ? "text-emerald-600"
                              : analysis.score === 2
                                ? "text-amber-600"
                                : "text-red-500"
                          )}
                        >
                          Password strength: {analysis.label}
                        </span>
                        <span className="text-muted-foreground">
                          {passwordValue.length}/12+ · ~10^{analysis.entropy}
                        </span>
                      </div>
                      <div className="mt-1 flex h-1.5 gap-1 overflow-hidden rounded-full">
                        {[0, 1, 2, 3].map((i) => (
                          <span
                            key={i}
                            className={cn(
                              "h-full flex-1 rounded-full transition-all duration-300",
                              i < analysis.score
                                ? passwordStrengthColor(analysis.score)
                                : "bg-muted"
                            )}
                          />
                        ))}
                      </div>
                      {/* zxcvbn feedback (e.g. "This is a top-10 common password") */}
                      {analysis.warnings[0] && (
                        <p className="mt-1.5 text-[11px] font-medium text-muted-foreground">
                          {analysis.warnings[0]}
                        </p>
                      )}
                      {/* HaveIBeenPwned breach status */}
                      {breach === "checking" && (
                        <p className="mt-1.5 text-[11px] text-muted-foreground">
                          Checking known breaches…
                        </p>
                      )}
                      {breach === "breached" && (
                        <p className="mt-1.5 rounded-md border border-red-200 bg-red-50 px-2.5 py-1.5 text-[11px] font-medium text-red-700 dark:border-red-500/30 dark:bg-red-950/40 dark:text-red-400">
                          ⚠️ This password appears in known data breaches — please choose a
                          different one.
                        </p>
                      )}
                      {breach === "safe" && (
                        <p className="mt-1.5 text-[11px] font-medium text-emerald-600">
                          ✓ Not found in known breaches
                        </p>
                      )}
                    </div>
                  )}
                </div>

                <AnimatePresence initial={false} mode="popLayout">
                  {!isLogin && (
                    <motion.div
                      key="confirm"
                      initial={{ opacity: 0, height: 0, marginBottom: 0 }}
                      animate={{ opacity: 1, height: "auto", marginBottom: 14 }}
                      exit={{ opacity: 0, height: 0, marginBottom: 0 }}
                      transition={{ duration: 0.22 }}
                      className="overflow-hidden"
                    >
                      <label className="mb-1.5 block text-sm font-semibold text-muted-foreground">
                        Confirm Password
                      </label>
                      <Input
                        type="password"
                        placeholder="••••••••"
                        aria-invalid={!!errors.confirmPassword}
                        {...field("confirmPassword")}
                      />
                      {errors.confirmPassword && (
                        <span className="mt-1.5 block text-xs font-medium text-red-600">
                          {errors.confirmPassword.message}
                        </span>
                      )}
                      {/* Live match indicator */}
                      {confirmValue.length > 0 && (
                        <span
                          aria-live="polite"
                          className={cn(
                            "mt-1.5 flex items-center gap-1 text-xs font-medium",
                            passwordsMatch ? "text-emerald-600" : "text-red-500"
                          )}
                        >
                          {passwordsMatch ? "✓ Passwords match" : "✕ Passwords do not match"}
                        </span>
                      )}
                    </motion.div>
                  )}
                </AnimatePresence>

                <motion.div
                  initial={{ opacity: 0, y: 12 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ ...spring, delay: 0.12 }}
                  className="flex items-center justify-between"
                >
                  {isLogin ? (
                    <span className="cursor-pointer text-sm font-medium text-brand hover:underline">
                      Forgot password?
                    </span>
                  ) : (
                    <span className="text-sm text-muted-foreground">
                      Password must be 6+ characters
                    </span>
                  )}
                </motion.div>

                <motion.div
                  whileHover={{ scale: 1.015 }}
                  whileTap={{ scale: 0.985 }}
                  transition={spring}
                >
                  <Button
                    type="submit"
                    variant="brand"
                    size="lg"
                    className="w-full rounded-xl bg-gradient-to-r from-orange-600 to-orange-500 font-semibold text-white shadow-lg shadow-orange-600/25 hover:from-orange-600 hover:to-orange-500 hover:shadow-orange-600/35"
                    disabled={isBusy}
                  >
                    {isBusy ? (
                      <>
                        <Loader2 className="size-4 animate-spin" /> Please wait…
                      </>
                    ) : isLogin ? (
                      "Sign In"
                    ) : (
                      "Create Account"
                    )}
                  </Button>
                </motion.div>

                {isLogin && (
                  <motion.button
                    type="button"
                    onClick={() => void runPasskeyFlow(false)}
                    disabled={passkeyLogin.isPending}
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    transition={{ ...spring, delay: 0.16 }}
                    className="flex w-full items-center justify-center gap-2 rounded-xl border border-gray-200 px-4 py-2.5 text-sm font-semibold text-gray-700 transition-colors hover:bg-gray-50 disabled:opacity-50 dark:border-gray-700 dark:text-gray-300 dark:hover:bg-gray-800"
                  >
                    {passkeyLogin.isPending ? (
                      <Loader2 className="size-4 animate-spin" />
                    ) : (
                      <KeyRound className="size-4 text-emerald-600" />
                    )}
                    Sign in with a passkey
                  </motion.button>
                )}

                <p className="text-center text-sm text-muted-foreground">
                  {isLogin ? "Don't have an account? " : "Already have an account? "}
                  <button
                    type="button"
                    className="cursor-pointer font-semibold text-brand hover:underline"
                    onClick={switchMode}
                  >
                    {isLogin ? "Sign Up" : "Sign In"}
                  </button>
                </p>

                {/* divider + social login (matches the current product's look) */}
                <div className="my-1 flex items-center gap-3 text-xs text-muted-foreground">
                  <span className="h-px flex-1 bg-border" />
                  or continue with
                  <span className="h-px flex-1 bg-border" />
                </div>
                <div className="grid grid-cols-2 gap-3">
                  <Button type="button" variant="outline" className="justify-center gap-2">
                    <span className="text-base">🔵</span> Google
                  </Button>
                  <Button type="button" variant="outline" className="justify-center gap-2">
                    <span className="text-base">🟦</span> Facebook
                  </Button>
                </div>

                <button
                  type="button"
                  onClick={() => navigate("/")}
                  className="mx-auto flex items-center gap-1.5 text-sm text-muted-foreground transition-colors hover:text-foreground"
                >
                  <ArrowLeft className="size-3.5" /> Back to Home
                </button>
              </>
            )}
          </form>
        </div>
      </DialogContent>
    </Dialog>
  );
}
