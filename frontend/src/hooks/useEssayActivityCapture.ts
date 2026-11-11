"use client";

import { useEffect, useRef, useState } from "react";
import { EssayMalpracticeBatcher } from "@/lib/essayMalpracticeBatcher";

/**
 * useEssayActivityCapture — Task 4.3's client-side integrity capture,
 * adapted from assessment-service's useActivityCapture.ts (reused
 * fullscreen-lockdown/tab-switch behavior, per this task's own
 * instruction), scoped down for essay-writing's single-question shape:
 *
 *   - No question_time_spent/notifyActiveQuestion — that signal is
 *     meaningful across *multiple* questions per session; a single-question
 *     essay attempt has nothing to compare per-question time against, so
 *     it's dropped rather than kept as dead weight.
 *   - No connection_lost event — essay-service's own network resilience is
 *     essayDraftQueue.ts's autosave queue (Task 4.2's actual requirement),
 *     not an audit-log event; adding one anyway wasn't asked for here.
 *   - Paste is actively BLOCKED (preventDefault) and reported as
 *     "paste_attempt", not the generic "paste" — Task 4.3's explicit,
 *     essay-specific addition: pasting into a free-text response is a much
 *     stronger integrity signal than in an MCQ exam, which has no
 *     free-text field to paste into at all.
 *
 * tabSwitchCount/fullscreenExitCount are persisted to localStorage, keyed
 * by attemptId — same reasoning as the original: a pure in-memory count
 * resets the instant the tab closes, letting a student dodge the
 * client-side lockout by opening a fresh tab. The server-side malpractice
 * flag (scoring.py) is never fooled by this either way, since it's
 * computed from the cumulative EssayMalpracticeEvent rows against the one
 * shared attempt, not a per-tab count.
 */

function countStorageKey(attemptId: string, kind: "tab_switch" | "fullscreen_exit"): string {
  return `aptlogic_essay_violation_count_${kind}_${attemptId}`;
}

function readCount(attemptId: string, kind: "tab_switch" | "fullscreen_exit"): number {
  if (typeof window === "undefined") return 0;
  const raw = window.localStorage.getItem(countStorageKey(attemptId, kind));
  const n = raw ? parseInt(raw, 10) : 0;
  return Number.isFinite(n) && n >= 0 ? n : 0;
}

function incrementCount(attemptId: string, kind: "tab_switch" | "fullscreen_exit"): number {
  const next = readCount(attemptId, kind) + 1;
  window.localStorage.setItem(countStorageKey(attemptId, kind), String(next));
  return next;
}

/** Called once an attempt has genuinely reached a terminal status
 * (SUBMITTED/AUTO_SUBMITTED) — the one point it's safe to stop tracking. */
export function clearEssayViolationCounts(attemptId: string): void {
  if (typeof window === "undefined") return;
  window.localStorage.removeItem(countStorageKey(attemptId, "tab_switch"));
  window.localStorage.removeItem(countStorageKey(attemptId, "fullscreen_exit"));
}

export function useEssayActivityCapture(attemptId: string | null) {
  const batcherRef = useRef<EssayMalpracticeBatcher | null>(null);
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [tabSwitchCount, setTabSwitchCount] = useState(0);
  const [fullscreenExitCount, setFullscreenExitCount] = useState(0);
  const [pasteAttempts, setPasteAttempts] = useState(0);

  useEffect(() => {
    if (!attemptId) return;

    setTabSwitchCount(readCount(attemptId, "tab_switch"));
    setFullscreenExitCount(readCount(attemptId, "fullscreen_exit"));
    setPasteAttempts(0); // never persisted — same convention as screenshotAttempts in the original

    const batcher = new EssayMalpracticeBatcher(attemptId);
    batcherRef.current = batcher;
    batcher.start();

    const onVisibilityChange = () => {
      if (document.visibilityState === "hidden") {
        batcher.record("tab_switch");
        setTabSwitchCount(incrementCount(attemptId, "tab_switch"));
      }
    };
    const onBlur = () => batcher.record("window_blur");
    const onFullscreenChange = () => {
      const fs = !!document.fullscreenElement;
      setIsFullscreen(fs);
      if (!fs) {
        batcher.record("fullscreen_exit");
        setFullscreenExitCount(incrementCount(attemptId, "fullscreen_exit"));
      }
    };
    const onCopy = (e: ClipboardEvent) => { e.preventDefault(); batcher.record("copy"); };
    const onPaste = (e: ClipboardEvent) => {
      e.preventDefault();
      setPasteAttempts(c => c + 1);
      batcher.record("paste_attempt");
    };
    const onContextMenu = () => batcher.record("contextmenu");
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "PrintScreen") batcher.record("screenshot_attempt");
    };
    const onStorage = (e: StorageEvent) => {
      if (e.key === countStorageKey(attemptId, "tab_switch")) {
        setTabSwitchCount(readCount(attemptId, "tab_switch"));
      } else if (e.key === countStorageKey(attemptId, "fullscreen_exit")) {
        setFullscreenExitCount(readCount(attemptId, "fullscreen_exit"));
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

    setIsFullscreen(!!document.fullscreenElement);

    return () => {
      document.removeEventListener("visibilitychange", onVisibilityChange);
      window.removeEventListener("blur", onBlur);
      document.removeEventListener("fullscreenchange", onFullscreenChange);
      document.removeEventListener("copy", onCopy);
      document.removeEventListener("paste", onPaste);
      document.removeEventListener("contextmenu", onContextMenu);
      document.removeEventListener("keydown", onKeyDown);
      window.removeEventListener("storage", onStorage);
      batcher.stop();
      batcherRef.current = null;
      // Deliberately does NOT clear persisted counts here — same reasoning
      // as the original: this cleanup also runs on an ordinary in-app
      // navigation away from a still-IN_PROGRESS attempt, not just a real
      // submit. Only clearEssayViolationCounts (called explicitly once a
      // terminal status is confirmed) removes them.
    };
  }, [attemptId]);

  const requestFullscreen = (): Promise<void> => {
    if (!document.documentElement.requestFullscreen) {
      return Promise.reject(new Error("Fullscreen API not supported"));
    }
    return document.documentElement.requestFullscreen();
  };

  return { isFullscreen, requestFullscreen, tabSwitchCount, fullscreenExitCount, pasteAttempts };
}
