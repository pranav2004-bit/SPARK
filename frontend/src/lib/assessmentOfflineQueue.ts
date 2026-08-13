import axios from "axios";
import api from "./api";

/**
 * assessmentOfflineQueue.ts — client-side resilience for answer autosave
 * during an exam (Task 5.3, closes AT10).
 *
 * The backend's PUT .../answer/ endpoint is an idempotent upsert (Task
 * 5.2) — replaying the same queued write after a reconnect is safe by
 * construction, so this module can be a dumb "keep retrying until it
 * sticks" queue with no conflict-resolution logic of its own.
 *
 * Storage: one localStorage entry per session (`aptlogic_assessment_queue_<sessionId>`),
 * holding a map of questionId -> the latest pending selection for that
 * question. A second local answer for the same question before the first
 * flush REPLACES the pending entry rather than queuing both — only the
 * student's latest intent matters, and it keeps the queue bounded by
 * question count, not by how many times they changed their mind.
 */

export interface QueuedAnswer {
  selectedOptionIds: string[];
  queuedAt: string;
}

type Queue = Record<string, QueuedAnswer>; // questionId -> pending answer

function storageKey(sessionId: string): string {
  return `aptlogic_assessment_queue_${sessionId}`;
}

function readQueue(sessionId: string): Queue {
  if (typeof window === "undefined") return {};
  try {
    const raw = window.localStorage.getItem(storageKey(sessionId));
    return raw ? (JSON.parse(raw) as Queue) : {};
  } catch {
    // Corrupted entry (manual tampering, storage quota edge case) — treat
    // as empty rather than throwing and breaking the whole exam page.
    return {};
  }
}

function writeQueue(sessionId: string, queue: Queue): void {
  if (typeof window === "undefined") return;
  if (Object.keys(queue).length === 0) {
    window.localStorage.removeItem(storageKey(sessionId));
  } else {
    window.localStorage.setItem(storageKey(sessionId), JSON.stringify(queue));
  }
}

/** Adds/replaces one question's pending answer in the local queue. */
export function enqueueAnswer(sessionId: string, questionId: string, selectedOptionIds: string[]): void {
  const queue = readQueue(sessionId);
  queue[questionId] = { selectedOptionIds, queuedAt: new Date().toISOString() };
  writeQueue(sessionId, queue);
}

/** Removes one question's entry after a confirmed successful flush. */
export function dequeueAnswer(sessionId: string, questionId: string): void {
  const queue = readQueue(sessionId);
  delete queue[questionId];
  writeQueue(sessionId, queue);
}

export function pendingCount(sessionId: string): number {
  return Object.keys(readQueue(sessionId)).length;
}

/** True only for transport-level failures — never for a real HTTP response
 * (4xx/5xx). A 403 (time expired, assignment closed) is a genuine
 * rejection, not a connectivity problem — retrying it forever would be
 * wrong; the caller should surface that as a real error, not silently requeue. */
function isRetryableNetworkError(err: unknown): boolean {
  if (!axios.isAxiosError(err)) return false;
  return err.response === undefined;
}

/**
 * Attempts to save one answer live. On a transport-level failure, queues
 * it locally instead of throwing — the caller (the exam UI) shows a
 * "saved locally, reconnecting…" state rather than an error. On a real
 * HTTP rejection (4xx/5xx), throws as usual — that's a genuine failure,
 * not a connectivity gap the queue can fix.
 */
export async function saveAnswerResilient(
  sessionId: string,
  questionId: string,
  selectedOptionIds: string[]
): Promise<"saved" | "queued"> {
  try {
    await api.put(`/assessments/student/sessions/${sessionId}/questions/${questionId}/answer/`, {
      selected_option_ids: selectedOptionIds,
    });
    dequeueAnswer(sessionId, questionId);
    return "saved";
  } catch (err) {
    if (isRetryableNetworkError(err)) {
      enqueueAnswer(sessionId, questionId, selectedOptionIds);
      return "queued";
    }
    throw err;
  }
}

/**
 * Flushes every queued answer for a session. Called on reconnect (the
 * browser's `online` event) and on a periodic timer while anything remains
 * queued. Each entry is retried independently — one still-failing entry
 * doesn't block the others from flushing.
 *
 * Returns the number of entries that flushed successfully this call.
 */
export async function flushQueue(sessionId: string): Promise<number> {
  const queue = readQueue(sessionId);
  const entries = Object.entries(queue);
  if (entries.length === 0) return 0;

  let flushed = 0;
  for (const [questionId, { selectedOptionIds }] of entries) {
    try {
      await api.put(`/assessments/student/sessions/${sessionId}/questions/${questionId}/answer/`, {
        selected_option_ids: selectedOptionIds,
      });
      dequeueAnswer(sessionId, questionId);
      flushed += 1;
    } catch (err) {
      // Still unreachable, or a real rejection (e.g. the session expired
      // while offline) — leave it queued for a real network error so the
      // next flush attempt retries it; a genuine 4xx means the answer is
      // stale (session no longer writable) and clearing it prevents an
      // infinite retry loop against a request that will never succeed.
      if (!isRetryableNetworkError(err)) {
        dequeueAnswer(sessionId, questionId);
      }
    }
  }
  return flushed;
}
