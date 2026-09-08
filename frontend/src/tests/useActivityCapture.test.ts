/**
 * @jest-environment jsdom
 *
 * Regression tests for the 2026-08-18 "full transparency" additions to
 * useActivityCapture.ts: PrintScreen now also reaches the backend (not
 * just the client-only live counter), and a lost/restored connection is
 * reported once connectivity returns, carrying the true original loss
 * time and outage duration.
 */

const mockRecord = jest.fn();
const mockStart = jest.fn();
const mockStop = jest.fn();
jest.mock("@/lib/activityLogBatcher", () => ({
  ActivityLogBatcher: jest.fn().mockImplementation(() => ({
    record: mockRecord,
    start: mockStart,
    stop: mockStop,
  })),
}));

import { renderHook, act } from "@testing-library/react";
import { useActivityCapture } from "@/hooks/useActivityCapture";

beforeEach(() => {
  mockRecord.mockClear();
  mockStart.mockClear();
  mockStop.mockClear();
  window.localStorage.clear();
});

describe("useActivityCapture — screenshot_attempt", () => {
  it("sends a screenshot_attempt event to the backend on PrintScreen", () => {
    renderHook(() => useActivityCapture("session-1"));

    act(() => { document.dispatchEvent(new KeyboardEvent("keydown", { key: "PrintScreen" })); });

    expect(mockRecord).toHaveBeenCalledWith("screenshot_attempt");
  });

  it("does not record anything for an unrelated key", () => {
    renderHook(() => useActivityCapture("session-1"));

    act(() => { document.dispatchEvent(new KeyboardEvent("keydown", { key: "a" })); });

    expect(mockRecord).not.toHaveBeenCalledWith("screenshot_attempt");
  });
});

describe("useActivityCapture — connection_lost", () => {
  it("records connection_lost once back online, with the original loss time and duration", () => {
    jest.useFakeTimers().setSystemTime(new Date("2026-08-18T10:00:00.000Z"));
    renderHook(() => useActivityCapture("session-1"));

    act(() => { window.dispatchEvent(new Event("offline")); });
    jest.setSystemTime(new Date("2026-08-18T10:00:47.000Z")); // 47s later
    act(() => { window.dispatchEvent(new Event("online")); });

    expect(mockRecord).toHaveBeenCalledWith(
      "connection_lost",
      { duration_seconds: 47 },
      new Date("2026-08-18T10:00:00.000Z"),
    );
    jest.useRealTimers();
  });

  it("does not record connection_lost on 'online' without a preceding 'offline'", () => {
    renderHook(() => useActivityCapture("session-1"));

    act(() => { window.dispatchEvent(new Event("online")); });

    expect(mockRecord).not.toHaveBeenCalledWith("connection_lost", expect.anything(), expect.anything());
  });

  it("only reports once per outage — a second 'online' without a new 'offline' is a no-op", () => {
    jest.useFakeTimers().setSystemTime(new Date("2026-08-18T10:00:00.000Z"));
    renderHook(() => useActivityCapture("session-1"));

    act(() => { window.dispatchEvent(new Event("offline")); });
    jest.setSystemTime(new Date("2026-08-18T10:00:10.000Z"));
    act(() => { window.dispatchEvent(new Event("online")); });
    act(() => { window.dispatchEvent(new Event("online")); }); // spurious repeat

    const connectionLostCalls = mockRecord.mock.calls.filter(c => c[0] === "connection_lost");
    expect(connectionLostCalls).toHaveLength(1);
    jest.useRealTimers();
  });

  it("treats the page loading already offline as the start of an outage", () => {
    const originalOnLine = Object.getOwnPropertyDescriptor(window.navigator, "onLine");
    Object.defineProperty(window.navigator, "onLine", { value: false, configurable: true });
    jest.useFakeTimers().setSystemTime(new Date("2026-08-18T10:00:00.000Z"));

    renderHook(() => useActivityCapture("session-1"));
    jest.setSystemTime(new Date("2026-08-18T10:00:05.000Z"));
    act(() => { window.dispatchEvent(new Event("online")); });

    expect(mockRecord).toHaveBeenCalledWith(
      "connection_lost",
      { duration_seconds: 5 },
      new Date("2026-08-18T10:00:00.000Z"),
    );

    jest.useRealTimers();
    if (originalOnLine) Object.defineProperty(window.navigator, "onLine", originalOnLine);
  });
});

