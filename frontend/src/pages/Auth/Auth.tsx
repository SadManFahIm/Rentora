import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { useLogin, useRegister } from "../../hooks/useAuth";
import "./Auth.css";

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
        { onSuccess: () => navigate("/dashboard") }
      );
    } else {
      register.mutate(
        { name: values.name, email: values.email, password: values.password },
        { onSuccess: () => navigate("/dashboard") }
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
    <div className="modal-overlay">
      <form className="auth-modal" onSubmit={onSubmit} noValidate>
        <h2>{isLogin ? "Welcome Back!" : "Create Account"}</h2>
        <p>
          {isLogin
            ? "Sign in to access your dashboard, messages, and bookings."
            : "Join RentRoom BD and find your perfect room."}
        </p>

        <div className="social-btns">
          <button type="button" className="social-btn">🔵 Continue with Google</button>
          <button type="button" className="social-btn">🟦 Continue with Facebook</button>
        </div>
        <div className="divider">or with email</div>

        {rootError && (
          <div className="auth-error">
            Something went wrong. Please check your details and try again.
          </div>
        )}

        {!isLogin && (
          <div className="input-group">
            <label>Full Name</label>
            <input
              placeholder="Your name"
              className={errors.name ? "has-error" : ""}
              {...field("name")}
            />
            {errors.name && <span className="field-error">{errors.name.message}</span>}
          </div>
        )}

        <div className="input-group">
          <label>Email Address</label>
          <input
            type="email"
            placeholder="you@email.com"
            className={errors.email ? "has-error" : ""}
            {...field("email")}
          />
          {errors.email && <span className="field-error">{errors.email.message}</span>}
        </div>

        <div className="input-group">
          <label>Password</label>
          <input
            type="password"
            placeholder="••••••••"
            className={errors.password ? "has-error" : ""}
            {...field("password")}
          />
          {errors.password && <span className="field-error">{errors.password.message}</span>}
        </div>

        {!isLogin && (
          <div className="input-group">
            <label>Confirm Password</label>
            <input
              type="password"
              placeholder="••••••••"
              className={errors.confirmPassword ? "has-error" : ""}
              {...field("confirmPassword")}
            />
            {errors.confirmPassword && (
              <span className="field-error">{errors.confirmPassword.message}</span>
            )}
          </div>
        )}

        {isLogin && (
          <div style={{ textAlign: "right", marginBottom: 16 }}>
            <span className="forgot-link">Forgot password?</span>
          </div>
        )}

        <button
          type="submit"
          className="btn-primary auth-submit"
          disabled={isSubmitting || login.isPending || register.isPending}
        >
          {isSubmitting || login.isPending || register.isPending
            ? "Please wait…"
            : isLogin
              ? "Sign In"
              : "Create Account"}
        </button>

        <div className="auth-switch">
          {isLogin ? "Don't have an account? " : "Already have an account? "}
          <span onClick={switchMode}>{isLogin ? "Sign Up" : "Sign In"}</span>
        </div>

        <div style={{ textAlign: "center", marginTop: 12 }}>
          <button
            type="button"
            className="btn-outline"
            style={{ fontSize: "0.85rem", padding: "8px 20px" }}
            onClick={() => navigate("/")}
          >
            ← Back to Home
          </button>
        </div>
      </form>
    </div>
  );
}
