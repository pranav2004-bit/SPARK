"use client";

import { useState, useCallback, useEffect, useRef } from "react";
import { saveAnswerResilient, flushQueue, pendingCount } from "@/lib/assessmentOfflineQueue";

// Matches the ~20-30s server-time polling cadence elsewhere (ADR 001) —
// no need to hammer the network faster than that while offline.
const FLUSH_RETRY_INTERVAL_MS = 8000;

/**
 * useOfflineAnswerQueue — wires assessmentOfflineQueue.ts (Task 5.3) into
 * a component. The exam UI (Task 5.4) calls `saveAnswer` on every option
 * change; a transient network failure is absorbed here (queued locally,
 * retried in the background) rather than surfaced as an error.
 */
export function useOfflineAnswerQueue(sessionId: string) {
  const [isReconnecting, setIsReconnecting] = useState(false);
  const [pending, setPending] = useState(0);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const refreshPendingCount = useCallback(() => {
    setPending(pendingCount(sessionId));
  }, [sessionId]);

  const attemptFlush = useCallback(async () => {
    await flushQueue(sessionId);
    refreshPendingCount();
  }, [sessionId, refreshPendingCount]);

  const saveAnswer = useCallback(
    async (questionId: string, selectedOptionIds: string[]) => {
      const outcome = await saveAnswerResilient(sessionId, questionId, selectedOptionIds);
      if (outcome === "queued") setIsReconnecting(true);
      refreshPendingCount();
      return outcome;
    },
    [sessionId, refreshPendingCount]
  );

  useEffect(() => {
    refreshPendingCount();

    const handleOnline = () => { attemptFlush(); };
    window.addEventListener("online", handleOnline);

    intervalRef.current = setInterval(() => {
      if (pendingCount(sessionId) > 0) attemptFlush();
    }, FLUSH_RETRY_INTERVAL_MS);

    return () => {
      window.removeEventListener("online", handleOnline);
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
  }, [sessionId, attemptFlush, refreshPendingCount]);

  useEffect(() => {
    if (pending === 0) setIsReconnecting(false);
  }, [pending]);

  return { saveAnswer, isReconnecting, pendingCount: pending };
}
