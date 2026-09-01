import axios, { AxiosError, type AxiosResponse, type InternalAxiosRequestConfig } from "axios";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { api, clearTokens, setTokens, ACCESS_TOKEN_KEY, REFRESH_TOKEN_KEY } from "./api";

// A 401 that axios would deliver through the response interceptor.
function rejectWith401(config: InternalAxiosRequestConfig): never {
  const response: AxiosResponse = {
    status: 401,
    statusText: "Unauthorized",
    headers: {},
    config,
    data: { detail: "Invalid token." },
  };
  throw new AxiosError(
    "Request failed with status code 401",
    "ERR_BAD_REQUEST",
    config,
    null,
    response
  );
}

// Point the instance at a stub adapter so requests fail with 401 without a
// real server. (The request interceptor still runs, so a stored token gets
// attached — exactly what we want to exercise.)
const force401 = () => {
  api.defaults.adapter = async (config: InternalAxiosRequestConfig) => {
    rejectWith401(config);
  };
};

describe("api 401 handling — anonymous vs. session", () => {
  let assignSpy: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    localStorage.clear();
    assignSpy = vi.fn();
    vi.stubGlobal("window", {
      ...window,
      location: { ...window.location, assign: assignSpy, pathname: "/rooms" },
    });
    force401();
    vi.spyOn(axios, "post").mockRejectedValue(new Error("No network in tests"));
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
    delete api.defaults.adapter;
    clearTokens();
  });

  it("does NOT bounce to /auth for an anonymous visitor's 401 (no tokens)", async () => {
    await expect(api.get("/saved-searches/")).rejects.toThrow();
    expect(assignSpy).not.toHaveBeenCalled();
  });

  it("bounces to /auth when a stored session turns out invalid (401)", async () => {
    setTokens("access-token", "refresh-token");
    await expect(api.get("/saved-searches/")).rejects.toThrow();
    expect(assignSpy).toHaveBeenCalledWith("/auth");
    // Tokens are cleared so we don't loop.
    expect(localStorage.getItem(ACCESS_TOKEN_KEY)).toBeNull();
    expect(localStorage.getItem(REFRESH_TOKEN_KEY)).toBeNull();
  });

  it("does not bounce for 401s on auth endpoints themselves (login form)", async () => {
    setTokens("access-token", "refresh-token");
    await expect(api.post("/auth/login/")).rejects.toThrow();
    expect(assignSpy).not.toHaveBeenCalled();
  });
});
