/**
 * @jest-environment jsdom
 *
 * Component-level regression tests for PortalLoginForm + admin/super-admin
 * login page wiring.
 *
 * Why these tests exist:
 *   The previous portalLoginForm.test.ts verified the STATIC CONFIG values
 *   (apiEndpoint, cookieRole, redirectTo) exported from the login pages.
 *   These tests verify the DYNAMIC BEHAVIOUR: that when a user actually fills
 *   in the form and submits it, the correct sequence of side-effects fires —
 *   in the right order, with the right arguments.
 *
 *   Without these tests the following silent failures were undetected:
 *     • PortalLoginForm calls the wrong API endpoint on submit
 *     • setAuthCookies is called with the wrong role after a successful login
 *     • router.push never fires (user stays on login page after success)
 *     • Error message is never shown (user sees a blank form after a bad password)
 *     • Admin login page passes wrong props to PortalLoginForm
 *
 * What is tested (7 scenarios):
 *   1. Successful admin login — api.post called with correct endpoint + body
 *   2. Successful admin login — setAuthCookies called with "admin" + access token
 *   3. Successful admin login — setTokens called with full token + user payload
 *   4. Successful admin login — router.push fires with /admin/batch
 *   5. Failed login — server error message shown in the DOM
 *   6. Successful super-admin login — api.post called with /auth/login/ + role body
 *   7. Successful super-admin login — setAuthCookies called with "super_admin"
 *
 * Mock strategy:
 *   • next/navigation  — mock router with captured push calls
 *   • next/image       — render a plain <img> (Next.js Image uses browser APIs
 *                        not available in jsdom)
 *   • @/lib/api        — spy on api.post per-test (same spyOn pattern as useAuth tests)
 *   • @/lib/auth-store — mock setTokens to capture call args
 *   • @/lib/cookies    — mock setAuthCookies to capture call args
 *   • ScrollingUpdates — stubbed out (makes its own API call, irrelevant here)
 */

// ── Environment note ──────────────────────────────────────────────────────────
// The @jest-environment jsdom docblock above overrides the project-level
// testEnvironment: "node" for this file only. All other test files are unaffected.

// ── Module mocks ──────────────────────────────────────────────────────────────

const mockPush = jest.fn();
jest.mock("next/navigation", () => ({
  useRouter: () => ({ push: mockPush }),
}));

// Next.js <Image> uses browser APIs (IntersectionObserver, etc.) unavailable
// in jsdom. Replace with a plain <img>, stripping Next.js-only props that
// React would otherwise warn about (priority, fill, quality, placeholder, etc.).
jest.mock("next/image", () => ({
  __esModule: true,
  default: ({ src, alt, priority, fill, quality, placeholder, blurDataURL, loader, unoptimized, ...rest }: any) =>
    <img src={src} alt={alt} {...rest} />,
}));

// ScrollingUpdates makes its own API call — stub it entirely.
jest.mock("@/components/ui/ScrollingUpdates", () => ({
  ScrollingUpdates: () => null,
}));

const mockSetTokens = jest.fn();
const mockClearAuth = jest.fn();
jest.mock("@/lib/auth-store", () => ({
  useAuthStore: jest.fn(() => ({
    setTokens: mockSetTokens,
    clearAuth: mockClearAuth,
    accessToken: null,
    refreshToken: null,
    user: null,
  })),
}));

const mockSetAuthCookies = jest.fn();
jest.mock("@/lib/cookies", () => ({
  setAuthCookies: (...args: any[]) => mockSetAuthCookies(...args),
  clearAuthCookies: jest.fn(),
  isValidRole: jest.fn(() => true),
}));

// ── Imports ───────────────────────────────────────────────────────────────────

import React from "react";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ShieldCheck, Shield } from "lucide-react";
import { PortalLoginForm } from "../components/auth/PortalLoginForm";
import { ADMIN_LOGIN_CONFIG, SUPER_ADMIN_LOGIN_CONFIG } from "../lib/constants";
import api from "../lib/api";

