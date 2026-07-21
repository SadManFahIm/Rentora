import { useState } from "react";
import { useApp } from "../../context/AppContext";
import "./Auth.css";

export default function Auth({ setPage }) {
  const { setUser } = useApp();
  const [isLogin, setIsLogin] = useState(true);
  const [form, setForm] = useState({ name: "", email: "", password: "" });

  const update = (key, val) => setForm((f) => ({ ...f, [key]: val }));

  const handleSubmit = () => {
    if (form.email && form.password) {
      setUser({ name: form.name || "User", email: form.email });
      setPage("dashboard");
    }
  };

  return (
    <div className="modal-overlay">
      <div className="auth-modal">
        <h2>{isLogin ? "Welcome Back!" : "Create Account"}</h2>
        <p>{isLogin ? "Sign in to access your dashboard, messages, and bookings." : "Join RentRoom BD and find your perfect room."}</p>

        <div className="social-btns">
          <button className="social-btn">🔵 Continue with Google</button>
          <button className="social-btn">🟦 Continue with Facebook</button>
        </div>
        <div className="divider">or with email</div>

        {!isLogin && (
          <div className="input-group">
            <label>Full Name</label>
            <input placeholder="Your name" value={form.name} onChange={(e) => update("name", e.target.value)} />
          </div>
        )}
        <div className="input-group">
          <label>Email Address</label>
          <input type="email" placeholder="you@email.com" value={form.email} onChange={(e) => update("email", e.target.value)} />
        </div>
        <div className="input-group">
          <label>Password</label>
          <input type="password" placeholder="••••••••" value={form.password} onChange={(e) => update("password", e.target.value)} />
        </div>

        {isLogin && (
          <div style={{ textAlign: "right", marginBottom: 16 }}>
            <span className="forgot-link">Forgot password?</span>
          </div>
        )}

        <button className="btn-primary auth-submit" onClick={handleSubmit}>
          {isLogin ? "Sign In" : "Create Account"}
        </button>

        <div className="auth-switch">
          {isLogin ? "Don't have an account? " : "Already have an account? "}
          <span onClick={() => setIsLogin(!isLogin)}>
            {isLogin ? "Sign Up" : "Sign In"}
          </span>
        </div>

        <div style={{ textAlign: "center", marginTop: 12 }}>
          <button className="btn-outline" style={{ fontSize: "0.85rem", padding: "8px 20px" }} onClick={() => setPage("home")}>
            ← Back to Home
          </button>
        </div>
      </div>
    </div>
  );
}
