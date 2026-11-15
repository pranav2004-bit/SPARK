"use client";

import { useEffect } from "react";

/**
 * Recovers from a stale-deployment asset mismatch (added 2026-11-15,
 * production-readiness audit).
 *
 * Every Vercel deploy ships CSS/JS files under a new content hash and
 * deletes the previous build's files. A tab left open across a deploy
 * still references the OLD hashed filenames — its next in-app navigation
 * (or a lazy-loaded chunk) requests a file that no longer exists on the
 * server. For a missing stylesheet this fails silently (the browser just
 * never applies it — the page renders real content with zero layout/
 * colour, "CSS is breaking, only text visible"); for a missing JS chunk it
 * throws a catchable ChunkLoadError. A hard refresh always fixes it
 * instantly, because that's a fresh document load against the CURRENT
 * build's manifest — this just does that refresh automatically instead of
 * leaving a student staring at a broken-looking page.
 *
 * `error` events from a failed <link>/<script> don't bubble, so they're
 * only observable via a capturing listener on window.
 */
export function StaleAssetReloader() {
  useEffect(() => {
    if (typeof window === "undefined") return;

    const RELOAD_KEY = "spark_stale_asset_reload_at";
    // Guards against a tight reload loop if the asset is STILL missing
    // right after reloading (a genuine, unrelated server/network outage,
    // not a stale deploy) — but still allows a real reload again much
    // later, for a second, genuinely new deploy during a long-lived tab
    // (an hours-long exam session included).
    const MIN_GAP_MS = 10_000;

    function reloadOnce() {
      const last = Number(sessionStorage.getItem(RELOAD_KEY) ?? 0);
      if (Date.now() - last < MIN_GAP_MS) return;
      sessionStorage.setItem(RELOAD_KEY, String(Date.now()));
      window.location.reload();
    }

    function isNextStaticAsset(url: string | undefined | null): boolean {
      return !!url && url.includes("/_next/static/");
    }

    function handleResourceError(event: Event) {
      const target = event.target;
      if (!(target instanceof HTMLElement)) return;
      if (target instanceof HTMLLinkElement && target.rel === "stylesheet" && isNextStaticAsset(target.href)) {
        reloadOnce();
      } else if (target instanceof HTMLScriptElement && isNextStaticAsset(target.src)) {
        reloadOnce();
      }
    }

    function handleChunkRejection(event: PromiseRejectionEvent) {
      const reason = event.reason as { name?: string; message?: string } | undefined;
      const name = reason?.name ?? "";
      const message = String(reason?.message ?? "");
      if (name === "ChunkLoadError" || /loading (chunk|css chunk)/i.test(message)) {
        reloadOnce();
      }
    }

    window.addEventListener("error", handleResourceError, true);
    window.addEventListener("unhandledrejection", handleChunkRejection);
    return () => {
      window.removeEventListener("error", handleResourceError, true);
      window.removeEventListener("unhandledrejection", handleChunkRejection);
    };
  }, []);

  return null;
}