// ── Shared test data ──────────────────────────────────────────────────────────

const ADMIN_SUCCESS_RESPONSE = {
  data: {
    success: true,
    data: {
      access_token: "access_tok_admin",
      refresh_token: "refresh_tok_admin",
      user: { email: "admin@test.com", role: "admin" },
    },
  },
};

const SUPER_ADMIN_SUCCESS_RESPONSE = {
  data: {
    success: true,
    data: {
      access_token: "access_tok_sa",
      refresh_token: "refresh_tok_sa",
      user: {
        id: "sa_1",
        email: "superadmin@test.com",
        name: "Super Admin",
        role: "super_admin",
        institution_id: "inst_1",
        institution_name: "Test University",
      },
    },
  },
};

// Minimal props to render PortalLoginForm in admin configuration
const ADMIN_FORM_PROPS = {
  leftTitle: "Admin Portal",
  leftTagline: "Manage students and batches.",
  features: [],
  badgeLabel: "Admin Portal",
  badgeIcon: ShieldCheck,
  cardTitle: "Sign In",
  cardSubtitle: "Sign in to manage",
  ...ADMIN_LOGIN_CONFIG,
};

const SUPER_ADMIN_FORM_PROPS = {
  leftTitle: "Super Admin Portal",
  leftTagline: "Platform-wide oversight.",
  features: [],
  badgeLabel: "Super Admin",
  badgeIcon: Shield,
  cardTitle: "Sign In",
  cardSubtitle: "Sign in to manage",
  ...SUPER_ADMIN_LOGIN_CONFIG,
};

// ── Helpers ───────────────────────────────────────────────────────────────────

async function fillAndSubmit(email: string, password: string) {
  const user = userEvent.setup();
  await user.type(screen.getByPlaceholderText(/enter your email/i), email);
  await user.type(screen.getByPlaceholderText(/enter your password/i), password);
  await user.click(screen.getByRole("button", { name: /sign in/i }));
}

// ── Setup ─────────────────────────────────────────────────────────────────────

beforeEach(() => {
  mockPush.mockClear();
  mockSetTokens.mockClear();
  mockSetAuthCookies.mockClear();
  mockClearAuth.mockClear();
  jest.spyOn(api, "post").mockResolvedValue(ADMIN_SUCCESS_RESPONSE as any);
});

afterEach(() => {
  jest.restoreAllMocks();
});

// ─────────────────────────────────────────────────────────────────────────────
// Scenario 1–4: Successful admin login
// ─────────────────────────────────────────────────────────────────────────────

