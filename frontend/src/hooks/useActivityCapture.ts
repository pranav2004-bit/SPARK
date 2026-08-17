"use client";

import { useEffect, useRef, useState } from "react";
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
 * prevention. Reported here as a live count, not sent to the backend
 * (ActivityLog's event_type choices don't include it — this is a
 * client-only UX warning, not a new audit-trail signal).
 */
export function useActivityCapture(sessionId: string | null) {
  const batcherRef = useRef<ActivityLogBatcher | null>(null);
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [tabSwitchCount, setTabSwitchCount] = useState(0);
  const [fullscreenExitCount, setFullscreenExitCount] = useState(0);
  const [screenshotAttempts, setScreenshotAttempts] = useState(0);

  useEffect(() => {
    if (!sessionId) return;

    // Fresh counts for this session — guards against stale counts carrying
    // over if this hook is ever reused across two different sessionIds in
    // the same mounted component instance.
    setTabSwitchCount(0);
    setFullscreenExitCount(0);
    setScreenshotAttempts(0);

    const batcher = new ActivityLogBatcher(sessionId);
    batcherRef.current = batcher;
    batcher.start();

    const onVisibilityChange = () => {
      if (document.visibilityState === "hidden") {
        batcher.record("tab_switch");
        setTabSwitchCount(c => c + 1);
      }
    };
    const onBlur = () => batcher.record("window_blur");
    const onFullscreenChange = () => {
      const fs = !!document.fullscreenElement;
      setIsFullscreen(fs);
      if (!fs) {
        batcher.record("fullscreen_exit");
        setFullscreenExitCount(c => c + 1);
      }
    };
    const onCopy = (e: ClipboardEvent) => { e.preventDefault(); batcher.record("copy"); };
    const onPaste = (e: ClipboardEvent) => { e.preventDefault(); batcher.record("paste"); };
    const onContextMenu = () => batcher.record("contextmenu");
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "PrintScreen") setScreenshotAttempts(c => c + 1);
    };

    document.addEventListener("visibilitychange", onVisibilityChange);
    window.addEventListener("blur", onBlur);
    document.addEventListener("fullscreenchange", onFullscreenChange);
    document.addEventListener("copy", onCopy);
    document.addEventListener("paste", onPaste);
    document.addEventListener("contextmenu", onContextMenu);
    document.addEventListener("keydown", onKeyDown);

    setIsFullscreen(!!document.fullscreenElement);

    return () => {
      document.removeEventListener("visibilitychange", onVisibilityChange);
      window.removeEventListener("blur", onBlur);
      document.removeEventListener("fullscreenchange", onFullscreenChange);
      document.removeEventListener("copy", onCopy);
      document.removeEventListener("paste", onPaste);
      document.removeEventListener("contextmenu", onContextMenu);
      document.removeEventListener("keydown", onKeyDown);
      batcher.stop();
      batcherRef.current = null;
    };
  }, [sessionId]);

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
  };
}
