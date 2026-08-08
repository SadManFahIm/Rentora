import { api, setTokens, clearTokens, getRefreshToken } from "./api";
import { mapUser, type ApiUser } from "./mappers";
import type { User, LoginCredentials, RegisterPayload } from "../types";

// ============================================================
// AUTH SERVICE — real dj-rest-auth / SimpleJWT endpoints
// ============================================================

interface AuthApiResponse {
  access: string;
  refresh: string;
  user: ApiUser;
}

/** Derive a username from the email local-part (allauth requires username). */
const usernameFromEmail = (email: string): string => email.trim();

export const authService = {
  /** POST /auth/login/ → persist tokens, return the mapped user.
   *
   * The backend login accepts either an email address or a username. Send
   * whichever the user typed: an "@"-containing value is an email, anything
   * else (e.g. the demo usernames like `rahim.hossain`) is a username.
   */
  async login({ email, password }: LoginCredentials): Promise<User> {
    const loginField = email.includes("@") ? "email" : "username";
    const { data } = await api.post<AuthApiResponse>("/auth/login/", {
      [loginField]: email,
      password,
    });
    setTokens(data.access, data.refresh);
    return mapUser(data.user);
  },

  /** POST /auth/register/ → persist tokens, return the mapped user. */
  async register({ name, email, password }: RegisterPayload): Promise<User> {
    const { data } = await api.post<AuthApiResponse>("/auth/register/", {
      username: usernameFromEmail(email),
      email,
      password1: password,
      password2: password,
      name,
    });
    setTokens(data.access, data.refresh);
    return mapUser(data.user);
  },

  /** POST /auth/logout/ (best-effort) then clear local tokens. */
  async logout(): Promise<void> {
    const refresh = getRefreshToken();
    try {
      await api.post("/auth/logout/", refresh ? { refresh } : {});
    } catch {
      // Even if the server call fails (expired token, offline), we still
      // want the client fully signed out.
    } finally {
      clearTokens();
    }
  },

  /** GET /auth/user/ → the current authenticated user. */
  async getProfile(): Promise<User> {
    const { data } = await api.get<ApiUser>("/auth/user/");
    return mapUser(data);
  },

  /** PATCH /auth/user/ → update and return the current user. */
  async updateProfile(payload: Partial<ApiUser>): Promise<User> {
    const { data } = await api.patch<ApiUser>("/auth/user/", payload);
    return mapUser(data);
  },
};

export default authService;
