"use client";

import { useEffect, useRef, useState } from "react";
import { ActivityLogBatcher } from "@/lib/activityLogBatcher";

/**
 * useActivityCapture — wires up the DOM listeners for Task 6.1's anti-cheat
 * signals and batches them through ActivityLogBatcher. Also tracks
 * fullscreen state so the exam page can show a non-blocking re-prompt on
 * exit (a UX nudge, not a hard lock — per the spec, hard-blocking risks
 * locking a legitimate student out on a flaky browser).
 */
export function useActivityCapture(sessionId: string | null) {
  const batcherRef = useRef<ActivityLogBatcher | null>(null);
  const [isFullscreen, setIsFullscreen] = useState(false);

  useEffect(() => {
    if (!sessionId) return;

    const batcher = new ActivityLogBatcher(sessionId);
    batcherRef.current = batcher;
    batcher.start();

    const onVisibilityChange = () => {
      if (document.visibilityState === "hidden") batcher.record("tab_switch");
    };
    const onBlur = () => batcher.record("window_blur");
    const onFullscreenChange = () => {
      const fs = !!document.fullscreenElement;
      setIsFullscreen(fs);
      if (!fs) batcher.record("fullscreen_exit");
    };
    const onCopy = () => batcher.record("copy");
    const onPaste = () => batcher.record("paste");
    const onContextMenu = () => batcher.record("contextmenu");

    document.addEventListener("visibilitychange", onVisibilityChange);
    window.addEventListener("blur", onBlur);
    document.addEventListener("fullscreenchange", onFullscreenChange);
    document.addEventListener("copy", onCopy);
    document.addEventListener("paste", onPaste);
    document.addEventListener("contextmenu", onContextMenu);

    setIsFullscreen(!!document.fullscreenElement);

    return () => {
      document.removeEventListener("visibilitychange", onVisibilityChange);
      window.removeEventListener("blur", onBlur);
      document.removeEventListener("fullscreenchange", onFullscreenChange);
      document.removeEventListener("copy", onCopy);
      document.removeEventListener("paste", onPaste);
      document.removeEventListener("contextmenu", onContextMenu);
      batcher.stop();
      batcherRef.current = null;
    };
  }, [sessionId]);

  const requestFullscreen = () => {
    document.documentElement.requestFullscreen?.().catch(() => {
      // Fullscreen can be denied/unsupported (e.g. iframe restrictions,
      // some mobile browsers) — the prompt just stays dismissible, never
      // blocks the exam over it.
    });
  };

  return { isFullscreen, requestFullscreen };
}
