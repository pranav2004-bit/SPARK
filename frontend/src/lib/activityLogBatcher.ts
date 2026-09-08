import api from "./api";

/**
 * activityLogBatcher.ts — client-side event capture for anti-cheat
 * signals (Task 6.1), feeding Task 6.2's bulk-insert endpoint.
 *
 * Reuses the batching principle from Task 5.3 (assessmentOfflineQueue.ts):
 * never fire one HTTP call per event — buffer and send in batches, both on
 * a timer and when the buffer fills. Unlike the answer queue, this buffer
 * is intentionally NOT persisted to localStorage — losing a few
 * not-yet-flushed audit events on a hard crash is acceptable (per the
 * spec: "a deterrent + audit trail, not a guarantee"), whereas losing an
 * answer would not be.
 */

export type ActivityEventType =
  | "tab_switch" | "window_blur" | "fullscreen_exit" | "copy" | "paste" | "contextmenu"
  | "screenshot_attempt" | "connection_lost" | "question_time_spent";

interface BufferedEvent {
  event_type: ActivityEventType;
  occurred_at: string;
  metadata?: Record<string, unknown>;
}

const FLUSH_INTERVAL_MS = 10000;
const FORCE_FLUSH_AT = 20; // matches core/settings.py's ActivityLog batch expectations

export class ActivityLogBatcher {
  private buffer: BufferedEvent[] = [];
  private timer: ReturnType<typeof setInterval> | null = null;

  constructor(private sessionId: string) {}

  /**
   * occurredAt: defaults to "now" (every existing caller). connection_lost
   * is the one exception — it can only ever be reported once connectivity
   * returns (there's no network to send it over at the actual moment of
   * loss), so that caller passes the real detected loss time here instead
   * of letting it default to "whenever we finally got back online."
   */
  record(eventType: ActivityEventType, metadata?: Record<string, unknown>, occurredAt?: Date): void {
    this.buffer.push({ event_type: eventType, occurred_at: (occurredAt ?? new Date()).toISOString(), metadata });
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
      await api.post(`/assessments/student/sessions/${this.sessionId}/activity-logs/`, { events });
    } catch {
      // Best-effort — a lost batch of audit events doesn't affect exam
      // integrity enforcement (entirely server-side/timing-based, Task
      // 4.2), only the completeness of the admin's post-hoc review.
    }
  }
}
