/**
 * Regression tests for src/lib/activityLogBatcher.ts (Task 6.1).
 *
 * Why these tests exist:
 *   The batcher must never fire one HTTP call per captured event — it
 *   buffers and sends in batches, both on a timer and when the buffer
 *   fills. These tests confirm the buffering/flush-triggering logic
 *   directly, without needing a real browser event or a live server.
 */

jest.useFakeTimers();

const mockPost = jest.fn().mockResolvedValue({ data: { success: true } });
jest.mock("../lib/api", () => ({
  __esModule: true,
  default: { post: (...args: unknown[]) => mockPost(...args) },
}));

import { ActivityLogBatcher } from "../lib/activityLogBatcher";

beforeEach(() => {
  mockPost.mockClear();
  mockPost.mockResolvedValue({ data: { success: true } });
});

afterEach(() => {
  jest.clearAllTimers();
});

describe("ActivityLogBatcher", () => {
  it("does not call the API for a single recorded event before the timer fires", () => {
    const batcher = new ActivityLogBatcher("session-1");
    batcher.start();
    batcher.record("tab_switch");

    expect(mockPost).not.toHaveBeenCalled();
    batcher.stop();
  });

  it("flushes on the periodic timer with all buffered events in one call", async () => {
    const batcher = new ActivityLogBatcher("session-1");
    batcher.start();
    batcher.record("tab_switch");
    batcher.record("window_blur");
    batcher.record("copy");

    jest.advanceTimersByTime(10000);
    await Promise.resolve();

    expect(mockPost).toHaveBeenCalledTimes(1);
    const [url, body] = mockPost.mock.calls[0];
    expect(url).toBe("/assessments/student/sessions/session-1/activity-logs/");
    expect(body.events).toHaveLength(3);
    expect(body.events.map((e: { event_type: string }) => e.event_type)).toEqual([
      "tab_switch", "window_blur", "copy",
    ]);
    batcher.stop();
  });

  it("force-flushes once the buffer reaches 20 events, without waiting for the timer", () => {
    const batcher = new ActivityLogBatcher("session-1");
    batcher.start();
    for (let i = 0; i < 20; i++) batcher.record("contextmenu");

    expect(mockPost).toHaveBeenCalledTimes(1);
    expect(mockPost.mock.calls[0][1].events).toHaveLength(20);
    batcher.stop();
  });

  it("does not flush an empty buffer on the timer tick", async () => {
    const batcher = new ActivityLogBatcher("session-1");
    batcher.start();
    jest.advanceTimersByTime(10000);
    await Promise.resolve();
    expect(mockPost).not.toHaveBeenCalled();
    batcher.stop();
  });

  it("includes optional metadata when provided", async () => {
    const batcher = new ActivityLogBatcher("session-1");
    batcher.start();
    batcher.record("paste", { length: 42 });
    jest.advanceTimersByTime(10000);
    await Promise.resolve();

    expect(mockPost.mock.calls[0][1].events[0].metadata).toEqual({ length: 42 });
    batcher.stop();
  });

  it("stop() flushes any remaining buffered events immediately", async () => {
    const batcher = new ActivityLogBatcher("session-1");
    batcher.start();
    batcher.record("fullscreen_exit");
    batcher.stop();
    await Promise.resolve();

    expect(mockPost).toHaveBeenCalledTimes(1);
    expect(mockPost.mock.calls[0][1].events).toHaveLength(1);
  });

  it("swallows a failed flush without throwing (best-effort audit trail)", async () => {
    mockPost.mockRejectedValueOnce(new Error("network error"));
    const batcher = new ActivityLogBatcher("session-1");
    batcher.start();
    batcher.record("tab_switch");

    await expect(async () => {
      jest.advanceTimersByTime(10000);
      await Promise.resolve();
      await Promise.resolve();
    }).not.toThrow();
    batcher.stop();
  });

  it("buffer is cleared after a flush — next flush only sends new events", async () => {
    const batcher = new ActivityLogBatcher("session-1");
    batcher.start();
    batcher.record("tab_switch");
    jest.advanceTimersByTime(10000);
    await Promise.resolve();

    batcher.record("copy");
    jest.advanceTimersByTime(10000);
    await Promise.resolve();

    expect(mockPost).toHaveBeenCalledTimes(2);
    expect(mockPost.mock.calls[1][1].events).toHaveLength(1);
    expect(mockPost.mock.calls[1][1].events[0].event_type).toBe("copy");
    batcher.stop();
  });
});
