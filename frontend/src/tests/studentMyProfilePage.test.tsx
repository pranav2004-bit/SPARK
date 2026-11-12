/**
 * @jest-environment jsdom
 *
 * Regression coverage for a real production bug: a first-time student who
 * changed their password during profile setup got sent back to the setup
 * page on their very next login, even though they'd already completed it.
 *
 * Root cause: changing the password bumps the user's token_version in
 * auth-service, which immediately invalidates the token the page was still
 * holding from the original login. The setup flow's two remaining calls
 * (PUT /users/me/, then PATCH /auth/profile/complete/ — the one that
 * actually persists is_profile_completed=True in auth-service) kept using
 * that now-stale token, so auth-service rejected the PATCH before its view
 * body ever ran. Fixed by applying the fresh tokens the change-password
 * call returns immediately, before either subsequent call fires — these
 * tests assert exactly that ordering, not just that the calls eventually
 * happen.
 */

jest.mock("next/navigation", () => ({
  useRouter: () => ({ push: jest.fn() }),
}));

jest.mock("@/components/layout/StudentLayout", () => ({
  StudentLayout: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}));

const mockToastSuccess = jest.fn();
const mockToastError = jest.fn();
jest.mock("@/components/ui/Toast", () => ({
  useToast: () => ({ success: mockToastSuccess, error: mockToastError }),
}));

jest.mock("@/lib/cookies", () => ({ setAuthCookies: jest.fn() }));
jest.mock("@/lib/scrollRedirect", () => ({ consumeScrollRedirect: () => null }));

const mockSetTokens = jest.fn();
const mockAuthStore = {
  user: {
    student_id: "stu-1",
    role: "student",
    is_profile_completed: false,
    fullname: "",
  },
  accessToken: "old-access-token",
  refreshToken: "old-refresh-token",
  setTokens: mockSetTokens,
};
jest.mock("@/lib/auth-store", () => ({
  useAuthStore: Object.assign(
    jest.fn((selector: any) => (typeof selector === "function" ? selector(mockAuthStore) : mockAuthStore)),
    { getState: jest.fn(() => mockAuthStore) },
  ),
}));

import React from "react";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import api from "@/lib/api";
import { setAuthCookies } from "@/lib/cookies";
import MyProfilePage from "@/app/students/my_profile/page";

const PROFILE = {
  student_id: "stu-1",
  fullname: "",
  college_email_id: "",
  is_profile_completed: false,
};

// jsdom's window.location isn't actually replaceable (it's non-configurable),
// so the component's final `window.location.href = ...` on success logs a
// harmless "Not implemented: navigation" console.error in every test below —
// expected jsdom noise, not a real failure; nothing to assert on here.

beforeEach(() => {
  mockSetTokens.mockClear();
  mockToastSuccess.mockClear();
  mockToastError.mockClear();
  (setAuthCookies as jest.Mock).mockClear();
});

afterEach(() => {
  jest.restoreAllMocks();
});

async function fillRequiredFields(user: ReturnType<typeof userEvent.setup>) {
  await user.type(screen.getByLabelText("Full name"), "Student Name");
  await user.type(screen.getByLabelText("College email"), "student@college.edu");
}

describe("Student My Profile — first-time setup", () => {
  it(
    "applies the fresh change-password tokens BEFORE syncing the profile, " +
      "not after (the actual regression)",
    async () => {
      const callOrder: string[] = [];
      jest.spyOn(api, "get").mockResolvedValue({ data: { data: PROFILE } } as any);
      jest.spyOn(api, "post").mockImplementation(async () => {
        callOrder.push("change-password");
        return {
          data: { data: { access_token: "fresh-access", refresh_token: "fresh-refresh" } },
        } as any;
      });
      jest.spyOn(api, "put").mockImplementation(async () => {
        callOrder.push("put-users-me");
        return { data: { data: { ...PROFILE, fullname: "Student Name", is_profile_completed: true } } } as any;
      });
      jest.spyOn(api, "patch").mockImplementation(async () => {
        callOrder.push("patch-profile-complete");
        return {
          data: { data: { access_token: "final-access", refresh_token: "final-refresh" } },
        } as any;
      });
      mockSetTokens.mockImplementation((access: string) => {
        if (access === "fresh-access") callOrder.push("setTokens-fresh");
        if (access === "final-access") callOrder.push("setTokens-final");
      });

      const user = userEvent.setup();
      render(<MyProfilePage />);
      await waitFor(() => expect(screen.getByLabelText("Full name")).toBeInTheDocument());

      await fillRequiredFields(user);
      await user.click(screen.getByText("Change default password"));
      await user.type(screen.getByLabelText("Current password"), "defaultpass123");
      await user.type(screen.getByLabelText("New password"), "brandnewpass456");
      await user.type(screen.getByLabelText("Confirm new password"), "brandnewpass456");
      await user.click(screen.getByRole("button", { name: /complete setup/i }));

      await waitFor(() => expect(callOrder).toContain("patch-profile-complete"));

      // The core regression assertion: the fresh tokens from step 1 must be
      // applied strictly before the two calls that depend on them firing —
      // not merely "eventually called at some point".
      const freshIdx = callOrder.indexOf("setTokens-fresh");
      const putIdx = callOrder.indexOf("put-users-me");
      const patchIdx = callOrder.indexOf("patch-profile-complete");
      expect(freshIdx).toBeGreaterThanOrEqual(0);
      expect(freshIdx).toBeLessThan(putIdx);
      expect(freshIdx).toBeLessThan(patchIdx);

      // And the final sync's own tokens are still applied last, as before.
      expect(mockSetTokens).toHaveBeenLastCalledWith(
        "final-access", "final-refresh", expect.anything(),
      );
      expect(setAuthCookies).toHaveBeenCalledWith("student", "fresh-access");
      expect(setAuthCookies).toHaveBeenCalledWith("student", "final-access");
    },
    15000, // typing across 5 fields comfortably exceeds jest's 5s default
  );

  it("never calls the change-password endpoint or applies interim tokens when the student keeps the default password", async () => {
    jest.spyOn(api, "get").mockResolvedValue({ data: { data: PROFILE } } as any);
    const postSpy = jest.spyOn(api, "post");
    jest.spyOn(api, "put").mockResolvedValue({
      data: { data: { ...PROFILE, fullname: "Student Name", is_profile_completed: true } },
    } as any);
    jest.spyOn(api, "patch").mockResolvedValue({
      data: { data: { access_token: "final-access", refresh_token: "final-refresh" } },
    } as any);

    const user = userEvent.setup();
    render(<MyProfilePage />);
    await waitFor(() => expect(screen.getByLabelText("Full name")).toBeInTheDocument());

    await fillRequiredFields(user);
    // "Change default password" checkbox deliberately left unchecked.
    await user.click(screen.getByRole("button", { name: /complete setup/i }));

    await waitFor(() => expect(mockSetTokens).toHaveBeenCalledTimes(1));
    expect(postSpy).not.toHaveBeenCalled();
    expect(mockSetTokens).toHaveBeenCalledWith("final-access", "final-refresh", expect.anything());
  });
});
