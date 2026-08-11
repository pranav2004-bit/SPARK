/**
 * scrollRedirect — sessionStorage helper for post-login deep-link flow.
 *
 * When an unauthenticated user clicks a scroll update link we can't navigate
 * them directly there. Instead we:
 *   1. save(path) — store the intended path
 *   2. Redirect to /students/login
 *   3. After login (or after profile setup), consume() to get the path back
 *      and navigate there. consume() deletes the entry so it fires only once.
 *
 * Security: consume() validates the saved path is a student route before
 * returning it, so an attacker who manipulates sessionStorage cannot redirect
 * a freshly-logged-in student to /admin/...
 */

const KEY = "spark.scroll.redirect";

/** Persist an intended destination path for use after login. */
export function saveScrollRedirect(path: string): void {
  if (typeof window === "undefined") return;
  try {
    sessionStorage.setItem(KEY, path);
  } catch {
    // Storage unavailable (private mode quirk) — silently ignore
  }
}

/**
 * Read and remove the saved redirect.
 * Returns the path only if it is a valid, same-origin /students/ route.
 * Returns null if nothing is saved or validation fails.
 */
export function consumeScrollRedirect(): string | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = sessionStorage.getItem(KEY);
    if (!raw) return null;
    sessionStorage.removeItem(KEY);

    // Normalise: accept both "/students/..." and "http://localhost/students/..."
    let pathname = raw;
    try {
      const u = new URL(raw, window.location.origin);
      // Reject cross-origin URLs entirely
      if (u.origin !== window.location.origin) return null;
      pathname = u.pathname;
    } catch {
      // raw was already a relative path — use as-is
    }

    // Only allow student-module pages
    if (!pathname.startsWith("/students/")) return null;
    // Block sensitive student sub-routes if any are added later
    if (pathname.startsWith("/students/login")) return null;

    return pathname;
  } catch {
    return null;
  }
}
