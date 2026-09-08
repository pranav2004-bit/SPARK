"use client";

import { useEffect, useRef, useState, useCallback } from "react";
import { ActivityLogBatcher } from "@/lib/activityLogBatcher";

/**
 * useActivityCapture — wires up the DOM listeners for Task 6.1's anti-cheat
 * signals and batches them through ActivityLogBatcher. Also tracks
 * fullscreen state, and per-type live counts (tabSwitchCount,
 * fullscreenExitCount) so the exam page can show a graduated warning on
 * every occurrence and a hard lockout once a count crosses the same
 * threshold the backend's own malpractice check uses (scoring.py's
 * TAB_SWITCH_THRESHOLD=5 / FULLSCREEN_EXIT_THRESHOLD=3 — kept in sync by
 * convention, not a shared import, since there's no API surface exposing
 * those constants to the frontend).
 *
 * Copy/paste are actively blocked here (preventDefault), not just logged —
 * this exam is multiple-choice only, so there's no legitimate reason for a
 * student to need clipboard access on this page.
 *
 * screenshotAttempts is intentionally best-effort: browsers have no API to
 * detect a screenshot in general (OS-level tools, phone cameras, and
 * Mac's Cmd+Shift+3/4/5 are all invisible to a web page). This only catches
 * the Windows PrintScreen key, which is the one screenshot method a
 * keydown listener can see at all — a partial deterrent, not real
 * prevention. Reported here as a live count AND sent to the backend as a
 * screenshot_attempt event (2026-08-18) — the admin timeline is meant to
 * be a complete record, not just the subset that also happens to warrant
 * an in-exam UI warning.
 *
 * connection_lost (2026-08-18): the browser's online/offline events are
 * used to detect a lost connection, but the event is only ever *recorded*
 * once "online" fires again — see activityLogBatcher.record()'s doc
 * comment for why (nothing can be POSTed while genuinely offline). The
 * true loss time and outage duration are preserved in the event itself,
 * not just "whenever we happened to notice we were back."
 *
 * question_time_spent (2026-08-18): the exam page calls the returned
 * notifyActiveQuestion(questionNumber) every time the student navigates to
 * a different question (Prev/Next or the jump navigator). Only foreground
 * (tab-visible) time counts — accumulation pauses on the same
 * visibilitychange signal that drives tab_switch detection, and resumes
 * when the tab is visible again, so switching away mid-question doesn't
 * inflate that question's recorded time. A view under 1 second isn't
 * logged at all (not meaningful data, just noise from rapid navigation).
 *
 * tabSwitchCount/fullscreenExitCount are persisted to localStorage, keyed
 * by sessionId (same convention as assessmentOfflineQueue.ts), not held in
 * plain useState — audited 2026-08-17: pure in-memory counts reset the
 * instant the tab closes, so a student could open a fresh tab of the same
 * exam specifically to dodge the client-side lockout threshold. The
 * server-side malpractice flag was never fooled by this (it's computed
 * from cumulative ActivityLog rows against the one shared session, not a
 * per-tab count), but the client-side lockout — the thing that actually
 * auto-submits — was. A `storage` event listener also keeps any other
 * simultaneously-open tab of the same exam in sync with the shared count,
 * so two tabs open at once don't each think they're starting from zero.
 * This does NOT (and can't) fix the separate, inherent limitation that the
 * Visibility API can't distinguish "switched to my own other tab of this
 * exam" from "switched to a different application" — either one still
 * legitimately counts as a tab switch, same as it always has.
 */
function countStorageKey(sessionId: string, kind: "tab_switch" | "fullscreen_exit"): string {
  return `aptlogic_exam_violation_count_${kind}_${sessionId}`;
}

function readCount(sessionId: string, kind: "tab_switch" | "fullscreen_exit"): number {
  if (typeof window === "undefined") return 0;
  const raw = window.localStorage.getItem(countStorageKey(sessionId, kind));
  const n = raw ? parseInt(raw, 10) : 0;
  return Number.isFinite(n) && n >= 0 ? n : 0;
}

/** Reads-then-writes the persisted count and returns the new value — the
 * single source of truth this tab and every sibling tab both read from. */
function incrementCount(sessionId: string, kind: "tab_switch" | "fullscreen_exit"): number {
  const next = readCount(sessionId, kind) + 1;
  window.localStorage.setItem(countStorageKey(sessionId, kind), String(next));
  return next;
}

