import { act, renderHook } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { useVoiceSearch } from "./useVoiceSearch";

interface ResultEvent {
  results: ArrayLike<ArrayLike<{ transcript: string }>>;
}
interface ErrorEvent {
  error: string;
}

class FakeRecognition {
  lang = "";
  interimResults = false;
  maxAlternatives = 1;
  continuous = false;
  onresult: ((event: ResultEvent) => void) | null = null;
  onerror: ((event: ErrorEvent) => void) | null = null;
  onend: (() => void) | null = null;
  start = vi.fn();
  stop = vi.fn();
  abort = vi.fn();
}

let recognitionCtor: (new () => FakeRecognition) | null = null;
let created: FakeRecognition[] = [];

function installMock(): typeof FakeRecognition {
  const Ctor = vi.fn().mockImplementation(function (): FakeRecognition {
    const instance = new FakeRecognition();
    created.push(instance);
    return instance;
  }) as unknown as typeof FakeRecognition;
  recognitionCtor = Ctor;
  Object.defineProperty(window, "SpeechRecognition", {
    configurable: true,
    value: Ctor,
  });
  return Ctor;
}

function removeMock() {
  Object.defineProperty(window, "SpeechRecognition", {
    configurable: true,
    value: undefined,
  });
  Object.defineProperty(window, "webkitSpeechRecognition", {
    configurable: true,
    value: undefined,
  });
}

function lastInstance(): FakeRecognition {
  return created[created.length - 1];
}

describe("useVoiceSearch", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    removeMock();
    recognitionCtor = null;
    created = [];
  });

  it("reports unsupported when the Web Speech API is missing", () => {
    const { result } = renderHook(() => useVoiceSearch());
    expect(result.current.supported).toBe(false);
    expect(result.current.status).toBe("idle");
  });

  it("reports supported and flips to listening on start", () => {
    installMock();
    const { result } = renderHook(() => useVoiceSearch({ lang: "bn-BD" }));
    expect(result.current.supported).toBe(true);

    act(() => result.current.start());
    expect(recognitionCtor).toHaveBeenCalledTimes(1);
    const instance = lastInstance();
    expect(instance.lang).toBe("bn-BD");
    expect(result.current.status).toBe("listening");
    expect(instance.start).toHaveBeenCalled();
  });

  it("delivers the Bangla transcript through onTranscript", () => {
    installMock();
    const onTranscript = vi.fn();
    const { result } = renderHook(() => useVoiceSearch({ onTranscript }));

    act(() => result.current.start());
    act(() => {
      lastInstance().onresult?.({
        results: [[{ transcript: "উত্তরা ১০ হাজারের মধ্যে রুম" }]],
      });
    });

    expect(onTranscript).toHaveBeenCalledWith("উত্তরা ১০ হাজারের মধ্যে রুম");
    expect(result.current.status).toBe("processing");
  });

  it("reports denied on permission errors", () => {
    installMock();
    const { result } = renderHook(() => useVoiceSearch());

    act(() => result.current.start());
    act(() => {
      lastInstance().onerror?.({ error: "not-allowed" });
    });

    expect(result.current.status).toBe("denied");
  });

  it("stop aborts an active session and returns to idle", () => {
    installMock();
    const { result } = renderHook(() => useVoiceSearch());

    act(() => result.current.start());
    expect(result.current.status).toBe("listening");

    act(() => result.current.stop());
    expect(lastInstance().abort).toHaveBeenCalled();
    expect(result.current.status).toBe("idle");
  });
});
