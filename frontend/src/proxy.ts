import { NextRequest, NextResponse } from "next/server";
import { PORTAL_LOGIN_BY_PREFIX, isValidRole } from "@/lib/portalRouting";

export { isValidRole };

// Modules relocated to another portal (2026-08-18), or removed from a portal
// entirely (2026-08-19: Students dropped from Admin — Batches alone remains).
// Old bookmarks/links land here first, before any auth check.
const MOVED_PATHS: Record<string, string> = {
  "/super-admin/dlq": "/it/dlq",
  "/admin/inquiries": "/it/inquiries",
  "/admin/students": "/admin/batch",
  "/super-admin/students": "/super-admin/batches",
  "/super-admin/it-accounts": "/super-admin/overview",
};

// Login pages — always rendered, never redirected away from here. The
// "already logged in in this tab, skip the form" decision moved client-side
// (PortalLoginForm.tsx / students/login/page.tsx) — see the block comment
// below for why it can no longer live in this file.
const LOGIN_PATHS = new Set([
  "/admin/login", "/students/login", "/super-admin/login", "/it/login",
]);

/**
 * Coarse, browser-wide gate only (rewritten 2026-08-27).
 *
 * Before this rewrite, this middleware also decided "does this cookie's
 * role match the portal being requested" and "is this an authenticated
 * user hitting a login page, bounce them to their own home" — both read
 * the `aptlogic_role`/`aptlogic_access` cookies. That broke simultaneous
 * multi-tab use: cookies are shared across every tab of the same
 * browser/origin, but the actual auth state (Zustand + sessionStorage, see
 * auth-store.ts) is genuinely per-tab by design. An admin tab and a
 * student tab open side by side would fight over what the shared cookie
 * says — logging into the second tab overwrites it for both — so the
 * *other*, earlier tab would get redirected to the wrong portal on its
 * very next navigation (middleware runs on every client-side transition
 * too, not just full page loads).
 *
 * The fix: this middleware now only asks "is there ANY session cookie at
 * all" for a *protected, non-login* portal path — enough to keep a fully
 * anonymous, never-logged-in-anywhere visitor from seeing a flash of
 * protected chrome before client JS can react, which a pure client-side
 * guard can't prevent on its own. It never inspects *which* role the
 * cookie claims. The real per-tab enforcement — "does THIS tab's own
 * session match THIS portal" and "THIS tab is already logged in, skip the
 * login form" — moved to usePortalGuard.ts (used by every portal layout)
 * and to PortalLoginForm.tsx / students/login/page.tsx respectively, both
 * reading the tab-local Zustand store instead of the shared cookie.
 */
export function proxy(request: NextRequest) {
  const { pathname } = request.nextUrl;

  const movedTo = MOVED_PATHS[pathname];
  if (movedTo) {
    return NextResponse.redirect(new URL(movedTo, request.url));
  }

  const portalPrefix = Object.keys(PORTAL_LOGIN_BY_PREFIX).find(
    (prefix) => pathname === prefix || pathname.startsWith(prefix + "/")
  );
  if (!portalPrefix) {
    return NextResponse.next();
  }

  if (LOGIN_PATHS.has(pathname)) {
    return NextResponse.next();
  }

  const hasAnySession = !!request.cookies.get("aptlogic_access")?.value;
  if (!hasAnySession) {
    return NextResponse.redirect(new URL(PORTAL_LOGIN_BY_PREFIX[portalPrefix], request.url));
  }

  return NextResponse.next();
}

export const config = {
  matcher: [
    // Exclude Next.js internals, API routes, and static assets
    "/((?!_next/static|_next/image|favicon\\.ico|api/).*)",
  ],
};

// Alias for test compatibility — tests import { middleware } from "../proxy"
export { proxy as middleware };
