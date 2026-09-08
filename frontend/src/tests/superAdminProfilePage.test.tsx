/**
 * @jest-environment jsdom
 *
 * Coverage for the Super Admin "My Profile" page (2026-08-20) — mirrors
 * admin/profile/page.tsx exactly, using the same /auth/me/ and
 * /auth/me/change-password/ endpoints (opened to Super Admin the same day).
 * No AdminLayout/ITLayout mock needed here — super-admin/* pages are
 * chrome-free (Pattern B, file-based layout.tsx provides chrome instead).
 */

jest.mock("next/navigation", () => ({
  useRouter: () => ({ push: jest.fn() }),
}));

const mockToastSuccess = jest.fn();
const mockToastError = jest.fn();
jest.mock("@/components/ui/Toast", () => ({
  useToast: () => ({
    showToast: jest.fn(),
    success: mockToastSuccess,
    error: mockToastError,
    warning: jest.fn(),
  }),
}));

const mockAuthStore = {
  user: { id: "sa-1", role: "super_admin", email: "dean@test.com", name: "Dean Original" },
  accessToken: "fake-token",
  clearAuth: jest.fn(),
  setUser: jest.fn(),
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
import SuperAdminProfilePage from "@/app/super-admin/profile/page";

const PROFILE = {
  id: "sa-1",
  email: "dean@test.com",
  name: "Dean Original",
  is_active: true,
  date_joined: "2026-08-01T00:00:00Z",
};

beforeEach(() => {
  mockToastSuccess.mockClear();
  mockToastError.mockClear();
});

afterEach(() => {
  jest.restoreAllMocks();
});

describe("Super Admin — My Profile page", () => {
  it("loads and displays the profile from /auth/me/", async () => {
    const getSpy = jest.spyOn(api, "get").mockResolvedValue({ data: { data: PROFILE } } as any);
    render(<SuperAdminProfilePage />);
    await waitFor(() => expect(screen.getAllByText("Dean Original").length).toBeGreaterThan(0));
    expect(getSpy).toHaveBeenCalledWith("/auth/me/");
    expect(screen.getAllByText("dean@test.com").length).toBeGreaterThan(0);
  });

  it("edits the name via PATCH /auth/me/", async () => {
    const user = userEvent.setup();
    jest.spyOn(api, "get").mockResolvedValue({ data: { data: PROFILE } } as any);
    const patchSpy = jest.spyOn(api, "patch").mockResolvedValue({
      data: { data: { ...PROFILE, name: "Dean Renamed" } },
    } as any);
    render(<SuperAdminProfilePage />);
    await waitFor(() => expect(screen.getAllByText("Dean Original").length).toBeGreaterThan(0));

    await user.click(screen.getByRole("button", { name: /edit/i }));
    const nameInput = screen.getByPlaceholderText("Your full name");
    await user.clear(nameInput);
    await user.type(nameInput, "Dean Renamed");
    await user.click(screen.getByRole("button", { name: /save/i }));

    await waitFor(() => expect(patchSpy).toHaveBeenCalledWith("/auth/me/", { name: "Dean Renamed" }));
    await waitFor(() => expect(screen.getAllByText("Dean Renamed").length).toBeGreaterThan(0));
    expect(mockToastSuccess).toHaveBeenCalledWith("Name updated successfully.");
  });

  it("changes the password via POST /auth/me/change-password/", async () => {
    const user = userEvent.setup();
    jest.spyOn(api, "get").mockResolvedValue({ data: { data: PROFILE } } as any);
    const postSpy = jest.spyOn(api, "post").mockResolvedValue({ data: {} } as any);
    render(<SuperAdminProfilePage />);
    await waitFor(() => expect(screen.getAllByText("Dean Original").length).toBeGreaterThan(0));

    await user.click(screen.getByRole("button", { name: /change password/i }));
    await user.type(screen.getByPlaceholderText("Enter your current password"), "OldPass@1");
    await user.type(screen.getByPlaceholderText("Min. 8 characters"), "NewPass@123");
    await user.type(screen.getByPlaceholderText("Re-enter new password"), "NewPass@123");
    await user.click(screen.getByRole("button", { name: /update password/i }));

    await waitFor(() => expect(postSpy).toHaveBeenCalledWith("/auth/me/change-password/", {
      current_password: "OldPass@1",
      new_password: "NewPass@123",
      confirm_password: "NewPass@123",
    }));
    expect(mockToastSuccess).toHaveBeenCalledWith("Password changed. Logging you out in a moment…");
  });

  it("rejects mismatched new/confirm passwords without calling the API", async () => {
    const user = userEvent.setup();
    jest.spyOn(api, "get").mockResolvedValue({ data: { data: PROFILE } } as any);
    const postSpy = jest.spyOn(api, "post").mockResolvedValue({ data: {} } as any);
    render(<SuperAdminProfilePage />);
    await waitFor(() => expect(screen.getAllByText("Dean Original").length).toBeGreaterThan(0));

    await user.click(screen.getByRole("button", { name: /change password/i }));
    await user.type(screen.getByPlaceholderText("Enter your current password"), "OldPass@1");
    await user.type(screen.getByPlaceholderText("Min. 8 characters"), "NewPass@123");
    await user.type(screen.getByPlaceholderText("Re-enter new password"), "Mismatch@123");
    await user.click(screen.getByRole("button", { name: /update password/i }));

    await waitFor(() => expect(screen.getByText("Passwords do not match.")).toBeInTheDocument());
    expect(postSpy).not.toHaveBeenCalled();
  });

  it("shows a retry option when the profile fails to load", async () => {
    jest.spyOn(api, "get").mockRejectedValue(new Error("network error"));
    render(<SuperAdminProfilePage />);
    await waitFor(() => expect(screen.getByText("Retry")).toBeInTheDocument());
  });
});
