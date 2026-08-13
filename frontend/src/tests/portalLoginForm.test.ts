/**
 * Regression tests for Phase 6 login page config contracts + cookie helpers.
 *
 * Why these tests exist:
 *   Phase 6 refactored the admin login page (312-line inline → PortalLoginForm
 *   component) and created the super-admin login page. The auth-critical config
 *   (apiEndpoint, cookieRole, redirectTo, extraBody) is now extracted into
 *   exported constants so a wrong value is caught immediately by this test,
 *   rather than being silently wrong in production.
 *
 *   Additionally, setAuthCookies and clearAuthCookies are called by PortalLoginForm
 *   on every successful login and logout respectively — their correctness is
 *   foundational to the entire auth flow.
 *
 * What is tested:
 *   1. Admin login page config — apiEndpoint, cookieRole, redirectTo
 *   2. Super-admin login page config — apiEndpoint, cookieRole, redirectTo, extraBody
 *   3. setAuthCookies — writes aptlogic_role and aptlogic_access cookies
 *   4. clearAuthCookies — expires both cookies (max-age=0)
 *
 * Mock strategy:
 *   document.cookie is shimmed at module level for the Node.js test environment
 *   using a getter/setter that accumulates all cookie strings set during a test.
 *   This allows asserting cookie values without a browser or jsdom.
 */

// ── document.cookie shim for Node.js environment ──────────────────────────────

const cookieJar: string[] = [];

beforeAll(() => {
  Object.defineProperty(global, "document", {
    value: {
      get cookie() {
        return cookieJar.join("; ");
      },
      set cookie(v: string) {
        cookieJar.push(v);
      },
    },
    configurable: true,
    writable: true,
  });
});

beforeEach(() => {
  cookieJar.length = 0; // reset between tests
});

// ── Imports ───────────────────────────────────────────────────────────────────

import { ADMIN_LOGIN_CONFIG, SUPER_ADMIN_LOGIN_CONFIG } from "../lib/constants";
import { setAuthCookies, clearAuthCookies } from "../lib/cookies";

// ─────────────────────────────────────────────────────────────────────────────
// 1. Admin login page config contract
// ─────────────────────────────────────────────────────────────────────────────

describe("Admin login page config contract", () => {
  it("apiEndpoint is /auth/login/ (shared auth-service endpoint)", () => {
    expect(ADMIN_LOGIN_CONFIG.apiEndpoint).toBe("/auth/login/");
  });

  it("cookieRole is 'admin'", () => {
    expect(ADMIN_LOGIN_CONFIG.cookieRole).toBe("admin");
  });

  it("redirectTo is /admin/batch (the landing page after admin login)", () => {
    expect(ADMIN_LOGIN_CONFIG.redirectTo).toBe("/admin/batch");
  });

  it("extraBody sends role: admin to distinguish from other role logins", () => {
    expect(ADMIN_LOGIN_CONFIG.extraBody).toEqual({ role: "admin" });
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// 2. Super-admin login page config contract
// ─────────────────────────────────────────────────────────────────────────────

describe("Super-admin login page config contract", () => {
  it("apiEndpoint is /auth/login/ (shared auth-service endpoint)", () => {
    expect(SUPER_ADMIN_LOGIN_CONFIG.apiEndpoint).toBe("/auth/login/");
  });

  it("cookieRole is 'super_admin'", () => {
    expect(SUPER_ADMIN_LOGIN_CONFIG.cookieRole).toBe("super_admin");
  });

  it("redirectTo is /super-admin/overview", () => {
    expect(SUPER_ADMIN_LOGIN_CONFIG.redirectTo).toBe("/super-admin/overview");
  });

  it("extraBody sends role: super_admin to distinguish from other role logins", () => {
    expect(SUPER_ADMIN_LOGIN_CONFIG.extraBody).toEqual({ role: "super_admin" });
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// 3. setAuthCookies — called on every successful login
// ─────────────────────────────────────────────────────────────────────────────

describe("setAuthCookies", () => {
  it("writes aptlogic_role cookie with the correct role value", () => {
    setAuthCookies("admin", "tok_abc");
    expect(cookieJar.some((c) => c.includes("aptlogic_role=admin"))).toBe(true);
  });

  it("writes aptlogic_access cookie with the correct token value", () => {
    setAuthCookies("admin", "tok_abc");
    expect(cookieJar.some((c) => c.includes("aptlogic_access=tok_abc"))).toBe(true);
  });

  it("writes two cookies — one for role, one for access token", () => {
    setAuthCookies("super_admin", "tok_xyz");
    const roleSet = cookieJar.some((c) => c.includes("aptlogic_role=super_admin"));
    const tokenSet = cookieJar.some((c) => c.includes("aptlogic_access=tok_xyz"));
    expect(roleSet).toBe(true);
    expect(tokenSet).toBe(true);
  });

  it("includes SameSite=Strict on the role cookie (CSRF protection)", () => {
    setAuthCookies("admin", "tok_abc");
    const roleCookie = cookieJar.find((c) => c.includes("aptlogic_role="));
    expect(roleCookie).toContain("SameSite=Strict");
  });

  it("includes a non-zero max-age on the role cookie (cookie persists across page reloads)", () => {
    setAuthCookies("admin", "tok_abc");
    const roleCookie = cookieJar.find((c) => c.includes("aptlogic_role="));
    // max-age should be a positive integer (7 days = 604800 seconds)
    const match = roleCookie?.match(/max-age=(\d+)/);
    expect(match).not.toBeNull();
    expect(Number(match![1])).toBeGreaterThan(0);
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// 4. clearAuthCookies — called on every logout
// ─────────────────────────────────────────────────────────────────────────────

describe("clearAuthCookies", () => {
  it("expires the aptlogic_role cookie with max-age=0", () => {
    clearAuthCookies();
    const roleClear = cookieJar.find((c) => c.includes("aptlogic_role="));
    expect(roleClear).toContain("max-age=0");
  });

  it("expires the aptlogic_access cookie with max-age=0", () => {
    clearAuthCookies();
    const tokenClear = cookieJar.find((c) => c.includes("aptlogic_access="));
    expect(tokenClear).toContain("max-age=0");
  });

  it("clears both cookies in a single call", () => {
    clearAuthCookies();
    const clearsRole = cookieJar.some((c) => c.includes("aptlogic_role=") && c.includes("max-age=0"));
    const clearsToken = cookieJar.some((c) => c.includes("aptlogic_access=") && c.includes("max-age=0"));
    expect(clearsRole).toBe(true);
    expect(clearsToken).toBe(true);
  });

  it("cookies set by setAuthCookies are fully overwritten by clearAuthCookies (logout after login)", () => {
    // Simulate a full login → logout cycle in one test
    setAuthCookies("admin", "live_token");
    clearAuthCookies();
    // Both cookies must have a max-age=0 entry — which browsers treat as deletion
    const roleClear = cookieJar.find((c) => c.includes("aptlogic_role=") && c.includes("max-age=0"));
    const tokenClear = cookieJar.find((c) => c.includes("aptlogic_access=") && c.includes("max-age=0"));
    expect(roleClear).toBeDefined();
    expect(tokenClear).toBeDefined();
  });
});
