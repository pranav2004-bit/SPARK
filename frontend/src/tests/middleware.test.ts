/**
 * Unit tests for middleware routing logic.
 * next/server is mocked — these tests exercise the pure decision logic only.
 */

// Capture what redirect was called with
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
// isValidRole helper
// ---------------------------------------------------------------------------

describe("isValidRole", () => {
  it("accepts valid roles", () => {
    expect(isValidRole("admin")).toBe(true);
    expect(isValidRole("student")).toBe(true);
    expect(isValidRole("super_admin")).toBe(true);
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

  it("allows unauthenticated access to /admin/login", () => {
    middleware(req("/admin/login"));
    expect(wasAllowed()).toBe(true);
    expect(redirectCalls.length).toBe(0);
  });

  it("allows unauthenticated access to /students/login", () => {
    middleware(req("/students/login"));
    expect(wasAllowed()).toBe(true);
  });

  it("allows unauthenticated access to /super-admin/login", () => {
    middleware(req("/super-admin/login"));
    expect(wasAllowed()).toBe(true);
  });
});

// ---------------------------------------------------------------------------
// Unauthenticated portal access (smoke + sanity — test rows 1 & 2)
// ---------------------------------------------------------------------------

describe("Unauthenticated portal access", () => {
  it("redirects /admin/students to /admin/login when no cookie", () => {
    middleware(req("/admin/students"));
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

  it("redirects /admin/batch to /admin/login when cookie is garbage", () => {
    middleware(req("/admin/batch", { aptlogic_role: "hacker" }));
    expect(lastRedirect()).toBe("/admin/login");
  });
});

// ---------------------------------------------------------------------------
// Correct role → allowed through (functionality — test row 3)
// ---------------------------------------------------------------------------

describe("Authenticated access to own portal", () => {
  it("allows admin to access /admin/students", () => {
    middleware(req("/admin/students", { aptlogic_role: "admin" }));
    expect(wasAllowed()).toBe(true);
    expect(redirectCalls.length).toBe(0);
  });

  it("allows student to access /students/home", () => {
    middleware(req("/students/home", { aptlogic_role: "student" }));
    expect(wasAllowed()).toBe(true);
    expect(redirectCalls.length).toBe(0);
  });

  it("allows super_admin to access /super-admin/overview", () => {
    middleware(req("/super-admin/overview", { aptlogic_role: "super_admin" }));
    expect(wasAllowed()).toBe(true);
    expect(redirectCalls.length).toBe(0);
  });
});

// ---------------------------------------------------------------------------
// Wrong-role cross-portal access (negative — test row 4)
// ---------------------------------------------------------------------------

describe("Cross-portal access blocked", () => {
  it("redirects student trying to access /admin/students to /students/home", () => {
    middleware(req("/admin/students", { aptlogic_role: "student" }));
    expect(lastRedirect()).toBe("/students/home");
  });

  it("redirects admin trying to access /students/home to /admin/batch", () => {
    middleware(req("/students/home", { aptlogic_role: "admin" }));
    expect(lastRedirect()).toBe("/admin/batch");
  });

  it("redirects admin trying to access /super-admin/admins to /admin/batch", () => {
    middleware(req("/super-admin/admins", { aptlogic_role: "admin" }));
    expect(lastRedirect()).toBe("/admin/batch");
  });

  it("redirects super_admin trying to access /admin/batch to /super-admin/overview", () => {
    middleware(req("/admin/batch", { aptlogic_role: "super_admin" }));
    expect(lastRedirect()).toBe("/super-admin/overview");
  });
});

// ---------------------------------------------------------------------------
// Authenticated user on login page → redirect to portal home (edge — test row 6)
// ---------------------------------------------------------------------------

describe("Authenticated user on login page", () => {
  it("redirects authenticated admin from /admin/login to /admin/batch", () => {
    middleware(req("/admin/login", { aptlogic_role: "admin" }));
    expect(lastRedirect()).toBe("/admin/batch");
  });

  it("redirects authenticated student from /students/login to /students/home", () => {
    middleware(req("/students/login", { aptlogic_role: "student" }));
    expect(lastRedirect()).toBe("/students/home");
  });

  it("redirects authenticated super_admin from /super-admin/login to /super-admin/overview", () => {
    middleware(req("/super-admin/login", { aptlogic_role: "super_admin" }));
    expect(lastRedirect()).toBe("/super-admin/overview");
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
