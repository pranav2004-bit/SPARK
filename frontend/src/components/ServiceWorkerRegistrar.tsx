"use client";

import { useEffect } from "react";

/**
 * Registers the SPARK service worker once the page is fully loaded.
 * Drop this inside the root layout — it renders nothing visible.
 */
export function ServiceWorkerRegistrar() {
  useEffect(() => {
    if (typeof window === "undefined") return;
    if (!("serviceWorker" in navigator)) return;

    const register = () => {
      navigator.serviceWorker
        .register("/sw.js")
        .catch((err) => {
          // Silently ignore registration failures in development or
          // when running on http:// (service workers require https or localhost)
          if (process.env.NODE_ENV === "development") {
            console.debug("[SW] Registration skipped:", err.message);
          }
        });
    };

    // Defer registration until after load so it never blocks the critical path
    if (document.readyState === "complete") {
      register();
    } else {
      window.addEventListener("load", register, { once: true });
    }
  }, []);

  return null;
}