describe("Successful admin login — full submit flow", () => {
  beforeEach(() => {
    jest.spyOn(api, "post").mockResolvedValue(ADMIN_SUCCESS_RESPONSE as any);
    render(<PortalLoginForm {...ADMIN_FORM_PROPS} />);
  });

  it("calls api.post with the correct admin endpoint and credentials", async () => {
    await fillAndSubmit("admin@test.com", "password123");
    await waitFor(() => {
      expect(api.post).toHaveBeenCalledWith("/auth/login/", {
        email: "admin@test.com",
        password: "password123",
        role: "admin",
      });
    });
  });

  it("calls setAuthCookies with 'admin' role and the access token", async () => {
    await fillAndSubmit("admin@test.com", "password123");
    await waitFor(() => {
      expect(mockSetAuthCookies).toHaveBeenCalledWith(
        "admin",
        "access_tok_admin"
      );
    });
  });

  it("calls setTokens with access token, refresh token, and user object", async () => {
    await fillAndSubmit("admin@test.com", "password123");
    await waitFor(() => {
      expect(mockSetTokens).toHaveBeenCalledWith(
        "access_tok_admin",
        "refresh_tok_admin",
        { email: "admin@test.com", role: "admin" }
      );
    });
  });

  it("redirects to /admin/batch after successful login", async () => {
    await fillAndSubmit("admin@test.com", "password123");
    await waitFor(() => {
      expect(mockPush).toHaveBeenCalledWith("/admin/batch");
    });
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// Scenario 5: Failed login — error message shown
// ─────────────────────────────────────────────────────────────────────────────

describe("Failed admin login — error handling", () => {
  it("displays the server error message when credentials are wrong", async () => {
    jest.spyOn(api, "post").mockRejectedValue({
      isAxiosError: true,
      response: { status: 401, data: { detail: "Invalid credentials." } },
    });
    render(<PortalLoginForm {...ADMIN_FORM_PROPS} />);

    await fillAndSubmit("admin@test.com", "wrongpassword");

    await waitFor(() => {
      expect(screen.getByRole("alert")).toHaveTextContent("Invalid credentials.");
    });
  });

  it("does NOT call setAuthCookies or router.push when login fails", async () => {
    jest.spyOn(api, "post").mockRejectedValue({
      isAxiosError: true,
      response: { status: 401, data: { detail: "Invalid credentials." } },
    });
    render(<PortalLoginForm {...ADMIN_FORM_PROPS} />);

    await fillAndSubmit("admin@test.com", "wrongpassword");

    await waitFor(() => {
      expect(mockSetAuthCookies).not.toHaveBeenCalled();
      expect(mockPush).not.toHaveBeenCalled();
    });
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// Scenario 6–7: Successful super-admin login
// ─────────────────────────────────────────────────────────────────────────────

describe("Successful super-admin login — full submit flow", () => {
  beforeEach(() => {
    jest.spyOn(api, "post").mockResolvedValue(
      SUPER_ADMIN_SUCCESS_RESPONSE as any
    );
    render(<PortalLoginForm {...SUPER_ADMIN_FORM_PROPS} />);
  });

  it("calls api.post with /auth/login/ and includes role: super_admin in body", async () => {
    await fillAndSubmit("superadmin@test.com", "password123");
    await waitFor(() => {
      expect(api.post).toHaveBeenCalledWith("/auth/login/", {
        email: "superadmin@test.com",
        password: "password123",
        role: "super_admin",
      });
    });
  });

  it("calls setAuthCookies with 'super_admin' role and the access token", async () => {
    await fillAndSubmit("superadmin@test.com", "password123");
    await waitFor(() => {
      expect(mockSetAuthCookies).toHaveBeenCalledWith(
        "super_admin",
        "access_tok_sa"
      );
    });
  });

  it("redirects to /super-admin/overview after successful login", async () => {
    await fillAndSubmit("superadmin@test.com", "password123");
    await waitFor(() => {
      expect(mockPush).toHaveBeenCalledWith("/super-admin/overview");
    });
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// Scenario: Form validation — submit blocked without input
// ─────────────────────────────────────────────────────────────────────────────

describe("Form validation", () => {
  it("does NOT call api.post when form is submitted empty", async () => {
    render(<PortalLoginForm {...ADMIN_FORM_PROPS} />);
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: /sign in/i }));

    // Wait a tick to ensure any async effects settle
    await waitFor(() => {
      expect(api.post).not.toHaveBeenCalled();
    });
  });

  it("shows required-field error when email is missing", async () => {
    render(<PortalLoginForm {...ADMIN_FORM_PROPS} />);
    const user = userEvent.setup();
    await user.type(screen.getByPlaceholderText(/enter your password/i), "pass123");
    await user.click(screen.getByRole("button", { name: /sign in/i }));

    await waitFor(() => {
      expect(screen.getByText(/email is required/i)).toBeInTheDocument();
    });
  });

  it("shows required-field error when password is missing", async () => {
    render(<PortalLoginForm {...ADMIN_FORM_PROPS} />);
    const user = userEvent.setup();
    await user.type(screen.getByPlaceholderText(/enter your email/i), "admin@test.com");
    await user.click(screen.getByRole("button", { name: /sign in/i }));

    await waitFor(() => {
      expect(screen.getByText(/password is required/i)).toBeInTheDocument();
    });
  });
});
