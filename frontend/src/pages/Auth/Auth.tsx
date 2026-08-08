import { useMemo, useState } from "react";
import { Navigate, useNavigate } from "react-router-dom";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { toast } from "sonner";
import { motion, AnimatePresence } from "motion/react";
import { ArrowLeft, Home, Loader2 } from "lucide-react";
import { useApp } from "../../context/AppContext";
import { useLogin, useRegister } from "../../hooks/useAuth";
import { getApiErrorMessage } from "../../services/errors";
import { Dialog, DialogContent, DialogTitle } from "../../components/ui/dialog";
import { Button } from "../../components/ui/button";
import { Input } from "../../components/ui/input";
import { VisuallyHidden } from "../../components/ui/visually-hidden";
import { cn } from "../../lib/utils";

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
  const [isLogin, setIsLogin] = useState(true);
  const login = useLogin();
  const register = useRegister();

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
    formState: { errors, isSubmitting },
  } = useForm<AuthFormValues>({
    resolver: zodResolver(schema),
    defaultValues: { name: "", email: "", password: "", confirmPassword: "" },
    // Keep hidden-mode fields registered so they stay "" instead of
    // undefined on submit (see schema note above).
    shouldUnregister: false,
    mode: "onTouched",
  });

  const rootError = login.isError || register.isError;
  const isBusy = isSubmitting || login.isPending || register.isPending;

  const onSubmit = handleSubmit((values) => {
    if (isLogin) {
      login.mutate(
        { email: values.email, password: values.password },
        {
          onSuccess: (user) => {
            toast.success(`Welcome back, ${user.name}!`);
            navigate("/dashboard");
          },
          onError: (error) => toast.error(getApiErrorMessage(error, "Invalid email or password.")),
        }
      );
    } else {
      register.mutate(
        { name: values.name, email: values.email, password: values.password },
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
                  : "Join RentRoom BD and find your perfect room."}
              </motion.p>
            </AnimatePresence>
          </div>
        </div>

        {/* ---------- Form body (frosted panel) ---------- */}
        <div className="relative bg-background px-8 pb-8 pt-6">
          <VisuallyHidden>
            <DialogTitle>{isLogin ? "Welcome Back!" : "Create Account"}</DialogTitle>
          </VisuallyHidden>

          <form onSubmit={onSubmit} noValidate className="flex flex-col gap-3.5">
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
                  <Input placeholder="Your name" aria-invalid={!!errors.name} {...field("name")} />
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
          </form>
        </div>
      </DialogContent>
    </Dialog>
  );
}
