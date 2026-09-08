"use client";

import { useState, useEffect, useRef, useCallback } from "react";
import api from "@/lib/api";
import type { ApiSuccess } from "@/types";

// ADR 001, decision point 5: a lightweight poll every 20-30s, not a
// WebSocket — the countdown is cosmetic, server-side revalidation on every
// write is the real enforcement (Task 4.2).
const POLL_INTERVAL_MS = 20000;

interface ServerTimeResponse {
  server_time: string;
  session_id?: string;
  ends_at?: string;
}

export interface TimerExtension {
  /** Local Date.now() when this extension was detected — a fresh object
   * every time (even if addedMinutes repeats), so a caller's effect keyed
   * on this fires exactly once per real extension via reference identity,
   * without needing to reset it back to null afterward. */
  detectedAtMs: number;
  addedMinutes: number;
}

/**
 * useServerTimeSync — the client half of Task 4.2's server-time-sync
 * endpoint, with Task 5.3's graceful-degradation requirement: a transient
 * polling failure keeps the countdown ticking from the last known
 * server-vs-local clock offset rather than freezing the UI or showing an
 * error. The server still hard-revalidates on the next successful
 * submit/autosave regardless of what this display shows in the meantime.
 *
 * lastExtension (added 2026-08-17): an admin's .../sessions/<id>/extend/
 * call is the only thing that ever moves ends_at later after a session
 * starts (ADR 001) — so if a poll's ends_at is meaningfully greater than
 * the previous poll's, that's a real extension, not just normal ticking.
 * There's no push channel (ADR 001, decision point 5 — polling only), so
 * this is detected on the *next* poll after the admin's action, up to
 * POLL_INTERVAL_MS later, not instantly.
 *
 * `endpoint` (added 2026-08-27, default unchanged): lets the admin
 * mock-test trial page reuse this exact hook against a different URL
 * (/assessments/admin/trial/server-time/) — same {server_time, ends_at}
 * response shape and polling logic, just a trial session instead of a
 * student one.
 */
export function useServerTimeSync(endpoint: string = "/assessments/student/server-time/") {
  const [secondsRemaining, setSecondsRemaining] = useState<number | null>(null);
  const [isSyncFailing, setIsSyncFailing] = useState(false);
  const [lastExtension, setLastExtension] = useState<TimerExtension | null>(null);
  const offsetRef = useRef(0); // serverNow - Date.now(), from the last successful poll
  const endsAtRef = useRef<number | null>(null);

  const poll = useCallback(async () => {
    try {
      const res = await api.get<ApiSuccess<ServerTimeResponse>>(endpoint);
      const data = res.data.data;
      offsetRef.current = new Date(data.server_time).getTime() - Date.now();
      if (data.ends_at) {
        const newEndsAt = new Date(data.ends_at).getTime();
        const previousEndsAt = endsAtRef.current;
        // previousEndsAt !== null excludes the very first poll (nothing to
        // compare against yet, not an extension). The 1000ms slop absorbs
        // sub-second float/rounding noise between polls, not a real change.
        if (previousEndsAt !== null && newEndsAt > previousEndsAt + 1000) {
          setLastExtension({
            detectedAtMs: Date.now(),
            addedMinutes: Math.round((newEndsAt - previousEndsAt) / 60000),
          });
        }
        endsAtRef.current = newEndsAt;
      }
      setIsSyncFailing(false);
    } catch {
      setIsSyncFailing(true);
    }
  }, [endpoint]);

  useEffect(() => {
    poll();
    const pollTimer = setInterval(poll, POLL_INTERVAL_MS);

    const tickTimer = setInterval(() => {
      if (endsAtRef.current === null) return;
      const localNow = Date.now() + offsetRef.current;
      setSecondsRemaining(Math.max(0, Math.round((endsAtRef.current - localNow) / 1000)));
    }, 1000);

    return () => {
      clearInterval(pollTimer);
      clearInterval(tickTimer);
    };
  }, [poll]);

  return { secondsRemaining, isSyncFailing, lastExtension };
}
