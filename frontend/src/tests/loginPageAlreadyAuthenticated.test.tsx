/**
 * @jest-environment jsdom
 *
 * Coverage for the "already authenticated in THIS tab → redirect to that
 * role's own home" mount-time check added 2026-08-27 to PortalLoginForm.tsx
 * (admin/super-admin/it) and students/login/page.tsx (student, hand-rolled,
 * doesn't use PortalLoginForm). This replaces the equivalent behavior that
 * used to live in proxy.ts reading the shared aptlogic_role cookie — the
 * fix for a cross-tab bug where opening a login page in one tab could
 * redirect based on a DIFFERENT, more-recently-logged-in tab's cookie
 * rather than this tab's own session. Reads useAuth() (sessionStorage,
 * genuinely tab-isolated), never a cookie.
 */

const mockReplace = jest.fn();
jest.mock("next/navigation", () => ({
  useRouter: () => ({ push: jest.fn(), replace: mockReplace }),
}));

jest.mock("next/image", () => ({
  __esModule: true,
  default: (props: Record<string, unknown>) => <img alt="" {...props} />,
}));

jest.mock("@/components/ui/ScrollingUpdates", () => ({ ScrollingUpdates: () => null }));

jest.mock("@/lib/auth-store", () => ({
  useAuthStore: () => ({ setTokens: jest.fn() }),
}));

let mockAuthState: {
  user: { role: string; is_profile_completed?: boolean } | null;
  isAuthenticated: boolean;
  hasHydrated: boolean;
};
jest.mock("@/hooks/useAuth", () => ({
  useAuth: () => mockAuthState,
}));

import React from "react";
import { render } from "@testing-library/react";
import { ShieldCheck } from "lucide-react";
import { PortalLoginForm } from "@/components/auth/PortalLoginForm";
import StudentLoginPage from "@/app/students/login/page";

function AdminForm() {
  return (
    <PortalLoginForm
      leftTitle="t" leftTagline="t" features={[]}
      badgeLabel="Admin" badgeIcon={ShieldCheck} cardTitle="t" cardSubtitle="t"
      apiEndpoint="/auth/login/" cookieRole="admin" redirectTo="/admin/batch"
    />
  );
}

beforeEach(() => {
  mockReplace.mockClear();
});

describe("PortalLoginForm — already authenticated redirect", () => {
  it("does not redirect when this tab isn't authenticated", () => {
    mockAuthState = { user: null, isAuthenticated: false, hasHydrated: true };
    render(<AdminForm />);
    expect(mockReplace).not.toHaveBeenCalled();
  });

  it("does not redirect before hydration completes, even if the store already shows a user — avoids a flash-redirect race", () => {
    mockAuthState = { user: { role: "admin" }, isAuthenticated: true, hasHydrated: false };
    render(<AdminForm />);
    expect(mockReplace).not.toHaveBeenCalled();
  });

  it("redirects a MATCHING (admin) session straight to its own home", () => {
    mockAuthState = { user: { role: "admin" }, isAuthenticated: true, hasHydrated: true };
    render(<AdminForm />);
    expect(mockReplace).toHaveBeenCalledWith("/admin/batch");
  });

  it("redirects a DIFFERENT role's session to THAT role's own home, not this form's redirectTo — a student tab opening the admin login form must land on the student home, never admin/batch", () => {
    mockAuthState = { user: { role: "student" }, isAuthenticated: true, hasHydrated: true };
    render(<AdminForm />);
    expect(mockReplace).toHaveBeenCalledWith("/students/home");
  });
});

describe("Student login page — already authenticated redirect", () => {
  it("does not redirect when this tab isn't authenticated", () => {
    mockAuthState = { user: null, isAuthenticated: false, hasHydrated: true };
    render(<StudentLoginPage />);
    expect(mockReplace).not.toHaveBeenCalled();
  });

  it("redirects an already-authenticated student session with a COMPLETED profile to /students/home", () => {
    mockAuthState = {
      user: { role: "student", is_profile_completed: true },
      isAuthenticated: true,
      hasHydrated: true,
    };
    render(<StudentLoginPage />);
    expect(mockReplace).toHaveBeenCalledWith("/students/home");
  });

  it("redirects an already-authenticated student session with an INCOMPLETE profile to /students/my_profile, not home — this mount-time check used to skip the profile-completion check entirely, unlike the fresh-login-submit path", () => {
    mockAuthState = {
      user: { role: "student", is_profile_completed: false },
      isAuthenticated: true,
      hasHydrated: true,
    };
    render(<StudentLoginPage />);
    expect(mockReplace).toHaveBeenCalledWith("/students/my_profile");
  });

  it("redirects a DIFFERENT role's session (the exact cross-tab scenario: an admin logged in on another tab) to that role's OWN home, not the student home — proves this tab's login page is no longer at the mercy of a different tab's more recent login", () => {
    mockAuthState = { user: { role: "admin" }, isAuthenticated: true, hasHydrated: true };
    render(<StudentLoginPage />);
    expect(mockReplace).toHaveBeenCalledWith("/admin/batch");
  });
});
