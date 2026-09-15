/**
 * Regression tests for src/lib/api.ts — Phase 6 modification.
 *
 * Why these tests exist:
 *   Phase 6 changed the 401 interceptor in api.ts: the two inline `loginPaths`
 *   records (one in the "no refresh token" branch, one in the "refresh failed"
 *   branch) were replaced with a single exported LOGIN_REDIRECT_PATHS constant.
 *   These tests verify: (a) the constant has correct values, (b) the request
 *   interceptor attaches Authorization headers correctly, and (c) the
 *   getErrorMessage utility extracts the right message from every DRF error shape.
 *
 * What is tested:
 *   1. LOGIN_REDIRECT_PATHS record — correct redirect target per role
 *   2. Request interceptor — Authorization header attached/skipped correctly
 *   3. getErrorMessage — handles all DRF/Axios error shapes
 *
 * Mock strategy:
 *   @/lib/auth-store is mocked to control what token/role the interceptor sees.
 *   The raw axios instance and the api interceptors are accessed directly through
 *   interceptors.request.forEach / interceptors.response.forEach so no HTTP
 *   requests are made.
 */

// ── Dependency mocks ──────────────────────────────────────────────────────────

const mockStore = {
  accessToken: null as string | null,
  user: null as { role: string } | null,
  refreshToken: null as string | null,
  clearAuth: jest.fn(),
  setAccessToken: jest.fn(),
};

jest.mock("@/lib/auth-store", () => ({
  useAuthStore: {
    getState: jest.fn(() => mockStore),
  },
}));

jest.mock("@/lib/cookies", () => ({
  clearAuthCookies: jest.fn(),
}));

// ── Imports (after mocks) ─────────────────────────────────────────────────────

import api, { LOGIN_REDIRECT_PATHS, getErrorMessage } from "../lib/api";
import axios from "axios";
import { clearAuthCookies } from "../lib/cookies";

// ── Helpers to access registered interceptors ─────────────────────────────────

function getRequestHandler(): ((config: any) => any) | null {
  let handler: ((c: any) => any) | null = null;
  // forEach exists on axios InterceptorManager at runtime but is not in the
  // TypeScript type definitions for this axios version — cast to any.
  (api.interceptors.request as any).forEach((interceptor: any) => {
    if (interceptor?.fulfilled) handler = interceptor.fulfilled;
  });
  return handler;
}

// ─────────────────────────────────────────────────────────────────────────────
// Resets
// ─────────────────────────────────────────────────────────────────────────────

beforeEach(() => {
  mockStore.accessToken = null;
  mockStore.user = null;
  mockStore.refreshToken = null;
  mockStore.clearAuth.mockClear();
  mockStore.setAccessToken.mockClear();
});

// ─────────────────────────────────────────────────────────────────────────────
// 1. LOGIN_REDIRECT_PATHS record values
// ─────────────────────────────────────────────────────────────────────────────

