/**
 * @jest-environment jsdom
 *
 * Regression tests for src/lib/assessmentOfflineQueue.ts (Task 5.3).
 *
 * Why these tests exist:
 *   A mid-exam network drop must never lose a student's answer (AT10).
 *   These tests simulate that: a transient network failure queues the
 *   answer locally instead of throwing, and a later flush (on reconnect)
 *   replays it. Because the backend endpoint is an idempotent upsert
 *   (Task 5.2), replaying is safe by construction — these tests confirm
 *   the CLIENT side holds up its end: nothing is lost, nothing duplicates,
 *   and a genuine rejection (not a network problem) is not silently
 *   swallowed into an infinite retry loop.
 */

jest.mock("@/lib/api", () => ({
  __esModule: true,
  default: { put: jest.fn() },
}));

import axios from "axios";
import api from "../lib/api";
import {
  enqueueAnswer, dequeueAnswer, pendingCount,
  saveAnswerResilient, flushQueue,
} from "../lib/assessmentOfflineQueue";

const SESSION_ID = "session-1";

function networkError() {
  const err = new Error("Network Error") as any;
  err.isAxiosError = true;
  err.response = undefined; // no response received — transport failure
  jest.spyOn(axios, "isAxiosError").mockReturnValue(true);
  return err;
}

function httpError(status: number) {
  const err = new Error("Request failed") as any;
  err.isAxiosError = true;
  err.response = { status };
  jest.spyOn(axios, "isAxiosError").mockReturnValue(true);
  return err;
}

beforeEach(() => {
  window.localStorage.clear();
  jest.clearAllMocks();
});

afterEach(() => {
  jest.restoreAllMocks();
});

describe("enqueue / dequeue / pendingCount", () => {
  it("queues an answer and reports it pending", () => {
    enqueueAnswer(SESSION_ID, "q1", ["a"]);
    expect(pendingCount(SESSION_ID)).toBe(1);
  });

  it("re-queuing the same question replaces, not duplicates", () => {
    enqueueAnswer(SESSION_ID, "q1", ["a"]);
    enqueueAnswer(SESSION_ID, "q1", ["b"]);
    expect(pendingCount(SESSION_ID)).toBe(1);
  });

  it("dequeue removes exactly the given question", () => {
    enqueueAnswer(SESSION_ID, "q1", ["a"]);
    enqueueAnswer(SESSION_ID, "q2", ["b"]);
    dequeueAnswer(SESSION_ID, "q1");
    expect(pendingCount(SESSION_ID)).toBe(1);
  });

  it("different sessions have independent queues", () => {
    enqueueAnswer("session-A", "q1", ["a"]);
    enqueueAnswer("session-B", "q1", ["b"]);
    expect(pendingCount("session-A")).toBe(1);
    expect(pendingCount("session-B")).toBe(1);
    dequeueAnswer("session-A", "q1");
    expect(pendingCount("session-A")).toBe(0);
    expect(pendingCount("session-B")).toBe(1);
  });
});

describe("saveAnswerResilient", () => {
  it("returns 'saved' and does not queue on a successful live PUT", async () => {
    (api.put as jest.Mock).mockResolvedValueOnce({ data: { success: true } });

    const outcome = await saveAnswerResilient(SESSION_ID, "q1", ["a"]);

    expect(outcome).toBe("saved");
    expect(pendingCount(SESSION_ID)).toBe(0);
  });

  it("queues locally and returns 'queued' on a network failure", async () => {
    (api.put as jest.Mock).mockRejectedValueOnce(networkError());

    const outcome = await saveAnswerResilient(SESSION_ID, "q1", ["a"]);

    expect(outcome).toBe("queued");
    expect(pendingCount(SESSION_ID)).toBe(1);
  });

  it("dequeues a stale entry once the live save succeeds", async () => {
    enqueueAnswer(SESSION_ID, "q1", ["stale"]);
    (api.put as jest.Mock).mockResolvedValueOnce({ data: { success: true } });

    await saveAnswerResilient(SESSION_ID, "q1", ["fresh"]);

    expect(pendingCount(SESSION_ID)).toBe(0);
  });

  it("throws (does not queue) on a real HTTP rejection like 403 time-expired", async () => {
    (api.put as jest.Mock).mockRejectedValueOnce(httpError(403));

    await expect(saveAnswerResilient(SESSION_ID, "q1", ["a"])).rejects.toBeTruthy();
    expect(pendingCount(SESSION_ID)).toBe(0);
  });

  // 2026-09-12: a 429 here can arrive with no fault of the student's own —
  // e.g. api.ts's refresh-on-401 interceptor getting rate-limited on a
  // shared exam-hall IP surfaces to this caller as a 429 on the original
  // PUT, not the underlying 401. Treating that like a genuine rejection
  // (403/404/etc.) would drop the answer instead of queuing it for retry.
  it("queues locally and returns 'queued' on a 429 rate-limit response", async () => {
    (api.put as jest.Mock).mockRejectedValueOnce(httpError(429));

    const outcome = await saveAnswerResilient(SESSION_ID, "q1", ["a"]);

    expect(outcome).toBe("queued");
    expect(pendingCount(SESSION_ID)).toBe(1);
  });
});

