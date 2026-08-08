import { describe, expect, it } from "vitest";
import { AxiosError } from "axios";
import { getApiErrorMessage } from "./errors";

function axiosErrorWith(body: unknown): AxiosError {
  const err = new AxiosError("Request failed with status code 400");
  err.response = { data: body } as AxiosError["response"];
  return err;
}

describe("getApiErrorMessage", () => {
  it("prefers the envelope message", () => {
    const err = axiosErrorWith({
      success: false,
      message: "A user is already registered with this email address.",
      errors: ["email: something else"],
    });
    expect(getApiErrorMessage(err, "fallback")).toBe(
      "A user is already registered with this email address."
    );
  });

  it("falls back to the first entry of the errors array", () => {
    const err = axiosErrorWith({
      success: false,
      errors: ["email: This field is required."],
    });
    expect(getApiErrorMessage(err, "fallback")).toBe("email: This field is required.");
  });

  it("uses the axios message when the body has no usable fields", () => {
    const err = axiosErrorWith({ success: false });
    expect(getApiErrorMessage(err, "fallback")).toBe("Request failed with status code 400");
  });

  it("handles a plain Error", () => {
    expect(getApiErrorMessage(new Error("boom"), "fallback")).toBe("boom");
  });

  it("returns the fallback for unknown values", () => {
    expect(getApiErrorMessage(undefined, "fallback")).toBe("fallback");
    expect(getApiErrorMessage("just a string", "fallback")).toBe("fallback");
  });

  it("returns the default fallback when none is given", () => {
    expect(getApiErrorMessage(undefined)).toBe("Something went wrong. Please try again.");
  });
});
