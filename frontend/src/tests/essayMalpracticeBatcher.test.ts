/**
 * Regression tests for src/lib/essayMalpracticeBatcher.ts (Task 4.3).
 * Mirrors activityLogBatcher.test.ts's own coverage, adapted for
 * essay-service's own endpoint path and event-type union (notably
 * "paste_attempt", not "paste" — Task 4.3's required rename). Unlike
 * ActivityLogBatcher, record() here takes no occurredAt override — essay-
 * service has no connection_lost-style "report this later with its true
 * original timestamp" use case, so that parameter was deliberately not
 * carried over.
 *
 * Why these tests exist: the batcher must never fire one HTTP call per
 * captured integrity event — it buffers and sends in batches, both on a
 * timer and when the buffer fills. These tests confirm that buffering/
 * flush-triggering logic directly, without needing a real browser event.
 */

jest.useFakeTimers();

const mockPost = jest.fn().mockResolvedValue({ data: { success: true } });
jest.mock("../lib/api", () => ({
  __esModule: true,
  default: { post: (...args: unknown[]) => mockPost(...args) },
}));

import { EssayMalpracticeBatcher } from "../lib/essayMalpracticeBatcher";

const ATTEMPT_ID = "attempt-1";

beforeEach(() => {
  mockPost.mockClear();
  mockPost.mockResolvedValue({ data: { success: true } });
});

afterEach(() => {
  jest.clearAllTimers();
});

describe("EssayMalpracticeBatcher", () => {
  it("does not call the API for a single recorded event before the timer fires", () => {
    const batcher = new EssayMalpracticeBatcher(ATTEMPT_ID);
    batcher.start();
    batcher.record("tab_switch");

    expect(mockPost).not.toHaveBeenCalled();
    batcher.stop();
  });

  it("flushes on the periodic timer with all buffered events in one call", async () => {
    const batcher = new EssayMalpracticeBatcher(ATTEMPT_ID);
    batcher.start();
    batcher.record("tab_switch");
    batcher.record("window_blur");
    batcher.record("paste_attempt");

    jest.advanceTimersByTime(10000);
    await Promise.resolve();

    expect(mockPost).toHaveBeenCalledTimes(1);
    const [url, body] = mockPost.mock.calls[0];
    expect(url).toBe(`/essay/student/attempts/${ATTEMPT_ID}/malpractice-events/`);
    expect(body.events).toHaveLength(3);
    expect(body.events.map((e: { event_type: string }) => e.event_type)).toEqual([
      "tab_switch", "window_blur", "paste_attempt",
    ]);
    batcher.stop();
  });

  it("force-flushes once the buffer reaches 20 events, without waiting for the timer", () => {
    const batcher = new EssayMalpracticeBatcher(ATTEMPT_ID);
    batcher.start();
    for (let i = 0; i < 20; i++) batcher.record("contextmenu");

    expect(mockPost).toHaveBeenCalledTimes(1);
    expect(mockPost.mock.calls[0][1].events).toHaveLength(20);
    batcher.stop();
  });

  it("does not flush an empty buffer on the timer tick", async () => {
    const batcher = new EssayMalpracticeBatcher(ATTEMPT_ID);
    batcher.start();
    jest.advanceTimersByTime(10000);
    await Promise.resolve();
    expect(mockPost).not.toHaveBeenCalled();
    batcher.stop();
  });

  it("includes optional metadata when provided", async () => {
    const batcher = new EssayMalpracticeBatcher(ATTEMPT_ID);
    batcher.start();
    batcher.record("screenshot_attempt", { key: "PrintScreen" });
    jest.advanceTimersByTime(10000);
    await Promise.resolve();

    expect(mockPost.mock.calls[0][1].events[0].metadata).toEqual({ key: "PrintScreen" });
    batcher.stop();
  });

  it("stop() flushes any remaining buffered events immediately", async () => {
    const batcher = new EssayMalpracticeBatcher(ATTEMPT_ID);
    batcher.start();
    batcher.record("fullscreen_exit");
    batcher.stop();
    await Promise.resolve();

    expect(mockPost).toHaveBeenCalledTimes(1);
    expect(mockPost.mock.calls[0][1].events).toHaveLength(1);
  });

  it("swallows a failed flush without throwing (best-effort audit trail, not exam enforcement)", async () => {
    mockPost.mockRejectedValueOnce(new Error("network error"));
    const batcher = new EssayMalpracticeBatcher(ATTEMPT_ID);
    batcher.start();
    batcher.record("tab_switch");

    await expect(async () => {
      jest.advanceTimersByTime(10000);
      await Promise.resolve();
      await Promise.resolve();
    }).not.toThrow();
    batcher.stop();
  });

  it("buffer is cleared after a flush — the next flush only sends new events", async () => {
    const batcher = new EssayMalpracticeBatcher(ATTEMPT_ID);
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

  it("defaults occurred_at to the time record() was called", async () => {
    const batcher = new EssayMalpracticeBatcher(ATTEMPT_ID);
    batcher.start();
    const recordedAt = Date.now();
    batcher.record("paste_attempt");
    jest.advanceTimersByTime(10000);
    await Promise.resolve();

    const occurredAt = new Date(mockPost.mock.calls[0][1].events[0].occurred_at);
    expect(Math.abs(recordedAt - occurredAt.getTime())).toBeLessThan(1000);
    batcher.stop();
  });

  it("scopes the endpoint URL to the given attemptId, not shared across instances", async () => {
    const batcherA = new EssayMalpracticeBatcher("attempt-A");
    batcherA.start();
    batcherA.record("tab_switch");
    batcherA.stop();
    await Promise.resolve();

    expect(mockPost).toHaveBeenCalledWith(
      "/essay/student/attempts/attempt-A/malpractice-events/",
      expect.anything(),
    );
  });
});