describe("LOGIN_REDIRECT_PATHS record", () => {
  it("maps student to /students/login (plural — not /student/login)", () => {
    expect(LOGIN_REDIRECT_PATHS["student"]).toBe("/students/login");
  });

  it("maps admin to /admin/login", () => {
    expect(LOGIN_REDIRECT_PATHS["admin"]).toBe("/admin/login");
  });

  it("maps super_admin to /super-admin/login", () => {
    expect(LOGIN_REDIRECT_PATHS["super_admin"]).toBe("/super-admin/login");
  });

  it("covers all three roles — no missing role key", () => {
    const roles = ["student", "admin", "super_admin"];
    roles.forEach((role) => {
      expect(LOGIN_REDIRECT_PATHS[role]).toBeDefined();
      expect(LOGIN_REDIRECT_PATHS[role]).toMatch(/^\/[a-z-/]+login$/);
    });
  });

  it("is consistent with useAuth LOGIN_PATHS — same values", async () => {
    // Cross-check: the two constants in different files must stay in sync.
    // If someone updates one but not the other, this test fails.
    const { LOGIN_PATHS } = await import("../hooks/useAuth");
    expect(LOGIN_REDIRECT_PATHS["student"]).toBe(LOGIN_PATHS["student"]);
    expect(LOGIN_REDIRECT_PATHS["admin"]).toBe(LOGIN_PATHS["admin"]);
    expect(LOGIN_REDIRECT_PATHS["super_admin"]).toBe(LOGIN_PATHS["super_admin"]);
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// 2. Request interceptor — Authorization header
// ─────────────────────────────────────────────────────────────────────────────

describe("Request interceptor — Authorization header", () => {
  it("attaches Bearer token on a normal API endpoint", () => {
    mockStore.accessToken = "access_token_123";
    const handler = getRequestHandler()!;
    const config = { url: "/api/users/students/", headers: {} as any };

    const result = handler(config);

    expect(result.headers["Authorization"]).toBe("Bearer access_token_123");
  });

  it("does NOT attach Authorization header on /login/ endpoints", () => {
    mockStore.accessToken = "access_token_123";
    const handler = getRequestHandler()!;
    const config = { url: "/admin/login/", headers: {} as any };

    const result = handler(config);

    expect(result.headers["Authorization"]).toBeUndefined();
  });

  it("does NOT attach Authorization header on /token/refresh/ endpoint", () => {
    mockStore.accessToken = "access_token_123";
    const handler = getRequestHandler()!;
    const config = { url: "/auth/token/refresh/", headers: {} as any };

    const result = handler(config);

    expect(result.headers["Authorization"]).toBeUndefined();
  });

  it("does NOT attach Authorization header when store has no access token", () => {
    mockStore.accessToken = null;
    const handler = getRequestHandler()!;
    const config = { url: "/api/users/students/", headers: {} as any };

    const result = handler(config);

    expect(result.headers["Authorization"]).toBeUndefined();
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// 3. getErrorMessage — DRF / Axios error shape handling
// ─────────────────────────────────────────────────────────────────────────────

describe("getErrorMessage", () => {
  function makeAxiosError(data: unknown, status = 400): unknown {
    const err = new Error("Request failed") as any;
    err.isAxiosError = true;
    err.response = { status, data };
    // Make axios.isAxiosError return true for this object
    jest.spyOn(axios, "isAxiosError").mockReturnValueOnce(true);
    return err;
  }

  afterEach(() => {
    jest.restoreAllMocks();
  });

  it("extracts data.message from an Axios error", () => {
    const err = makeAxiosError({ message: "Invalid credentials" });
    expect(getErrorMessage(err)).toBe("Invalid credentials");
  });

  it("extracts data.detail from an Axios error (DRF default)", () => {
    const err = makeAxiosError({ detail: "Authentication credentials were not provided." });
    expect(getErrorMessage(err)).toBe("Authentication credentials were not provided.");
  });

  it("extracts non_field_errors[0] from an Axios error (DRF non-field)", () => {
    const err = makeAxiosError({ non_field_errors: ["Email and password do not match."] });
    expect(getErrorMessage(err)).toBe("Email and password do not match.");
  });

  it("extracts the first field error from a DRF field-error shape", () => {
    const err = makeAxiosError({ email: ["Enter a valid email address."] });
    expect(getErrorMessage(err)).toBe("email: Enter a valid email address.");
  });

  it("returns a clear offline message for an Axios error with no response (network/timeout/DNS failure)", () => {
    const err = new Error("Network Error") as any;
    err.isAxiosError = true;
    err.response = undefined;
    jest.spyOn(axios, "isAxiosError").mockReturnValueOnce(true);
    expect(getErrorMessage(err)).toBe("No internet connection. Please check your network and try again.");
  });

  it("returns a clear rate-limit message for a 429, not the raw axios error string", () => {
    // Regression coverage (2026-09-15): before this, a 429 (nginx's rate-limit
    // JSON has no message/detail field) fell through to axios's generic
    // "Request failed with status code 429" being shown as-is on every login
    // screen — most concretely hit when several students/admins share one
    // IP (an exam hall/lab) and collide on the login rate limit at once.
    const err = makeAxiosError({ error: "Rate limit exceeded", retry_after: "12" }, 429);
    expect(getErrorMessage(err)).toBe("Too many attempts. Please wait a moment and try again.");
  });

  it("includes the server's Retry-After seconds when the header is present on a 429", () => {
    const err = makeAxiosError({ error: "Rate limit exceeded" }, 429) as any;
    err.response.headers = { "retry-after": "12" };
    expect(getErrorMessage(err)).toBe("Too many attempts. Please wait 12 seconds and try again.");
  });

  it("returns a clean fallback for a 500 with no recognizable body, not axios's raw string", () => {
    // Global fix (2026-09-15): every caller of getErrorMessage — all 4
    // login screens and everywhere else in the app — used to fall through
    // to axios's own generic "Request failed with status code 500" for
    // any response shape this helper doesn't recognize. Fixed once here
    // rather than per-screen, so it can never regress on just one of them.
    const err = makeAxiosError({}, 500);
    expect(getErrorMessage(err)).toBe("Something went wrong on our end. Please try again shortly.");
  });

  it("returns a clean fallback for a 400 with an unrecognized body shape", () => {
    const err = makeAxiosError("not an object with message/detail/field errors", 400);
    expect(getErrorMessage(err)).toBe("Something went wrong. Please try again.");
  });

  it("returns error.message for a plain JS Error instance", () => {
    const err = new Error("Network Error");
    expect(getErrorMessage(err)).toBe("Network Error");
  });

  it("returns a fallback string for an unknown error type", () => {
    expect(getErrorMessage(null)).toBe("An unexpected error occurred.");
    expect(getErrorMessage(undefined)).toBe("An unexpected error occurred.");
    expect(getErrorMessage("raw string error")).toBe("An unexpected error occurred.");
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// 4. Response interceptor — 401 redirect behaviour
//
// Why this section exists:
//   The interceptor has two redirect branches:
//     A) no refresh token stored → redirect immediately
//     B) refresh token exists but the refresh call fails → redirect after catch
//   Both branches use LOGIN_REDIRECT_PATHS and fall back via `role ?? "admin"`
//   when the user object is already null (token expired mid-session).
//   These tests confirm the interceptor actually FIRES with the right URL — not
//   just that the path constant has the right value.
// ─────────────────────────────────────────────────────────────────────────────

describe("Response interceptor — 401 redirect behaviour", () => {
  // ── Why jest.resetModules() is required here ────────────────────────────────
  // api.ts has a module-level `isRefreshing` flag. The "no refresh token" branch
  // sets isRefreshing = true before the early return — the finally block that resets
  // it to false only runs when a refresh is actually attempted. Result: the first
  // Branch-A test leaves isRefreshing = true; every subsequent test enters the
  // pending-queue branch and hangs indefinitely. jest.resetModules() before each
  // test gives a fresh module instance with isRefreshing = false.
  //
  // Note: jest.mock() factory registrations persist across resetModules(), so
  // @/lib/auth-store and @/lib/cookies still return their mock factories after each
  // reset. The mockStore object is the same reference throughout, so any mutations
  // in beforeEach/test setup are still visible to the freshly required module.
  // ────────────────────────────────────────────────────────────────────────────

  let mockLocationHref: string;
  let freshApi: any;
  let freshAxios: any;

  function getResponseErrorHandler(): (e: any) => Promise<any> {
    let handler: any = null;
    (freshApi.interceptors.response as any).forEach((interceptor: any) => {
      if (interceptor?.rejected) handler = interceptor.rejected;
    });
    return handler!;
  }

  function make401Error(url = "/api/some/protected/endpoint", retry = false) {
    return {
      response: { status: 401 },
      config: { url, _retry: retry, headers: {} as any },
    };
  }

  beforeEach(() => {
    jest.resetModules();

    // window does not exist in the Node test environment.
    // Provide a minimal stub so api.ts can write window.location.href.
    mockLocationHref = "";
    (global as any).window = {
      location: {
        pathname: "/students/login",
        get href() { return mockLocationHref; },
        set href(v: string) { mockLocationHref = v; },
      },
    };

    // Require fresh instances after the module registry is reset.
    freshApi = require("../lib/api").default;
    freshAxios = require("axios");

    mockStore.clearAuth.mockClear();
    (require("../lib/cookies").clearAuthCookies as jest.Mock).mockClear();
  });

  afterEach(() => {
    delete (global as any).window;
    jest.restoreAllMocks();
  });

  // ── Branch A: no refresh token — redirect immediately ─────────────────────

  it("redirects admin to /admin/login on 401 with no refresh token", async () => {
    mockStore.refreshToken = null;
    mockStore.user = { role: "admin" };

    await getResponseErrorHandler()(make401Error()).catch(() => {});

    expect(mockLocationHref).toBe("/admin/login");
  });

  it("redirects student to /students/login on 401 with no refresh token", async () => {
    // Validates the plural /students/ path — /student/login would be a silent bug.
    mockStore.refreshToken = null;
    mockStore.user = { role: "student" };

    await getResponseErrorHandler()(make401Error()).catch(() => {});

    expect(mockLocationHref).toBe("/students/login");
  });

  it("redirects super_admin to /super-admin/login on 401 with no refresh token", async () => {
    mockStore.refreshToken = null;
    mockStore.user = { role: "super_admin" };

    await getResponseErrorHandler()(make401Error()).catch(() => {});

    expect(mockLocationHref).toBe("/super-admin/login");
  });

  it("falls back to the current portal's login page when user is null on 401 — the key edge case", async () => {
    // Token expired (or never existed) and the auth store's user object is
    // null when the 401 fires. user?.role → undefined → falls back to
    // whichever portal window.location.pathname is under (here /students/login,
    // matching the test window mock), not a hardcoded /admin/login — a real
    // bug report: a fresh "Get Started" visit to /students/login was being
    // bounced to /admin/login by this exact fallback defaulting to "admin".
    mockStore.refreshToken = null;
    mockStore.user = null;

    await getResponseErrorHandler()(make401Error()).catch(() => {});

    expect(mockLocationHref).toBe("/students/login");
  });

  it("falls back to /admin/login when user is null and the path is under /admin", async () => {
    (global as any).window.location.pathname = "/admin/batch";
    mockStore.refreshToken = null;
    mockStore.user = null;

    await getResponseErrorHandler()(make401Error()).catch(() => {});

    expect(mockLocationHref).toBe("/admin/login");
  });

  it("falls back to /super-admin/login when user is null and the path is under /super-admin", async () => {
    (global as any).window.location.pathname = "/super-admin/overview";
    mockStore.refreshToken = null;
    mockStore.user = null;

    await getResponseErrorHandler()(make401Error()).catch(() => {});

    expect(mockLocationHref).toBe("/super-admin/login");
  });

  it("calls clearAuth and clearAuthCookies before redirecting on 401", async () => {
    mockStore.refreshToken = null;
    mockStore.user = { role: "admin" };

    await getResponseErrorHandler()(make401Error()).catch(() => {});

    expect(mockStore.clearAuth).toHaveBeenCalledTimes(1);
    // Use the fresh mock instance that was loaded by freshApi
    expect(require("../lib/cookies").clearAuthCookies).toHaveBeenCalledTimes(1);
  });

  // ── Interceptor bypass — /login/ and token/refresh endpoints ─────────────

  it("does NOT redirect when 401 arrives on a /login/ endpoint", async () => {
    // The PortalLoginForm handles its own 401 — the interceptor must not intercept.
    mockStore.refreshToken = null;
    mockStore.user = { role: "admin" };

    await getResponseErrorHandler()(make401Error("/admin/login/")).catch(() => {});

    expect(mockLocationHref).toBe("");
  });

  it("does NOT redirect when 401 arrives on the token/refresh endpoint", async () => {
    mockStore.refreshToken = null;
    mockStore.user = { role: "admin" };

    await getResponseErrorHandler()(make401Error("/auth/token/refresh/")).catch(() => {});

    expect(mockLocationHref).toBe("");
  });

  // ── Branch B: refresh token exists but refresh call fails ─────────────────

  it("redirects to role login page when refresh token exists but refresh fails", async () => {
    mockStore.refreshToken = "stale_refresh_token";
    mockStore.user = { role: "super_admin" };
    // Spy on the freshAxios instance — same instance freshApi uses internally.
    jest.spyOn(freshAxios, "post").mockRejectedValue(new Error("Token refresh failed"));

    await getResponseErrorHandler()(make401Error()).catch(() => {});

    expect(mockLocationHref).toBe("/super-admin/login");
  });

  it("falls back to the current portal's login page when refresh fails and user is null", async () => {
    // Same edge case as Branch A but in the catch block of the refresh attempt.
    mockStore.refreshToken = "stale_refresh_token";
    mockStore.user = null;
    jest.spyOn(freshAxios, "post").mockRejectedValue(new Error("Token refresh failed"));

    await getResponseErrorHandler()(make401Error()).catch(() => {});

    expect(mockLocationHref).toBe("/students/login");
  });

  // ── Branch C: refresh succeeds, but the retried request itself fails ──────
  //
  // Regression coverage for a real production bug: the retry call was
  // `return api(originalRequest);` (no `await`), which detached its promise
  // from this function's try/catch — a failure on the retry silently
  // propagated to the caller instead of being handled here. A user whose
  // refresh "succeeded" but whose retried request still 401'd (e.g. a
  // deactivated account, a bumped token_version) was left permanently
  // stuck on a broken page with no redirect back to login.

  it("redirects to login when the retry (post-refresh) also 401s", async () => {
    mockStore.refreshToken = "valid_refresh_token";
    mockStore.user = { role: "admin" };
    jest.spyOn(freshAxios, "post").mockResolvedValue({ data: { access: "new_access_token" } });
    jest.spyOn(freshApi, "request").mockRejectedValue({
      isAxiosError: true, response: { status: 401 },
    });

    await getResponseErrorHandler()(make401Error()).catch(() => {});

    expect(mockLocationHref).toBe("/admin/login");
    expect(mockStore.clearAuth).toHaveBeenCalledTimes(1);
  });

  it("does NOT redirect when the retry fails with a non-401 error (e.g. 500)", async () => {
    // A server error on the retried request is not a session problem —
    // force-logging the user out here would be wrong.
    mockStore.refreshToken = "valid_refresh_token";
    mockStore.user = { role: "admin" };
    jest.spyOn(freshAxios, "post").mockResolvedValue({ data: { access: "new_access_token" } });
    jest.spyOn(freshApi, "request").mockRejectedValue({
      isAxiosError: true, response: { status: 500 },
    });

    await expect(getResponseErrorHandler()(make401Error())).rejects.toMatchObject({
      response: { status: 500 },
    });

    expect(mockLocationHref).toBe("");
    expect(mockStore.clearAuth).not.toHaveBeenCalled();
  });

  it("returns the retried response on success after a refresh (happy path still works)", async () => {
    mockStore.refreshToken = "valid_refresh_token";
    mockStore.user = { role: "admin" };
    jest.spyOn(freshAxios, "post").mockResolvedValue({ data: { access: "new_access_token" } });
    jest.spyOn(freshApi, "request").mockResolvedValue({ data: { success: true } });

    const result = await getResponseErrorHandler()(make401Error());

    expect(result).toEqual({ data: { success: true } });
    expect(mockLocationHref).toBe("");
  });

  // ── 429 on token refresh — rate-limited, NOT proof the token is invalid ────
  //
  // Regression coverage for a real bug: students sharing one exam-hall IP
  // could exceed the gateway's per-IP rate limit on /auth/token/refresh/
  // (nginx.conf's token_refresh_zone), and the interceptor used to treat
  // ANY refresh failure — including this one — as a dead session and force
  // logout. A 429 here says nothing about the refresh token's validity; the
  // fix retries with backoff and, if still rate-limited, fails the one
  // in-flight request softly instead of clearing auth and redirecting.

  function make429Error(retryAfter = "0.01") {
    const err = new Error("Rate limit exceeded") as any;
    err.isAxiosError = true;
    err.response = { status: 429, headers: { "retry-after": retryAfter } };
    return err;
  }

  it("does NOT force logout when refresh keeps getting rate-limited (429)", async () => {
    mockStore.refreshToken = "valid_refresh_token";
    mockStore.user = { role: "student" };
    jest.spyOn(freshAxios, "post").mockRejectedValue(make429Error());

    await expect(getResponseErrorHandler()(make401Error())).rejects.toMatchObject({
      response: { status: 429 },
    });

    expect(mockStore.clearAuth).not.toHaveBeenCalled();
    expect(mockLocationHref).toBe("");
  });

  it("retries with backoff and succeeds once the rate limit clears, without forcing logout", async () => {
    mockStore.refreshToken = "valid_refresh_token";
    mockStore.user = { role: "student" };
    jest.spyOn(freshAxios, "post")
      .mockRejectedValueOnce(make429Error())
      .mockResolvedValueOnce({ data: { access: "new_access_token" } });
    jest.spyOn(freshApi, "request").mockResolvedValue({ data: { success: true } });

    const result = await getResponseErrorHandler()(make401Error());

    expect(result).toEqual({ data: { success: true } });
    expect(freshAxios.post).toHaveBeenCalledTimes(2);
    expect(mockStore.clearAuth).not.toHaveBeenCalled();
    expect(mockLocationHref).toBe("");
  });

  it("gives up and force-logs-out on a genuine 400 invalid/blacklisted refresh token (not 429)", async () => {
    mockStore.refreshToken = "stale_refresh_token";
    mockStore.user = { role: "student" };
    const err = new Error("Invalid or already blacklisted token") as any;
    err.isAxiosError = true;
    err.response = { status: 400 };
    jest.spyOn(freshAxios, "post").mockRejectedValue(err);

    await getResponseErrorHandler()(make401Error()).catch(() => {});

    expect(mockStore.clearAuth).toHaveBeenCalledTimes(1);
    expect(mockLocationHref).toBe("/students/login");
  });
});