/** Called by the exam page once a session has genuinely reached a terminal
 * status (SUBMITTED/AUTO_SUBMITTED) — the one point it's actually safe to
 * stop tracking a session's violation counts, as opposed to any other
 * reason this hook's effect might tear down (e.g. an in-app navigation
 * away from a still-active exam). */
export function clearExamViolationCounts(sessionId: string): void {
  if (typeof window === "undefined") return;
  window.localStorage.removeItem(countStorageKey(sessionId, "tab_switch"));
  window.localStorage.removeItem(countStorageKey(sessionId, "fullscreen_exit"));
}

interface QuestionView {
  questionNumber: number;
  accumulatedMs: number;
  /** ms timestamp the current foreground span started, or null while the
   * tab is hidden (paused). */
  visibleSinceMs: number | null;
}

export function useActivityCapture(sessionId: string | null) {
  const batcherRef = useRef<ActivityLogBatcher | null>(null);
  const offlineSinceRef = useRef<Date | null>(null);
  const questionViewRef = useRef<QuestionView | null>(null);
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [tabSwitchCount, setTabSwitchCount] = useState(0);
  const [fullscreenExitCount, setFullscreenExitCount] = useState(0);
  const [screenshotAttempts, setScreenshotAttempts] = useState(0);

  // Finalizes whatever question was being viewed — called both when the
  // student navigates to a different one and (via the effect's cleanup
  // below) when the session ends, so the very last question's time isn't
  // silently dropped just because there was no "next" navigation after it.
  const finalizeCurrentQuestionView = useCallback((batcher: ActivityLogBatcher) => {
    const qv = questionViewRef.current;
    if (!qv) return;
    let totalMs = qv.accumulatedMs;
    if (qv.visibleSinceMs !== null) totalMs += Date.now() - qv.visibleSinceMs;
    const seconds = Math.round(totalMs / 1000);
    if (seconds >= 1) {
      batcher.record("question_time_spent", { question_number: qv.questionNumber, seconds });
    }
    questionViewRef.current = null;
  }, []);

  // Exposed to the exam page — call with the newly-active question's
  // number every time navigation happens. Finalizes and records whatever
  // question was previously active (if any) before starting the new one.
  const notifyActiveQuestion = useCallback((questionNumber: number | undefined) => {
    const batcher = batcherRef.current;
    if (!batcher) return;
    finalizeCurrentQuestionView(batcher);
    if (questionNumber !== undefined) {
      questionViewRef.current = {
        questionNumber,
        accumulatedMs: 0,
        visibleSinceMs: document.visibilityState === "visible" ? Date.now() : null,
      };
    }
  }, [finalizeCurrentQuestionView]);

  useEffect(() => {
    if (!sessionId) return;

    // Pick up whatever's already persisted for this session — including
    // from a tab that was closed and reopened, or a sibling tab already
    // open right now — rather than starting back at 0.
    setTabSwitchCount(readCount(sessionId, "tab_switch"));
    setFullscreenExitCount(readCount(sessionId, "fullscreen_exit"));
    setScreenshotAttempts(0); // never persisted — see the doc comment above

    const batcher = new ActivityLogBatcher(sessionId);
    batcherRef.current = batcher;
    batcher.start();

    const onVisibilityChange = () => {
      const qv = questionViewRef.current;
      if (document.visibilityState === "hidden") {
        batcher.record("tab_switch");
        setTabSwitchCount(incrementCount(sessionId, "tab_switch"));
        // Pause question-view accumulation — time spent away from the tab
        // must not count toward whichever question happened to be active.
        if (qv && qv.visibleSinceMs !== null) {
          qv.accumulatedMs += Date.now() - qv.visibleSinceMs;
          qv.visibleSinceMs = null;
        }
      } else if (qv && qv.visibleSinceMs === null) {
        qv.visibleSinceMs = Date.now(); // resume
      }
    };
    const onBlur = () => batcher.record("window_blur");
    const onFullscreenChange = () => {
      const fs = !!document.fullscreenElement;
      setIsFullscreen(fs);
      if (!fs) {
        batcher.record("fullscreen_exit");
        setFullscreenExitCount(incrementCount(sessionId, "fullscreen_exit"));
      }
    };
    const onCopy = (e: ClipboardEvent) => { e.preventDefault(); batcher.record("copy"); };
    const onPaste = (e: ClipboardEvent) => { e.preventDefault(); batcher.record("paste"); };
    const onContextMenu = () => batcher.record("contextmenu");
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "PrintScreen") {
        setScreenshotAttempts(c => c + 1);
        batcher.record("screenshot_attempt");
      }
    };
    const onOffline = () => {
      offlineSinceRef.current = new Date();
    };
    const onOnline = () => {
      const since = offlineSinceRef.current;
      if (!since) return; // "online" without a preceding "offline" (e.g. initial load) — nothing to report
      offlineSinceRef.current = null;
      const durationSeconds = Math.round((Date.now() - since.getTime()) / 1000);
      batcher.record("connection_lost", { duration_seconds: durationSeconds }, since);
    };
    // Fires in every OTHER tab (never the one that made the write) when
    // localStorage changes — this is what keeps a sibling tab's displayed
    // count (and therefore its own lockout threshold check) in sync with
    // one this tab just incremented, instead of only updating on its own
    // next unrelated re-render.
    const onStorage = (e: StorageEvent) => {
      if (e.key === countStorageKey(sessionId, "tab_switch")) {
        setTabSwitchCount(readCount(sessionId, "tab_switch"));
      } else if (e.key === countStorageKey(sessionId, "fullscreen_exit")) {
        setFullscreenExitCount(readCount(sessionId, "fullscreen_exit"));
      }
    };

    document.addEventListener("visibilitychange", onVisibilityChange);
    window.addEventListener("blur", onBlur);
    document.addEventListener("fullscreenchange", onFullscreenChange);
    document.addEventListener("copy", onCopy);
    document.addEventListener("paste", onPaste);
    document.addEventListener("contextmenu", onContextMenu);
    document.addEventListener("keydown", onKeyDown);
    window.addEventListener("storage", onStorage);
    window.addEventListener("offline", onOffline);
    window.addEventListener("online", onOnline);

    setIsFullscreen(!!document.fullscreenElement);
    if (typeof navigator !== "undefined" && navigator.onLine === false) {
      offlineSinceRef.current = new Date(); // page loaded already offline
    }

    return () => {
      document.removeEventListener("visibilitychange", onVisibilityChange);
      window.removeEventListener("blur", onBlur);
      document.removeEventListener("fullscreenchange", onFullscreenChange);
      document.removeEventListener("copy", onCopy);
      document.removeEventListener("paste", onPaste);
      document.removeEventListener("contextmenu", onContextMenu);
      document.removeEventListener("keydown", onKeyDown);
      window.removeEventListener("storage", onStorage);
      window.removeEventListener("offline", onOffline);
      window.removeEventListener("online", onOnline);
      // Flushes whatever question was active when the session ended
      // (submit, auto-submit, or an in-app navigation away) — otherwise
      // the last question's time would never be recorded at all, since
      // there's no "next" navigation to trigger it via notifyActiveQuestion.
      finalizeCurrentQuestionView(batcher);
      batcher.stop();
      batcherRef.current = null;
      // Deliberately does NOT clear the persisted counts here — this
      // cleanup also runs on an ordinary in-app navigation away from a
      // still-IN_PROGRESS exam (a route change unmounts the component even
      // though the exam itself isn't over), and clearing on every unmount
      // would silently undo the whole point of persisting these in the
      // first place. Only clearExamViolationCounts (called explicitly by
      // the exam page once it confirms a real terminal session status)
      // ever removes them.
    };
  }, [sessionId, finalizeCurrentQuestionView]);

  // Explicitly rejects when the API doesn't exist at all (rather than
  // `?.()` silently resolving to undefined) — callers doing
  // `await requestFullscreen()` inside a try/catch (the exam page's entry
  // gate) need an unsupported browser to land in the catch branch exactly
  // like a denied permission does, not fall through as if it succeeded.
  const requestFullscreen = (): Promise<void> => {
    if (!document.documentElement.requestFullscreen) {
      return Promise.reject(new Error("Fullscreen API not supported"));
    }
    return document.documentElement.requestFullscreen();
  };

  return {
    isFullscreen, requestFullscreen,
    tabSwitchCount, fullscreenExitCount, screenshotAttempts,
    notifyActiveQuestion,
  };
}
