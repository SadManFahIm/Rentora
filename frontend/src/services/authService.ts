import { api, setTokens, clearTokens, getRefreshToken } from "./api";
import { mapUser, type ApiUser } from "./mappers";
import type { User, LoginCredentials, RegisterPayload, LoginResult } from "../types";

// ============================================================
// AUTH SERVICE — real dj-rest-auth / SimpleJWT endpoints
// ============================================================

interface AuthApiResponse {
  access: string;
  refresh: string;
  user: ApiUser;
}

/** Body returned by login when the account requires an email-OTP code. */
interface OtpPendingApiResponse {
  otp_required: true;
  challenge: string;
  destination_masked: string;
  expires_in: number;
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
  async login({ email, password }: LoginCredentials): Promise<LoginResult> {
    const loginField = email.includes("@") ? "email" : "username";
    const { data } = await api.post<AuthApiResponse | OtpPendingApiResponse>("/auth/login/", {
      [loginField]: email,
      password,
    });
    if ("otp_required" in data) {
      // 2FA account: do NOT store tokens yet — the user must first prove
      // the one-time code via authService.verifyOtp().
      return {
        otpRequired: true,
        challenge: data.challenge,
        destinationMasked: data.destination_masked,
        expiresIn: data.expires_in,
        user: mapUser(data.user),
      };
    }
    setTokens(data.access, data.refresh);
    return { user: mapUser(data.user), access: data.access, refresh: data.refresh };
  },

  /**
   * POST /auth/otp/verify/ — exchange (challenge, code) for JWTs.
   * Pass ``recoveryCode`` instead of ``code`` to use a backup code.
   */
  async verifyOtp(challenge: string, code: string, recoveryCode = ""): Promise<User> {
    const { data } = await api.post<AuthApiResponse>("/auth/otp/verify/", {
      challenge,
      ...(recoveryCode ? { recovery_code: recoveryCode } : { code }),
    });
    setTokens(data.access, data.refresh);
    return mapUser(data.user);
  },

  /** POST /auth/otp/resend/ — re-issue the one-time code (cooldown-guarded). */
  async resendOtp(challenge: string): Promise<void> {
    await api.post("/auth/otp/resend/", { challenge });
  },

  /**
   * POST /auth/otp/toggle/ — disable 2FA, or begin ENABLING it.
   * Enabling is two-step: this returns a pending email challenge; finish it
   * with confirmEnable2fa().
   */
  async toggle2fa(
    enable: boolean,
    password = ""
  ): Promise<{
    otpEnabled: boolean;
    pendingEnable?: boolean;
    challenge?: string;
    destinationMasked?: string;
  }> {
    const { data } = await api.post<{
      otp_enabled: boolean;
      pending_enable?: boolean;
      challenge?: string;
      destination_masked?: string;
    }>("/auth/otp/toggle/", { enable, password });
    return {
      otpEnabled: data.otp_enabled,
      pendingEnable: data.pending_enable,
      challenge: data.challenge,
      destinationMasked: data.destination_masked,
    };
  },

  /** POST /auth/otp/confirm-enable/ — verify the emailed code, get recovery codes. */
  async confirmEnable2fa(
    challenge: string,
    code: string
  ): Promise<{ otpEnabled: boolean; recoveryCodes: string[] }> {
    const { data } = await api.post<{ otp_enabled: boolean; recovery_codes: string[] }>(
      "/auth/otp/confirm-enable/",
      { challenge, code }
    );
    return { otpEnabled: data.otp_enabled, recoveryCodes: data.recovery_codes };
  },

  // ---- Passkeys (WebAuthn / FIDO2) ----

  /** POST /auth/passkey/register/begin/ → options for the browser ceremony. */
  async passkeyRegisterBegin(): Promise<Record<string, unknown>> {
    const { data } = await api.post("/auth/passkey/register/begin/");
    return data;
  },

  /** POST /auth/passkey/register/complete/ → store the new credential. */
  async passkeyRegisterComplete(
    response: Record<string, unknown>,
    name = ""
  ): Promise<{ verified: boolean; credentialId: string }> {
    const { data } = await api.post<{ verified: boolean; credential_id: string }>(
      "/auth/passkey/register/complete/",
      { response, name }
    );
    return { verified: data.verified, credentialId: data.credential_id };
  },

  /** POST /auth/passkey/login/begin/ → options + challenge_id. */
  async passkeyLoginBegin(): Promise<{ challenge_id: string } & Record<string, unknown>> {
    const { data } = await api.post("/auth/passkey/login/begin/");
    return data;
  },

  /** POST /auth/passkey/login/complete/ → verified → JWTs (or pending OTP). */
  async passkeyLoginComplete(
    challengeId: string,
    response: Record<string, unknown>
  ): Promise<LoginResult> {
    const { data } = await api.post<AuthApiResponse | OtpPendingApiResponse>(
      "/auth/passkey/login/complete/",
      { challenge_id: challengeId, response }
    );
    if ("otp_required" in data) {
      return {
        otpRequired: true,
        challenge: data.challenge,
        destinationMasked: data.destination_masked,
        expiresIn: data.expires_in,
        user: mapUser(data.user),
      };
    }
    setTokens(data.access, data.refresh);
    return { user: mapUser(data.user), access: data.access, refresh: data.refresh };
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
