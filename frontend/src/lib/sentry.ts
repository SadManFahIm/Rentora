// ============================================================
// SENTRY — client-side error tracking (Phase 9)
// ============================================================
// Initialised from VITE_SENTRY_DSN; no-op when the DSN is not set, so local
// dev and CI never send events. All public methods are safe to call even
// when Sentry is not configured (they become no-ops internally).
import * as Sentry from "@sentry/react";
import { env } from "../config/env";

export const sentryEnabled = Boolean(env.SENTRY_DSN);

export function initSentry(): void {
  if (!env.SENTRY_DSN) return;
  Sentry.init({
    dsn: env.SENTRY_DSN,
    environment: import.meta.env.MODE,
    tracesSampleRate: 0.1,
    // Keep user emails/IDs out of events unless we explicitly tag them.
    sendDefaultPii: false,
    integrations: [Sentry.browserTracingIntegration()],
  });
}

export { Sentry };
