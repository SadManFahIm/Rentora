// ESLint flat config (ESLint 9+).
// TypeScript-aware rules + React hooks/react-refresh, tuned for a Vite app.
import js from "@eslint/js";
import tseslint from "typescript-eslint";
import reactHooks from "eslint-plugin-react-hooks";
import reactRefresh from "eslint-plugin-react-refresh";

export default tseslint.config(
  { ignores: ["dist", "build", "node_modules"] },
  {
    files: ["**/*.{ts,tsx}"],
    extends: [
      js.configs.recommended,
      ...tseslint.configs.recommended,
      ...tseslint.configs.stylistic,
    ],
    languageOptions: {
      ecmaVersion: 2020,
      globals: {
        window: "readonly",
        document: "readonly",
        localStorage: "readonly",
        navigator: "readonly",
        URL: "readonly",
        WebSocket: "readonly",
        fetch: "readonly",
        console: "readonly",
        setTimeout: "readonly",
        clearTimeout: "readonly",
        setInterval: "readonly",
        clearInterval: "readonly",
        requestAnimationFrame: "readonly",
        cancelAnimationFrame: "readonly",
        location: "readonly",
        history: "readonly",
        AbortController: "readonly",
        Blob: "readonly",
        FileReader: "readonly",
        Image: "readonly",
        Audio: "readonly",
        Notification: "readonly",
        EventSource: "readonly",
        crypto: "readonly",
        HTMLElement: "readonly",
        HTMLInputElement: "readonly",
        HTMLDivElement: "readonly",
        HTMLButtonElement: "readonly",
        HTMLImageElement: "readonly",
        HTMLFormElement: "readonly",
        KeyboardEvent: "readonly",
        MouseEvent: "readonly",
        CustomEvent: "readonly",
        CustomElementRegistry: "readonly",
        IntersectionObserver: "readonly",
        MutationObserver: "readonly",
        ResizeObserver: "readonly",
        matchMedia: "readonly",
        getComputedStyle: "readonly",
        FormData: "readonly",
        File: "readonly",
        Element: "readonly",
        Node: "readonly",
        Event: "readonly",
        "process.env": "readonly",
        process: "readonly",
      },
    },
    plugins: {
      "react-hooks": reactHooks,
      "react-refresh": reactRefresh,
    },
    rules: {
      ...reactHooks.configs.recommended.rules,
      // Best-effort React-Compiler-era rules that false-positive on legitimate
      // patterns used across this codebase (URL <-> state sync, latest-value
      // refs, reset-on-key-change). These are documented React approaches —
      // refactoring them away would only add renders, not remove them.
      "react-hooks/set-state-in-effect": "off",
      "react-hooks/refs": "off",
      "react-refresh/only-export-components": [
        "warn",
        { allowConstantExport: true },
      ],
      // Allow explicit any where the codebase already leans on it (axios
      // error shapes, JSON payloads) — typechecker still guards the rest.
      "@typescript-eslint/no-explicit-any": "off",
      "@typescript-eslint/no-unused-vars": [
        "error",
        { argsIgnorePattern: "^_", varsIgnorePattern: "^_" },
      ],
    },
  }
);
