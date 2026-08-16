import { env } from "../config/env";
import { api } from "./api";
import type { AnalyticsSummary } from "../types";

/**
 * First-party product analytics (Tier 2).
 *
 * `track` is fire-and-forget by design: a failed analytics POST must never
 * block, toast, or retry a user interaction — it is dropped silently and
 * the page keeps working. Anonymous visitors are attributed by a per-tab
 * session id; authenticated requests (via the shared `api` instance) let
 * the backend attribute events to the user for user-scoped funnels.
 *
 * Never pass PII here — the backend bounds every payload.
 */

const EVENTS_ENDPOINT = `${env.API_BASE_URL}/api/v1/analytics/events/`;
const SESSION_KEY = "rentora_analytics_session";

function getSessionId(): string {
  let id = sessionStorage.getItem(SESSION_KEY);
  if (!id) {
    id = crypto.randomUUID();
    sessionStorage.setItem(SESSION_KEY, id);
  }
  return id;
}

export function track(event: string, properties?: Record<string, unknown>, path?: string): void {
  const enabled = import.meta.env.VITE_ANALYTICS_ENABLED !== "false";
  if (!enabled || typeof navigator === "undefined") return;

  const payload = {
    event,
    properties: properties ?? {},
    session_id: getSessionId(),
    path: path ?? window.location.pathname,
  };

  fetch(EVENTS_ENDPOINT, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
    keepalive: true, // survives navigation
  }).catch(() => {
    /* analytics must never break the app */
  });
}

export async function fetchAnalyticsSummary(days = 30): Promise<AnalyticsSummary> {
  const { data } = await api.get<AnalyticsSummary>("/api/v1/analytics/summary/", {
    params: { days },
  });
  return data;
}
