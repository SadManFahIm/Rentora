import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import { initSentry } from "./lib/sentry";

// Tailwind + design tokens (loaded before component CSS so existing
// class-based styles keep precedence over Tailwind preflight).
import "./styles/app.css";

// Error tracking must be initialised before the app renders.
initSentry();

const rootElement = document.getElementById("root");
if (!rootElement) {
  throw new Error("Root element #root not found");
}

ReactDOM.createRoot(rootElement).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);
