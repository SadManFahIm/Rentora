import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tsconfigPaths from "vite-tsconfig-paths";
import tailwindcss from "@tailwindcss/vite";

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react(), tsconfigPaths(), tailwindcss()],
  server: {
    port: 3000,
    open: true,
  },
  build: {
    outDir: "build",
  },
  test: {
    // jsdom globally: component tests (.tsx) need a DOM, and Vitest 4 removed
    // per-glob environments (environmentMatchGlobs) — the pure-logic suites
    // pass fine under jsdom too (Vitest keeps node globals available).
    environment: "jsdom",
    setupFiles: ["src/test/setup.ts"],
    include: ["src/**/*.test.{ts,tsx}"],
    coverage: {
      provider: "v8",
      exclude: ["**/*.test.{ts,tsx}"],
      reporter: ["text", "cobertura"],
      thresholds: {
        lines: 55,
        statements: 50,
      },
    },
  },
});
