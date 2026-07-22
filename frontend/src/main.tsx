import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";

// Tailwind + design tokens (loaded before component CSS so existing
// class-based styles keep precedence over Tailwind preflight).
import "./styles/app.css";

const rootElement = document.getElementById("root");
if (!rootElement) {
  throw new Error("Root element #root not found");
}

ReactDOM.createRoot(rootElement).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);