describe("useActivityCapture — notifyActiveQuestion / question_time_spent", () => {
  afterEach(() => jest.useRealTimers());

  it("records the previous question's foreground time when navigating to a new one", () => {
    jest.useFakeTimers().setSystemTime(new Date("2026-08-18T10:00:00.000Z"));
    const { result } = renderHook(() => useActivityCapture("session-1"));

    act(() => { result.current.notifyActiveQuestion(1); });
    jest.setSystemTime(new Date("2026-08-18T10:00:45.000Z")); // 45s on Q1
    act(() => { result.current.notifyActiveQuestion(2); });

    expect(mockRecord).toHaveBeenCalledWith("question_time_spent", { question_number: 1, seconds: 45 });
  });

  it("does not record a view under 1 second (avoids noise from rapid navigation)", () => {
    jest.useFakeTimers().setSystemTime(new Date("2026-08-18T10:00:00.000Z"));
    const { result } = renderHook(() => useActivityCapture("session-1"));

    act(() => { result.current.notifyActiveQuestion(1); });
    jest.setSystemTime(new Date("2026-08-18T10:00:00.400Z")); // 400ms
    act(() => { result.current.notifyActiveQuestion(2); });

    expect(mockRecord).not.toHaveBeenCalledWith("question_time_spent", expect.anything());
  });

  it("excludes time spent while the tab is hidden", () => {
    jest.useFakeTimers().setSystemTime(new Date("2026-08-18T10:00:00.000Z"));
    const visibilitySpy = jest.spyOn(document, "visibilityState", "get");
    const { result } = renderHook(() => useActivityCapture("session-1"));

    act(() => { result.current.notifyActiveQuestion(1); });
    jest.setSystemTime(new Date("2026-08-18T10:00:10.000Z")); // 10s visible
    visibilitySpy.mockReturnValue("hidden");
    act(() => { document.dispatchEvent(new Event("visibilitychange")); });
    jest.setSystemTime(new Date("2026-08-18T10:05:10.000Z")); // 5 minutes hidden — must not count
    visibilitySpy.mockReturnValue("visible");
    act(() => { document.dispatchEvent(new Event("visibilitychange")); });
    jest.setSystemTime(new Date("2026-08-18T10:05:20.000Z")); // +10s visible again
    act(() => { result.current.notifyActiveQuestion(2); });

    // 10s + 10s visible = 20s total, NOT 5min20s+ if the hidden window had counted.
    expect(mockRecord).toHaveBeenCalledWith("question_time_spent", { question_number: 1, seconds: 20 });
    visibilitySpy.mockRestore();
  });

  it("finalizes and flushes the last active question when the session ends", () => {
    jest.useFakeTimers().setSystemTime(new Date("2026-08-18T10:00:00.000Z"));
    const { result, rerender } = renderHook(
      ({ sessionId }: { sessionId: string | null }) => useActivityCapture(sessionId),
      { initialProps: { sessionId: "session-1" as string | null } },
    );

    act(() => { result.current.notifyActiveQuestion(3); });
    jest.setSystemTime(new Date("2026-08-18T10:00:30.000Z")); // 30s on Q3, no further navigation
    // Mirrors the real exam page: sessionId flips to null once the exam is
    // no longer IN_PROGRESS — there's no "next" navigation to trigger the
    // recording, so the hook's own cleanup must do it.
    act(() => { rerender({ sessionId: null }); });

    expect(mockRecord).toHaveBeenCalledWith("question_time_spent", { question_number: 3, seconds: 30 });
    expect(mockStop).toHaveBeenCalled();
  });

  it("records a distinct event per question across multiple navigations", () => {
    jest.useFakeTimers().setSystemTime(new Date("2026-08-18T10:00:00.000Z"));
    const { result } = renderHook(() => useActivityCapture("session-1"));

    act(() => { result.current.notifyActiveQuestion(1); });
    jest.setSystemTime(new Date("2026-08-18T10:00:10.000Z"));
    act(() => { result.current.notifyActiveQuestion(2); });
    jest.setSystemTime(new Date("2026-08-18T10:00:25.000Z"));
    act(() => { result.current.notifyActiveQuestion(1); }); // back to Q1

    const timeEvents = mockRecord.mock.calls.filter(c => c[0] === "question_time_spent");
    expect(timeEvents).toEqual([
      ["question_time_spent", { question_number: 1, seconds: 10 }],
      ["question_time_spent", { question_number: 2, seconds: 15 }],
    ]);
  });
});
