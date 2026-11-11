import axios from "axios";
import api from "./api";

/**
 * essayDraftQueue.ts — client-side resilience for draft autosave during an
 * essay attempt (Task 4.2, closes ET10). Adapted from assessment-service's
 * assessmentOfflineQueue.ts, simplified: that queue maps questionId ->
 * pending answer (many questions per session); essay-service has exactly
 * one draft per attempt, so this is a single pending string per attemptId,
 * not a map.
 *
 * The backend's PUT .../autosave/ endpoint is an idempotent upsert — replaying
 * the same queued write after a reconnect is safe by construction, so this
 * module is a dumb "keep retrying until it sticks" queue with no
 * conflict-resolution logic of its own.
 */

function storageKey(attemptId: string): string {
  return `aptlogic_essay_draft_queue_${attemptId}`;
}

function readQueued(attemptId: string): string | null {
  if (typeof window === "undefined") return null;
  try {
    return window.localStorage.getItem(storageKey(attemptId));
  } catch {
    return null;
  }
}

function writeQueued(attemptId: string, draft: string | null): void {
  if (typeof window === "undefined") return;
  if (draft === null) {
    window.localStorage.removeItem(storageKey(attemptId));
  } else {
    window.localStorage.setItem(storageKey(attemptId), draft);
  }
}

export function pendingDraft(attemptId: string): string | null {
  return readQueued(attemptId);
}

/** Same transient-vs-genuine-rejection split as assessmentOfflineQueue.ts —
 * a transport-level failure or a 429 should retry, anything else (403 time
 * expired/closed, etc.) is a real rejection the caller must surface. */
function isRetryableNetworkError(err: unknown): boolean {
  if (!axios.isAxiosError(err)) return false;
  return err.response === undefined || err.response.status === 429;
}

/**
 * Attempts to save the draft live. On a transport-level failure or a 429,
 * queues it locally instead of throwing — the caller shows a "saved
 * locally, reconnecting…" state rather than an error. Any other HTTP
 * rejection throws as usual.
 */
export async function saveDraftResilient(attemptId: string, draftResponse: string): Promise<"saved" | "queued"> {
  try {
    await api.put(`/essay/student/attempts/${attemptId}/autosave/`, { draft_response: draftResponse });
    writeQueued(attemptId, null);
    return "saved";
  } catch (err) {
    if (isRetryableNetworkError(err)) {
      writeQueued(attemptId, draftResponse);
      return "queued";
    }
    throw err;
  }
}

/**
 * Flushes the queued draft for an attempt, if any. Called on reconnect (the
 * browser's `online` event) and on a periodic timer while anything remains
 * queued. Returns true if it flushed successfully.
 */
export async function flushDraftQueue(attemptId: string): Promise<boolean> {
  const queued = readQueued(attemptId);
  if (queued === null) return false;
  try {
    await api.put(`/essay/student/attempts/${attemptId}/autosave/`, { draft_response: queued });
    writeQueued(attemptId, null);
    return true;
  } catch (err) {
    if (!isRetryableNetworkError(err)) {
      // A genuine rejection (e.g. the attempt expired while offline) —
      // clearing prevents an infinite retry loop against a request that
      // will never succeed.
      writeQueued(attemptId, null);
    }
    return false;
  }
}
