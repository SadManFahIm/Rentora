import type { ApiResponse } from "./api";
import { setToken, clearToken, TOKEN_KEY, REFRESH_TOKEN_KEY } from "./api";
// import { api } from "./api"; // ← enable in Phase 3 for real HTTP calls
import type { User, LoginCredentials, RegisterPayload, AuthResponse } from "../types";

// ============================================================
// AUTH SERVICE
// Mock implementation — issues fake tokens and persists them so
// the Axios request interceptor has something to attach.
// ============================================================

const delay = (ms = 300) => new Promise((r) => setTimeout(r, ms));

const wrap = <T>(data: T): ApiResponse<T> => ({ data });

const fakeToken = (email: string): string =>
  `mock.${btoa(email)}.${Date.now()}`;

function persistSession(auth: AuthResponse): void {
  setToken(auth.token);
  localStorage.setItem(REFRESH_TOKEN_KEY, auth.refreshToken);
}

export const authService = {
  async login(credentials: LoginCredentials): Promise<ApiResponse<AuthResponse>> {
    await delay();
    const auth: AuthResponse = {
      user: { name: "User", email: credentials.email },
      token: fakeToken(credentials.email),
      refreshToken: fakeToken(`refresh:${credentials.email}`),
    };
    persistSession(auth);
    return wrap(auth);
    // Phase 3: return (await api.post<ApiResponse<AuthResponse>>("/auth/login", credentials)).data;
  },

  async register(payload: RegisterPayload): Promise<ApiResponse<AuthResponse>> {
    await delay();
    const auth: AuthResponse = {
      user: { name: payload.name, email: payload.email },
      token: fakeToken(payload.email),
      refreshToken: fakeToken(`refresh:${payload.email}`),
    };
    persistSession(auth);
    return wrap(auth);
    // Phase 3: return (await api.post<ApiResponse<AuthResponse>>("/auth/register", payload)).data;
  },

  async logout(): Promise<ApiResponse<null>> {
    await delay(100);
    clearToken();
    return wrap(null);
    // Phase 3: await api.post("/auth/logout"); clearToken(); ...
  },

  async refreshToken(): Promise<ApiResponse<AuthResponse>> {
    await delay(150);
    const email = "user@rentora.app";
    const auth: AuthResponse = {
      user: { name: "User", email },
      token: fakeToken(email),
      refreshToken: fakeToken(`refresh:${email}`),
    };
    persistSession(auth);
    return wrap(auth);
    // Phase 3: return (await api.post<ApiResponse<AuthResponse>>("/auth/refresh", { refreshToken: localStorage.getItem(REFRESH_TOKEN_KEY) })).data;
  },

  async googleOAuth(): Promise<ApiResponse<AuthResponse>> {
    await delay();
    const email = "google.user@gmail.com";
    const auth: AuthResponse = {
      user: { name: "Google User", email },
      token: fakeToken(email),
      refreshToken: fakeToken(`refresh:${email}`),
    };
    persistSession(auth);
    return wrap(auth);
    // Phase 3: redirect to `${API_BASE_URL}/auth/google` OAuth flow.
  },

  /** Read the persisted user, if any (mock — decodes nothing real). */
  getStoredUser(): User | null {
    return localStorage.getItem(TOKEN_KEY) ? { name: "User", email: "" } : null;
  },
};

export default authService;
