import api from "./api";

/**
 * essayMalpracticeBatcher.ts — client-side event capture for essay-writing
 * integrity signals (Task 4.3), feeding the malpractice-events bulk-insert
 * endpoint. Adapted from assessment-service's activityLogBatcher.ts (same
 * batching principle — never one HTTP call per event) rather than importing
 * it directly: that file belongs to a different service/deployment, and
 * essay-service's event-type union and endpoint path both differ (notably
 * "paste_attempt" here, not "paste" — Task 4.3's own required rename).
 * Not persisted to localStorage — same reasoning as the original: losing a
 * few not-yet-flushed audit events on a hard crash is acceptable (a
 * deterrent + audit trail, not a guarantee), unlike losing a draft.
 */

export type EssayMalpracticeEventType =
  | "tab_switch" | "window_blur" | "fullscreen_exit" | "copy" | "paste_attempt"
  | "contextmenu" | "screenshot_attempt";

interface BufferedEvent {
  event_type: EssayMalpracticeEventType;
  occurred_at: string;
  metadata?: Record<string, unknown>;
}

const FLUSH_INTERVAL_MS = 10000;
const FORCE_FLUSH_AT = 20; // matches core/settings.py's essay_malpractice_event batch expectations

export class EssayMalpracticeBatcher {
  private buffer: BufferedEvent[] = [];
  private timer: ReturnType<typeof setInterval> | null = null;

  constructor(private attemptId: string) {}

  record(eventType: EssayMalpracticeEventType, metadata?: Record<string, unknown>): void {
    this.buffer.push({ event_type: eventType, occurred_at: new Date().toISOString(), metadata });
    if (this.buffer.length >= FORCE_FLUSH_AT) {
      void this.flush();
    }
  }

  start(): void {
    this.timer = setInterval(() => void this.flush(), FLUSH_INTERVAL_MS);
  }

  stop(): void {
    if (this.timer) clearInterval(this.timer);
    this.timer = null;
    void this.flush();
  }

  private async flush(): Promise<void> {
    if (this.buffer.length === 0) return;
    const events = this.buffer;
    this.buffer = [];
    try {
      await api.post(`/essay/student/attempts/${this.attemptId}/malpractice-events/`, { events });
    } catch {
      // Best-effort — a lost batch of audit events doesn't affect exam
      // integrity enforcement (entirely server-side/timing-based, Task
      // 4.1), only the completeness of the admin's post-hoc review.
    }
  }
}
