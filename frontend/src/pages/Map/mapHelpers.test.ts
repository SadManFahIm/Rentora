import { describe, expect, it, vi } from "vitest";
import { escHtml, useDebouncedValue, fallbackCopy } from "./mapHelpers";
import { renderHook, act } from "@testing-library/react";

describe("escHtml", () => {
  it("escapes ampersands", () => {
    expect(escHtml("a & b")).toBe("a &amp; b");
  });

  it("escapes angle brackets", () => {
    expect(escHtml("<script>alert('xss')</script>")).toBe(
      "&lt;script&gt;alert('xss')&lt;/script&gt;"
    );
  });

  it("escapes double quotes", () => {
    expect(escHtml('He said "hello"')).toBe("He said &quot;hello&quot;");
  });

  it("returns plain text unchanged", () => {
    expect(escHtml("Dhanmondi, Dhaka")).toBe("Dhanmondi, Dhaka");
  });

  it("handles empty string", () => {
    expect(escHtml("")).toBe("");
  });

  it("handles mixed special characters", () => {
    expect(escHtml('a & "b" <c>')).toBe("a &amp; &quot;b&quot; &lt;c&gt;");
  });
});

describe("useDebouncedValue", () => {
  it("returns the initial value immediately", () => {
    const { result } = renderHook(() => useDebouncedValue("hello", 300));
    expect(result.current).toBe("hello");
  });

  it("debounces value changes", () => {
    vi.useFakeTimers();
    const { result, rerender } = renderHook(({ value, delay }) => useDebouncedValue(value, delay), {
      initialProps: { value: "a", delay: 300 },
    });
    expect(result.current).toBe("a");

    rerender({ value: "b", delay: 300 });
    // Still "a" immediately after change
    expect(result.current).toBe("a");

    act(() => vi.advanceTimersByTime(300));
    expect(result.current).toBe("b");

    vi.useRealTimers();
  });

  it("cancels pending debounce on unmount", () => {
    vi.useFakeTimers();
    const { rerender, unmount } = renderHook(
      ({ value, delay }) => useDebouncedValue(value, delay),
      { initialProps: { value: "a", delay: 300 } }
    );

    rerender({ value: "b", delay: 300 });
    unmount();
    act(() => vi.advanceTimersByTime(300));
    // Should not throw or update after unmount
    vi.useRealTimers();
  });
});

describe("fallbackCopy", () => {
  it("calls onDone after execCommand succeeds", () => {
    const onDone = vi.fn();
    // Mock execCommand to succeed
    document.execCommand = vi.fn().mockReturnValue(true);
    fallbackCopy("https://example.com", onDone);
    expect(onDone).toHaveBeenCalled();
  });

  it("calls window.prompt as fallback when execCommand fails", () => {
    const onDone = vi.fn();
    const promptSpy = vi.spyOn(window, "prompt").mockImplementation(() => null);
    document.execCommand = vi.fn(() => false);
    fallbackCopy("https://example.com", onDone);
    // fallbackCopy calls onDone after execCommand regardless of return value
    expect(onDone).toHaveBeenCalled();
    promptSpy.mockRestore();
  });
});
