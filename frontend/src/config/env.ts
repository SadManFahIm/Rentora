// ============================================================
// ENVIRONMENT CONFIG — typed access to Vite env variables
// ============================================================

interface AppEnv {
  API_BASE_URL: string;
  /** Origin (scheme + host + port) the WebSocket endpoints live under, e.g. "ws://localhost:8000". */
  WS_BASE_URL: string;
  /** Sentry DSN — empty when error tracking is not configured. */
  SENTRY_DSN: string;
}

/** Derive the ws(s):// origin from the REST API base URL, e.g.
 * "http://localhost:8000/api/v1" -> "ws://localhost:8000". */
function deriveWsBaseUrl(apiBaseUrl: string): string {
  try {
    const url = new URL(apiBaseUrl);
    url.protocol = url.protocol === "https:" ? "wss:" : "ws:";
    url.pathname = "";
    url.search = "";
    url.hash = "";
    return url.toString().replace(/\/$/, "");
  } catch {
    return "ws://localhost:8000";
  }
}

const apiBaseUrl: string = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000/api/v1";

export const env: AppEnv = {
  API_BASE_URL: apiBaseUrl,
  WS_BASE_URL: import.meta.env.VITE_WS_BASE_URL ?? deriveWsBaseUrl(apiBaseUrl),
  SENTRY_DSN: import.meta.env.VITE_SENTRY_DSN ?? "",
};

export default env;
