/**
 * @jest-environment jsdom
 *
 * Regression tests for src/hooks/useEssayActivityCapture.ts (Task 4.3).
 * Mirrors useActivityCapture.test.ts's own coverage, scoped to what this
 * hook actually keeps from that reference precedent (fullscreen-lockdown/
 * tab-switch/copy/contextmenu/screenshot capture, and localStorage-backed
 * violation counts) — it deliberately does not carry over
 * connection_lost or question_time_spent/notifyActiveQuestion, so there
 * are no equivalent tests for those here (see the hook's own docstring for
 * why). Paste is essay-service's own addition (reported as "paste_attempt",
 * not the original's generic "paste") and gets its own coverage below.
 */

const mockRecord = jest.fn();
const mockStart = jest.fn();
const mockStop = jest.fn();
jest.mock("@/lib/essayMalpracticeBatcher", () => ({
  EssayMalpracticeBatcher: jest.fn().mockImplementation(() => ({
    record: mockRecord,
    start: mockStart,
    stop: mockStop,
  })),
}));

import { renderHook, act } from "@testing-library/react";
import { useEssayActivityCapture, clearEssayViolationCounts } from "@/hooks/useEssayActivityCapture";

const ATTEMPT_ID = "attempt-1";

beforeEach(() => {
  mockRecord.mockClear();
  mockStart.mockClear();
  mockStop.mockClear();
  window.localStorage.clear();
});

describe("useEssayActivityCapture — tab_switch", () => {
  it("records tab_switch and increments the persisted count when the tab is hidden", () => {
    const visibilitySpy = jest.spyOn(document, "visibilityState", "get").mockReturnValue("hidden");
    const { result } = renderHook(() => useEssayActivityCapture(ATTEMPT_ID));

    act(() => { document.dispatchEvent(new Event("visibilitychange")); });

    expect(mockRecord).toHaveBeenCalledWith("tab_switch");
    expect(result.current.tabSwitchCount).toBe(1);
    visibilitySpy.mockRestore();
  });

  it("does not record tab_switch when visibility becomes visible", () => {
    const visibilitySpy = jest.spyOn(document, "visibilityState", "get").mockReturnValue("visible");
    renderHook(() => useEssayActivityCapture(ATTEMPT_ID));

    act(() => { document.dispatchEvent(new Event("visibilitychange")); });

    expect(mockRecord).not.toHaveBeenCalledWith("tab_switch");
    visibilitySpy.mockRestore();
  });

  it("persists the count across a remount for the same attemptId (survives a tab close/reopen)", () => {
    const visibilitySpy = jest.spyOn(document, "visibilityState", "get").mockReturnValue("hidden");
    const first = renderHook(() => useEssayActivityCapture(ATTEMPT_ID));
    act(() => { document.dispatchEvent(new Event("visibilitychange")); });
    first.unmount();

    const second = renderHook(() => useEssayActivityCapture(ATTEMPT_ID));
    expect(second.result.current.tabSwitchCount).toBe(1);
    visibilitySpy.mockRestore();
  });

  it("keeps counts independent between different attempt ids", () => {
    const visibilitySpy = jest.spyOn(document, "visibilityState", "get").mockReturnValue("hidden");
    renderHook(() => useEssayActivityCapture("attempt-A"));
    act(() => { document.dispatchEvent(new Event("visibilitychange")); });

    const { result } = renderHook(() => useEssayActivityCapture("attempt-B"));
    expect(result.current.tabSwitchCount).toBe(0);
    visibilitySpy.mockRestore();
  });
});

describe("useEssayActivityCapture — fullscreen_exit", () => {
  it("records fullscreen_exit and increments the persisted count on exiting fullscreen", () => {
    const { result } = renderHook(() => useEssayActivityCapture(ATTEMPT_ID));

    act(() => { document.dispatchEvent(new Event("fullscreenchange")); }); // document.fullscreenElement is null in jsdom -> exited

    expect(mockRecord).toHaveBeenCalledWith("fullscreen_exit");
    expect(result.current.fullscreenExitCount).toBe(1);
  });

  it("reflects entering fullscreen via isFullscreen without recording an exit", () => {
    const original = Object.getOwnPropertyDescriptor(Document.prototype, "fullscreenElement");
    Object.defineProperty(document, "fullscreenElement", { value: document.body, configurable: true });
    const { result } = renderHook(() => useEssayActivityCapture(ATTEMPT_ID));

    act(() => { document.dispatchEvent(new Event("fullscreenchange")); });

    expect(result.current.isFullscreen).toBe(true);
    expect(mockRecord).not.toHaveBeenCalledWith("fullscreen_exit");
    if (original) Object.defineProperty(document, "fullscreenElement", original);
    else delete (document as any).fullscreenElement;
  });
});

