/**
 * @jest-environment jsdom
 *
 * Coverage for usePortalGuard (added 2026-08-27) — the client-side,
 * per-tab replacement for the role-matching check that used to live in
 * proxy.ts. Reads the tab's own useAuth() state (sessionStorage-backed,
 * genuinely tab-isolated) rather than the shared aptlogic_role cookie, so
 * an admin tab and a student tab open side by side in one browser no
 * longer fight over which role a shared cookie says. See proxy.ts's own
 * comment for the full cross-tab bug this fixes.
 */

const mockReplace = jest.fn();
jest.mock("next/navigation", () => ({
  useRouter: () => ({ replace: mockReplace }),
}));

let mockAuthState: { user: { role: string } | null; isAuthenticated: boolean; hasHydrated: boolean };
jest.mock("@/hooks/useAuth", () => ({
  useAuth: () => mockAuthState,
}));

import React from "react";
import { render, screen } from "@testing-library/react";
import { usePortalGuard } from "@/hooks/usePortalGuard";
import type { PortalRole } from "@/lib/portalRouting";

function Harness({ role, skip }: { role: PortalRole; skip?: boolean }) {
  const { ready } = usePortalGuard(role, { skip });
  return <div data-testid="ready">{String(ready)}</div>;
}

beforeEach(() => {
  mockReplace.mockClear();
});

describe("usePortalGuard", () => {
  it("does nothing before hydration completes, even if unauthenticated — avoids a flash-redirect on a genuinely logged-in tab", () => {
    mockAuthState = { user: null, isAuthenticated: false, hasHydrated: false };
    render(<Harness role="admin" />);
    expect(mockReplace).not.toHaveBeenCalled();
  });

  it("redirects to the role's own login page once hydrated and unauthenticated", () => {
    mockAuthState = { user: null, isAuthenticated: false, hasHydrated: true };
    render(<Harness role="admin" />);
    expect(mockReplace).toHaveBeenCalledWith("/admin/login");
  });

  it("redirects a wrong-role tab session to the required role's login page — the actual cross-tab fix: a tab whose OWN session is 'student' must never render admin content just because a different tab's cookie says admin", () => {
    mockAuthState = { user: { role: "student" }, isAuthenticated: true, hasHydrated: true };
    render(<Harness role="admin" />);
    expect(mockReplace).toHaveBeenCalledWith("/admin/login");
  });

  it("does not redirect when the tab's own session role matches the required role", () => {
    mockAuthState = { user: { role: "admin" }, isAuthenticated: true, hasHydrated: true };
    render(<Harness role="admin" />);
    expect(mockReplace).not.toHaveBeenCalled();
  });

  it("does not redirect for any of the other three roles either, each against its own guard", () => {
    (["student", "super_admin", "it"] as PortalRole[]).forEach(role => {
      mockReplace.mockClear();
      mockAuthState = { user: { role }, isAuthenticated: true, hasHydrated: true };
      const { unmount } = render(<Harness role={role} />);
      expect(mockReplace).not.toHaveBeenCalled();
      unmount();
    });
  });

  it("skip:true suppresses the redirect entirely, even if unauthenticated — used by super-admin's layout while on its own login page", () => {
    mockAuthState = { user: null, isAuthenticated: false, hasHydrated: true };
    render(<Harness role="super_admin" skip />);
    expect(mockReplace).not.toHaveBeenCalled();
  });

  it("ready is true only when hydrated, authenticated, and role matches", () => {
    mockAuthState = { user: { role: "it" }, isAuthenticated: true, hasHydrated: true };
    render(<Harness role="it" />);
    expect(screen.getByTestId("ready").textContent).toBe("true");
  });

  it("ready is false when the role doesn't match, even though authenticated", () => {
    mockAuthState = { user: { role: "student" }, isAuthenticated: true, hasHydrated: true };
    render(<Harness role="admin" />);
    expect(screen.getByTestId("ready").textContent).toBe("false");
  });

  // bfcache restore coverage (2026-11-16 production-readiness audit): after
  // logout (api.ts's forceLogout does a hard window.location.href redirect,
  // a real page unload), the pre-logout protected page becomes eligible for
  // the browser's back-forward cache. A later back navigation can hand back
  // that frozen snapshot — still showing isAuthenticated: true in its own
  // frozen state — instantly, with no reason for this hook's own effect to
  // re-fire. The fix is a pageshow listener that forces a reload on a
  // persisted restore, re-reading this tab's actual (already-cleared)
  // sessionStorage from scratch.
  describe("bfcache restore (pageshow)", () => {
    // jsdom's window.location.reload is read-only and non-configurable —
    // neither reassignment, Object.defineProperty, nor jest.spyOn can
    // intercept it directly (same constraint the codebase already
    // documents for window.location.href in studentMyProfilePage.test.tsx).
    // Calling the real thing instead surfaces as a `console.error` ("Not
    // implemented: navigation") — harmless jsdom noise, but it reliably
    // proves reload() was actually invoked, which is what these tests
    // assert on instead of a call count on a mock.
    let errorSpy: jest.SpyInstance;

    beforeEach(() => {
      errorSpy = jest.spyOn(console, "error").mockImplementation(() => {});
    });

    afterEach(() => {
      errorSpy.mockRestore();
    });

    function firePageShow(persisted: boolean) {
      window.dispatchEvent(Object.assign(new Event("pageshow"), { persisted }));
    }

    it("reloads the page on a persisted (bfcache) pageshow restore", () => {
      mockAuthState = { user: { role: "admin" }, isAuthenticated: true, hasHydrated: true };
      render(<Harness role="admin" />);
      firePageShow(true);
      expect(errorSpy.mock.calls.some(args => String(args[0]).includes("Not implemented: navigation"))).toBe(true);
    });

    it("does not reload on an ordinary (non-bfcache) pageshow", () => {
      mockAuthState = { user: { role: "admin" }, isAuthenticated: true, hasHydrated: true };
      render(<Harness role="admin" />);
      firePageShow(false);
      expect(errorSpy.mock.calls.some(args => String(args[0]).includes("Not implemented: navigation"))).toBe(false);
    });

    it("does not reload when skip:true — matches super-admin's own login page, which has nothing sensitive to protect against a stale restore", () => {
      mockAuthState = { user: null, isAuthenticated: false, hasHydrated: true };
      render(<Harness role="super_admin" skip />);
      firePageShow(true);
      expect(errorSpy.mock.calls.some(args => String(args[0]).includes("Not implemented: navigation"))).toBe(false);
    });
  });
});
