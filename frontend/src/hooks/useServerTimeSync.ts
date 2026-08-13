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

/**
 * useServerTimeSync — the client half of Task 4.2's server-time-sync
 * endpoint, with Task 5.3's graceful-degradation requirement: a transient
 * polling failure keeps the countdown ticking from the last known
 * server-vs-local clock offset rather than freezing the UI or showing an
 * error. The server still hard-revalidates on the next successful
 * submit/autosave regardless of what this display shows in the meantime.
 */
export function useServerTimeSync() {
  const [secondsRemaining, setSecondsRemaining] = useState<number | null>(null);
  const [isSyncFailing, setIsSyncFailing] = useState(false);
  const offsetRef = useRef(0); // serverNow - Date.now(), from the last successful poll
  const endsAtRef = useRef<number | null>(null);

  const poll = useCallback(async () => {
    try {
      const res = await api.get<ApiSuccess<ServerTimeResponse>>("/assessments/student/server-time/");
      const data = res.data.data;
      offsetRef.current = new Date(data.server_time).getTime() - Date.now();
      if (data.ends_at) endsAtRef.current = new Date(data.ends_at).getTime();
      setIsSyncFailing(false);
    } catch {
      setIsSyncFailing(true);
    }
  }, []);

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

  return { secondsRemaining, isSyncFailing };
}