describe("useEssayActivityCapture — paste_attempt (essay-service's own addition)", () => {
  it("blocks paste, records paste_attempt (not the generic 'paste'), and increments pasteAttempts", () => {
    const { result } = renderHook(() => useEssayActivityCapture(ATTEMPT_ID));
    const evt = new Event("paste", { cancelable: true });

    act(() => { document.dispatchEvent(evt); });

    expect(evt.defaultPrevented).toBe(true);
    expect(mockRecord).toHaveBeenCalledWith("paste_attempt");
    expect(mockRecord).not.toHaveBeenCalledWith("paste");
    expect(result.current.pasteAttempts).toBe(1);
  });

  it("does not persist pasteAttempts across a remount (in-memory only, unlike tab_switch/fullscreen_exit)", () => {
    const first = renderHook(() => useEssayActivityCapture(ATTEMPT_ID));
    act(() => { document.dispatchEvent(new Event("paste", { cancelable: true })); });
    expect(first.result.current.pasteAttempts).toBe(1);
    first.unmount();

    const second = renderHook(() => useEssayActivityCapture(ATTEMPT_ID));
    expect(second.result.current.pasteAttempts).toBe(0);
  });
});

describe("useEssayActivityCapture — copy / contextmenu / screenshot_attempt", () => {
  it("blocks copy and records it", () => {
    renderHook(() => useEssayActivityCapture(ATTEMPT_ID));
    const evt = new Event("copy", { cancelable: true });

    act(() => { document.dispatchEvent(evt); });

    expect(evt.defaultPrevented).toBe(true);
    expect(mockRecord).toHaveBeenCalledWith("copy");
  });

  it("records contextmenu (right-click) without blocking it", () => {
    renderHook(() => useEssayActivityCapture(ATTEMPT_ID));

    act(() => { document.dispatchEvent(new Event("contextmenu")); });

    expect(mockRecord).toHaveBeenCalledWith("contextmenu");
  });

  it("records screenshot_attempt on PrintScreen", () => {
    renderHook(() => useEssayActivityCapture(ATTEMPT_ID));

    act(() => { document.dispatchEvent(new KeyboardEvent("keydown", { key: "PrintScreen" })); });

    expect(mockRecord).toHaveBeenCalledWith("screenshot_attempt");
  });

  it("does not record anything for an unrelated key", () => {
    renderHook(() => useEssayActivityCapture(ATTEMPT_ID));

    act(() => { document.dispatchEvent(new KeyboardEvent("keydown", { key: "a" })); });

    expect(mockRecord).not.toHaveBeenCalledWith("screenshot_attempt");
  });
});

describe("useEssayActivityCapture — cross-tab sync and cleanup", () => {
  it("picks up a count bumped in another tab via the storage event", () => {
    const { result } = renderHook(() => useEssayActivityCapture(ATTEMPT_ID));
    expect(result.current.tabSwitchCount).toBe(0);

    const key = `aptlogic_essay_violation_count_tab_switch_${ATTEMPT_ID}`;
    window.localStorage.setItem(key, "3");
    act(() => {
      window.dispatchEvent(new StorageEvent("storage", { key, newValue: "3" }));
    });

    expect(result.current.tabSwitchCount).toBe(3);
  });

  it("does not clear persisted counts on unmount (ordinary navigation away, not a real submit)", () => {
    const visibilitySpy = jest.spyOn(document, "visibilityState", "get").mockReturnValue("hidden");
    const { unmount } = renderHook(() => useEssayActivityCapture(ATTEMPT_ID));
    act(() => { document.dispatchEvent(new Event("visibilitychange")); });
    unmount();

    const key = `aptlogic_essay_violation_count_tab_switch_${ATTEMPT_ID}`;
    expect(window.localStorage.getItem(key)).toBe("1");
    visibilitySpy.mockRestore();
  });

  it("stop()s the batcher on unmount", () => {
    const { unmount } = renderHook(() => useEssayActivityCapture(ATTEMPT_ID));
    unmount();
    expect(mockStop).toHaveBeenCalled();
  });
});

describe("clearEssayViolationCounts", () => {
  it("removes both tab_switch and fullscreen_exit counts for the given attempt", () => {
    window.localStorage.setItem(`aptlogic_essay_violation_count_tab_switch_${ATTEMPT_ID}`, "4");
    window.localStorage.setItem(`aptlogic_essay_violation_count_fullscreen_exit_${ATTEMPT_ID}`, "2");

    clearEssayViolationCounts(ATTEMPT_ID);

    expect(window.localStorage.getItem(`aptlogic_essay_violation_count_tab_switch_${ATTEMPT_ID}`)).toBeNull();
    expect(window.localStorage.getItem(`aptlogic_essay_violation_count_fullscreen_exit_${ATTEMPT_ID}`)).toBeNull();
  });

  it("does not touch a different attempt's counts", () => {
    window.localStorage.setItem(`aptlogic_essay_violation_count_tab_switch_other-attempt`, "5");
    clearEssayViolationCounts(ATTEMPT_ID);
    expect(window.localStorage.getItem(`aptlogic_essay_violation_count_tab_switch_other-attempt`)).toBe("5");
  });
});
