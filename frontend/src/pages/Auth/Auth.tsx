import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { toast } from "sonner";
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

export default function Auth() {
  const navigate = useNavigate();
  const [isLogin, setIsLogin] = useState(true);
  const login = useLogin();
  const register = useRegister();

  // Single schema whose rules depend on the current mode:
  //  - Login:    email (valid) + password (min 6)
  //  - Register: name (required) + email + password + confirmPassword (match)
  const schema = useMemo(
    () =>
      z
        .object({
          name: z.string(),
          email: z
            .string()
            .min(1, "Email is required")
            .email("Enter a valid email address"),
          password: z
            .string()
            .min(1, "Password is required")
            .min(6, "Password must be at least 6 characters"),
          confirmPassword: z.string(),
        })
        .superRefine((data, ctx) => {
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
    mode: "onTouched",
  });

  const rootError = login.isError || register.isError;

  const onSubmit = handleSubmit((values) => {
    if (isLogin) {
      login.mutate(
        { email: values.email, password: values.password },
        {
          onSuccess: (user) => {
            toast.success(`Welcome back, ${user.name}!`);
            navigate("/dashboard");
          },
          onError: (error) =>
            toast.error(getApiErrorMessage(error, "Invalid email or password.")),
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

  return (
    <Dialog open onOpenChange={(open) => !open && navigate("/")}>
      <DialogContent className="max-w-110 gap-0 p-9" showCloseButton>
        <VisuallyHidden>
          <DialogTitle>{isLogin ? "Welcome Back!" : "Create Account"}</DialogTitle>
        </VisuallyHidden>
        <form onSubmit={onSubmit} noValidate>
          <h2 className="mb-2 font-display text-2xl font-extrabold text-foreground">
            {isLogin ? "Welcome Back!" : "Create Account"}
          </h2>
          <p className="mb-6 text-sm text-muted-foreground">
            {isLogin
              ? "Sign in to access your dashboard, messages, and bookings."
              : "Join RentRoom BD and find your perfect room."}
          </p>

          <div className="mb-5 flex flex-col gap-2.5">
            <Button type="button" variant="outline" className="justify-center">
              🔵 Continue with Google
            </Button>
            <Button type="button" variant="outline" className="justify-center">
              🟦 Continue with Facebook
            </Button>
          </div>

          <div className="relative mb-4 text-center text-sm text-muted-foreground before:absolute before:left-0 before:top-1/2 before:h-px before:w-[42%] before:bg-border after:absolute after:right-0 after:top-1/2 after:h-px after:w-[42%] after:bg-border">
            or with email
          </div>

          {rootError && (
            <div className="mb-4 rounded-lg border border-red-200 bg-red-50 px-3.5 py-2.5 text-sm text-red-700">
              Something went wrong. Please check your details and try again.
            </div>
          )}

          {!isLogin && (
            <div className="mb-4">
              <label className="mb-1.5 block text-sm font-semibold text-muted-foreground">Full Name</label>
              <Input
                placeholder="Your name"
                aria-invalid={!!errors.name}
                {...field("name")}
              />
              {errors.name && <span className="mt-1.5 block text-xs font-medium text-red-600">{errors.name.message}</span>}
            </div>
          )}

          <div className="mb-4">
            <label className="mb-1.5 block text-sm font-semibold text-muted-foreground">Email Address</label>
            <Input
              type="email"
              placeholder="you@email.com"
              aria-invalid={!!errors.email}
              {...field("email")}
            />
            {errors.email && <span className="mt-1.5 block text-xs font-medium text-red-600">{errors.email.message}</span>}
          </div>

          <div className="mb-4">
            <label className="mb-1.5 block text-sm font-semibold text-muted-foreground">Password</label>
            <Input
              type="password"
              placeholder="••••••••"
              aria-invalid={!!errors.password}
              {...field("password")}
            />
            {errors.password && <span className="mt-1.5 block text-xs font-medium text-red-600">{errors.password.message}</span>}
          </div>

          {!isLogin && (
            <div className="mb-4">
              <label className="mb-1.5 block text-sm font-semibold text-muted-foreground">Confirm Password</label>
              <Input
                type="password"
                placeholder="••••••••"
                aria-invalid={!!errors.confirmPassword}
                {...field("confirmPassword")}
              />
              {errors.confirmPassword && (
                <span className="mt-1.5 block text-xs font-medium text-red-600">{errors.confirmPassword.message}</span>
              )}
            </div>
          )}

          {isLogin && (
            <div className="mb-4 text-right">
              <span className="cursor-pointer text-sm text-brand">Forgot password?</span>
            </div>
          )}

          <Button
            type="submit"
            variant="brand"
            size="lg"
            className={cn("w-full", !isLogin && "mt-1")}
            disabled={isSubmitting || login.isPending || register.isPending}
          >
            {isSubmitting || login.isPending || register.isPending
              ? "Please wait…"
              : isLogin
                ? "Sign In"
                : "Create Account"}
          </Button>

          <div className="mt-4 text-center text-sm text-muted-foreground">
            {isLogin ? "Don't have an account? " : "Already have an account? "}
            <span className="cursor-pointer font-semibold text-brand" onClick={switchMode}>
              {isLogin ? "Sign Up" : "Sign In"}
            </span>
          </div>

          <div className="mt-3 text-center">
            <Button type="button" variant="outline" size="sm" onClick={() => navigate("/")}>
              ← Back to Home
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}