describe("flushQueue", () => {
  it("flushes all queued answers on success", async () => {
    enqueueAnswer(SESSION_ID, "q1", ["a"]);
    enqueueAnswer(SESSION_ID, "q2", ["b"]);
    (api.put as jest.Mock).mockResolvedValue({ data: { success: true } });

    const flushed = await flushQueue(SESSION_ID);

    expect(flushed).toBe(2);
    expect(pendingCount(SESSION_ID)).toBe(0);
  });

  it("returns 0 and changes nothing when the queue is empty", async () => {
    const flushed = await flushQueue(SESSION_ID);
    expect(flushed).toBe(0);
    expect(api.put).not.toHaveBeenCalled();
  });

  it("keeps a still-failing entry queued after a network-error flush attempt", async () => {
    enqueueAnswer(SESSION_ID, "q1", ["a"]);
    (api.put as jest.Mock).mockRejectedValueOnce(networkError());

    const flushed = await flushQueue(SESSION_ID);

    expect(flushed).toBe(0);
    expect(pendingCount(SESSION_ID)).toBe(1); // still there for the next attempt
  });

  it("drops an entry that gets a real HTTP rejection (not an infinite retry)", async () => {
    enqueueAnswer(SESSION_ID, "q1", ["a"]);
    (api.put as jest.Mock).mockRejectedValueOnce(httpError(403));

    const flushed = await flushQueue(SESSION_ID);

    expect(flushed).toBe(0);
    expect(pendingCount(SESSION_ID)).toBe(0); // cleared, not retried forever
  });

  it("keeps a still-failing entry queued after a 429 flush attempt (not dropped)", async () => {
    enqueueAnswer(SESSION_ID, "q1", ["a"]);
    (api.put as jest.Mock).mockRejectedValueOnce(httpError(429));

    const flushed = await flushQueue(SESSION_ID);

    expect(flushed).toBe(0);
    expect(pendingCount(SESSION_ID)).toBe(1); // still there for the next attempt
  });

  it("one failing entry does not block other entries from flushing", async () => {
    enqueueAnswer(SESSION_ID, "q1", ["a"]);
    enqueueAnswer(SESSION_ID, "q2", ["b"]);
    (api.put as jest.Mock)
      .mockRejectedValueOnce(networkError())
      .mockResolvedValueOnce({ data: { success: true } });

    const flushed = await flushQueue(SESSION_ID);

    expect(flushed).toBe(1);
    expect(pendingCount(SESSION_ID)).toBe(1); // only q1 remains
  });

  it("a queued-then-reconnected answer flushes successfully end to end", async () => {
    (api.put as jest.Mock).mockRejectedValueOnce(networkError());
    const first = await saveAnswerResilient(SESSION_ID, "q1", ["a"]);
    expect(first).toBe("queued");

    (api.put as jest.Mock).mockResolvedValueOnce({ data: { success: true } });
    const flushed = await flushQueue(SESSION_ID);

    expect(flushed).toBe(1);
    expect(pendingCount(SESSION_ID)).toBe(0);
  });
});
