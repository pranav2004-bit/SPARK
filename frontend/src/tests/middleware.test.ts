/**
 * Unit tests for middleware routing logic.
 * next/server is mocked — these tests exercise the pure decision logic only.
 *
 * Rewritten 2026-08-27 alongside proxy.ts's own rewrite: this middleware
 * used to also decide "does this cookie's role match the requested portal"
 * and "is this cookie's role already authenticated, bounce away from the
 * login page" — both broke simultaneous multi-tab use, since the
 * aptlogic_role/aptlogic_access cookies are shared across every tab of the
 * same browser/origin while the real auth state (sessionStorage) is
 * tab-isolated. Those two decisions moved client-side (usePortalGuard.ts,
 * PortalLoginForm.tsx / students/login/page.tsx) and are covered by their
 * own test files, not this one. This file now only proves the coarse gate
 * that's left: unauthenticated-anywhere visitors get redirected away from
 * protected paths, and a cookie of ANY role is enough to pass through
 * (role-matching is explicitly no longer this layer's job — see the
 * "Coarse gate — role no longer checked here" block below, which exists
 * specifically to guard against silently reintroducing the old bug).
 */

const redirectCalls: string[] = [];
const nextCalls: number[] = [];

jest.mock("next/server", () => ({
  NextResponse: {
    redirect: (url: URL) => {
      redirectCalls.push(url instanceof URL ? url.pathname : String(url));
      return { type: "redirect" };
    },
    next: () => {
      nextCalls.push(1);
      return { type: "next" };
    },
  },
}));

import { middleware, isValidRole, config } from "../proxy";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function req(pathname: string, cookies: Record<string, string> = {}) {
  return {
    nextUrl: { pathname },
    url: `http://localhost${pathname}`,
    cookies: {
      get: (name: string) => {
        const v = cookies[name];
        return v !== undefined ? { name, value: v } : undefined;
      },
    },
  } as unknown as Parameters<typeof middleware>[0];
}

function lastRedirect() {
  return redirectCalls[redirectCalls.length - 1];
}

function wasAllowed() {
  return nextCalls.length > 0;
}

beforeEach(() => {
  redirectCalls.length = 0;
  nextCalls.length = 0;
});

// ---------------------------------------------------------------------------
// isValidRole helper (re-exported from lib/portalRouting, still used by
// server-side JWT payload validation elsewhere — kept, still exported)
// ---------------------------------------------------------------------------

describe("isValidRole", () => {
  it("accepts valid roles", () => {
    expect(isValidRole("admin")).toBe(true);
    expect(isValidRole("student")).toBe(true);
    expect(isValidRole("super_admin")).toBe(true);
    expect(isValidRole("it")).toBe(true);
  });

  it("rejects invalid roles", () => {
    expect(isValidRole("superadmin")).toBe(false);
    expect(isValidRole("root")).toBe(false);
    expect(isValidRole("")).toBe(false);
  });
});

// ---------------------------------------------------------------------------
// Public routes pass through (smoke + sanity)
// ---------------------------------------------------------------------------

describe("Public routes", () => {
  it("allows unauthenticated access to /", () => {
    middleware(req("/"));
    expect(wasAllowed()).toBe(true);
    expect(redirectCalls.length).toBe(0);
  });

  it("allows unauthenticated access to /about", () => {
    middleware(req("/about"));
    expect(wasAllowed()).toBe(true);
  });
});

// ---------------------------------------------------------------------------
// Login pages always render — no cookie-based redirect either direction.
// This is the direct fix for the cross-tab bug: opening e.g.
// /students/login in a fresh tab must show the student login form even if
// a DIFFERENT tab's more recent login left an admin cookie set in this
// same browser. The "already logged in in THIS tab, skip the form" case
// is handled client-side instead (see PortalLoginForm.test.tsx /
// studentLoginPage.test.tsx), never here.
// ---------------------------------------------------------------------------

describe("Login pages always render, regardless of any cookie", () => {
  it("allows /admin/login with no cookie", () => {
    middleware(req("/admin/login"));
    expect(wasAllowed()).toBe(true);
    expect(redirectCalls.length).toBe(0);
  });

  it("allows /students/login with no cookie", () => {
    middleware(req("/students/login"));
    expect(wasAllowed()).toBe(true);
  });

  it("allows /super-admin/login with no cookie", () => {
    middleware(req("/super-admin/login"));
    expect(wasAllowed()).toBe(true);
  });

  it("allows /it/login with no cookie", () => {
    middleware(req("/it/login"));
    expect(wasAllowed()).toBe(true);
  });

  it("allows /admin/login even with an admin cookie already set (used to redirect away)", () => {
    middleware(req("/admin/login", { aptlogic_role: "admin", aptlogic_access: "tok" }));
    expect(wasAllowed()).toBe(true);
    expect(redirectCalls.length).toBe(0);
  });

  it("allows /students/login even with a DIFFERENT role's cookie set (the cross-tab bug) — a fresh student tab must still see the student form, not get bounced to the admin cookie's home", () => {
    middleware(req("/students/login", { aptlogic_role: "admin", aptlogic_access: "tok" }));
    expect(wasAllowed()).toBe(true);
    expect(redirectCalls.length).toBe(0);
  });
});

