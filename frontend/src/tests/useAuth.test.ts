/**
 * Regression tests for src/hooks/useAuth.ts — Phase 6 modification.
 *
 * Why these tests exist:
 *   Phase 6 rewrote the logout function in useAuth.ts (new LOGIN_PATHS record,
 *   new super_admin branch, new API endpoint for super_admin). These tests
 *   ensure the existing admin and student logout flows still work correctly
 *   and that the new super_admin flow is correct.
 *
 * What is tested:
 *   1. LOGIN_PATHS record — correct redirect target per role
 *   2. Computed role booleans — isAdmin, isStudent, isSuperAdmin, isAuthenticated
 *   3. logout() — calls the correct API endpoint per role (admin/super_admin only)
 *   4. logout() — always clears auth store + cookies (the finally block guarantee)
 *
 * Mock strategy:
 *   - react.useCallback is mocked as a transparent passthrough so the hook
 *     can be called directly in Node.js without a React rendering context.
 *   - @/lib/api is NOT module-mocked. Instead, jest.spyOn(api, "post") is used
 *     per-test. This avoids the ts-jest factory-closure timing issue where a
 *     variable referenced in a jest.mock factory may not be initialised yet.
 *   - All other external dependencies are fully mocked.
 */

// ── Dependency mocks (must appear before any import that uses them) ───────────

const mockPush = jest.fn();
jest.mock("next/navigation", () => ({
  useRouter: () => ({ push: mockPush }),
}));

const mockClearAuth = jest.fn();

// Shared mock store — mutate properties in each test to set role/tokens
const mockStore = {
  user: null as { role: string } | null,
  accessToken: null as string | null,
  refreshToken: null as string | null,
  clearAuth: mockClearAuth,
};

jest.mock("@/lib/auth-store", () => ({
  useAuthStore: Object.assign(
    // Hook call: const { user, accessToken, clearAuth } = useAuthStore()
    jest.fn(() => mockStore),
    // Namespace call: useAuthStore.getState().user?.role
    { getState: jest.fn(() => mockStore) }
  ),
}));

const mockClearAuthCookies = jest.fn();
jest.mock("@/lib/cookies", () => ({
  clearAuthCookies: () => mockClearAuthCookies(),
}));

// Make useCallback a transparent passthrough — required to call the hook
// directly in Node.js without a React component context.
jest.mock("react", () => ({
  ...jest.requireActual("react"),
  useCallback: (fn: any) => fn,
}));

// ── Imports (after mocks) ─────────────────────────────────────────────────────

// Import the REAL api module — its store/cookie deps are mocked above.
// We spy on api.post per-test so no HTTP calls are made.
import api from "../lib/api";
import { useAuth, LOGIN_PATHS } from "../hooks/useAuth";

// ── Test helpers ──────────────────────────────────────────────────────────────

function setRole(role: "admin" | "student" | "super_admin" | null) {
  mockStore.user = role ? { role } : null;
}

function setTokens(access: string | null, refresh: string | null) {
  mockStore.accessToken = access;
  mockStore.refreshToken = refresh;
}

beforeEach(() => {
  mockStore.user = null;
  mockStore.accessToken = null;
  mockStore.refreshToken = null;
  mockPush.mockClear();
  mockClearAuth.mockClear();
  mockClearAuthCookies.mockClear();
  // Default spy: api.post resolves immediately (no HTTP call)
  jest.spyOn(api, "post").mockResolvedValue({} as any);
});

afterEach(() => {
  jest.restoreAllMocks();
});

// ─────────────────────────────────────────────────────────────────────────────
// 1. LOGIN_PATHS record values
// ─────────────────────────────────────────────────────────────────────────────

