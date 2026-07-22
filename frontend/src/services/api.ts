import axios, {
  type AxiosInstance,
  type AxiosError,
  type InternalAxiosRequestConfig,
} from "axios";
import { toast } from "sonner";
import { env } from "../config/env";

// ============================================================
// API CLIENT — shared Axios instance + typed response wrapper
// ============================================================

/** Standard envelope every endpoint responds with. */
export interface ApiResponse<T> {
  data: T;
  meta?: Record<string, unknown>;
  errors?: string[];
}

export const TOKEN_KEY = "rentora_token";
export const REFRESH_TOKEN_KEY = "rentora_refresh_token";

export const getToken = (): string | null => localStorage.getItem(TOKEN_KEY);
export const setToken = (token: string): void =>
  localStorage.setItem(TOKEN_KEY, token);
export const clearToken = (): void => {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(REFRESH_TOKEN_KEY);
};

export const api: AxiosInstance = axios.create({
  baseURL: env.API_BASE_URL,
  headers: { "Content-Type": "application/json" },
  timeout: 15000,
});

// ---- Request interceptor: attach JWT ----
api.interceptors.request.use(
  (config: InternalAxiosRequestConfig) => {
    const token = getToken();
    if (token) {
      config.headers.set("Authorization", `Bearer ${token}`);
    }
    return config;
  },
  (error: AxiosError) => Promise.reject(error)
);

// ---- Response interceptor: global error handling ----
api.interceptors.response.use(
  (response) => response,
  (error: AxiosError<ApiResponse<unknown>>) => {
    const status = error.response?.status;

    if (status === 401) {
      // Session expired / not authenticated → drop token and bounce to auth.
      clearToken();
      if (window.location.pathname !== "/auth") {
        window.location.href = "/auth";
      }
    } else if (status && status >= 500) {
      const message =
        error.response?.data?.errors?.[0] ??
        "Something went wrong on our end. Please try again.";
      toast.error(message);
    }

    return Promise.reject(error);
  }
);

export default api;
