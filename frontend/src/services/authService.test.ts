import { describe, expect, it, vi, beforeEach } from "vitest";
import { AxiosError } from "axios";
import { getApiErrorMessage } from "./errors";

// Mock the shared API client + token helpers so tests never touch the network.
vi.mock("./api", () => ({
  api: {
    get: vi.fn(),
    post: vi.fn(),
    patch: vi.fn(),
  },
  setTokens: vi.fn(),
  clearTokens: vi.fn(),
  getRefreshToken: vi.fn(() => "refresh-123"),
}));

import { api, setTokens, clearTokens, getRefreshToken } from "./api";
import { authService } from "./authService";

const apiUser = {
  pk: 3,
  username: "rahim.hossain",
  email: "rahim.hossain@rentora.com",
  first_name: "Rahim",
  last_name: "Hossain",
  role: "landlord",
  avatar: null,
  nid_verified: true,
};

describe("authService.login", () => {
  beforeEach(() => vi.clearAllMocks());

  it("sends the value as email when it contains an @", async () => {
    (api.post as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      data: { access: "a", refresh: "r", user: apiUser },
    });
    const result = await authService.login({
      email: "rahim.hossain@rentora.com",
      password: "demo12345",
    });
    expect(api.post).toHaveBeenCalledWith("/auth/login/", {
      email: "rahim.hossain@rentora.com",
      password: "demo12345",
    });
    expect(result).not.toHaveProperty("otpRequired");
    if (!("otpRequired" in result)) {
      expect(result.user.name).toBe("Rahim Hossain");
    }
  });

  it("sends the value as username when it has no @ (demo usernames)", async () => {
    (api.post as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      data: { access: "a", refresh: "r", user: apiUser },
    });
    await authService.login({ email: "rahim.hossain", password: "demo12345" });
    expect(api.post).toHaveBeenCalledWith("/auth/login/", {
      username: "rahim.hossain",
      password: "demo12345",
    });
  });

  it("persists the returned tokens", async () => {
    (api.post as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      data: { access: "access-token", refresh: "refresh-token", user: apiUser },
    });
    const result = await authService.login({
      email: "rahim.hossain@rentora.com",
      password: "demo12345",
    });
    expect(setTokens).toHaveBeenCalledWith("access-token", "refresh-token");
    expect("otpRequired" in result && result.otpRequired).toBe(false);
  });

  it("returns a pending OTP challenge and stores no tokens for 2FA accounts", async () => {
    (api.post as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      data: {
        otp_required: true,
        challenge: "ch-abc",
        destination_masked: "r***@rentora.com",
        expires_in: 600,
        user: apiUser,
      },
    });
    const result = await authService.login({
      email: "rahim.hossain@rentora.com",
      password: "demo12345",
    });
    expect(setTokens).not.toHaveBeenCalled();
    expect(result).toMatchObject({
      otpRequired: true,
      challenge: "ch-abc",
      destinationMasked: "r***@rentora.com",
      expiresIn: 600,
    });
  });
});

describe("authService OTP two-factor", () => {
  beforeEach(() => vi.clearAllMocks());

  it("verifyOtp exchanges the code for tokens and returns the user", async () => {
    (api.post as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      data: { access: "a", refresh: "r", user: apiUser },
    });
    const user = await authService.verifyOtp("ch-abc", "123456");
    expect(api.post).toHaveBeenCalledWith("/auth/otp/verify/", {
      challenge: "ch-abc",
      code: "123456",
    });
    expect(setTokens).toHaveBeenCalledWith("a", "r");
    expect(user.username).toBe("rahim.hossain");
  });

  it("resendOtp posts the challenge", async () => {
    (api.post as ReturnType<typeof vi.fn>).mockResolvedValueOnce({ data: {} });
    await authService.resendOtp("ch-abc");
    expect(api.post).toHaveBeenCalledWith("/auth/otp/resend/", { challenge: "ch-abc" });
  });

  it("toggle2fa enables with the current password", async () => {
    (api.post as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      data: { otp_enabled: true },
    });
    const result = await authService.toggle2fa(true, "demo12345");
    expect(api.post).toHaveBeenCalledWith("/auth/otp/toggle/", {
      enable: true,
      password: "demo12345",
    });
    expect(result.otpEnabled).toBe(true);
  });

  it("toggle2fa disables without a password", async () => {
    (api.post as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      data: { otp_enabled: false },
    });
    await authService.toggle2fa(false);
    expect(api.post).toHaveBeenCalledWith("/auth/otp/toggle/", {
      enable: false,
      password: "",
    });
  });
});

describe("authService.register", () => {
  it("sends the snake_case registration payload", async () => {
    (api.post as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      data: { access: "a", refresh: "r", user: apiUser },
    });
    await authService.register({
      name: "Rahim Hossain",
      email: "rahim.hossain@rentora.com",
      password: "demo12345",
    });
    expect(api.post).toHaveBeenCalledWith("/auth/register/", {
      username: "rahim.hossain@rentora.com",
      email: "rahim.hossain@rentora.com",
      password1: "demo12345",
      password2: "demo12345",
      name: "Rahim Hossain",
    });
  });

  it("rejects when the backend reports a duplicate email (400)", async () => {
    const err = new AxiosError("Request failed with status code 400");
    err.response = {
      status: 400,
      data: {
        success: false,
        message: "A user is already registered with this email address.",
        errors: [],
      },
    } as AxiosError["response"];
    (api.post as ReturnType<typeof vi.fn>).mockRejectedValueOnce(err);

    await expect(
      authService.register({
        name: "Rahim Hossain",
        email: "rahim.hossain@rentora.com",
        password: "demo12345",
      })
    ).rejects.toBe(err);

    // And the error surfaces a readable message for the toast/UI layer.
    expect(getApiErrorMessage(err)).toBe("A user is already registered with this email address.");
  });
});

describe("authService.logout", () => {
  it("posts the refresh token then clears local tokens", async () => {
    (api.post as ReturnType<typeof vi.fn>).mockResolvedValueOnce({ data: {} });
    await authService.logout();
    expect(getRefreshToken).toHaveBeenCalled();
    expect(api.post).toHaveBeenCalledWith("/auth/logout/", { refresh: "refresh-123" });
    expect(clearTokens).toHaveBeenCalled();
  });

  it("still clears local tokens when the server call fails", async () => {
    (api.post as ReturnType<typeof vi.fn>).mockRejectedValueOnce(new Error("offline"));
    await expect(authService.logout()).resolves.toBeUndefined();
    expect(clearTokens).toHaveBeenCalled();
  });
});

describe("authService profile", () => {
  beforeEach(() => vi.clearAllMocks());

  it("getProfile maps the user", async () => {
    (api.get as ReturnType<typeof vi.fn>).mockResolvedValueOnce({ data: apiUser });
    const user = await authService.getProfile();
    expect(api.get).toHaveBeenCalledWith("/auth/user/");
    expect(user.username).toBe("rahim.hossain");
  });

  it("updateProfile patches and maps the user", async () => {
    (api.patch as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      data: { ...apiUser, first_name: "Rahim2" },
    });
    const user = await authService.updateProfile({ phone: "01712345678" });
    expect(api.patch).toHaveBeenCalledWith("/auth/user/", { phone: "01712345678" });
    expect(user.firstName).toBe("Rahim2");
  });
});
