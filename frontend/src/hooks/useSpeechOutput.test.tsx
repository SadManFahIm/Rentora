import { act, renderHook } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { useSpeechOutput } from "./useSpeechOutput";

class FakeUtterance {
  lang = "";
  voice: unknown = null;
  rate = 1;
  onend: (() => void) | null = null;
  onerror: (() => void) | null = null;
  constructor(public text: string) {}
}

let utterances: FakeUtterance[] = [];
interface VoiceLike {
  lang: string;
  name: string;
  default: boolean;
}
const speechSynthesisMock = {
  speak: vi.fn((u: FakeUtterance) => utterances.push(u)),
  cancel: vi.fn(),
  getVoices: vi.fn<() => VoiceLike[]>(() => []),
  speaking: false,
  paused: false,
  addEventListener: vi.fn(),
  removeEventListener: vi.fn(),
};

function installMock() {
  Object.defineProperty(window, "speechSynthesis", {
    configurable: true,
    value: speechSynthesisMock,
  });
  Object.defineProperty(window, "SpeechSynthesisUtterance", {
    configurable: true,
    value: FakeUtterance,
  });
}

function removeMock() {
  Object.defineProperty(window, "speechSynthesis", {
    configurable: true,
    value: undefined,
  });
  Object.defineProperty(window, "SpeechSynthesisUtterance", {
    configurable: true,
    value: undefined,
  });
}

describe("useSpeechOutput (Phase 15 — B3)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    removeMock();
    utterances = [];
  });

  it("reports unsupported when speechSynthesis is missing", () => {
    const { result } = renderHook(() => useSpeechOutput("bn-BD"));
    expect(result.current.supported).toBe(false);
    expect(result.current.status).toBe("idle");
  });

  it("speaks text with a Bangla voice when one is available", () => {
    installMock();
    speechSynthesisMock.getVoices.mockReturnValue([
      { lang: "en-US", name: "English", default: true },
      { lang: "bn-BD", name: "Bengali (Bangladesh)", default: false },
    ]);
    const { result } = renderHook(() => useSpeechOutput("bn-BD"));
    act(() => result.current.speak("ভাড়া কত?"));

    expect(speechSynthesisMock.cancel).toHaveBeenCalled();
    expect(speechSynthesisMock.speak).toHaveBeenCalledTimes(1);
    expect(utterances[0].lang).toBe("bn-BD");
    expect(result.current.status).toBe("speaking");
  });

  it("falls back to the browser default voice when no Bangla voice exists", () => {
    installMock();
    speechSynthesisMock.getVoices.mockReturnValue([
      { lang: "en-US", name: "English", default: true },
    ]);
    const { result } = renderHook(() => useSpeechOutput("bn-BD"));
    act(() => result.current.speak("How much is the rent?"));
    expect(utterances[0].lang).toBe("bn-BD");
    expect(utterances[0].voice).toBeNull();
  });

  it("returns to idle when the utterance finishes and stops on demand", () => {
    installMock();
    const { result } = renderHook(() => useSpeechOutput("en"));
    act(() => result.current.speak("Hello"));
    expect(result.current.status).toBe("speaking");

    act(() => utterances[0].onend?.());
    expect(result.current.status).toBe("idle");

    act(() => result.current.speak("Again"));
    act(() => result.current.stop());
    expect(speechSynthesisMock.cancel).toHaveBeenCalled();
    expect(result.current.status).toBe("idle");
  });
});