describe("LOGIN_PATHS record", () => {
  it("maps admin to /admin/login", () => {
    expect(LOGIN_PATHS["admin"]).toBe("/admin/login");
  });

  it("maps student to /students/login (plural — not /student/login)", () => {
    expect(LOGIN_PATHS["student"]).toBe("/students/login");
  });

  it("maps super_admin to /super-admin/login", () => {
    expect(LOGIN_PATHS["super_admin"]).toBe("/super-admin/login");
  });

  it("logout falls back to /login for an unknown role", async () => {
    // Simulates a corrupted store with an unrecognised role value
    mockStore.user = { role: "unknown_role" };
    setTokens(null, null);
    const { logout } = useAuth();
    await logout();
    // LOGIN_PATHS["unknown_role"] is undefined → fallback ?? "/login"
    expect(mockPush).toHaveBeenCalledWith("/login");
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// 2. Computed role booleans
// ─────────────────────────────────────────────────────────────────────────────

describe("Computed role booleans", () => {
  it("isAdmin=true, isStudent=false, isSuperAdmin=false when role is admin", () => {
    setRole("admin");
    const { isAdmin, isStudent, isSuperAdmin } = useAuth();
    expect(isAdmin).toBe(true);
    expect(isStudent).toBe(false);
    expect(isSuperAdmin).toBe(false);
  });

  it("isStudent=true, isAdmin=false, isSuperAdmin=false when role is student", () => {
    setRole("student");
    const { isAdmin, isStudent, isSuperAdmin } = useAuth();
    expect(isAdmin).toBe(false);
    expect(isStudent).toBe(true);
    expect(isSuperAdmin).toBe(false);
  });

  it("isSuperAdmin=true, isAdmin=false, isStudent=false when role is super_admin", () => {
    setRole("super_admin");
    const { isAdmin, isStudent, isSuperAdmin } = useAuth();
    expect(isAdmin).toBe(false);
    expect(isStudent).toBe(false);
    expect(isSuperAdmin).toBe(true);
  });

  it("isAuthenticated=true when both accessToken and user are present", () => {
    setRole("admin");
    setTokens("access_tok", "refresh_tok");
    const { isAuthenticated } = useAuth();
    expect(isAuthenticated).toBe(true);
  });

  it("isAuthenticated=false when accessToken is null", () => {
    setRole("admin");
    setTokens(null, "refresh_tok");
    const { isAuthenticated } = useAuth();
    expect(isAuthenticated).toBe(false);
  });

  it("isAuthenticated=false when user is null", () => {
    setRole(null);
    setTokens("access_tok", null);
    const { isAuthenticated } = useAuth();
    expect(isAuthenticated).toBe(false);
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// 3. logout — API endpoint selection by role
// ─────────────────────────────────────────────────────────────────────────────

describe("logout — API endpoint selection", () => {
  it("calls POST /auth/logout/ with refresh token for admin role", async () => {
    setRole("admin");
    setTokens("access_tok", "ref_tok_admin");

    const { logout } = useAuth();
    await logout();

    expect(api.post).toHaveBeenCalledTimes(1);
    expect(api.post).toHaveBeenCalledWith("/auth/logout/", {
      refresh_token: "ref_tok_admin",
    });
  });

  it("calls POST /auth/logout/ with refresh token for super_admin role", async () => {
    setRole("super_admin");
    setTokens("access_tok", "ref_tok_sa");

    const { logout } = useAuth();
    await logout();

    expect(api.post).toHaveBeenCalledTimes(1);
    expect(api.post).toHaveBeenCalledWith("/auth/logout/", {
      refresh_token: "ref_tok_sa",
    });
  });

  it("calls POST /auth/logout/ with refresh token for student role", async () => {
    setRole("student");
    setTokens("access_tok", "ref_tok_student");

    const { logout } = useAuth();
    await logout();

    expect(api.post).toHaveBeenCalledTimes(1);
    expect(api.post).toHaveBeenCalledWith("/auth/logout/", {
      refresh_token: "ref_tok_student",
    });
  });

  it("does NOT call logout API when refresh token is absent", async () => {
    setRole("admin");
    setTokens("access_tok", null); // no refresh token

    const { logout } = useAuth();
    await logout();

    expect(api.post).not.toHaveBeenCalled();
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// 4. logout — finally block guarantees (clears state regardless of API result)
// ─────────────────────────────────────────────────────────────────────────────

describe("logout — finally block always clears state", () => {
  it("clears auth store after successful API logout", async () => {
    setRole("admin");
    setTokens("tok", "ref");

    const { logout } = useAuth();
    await logout();

    expect(mockClearAuth).toHaveBeenCalledTimes(1);
  });

  it("clears cookies after successful API logout", async () => {
    setRole("admin");
    setTokens("tok", "ref");

    const { logout } = useAuth();
    await logout();

    expect(mockClearAuthCookies).toHaveBeenCalledTimes(1);
  });

  it("clears auth store even when API call throws", async () => {
    setRole("admin");
    setTokens("tok", "ref");
    jest.spyOn(api, "post").mockRejectedValue(new Error("Network error"));

    const { logout } = useAuth();
    await logout();

    expect(mockClearAuth).toHaveBeenCalledTimes(1);
  });

  it("clears cookies even when API call throws", async () => {
    setRole("admin");
    setTokens("tok", "ref");
    jest.spyOn(api, "post").mockRejectedValue(new Error("Network error"));

    const { logout } = useAuth();
    await logout();

    expect(mockClearAuthCookies).toHaveBeenCalledTimes(1);
  });

  it("redirects admin to /admin/login even when API call throws", async () => {
    setRole("admin");
    setTokens("tok", "ref");
    jest.spyOn(api, "post").mockRejectedValue(new Error("Network error"));

    const { logout } = useAuth();
    await logout();

    expect(mockPush).toHaveBeenCalledWith("/admin/login");
  });

  it("redirects student to /students/login after API logout call", async () => {
    setRole("student");
    setTokens("tok", "ref");

    const { logout } = useAuth();
    await logout();

    expect(mockPush).toHaveBeenCalledWith("/students/login");
  });
});
