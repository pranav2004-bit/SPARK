/**
 * @jest-environment jsdom
 *
 * Regression tests for src/lib/essayDraftQueue.ts (Task 4.2, closes ET10).
 * Mirrors assessmentOfflineQueue.test.ts's own coverage, scaled down for
 * essay-service's single-pending-draft-per-attempt shape (no per-question
 * map — there's exactly one question per attempt, so this queue only ever
 * holds one string per attemptId, not a collection).
 *
 * Why these tests exist: a mid-write network drop must never lose a
 * student's essay draft. These tests simulate that directly against the
 * module's own exports (not through the page, which mocks this module
 * away) — a transient failure queues locally instead of throwing, a later
 * flush replays it, and a genuine rejection (e.g. the attempt expired)
 * clears the queue rather than retrying forever.
 */

jest.mock("@/lib/api", () => ({
  __esModule: true,
  default: { put: jest.fn() },
}));

import axios from "axios";
import api from "../lib/api";
import { pendingDraft, saveDraftResilient, flushDraftQueue } from "../lib/essayDraftQueue";

const ATTEMPT_ID = "attempt-1";

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

describe("pendingDraft", () => {
  it("returns null when nothing is queued for this attempt", () => {
    expect(pendingDraft(ATTEMPT_ID)).toBeNull();
  });

  it("different attempts have independent queued drafts", async () => {
    (api.put as jest.Mock).mockRejectedValueOnce(networkError());
    await saveDraftResilient("attempt-A", "draft A");
    expect(pendingDraft("attempt-A")).toBe("draft A");
    expect(pendingDraft("attempt-B")).toBeNull();
  });
});

describe("saveDraftResilient", () => {
  it("returns 'saved' and queues nothing on a successful live PUT", async () => {
    (api.put as jest.Mock).mockResolvedValueOnce({ data: { success: true } });

    const outcome = await saveDraftResilient(ATTEMPT_ID, "hello world");

    expect(outcome).toBe("saved");
    expect(pendingDraft(ATTEMPT_ID)).toBeNull();
  });

  it("queues locally and returns 'queued' on a network failure", async () => {
    (api.put as jest.Mock).mockRejectedValueOnce(networkError());

    const outcome = await saveDraftResilient(ATTEMPT_ID, "hello world");

    expect(outcome).toBe("queued");
    expect(pendingDraft(ATTEMPT_ID)).toBe("hello world");
  });

  it("clears a stale queued draft once a live save succeeds", async () => {
    (api.put as jest.Mock).mockRejectedValueOnce(networkError());
    await saveDraftResilient(ATTEMPT_ID, "stale draft");
    expect(pendingDraft(ATTEMPT_ID)).toBe("stale draft");

    (api.put as jest.Mock).mockResolvedValueOnce({ data: { success: true } });
    await saveDraftResilient(ATTEMPT_ID, "fresh draft");

    expect(pendingDraft(ATTEMPT_ID)).toBeNull();
  });

  it("a newer queued draft replaces an older one, not appends", async () => {
    (api.put as jest.Mock).mockRejectedValue(networkError());
    await saveDraftResilient(ATTEMPT_ID, "first attempt at the essay");
    await saveDraftResilient(ATTEMPT_ID, "first attempt at the essay, revised");

    expect(pendingDraft(ATTEMPT_ID)).toBe("first attempt at the essay, revised");
  });

  it("throws (does not queue) on a real HTTP rejection like 403 time-expired", async () => {
    (api.put as jest.Mock).mockRejectedValueOnce(httpError(403));

    await expect(saveDraftResilient(ATTEMPT_ID, "too late")).rejects.toBeTruthy();
    expect(pendingDraft(ATTEMPT_ID)).toBeNull();
  });

  it("queues locally and returns 'queued' on a 429 rate-limit response", async () => {
    (api.put as jest.Mock).mockRejectedValueOnce(httpError(429));

    const outcome = await saveDraftResilient(ATTEMPT_ID, "hello world");

    expect(outcome).toBe("queued");
    expect(pendingDraft(ATTEMPT_ID)).toBe("hello world");
  });
});

describe("flushDraftQueue", () => {
  it("flushes the queued draft on success", async () => {
    (api.put as jest.Mock).mockRejectedValueOnce(networkError());
    await saveDraftResilient(ATTEMPT_ID, "queued text");

    (api.put as jest.Mock).mockResolvedValueOnce({ data: { success: true } });
    const flushed = await flushDraftQueue(ATTEMPT_ID);

    expect(flushed).toBe(true);
    expect(pendingDraft(ATTEMPT_ID)).toBeNull();
  });

  it("returns false and calls nothing when there is no queued draft", async () => {
    const flushed = await flushDraftQueue(ATTEMPT_ID);
    expect(flushed).toBe(false);
    expect(api.put).not.toHaveBeenCalled();
  });

  it("keeps a still-failing draft queued after a network-error flush attempt", async () => {
    (api.put as jest.Mock).mockRejectedValueOnce(networkError());
    await saveDraftResilient(ATTEMPT_ID, "queued text");

    (api.put as jest.Mock).mockRejectedValueOnce(networkError());
    const flushed = await flushDraftQueue(ATTEMPT_ID);

    expect(flushed).toBe(false);
    expect(pendingDraft(ATTEMPT_ID)).toBe("queued text"); // still there for the next attempt
  });

  it("drops a draft that gets a real HTTP rejection instead of retrying forever", async () => {
    (api.put as jest.Mock).mockRejectedValueOnce(networkError());
    await saveDraftResilient(ATTEMPT_ID, "queued text");

    (api.put as jest.Mock).mockRejectedValueOnce(httpError(403));
    const flushed = await flushDraftQueue(ATTEMPT_ID);

    expect(flushed).toBe(false);
    expect(pendingDraft(ATTEMPT_ID)).toBeNull(); // cleared, not retried forever
  });

  it("keeps a still-failing draft queued after a 429 flush attempt (not dropped)", async () => {
    (api.put as jest.Mock).mockRejectedValueOnce(networkError());
    await saveDraftResilient(ATTEMPT_ID, "queued text");

    (api.put as jest.Mock).mockRejectedValueOnce(httpError(429));
    const flushed = await flushDraftQueue(ATTEMPT_ID);

    expect(flushed).toBe(false);
    expect(pendingDraft(ATTEMPT_ID)).toBe("queued text");
  });
});
