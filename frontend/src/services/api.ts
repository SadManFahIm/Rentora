import axios, {
  type AxiosInstance,
  type AxiosError,
  type InternalAxiosRequestConfig,
} from "axios";
import { toast } from "sonner";
import { env } from "../config/env";

// ============================================================
// API CLIENT — shared Axios instance, JWT handling + refresh
// ============================================================

export const ACCESS_TOKEN_KEY = "rentora_access";
export const REFRESH_TOKEN_KEY = "rentora_refresh";

export const getAccessToken = (): string | null =>
  localStorage.getItem(ACCESS_TOKEN_KEY);
export const getRefreshToken = (): string | null =>
  localStorage.getItem(REFRESH_TOKEN_KEY);

export const setTokens = (access: string, refresh?: string): void => {
  localStorage.setItem(ACCESS_TOKEN_KEY, access);
  if (refresh) localStorage.setItem(REFRESH_TOKEN_KEY, refresh);
};

export const clearTokens = (): void => {
  localStorage.removeItem(ACCESS_TOKEN_KEY);
  localStorage.removeItem(REFRESH_TOKEN_KEY);
};

export const isAuthenticated = (): boolean => getAccessToken() !== null;

export const api: AxiosInstance = axios.create({
  baseURL: env.API_BASE_URL,
  headers: { "Content-Type": "application/json" },
  timeout: 15000,
});

// ---- Request interceptor: attach the access token ----
api.interceptors.request.use(
  (config: InternalAxiosRequestConfig) => {
    const token = getAccessToken();
    if (token) {
      config.headers.set("Authorization", `Bearer ${token}`);
    }
    return config;
  },
  (error: AxiosError) => Promise.reject(error)
);

// ---- Response interceptor: refresh-on-401 + error toasts ----

/** Endpoints that must never trigger a refresh-retry (they *are* auth). */
const AUTH_PATHS = ["/auth/login/", "/auth/register/", "/auth/token/refresh/"];
const isAuthPath = (url?: string): boolean =>
  !!url && AUTH_PATHS.some((p) => url.includes(p));

const redirectToAuth = (): void => {
  clearTokens();
  if (window.location.pathname !== "/auth") {
    window.location.assign("/auth");
  }
};

// Single-flight refresh: while one refresh is in progress, queued requests
// await the same promise instead of each firing their own refresh call.
let refreshPromise: Promise<string> | null = null;

async function refreshAccessToken(): Promise<string> {
  const refresh = getRefreshToken();
  if (!refresh) throw new Error("No refresh token");

  // Bare axios call (no interceptors) to avoid a refresh→401→refresh loop.
  const { data } = await axios.post<{ access: string; refresh?: string }>(
    `${env.API_BASE_URL}/auth/token/refresh/`,
    { refresh },
    { headers: { "Content-Type": "application/json" } }
  );
  setTokens(data.access, data.refresh);
  return data.access;
}

interface RetriableConfig extends InternalAxiosRequestConfig {
  _retry?: boolean;
}

api.interceptors.response.use(
  (response) => response,
  async (error: AxiosError<{ errors?: string[]; message?: string }>) => {
    const status = error.response?.status;
    const original = error.config as RetriableConfig | undefined;

    // ---- 401 → try a token refresh once, then retry the request ----
    if (
      status === 401 &&
      original &&
      !original._retry &&
      !isAuthPath(original.url) &&
      getRefreshToken()
    ) {
      original._retry = true;
      try {
        refreshPromise = refreshPromise ?? refreshAccessToken();
        const newAccess = await refreshPromise;
        refreshPromise = null;
        original.headers.set("Authorization", `Bearer ${newAccess}`);
        return api(original);
      } catch (refreshError) {
        refreshPromise = null;
        redirectToAuth();
        return Promise.reject(refreshError);
      }
    }

    // ---- 401 with no way to recover → bounce to auth ----
    if (status === 401 && !isAuthPath(original?.url)) {
      redirectToAuth();
    } else if (status === 429) {
      toast.error("Too many requests — please slow down and try again shortly.");
    } else if (status && status >= 500) {
      const message =
        error.response?.data?.message ??
        error.response?.data?.errors?.[0] ??
        "Something went wrong on our end. Please try again.";
      toast.error(message);
    }

    return Promise.reject(error);
  }
);

export default api;
