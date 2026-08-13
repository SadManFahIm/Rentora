import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import { initSentry } from "./lib/sentry";

// Tailwind + design tokens (loaded before component CSS so existing
// class-based styles keep precedence over Tailwind preflight).
import "./styles/app.css";

// Error tracking must be initialised before the app renders.
initSentry();

// ---- PWA: register the service worker up front (idempotent with the push
// opt-in path — same scope returns the same registration). Only runs in a
// secure context (https or localhost) so it never ships over plain http.
if ("serviceWorker" in navigator && (window.isSecureContext || location.hostname === "localhost")) {
  navigator.serviceWorker.register("/sw.js").catch(() => {
    /* offline/push are progressive enhancements — never block the app */
  });
}

const rootElement = document.getElementById("root");
if (!rootElement) {
  throw new Error("Root element #root not found");
}

ReactDOM.createRoot(rootElement).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);