// ---------------------------------------------------------------------------
// Unauthenticated (zero session cookie) portal access → redirect to login
// ---------------------------------------------------------------------------

describe("Unauthenticated portal access", () => {
  it("redirects /admin/resources to /admin/login when no cookie", () => {
    middleware(req("/admin/resources"));
    expect(lastRedirect()).toBe("/admin/login");
  });

  it("redirects /students/practice to /students/login when no cookie", () => {
    middleware(req("/students/practice"));
    expect(lastRedirect()).toBe("/students/login");
  });

  it("redirects /super-admin/overview to /super-admin/login when no cookie", () => {
    middleware(req("/super-admin/overview"));
    expect(lastRedirect()).toBe("/super-admin/login");
  });

  it("redirects /it/welcome to /it/login when no cookie", () => {
    middleware(req("/it/welcome"));
    expect(lastRedirect()).toBe("/it/login");
  });

  it("redirects /admin/batch to /admin/login when only aptlogic_role is set but aptlogic_access is missing", () => {
    // The coarse gate checks aptlogic_access specifically (the token cookie,
    // not the role cookie) — a role cookie alone without an access token
    // is not a real session.
    middleware(req("/admin/batch", { aptlogic_role: "admin" }));
    expect(lastRedirect()).toBe("/admin/login");
  });
});

// ---------------------------------------------------------------------------
// Coarse gate — role no longer checked here (the actual fix). Any session
// cookie at all is enough to pass the middleware layer for ANY portal path;
// per-tab role enforcement happens client-side (usePortalGuard). These
// tests exist specifically to catch a regression back to the old
// cross-tab-breaking behavior, not because a wrong-role cookie passing
// through here is desirable on its own — it's the necessary consequence of
// fixing multi-tab support, corrected one layer down instead.
// ---------------------------------------------------------------------------

describe("Coarse gate — role no longer checked here", () => {
  it("allows a student cookie through to /admin/resources (client-side guard corrects it)", () => {
    middleware(req("/admin/resources", { aptlogic_role: "student", aptlogic_access: "tok" }));
    expect(wasAllowed()).toBe(true);
    expect(redirectCalls.length).toBe(0);
  });

  it("allows an admin cookie through to /students/home", () => {
    middleware(req("/students/home", { aptlogic_role: "admin", aptlogic_access: "tok" }));
    expect(wasAllowed()).toBe(true);
    expect(redirectCalls.length).toBe(0);
  });

  it("allows a garbage/unrecognised role cookie through, as long as an access token exists", () => {
    middleware(req("/admin/batch", { aptlogic_role: "hacker", aptlogic_access: "tok" }));
    expect(wasAllowed()).toBe(true);
    expect(redirectCalls.length).toBe(0);
  });

  it("allows the matching role's own portal through too (unchanged, just no longer the point of this layer)", () => {
    middleware(req("/admin/resources", { aptlogic_role: "admin", aptlogic_access: "tok" }));
    expect(wasAllowed()).toBe(true);
    expect(redirectCalls.length).toBe(0);
  });
});

// ---------------------------------------------------------------------------
// Middleware config (matcher) is correctly defined
// ---------------------------------------------------------------------------

describe("Middleware config", () => {
  it("exports a config object with a matcher array", () => {
    expect(config).toBeDefined();
    expect(Array.isArray(config.matcher)).toBe(true);
    expect(config.matcher.length).toBeGreaterThan(0);
  });

  it("matcher pattern excludes _next/static paths", () => {
    const pattern = config.matcher[0];
    expect(typeof pattern === "string" ? pattern : "").toContain("_next/static");
  });

  it("matcher pattern excludes api paths", () => {
    const pattern = config.matcher[0];
    expect(typeof pattern === "string" ? pattern : "").toContain("api/");
  });
});

// ---------------------------------------------------------------------------
// Moved modules — old URLs redirect to their new location (2026-08-18:
// Dead Letter Queue moved Super Admin -> IT, Inquiries moved Admin -> IT).
// Unaffected by the coarse-gate rewrite — this redirect runs before any
// auth check either way.
// ---------------------------------------------------------------------------

describe("Moved-module redirects", () => {
  it("redirects /super-admin/dlq to /it/dlq for an unauthenticated visitor", () => {
    middleware(req("/super-admin/dlq"));
    expect(lastRedirect()).toBe("/it/dlq");
  });

  it("redirects /admin/inquiries to /it/inquiries for an unauthenticated visitor", () => {
    middleware(req("/admin/inquiries"));
    expect(lastRedirect()).toBe("/it/inquiries");
  });

  it("redirects /super-admin/dlq to /it/dlq even with a cookie present", () => {
    middleware(req("/super-admin/dlq", { aptlogic_role: "super_admin", aptlogic_access: "tok" }));
    expect(lastRedirect()).toBe("/it/dlq");
  });

  it("redirects /admin/inquiries to /it/inquiries even with a cookie present", () => {
    middleware(req("/admin/inquiries", { aptlogic_role: "admin", aptlogic_access: "tok" }));
    expect(lastRedirect()).toBe("/it/inquiries");
  });

  it("does not redirect the new IT paths themselves", () => {
    middleware(req("/it/dlq", { aptlogic_role: "it", aptlogic_access: "tok" }));
    expect(wasAllowed()).toBe(true);
    expect(redirectCalls.length).toBe(0);
  });

  it("a second request to the moved path (any role's cookie) just passes through — role-based bouncing moved client-side, no longer a middleware concern", () => {
    middleware(req("/super-admin/dlq", { aptlogic_role: "super_admin", aptlogic_access: "tok" }));
    expect(lastRedirect()).toBe("/it/dlq");
    // Second request: the browser now requests /it/dlq directly. Under the
    // old behavior this would bounce a super_admin cookie back to
    // /super-admin/overview; now it's just allowed through (ITLayout's own
    // usePortalGuard("it") is what actually redirects a wrong-role TAB).
    middleware(req("/it/dlq", { aptlogic_role: "super_admin", aptlogic_access: "tok" }));
    expect(wasAllowed()).toBe(true);
  });

  // Students dropped from Admin entirely (2026-08-19) — unlike DLQ/Inquiries,
  // there's no equivalent Admin page to land on, so old bookmarks land back
  // on Admin's own remaining module (Batches), not on another portal.
  it("redirects /admin/students to /admin/batch for an unauthenticated visitor", () => {
    middleware(req("/admin/students"));
    expect(lastRedirect()).toBe("/admin/batch");
  });

  it("redirects /admin/students to /admin/batch even with a cookie present", () => {
    middleware(req("/admin/students", { aptlogic_role: "admin", aptlogic_access: "tok" }));
    expect(lastRedirect()).toBe("/admin/batch");
  });

  it("a second request to the moved path just passes through", () => {
    middleware(req("/admin/students", { aptlogic_role: "admin", aptlogic_access: "tok" }));
    expect(lastRedirect()).toBe("/admin/batch");
    middleware(req("/admin/batch", { aptlogic_role: "admin", aptlogic_access: "tok" }));
    expect(wasAllowed()).toBe(true);
  });

  // Students also dropped from Super Admin (2026-08-19) — same reasoning
  // and same redirect target pattern as Admin, just a different portal.
  it("redirects /super-admin/students to /super-admin/batches for an unauthenticated visitor", () => {
    middleware(req("/super-admin/students"));
    expect(lastRedirect()).toBe("/super-admin/batches");
  });

  it("redirects /super-admin/students to /super-admin/batches even with a cookie present", () => {
    middleware(req("/super-admin/students", { aptlogic_role: "super_admin", aptlogic_access: "tok" }));
    expect(lastRedirect()).toBe("/super-admin/batches");
  });

  it("a second request to the moved path just passes through", () => {
    middleware(req("/super-admin/students", { aptlogic_role: "super_admin", aptlogic_access: "tok" }));
    expect(lastRedirect()).toBe("/super-admin/batches");
    middleware(req("/super-admin/batches", { aptlogic_role: "super_admin", aptlogic_access: "tok" }));
    expect(wasAllowed()).toBe(true);
  });

  // "IT Accounts" removed from Super Admin entirely (2026-08-20) — IT is now
  // the bootstrapped root and Super Admin no longer manages IT accounts at
  // all, so old bookmarks land on Super Admin's own portal home rather than
  // another module (there's no equivalent page left in this portal).
  it("redirects /super-admin/it-accounts to /super-admin/overview for an unauthenticated visitor", () => {
    middleware(req("/super-admin/it-accounts"));
    expect(lastRedirect()).toBe("/super-admin/overview");
  });

  it("redirects /super-admin/it-accounts to /super-admin/overview even with a cookie present", () => {
    middleware(req("/super-admin/it-accounts", { aptlogic_role: "super_admin", aptlogic_access: "tok" }));
    expect(lastRedirect()).toBe("/super-admin/overview");
  });

  it("a second request to the moved path just passes through", () => {
    middleware(req("/super-admin/it-accounts", { aptlogic_role: "super_admin", aptlogic_access: "tok" }));
    expect(lastRedirect()).toBe("/super-admin/overview");
    middleware(req("/super-admin/overview", { aptlogic_role: "super_admin", aptlogic_access: "tok" }));
    expect(wasAllowed()).toBe(true);
  });
});
