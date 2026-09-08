/**
 * @jest-environment jsdom
 *
 * Coverage for the IT "Super Admins" management page (2026-08-20) — IT is
 * now the platform's bootstrapped root and provisions Super Admin accounts
 * the same way it/admins/page.tsx provisions Admin accounts, via
 * /auth/super-admins/. Unlike Admin, Super Admin has no read-only remnant
 * of its own on this resource — zero access, not even GET.
 */

jest.mock("next/navigation", () => ({
  useRouter: () => ({ push: jest.fn() }),
}));

jest.mock("@/components/layout/ITLayout", () => ({
  ITLayout: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}));

const mockToastSuccess = jest.fn();
const mockToastError = jest.fn();
jest.mock("@/components/ui/Toast", () => ({
  useToast: () => ({ success: mockToastSuccess, error: mockToastError }),
}));

const ECE_DEPT = { id: "d-ece", code: "ECE", name: "Electronics and Communication Engineering", is_active: true, created_at: "", updated_at: "" };
const MECH_DEPT = { id: "d-mech", code: "MECH", name: "Mechanical Engineering", is_active: true, created_at: "", updated_at: "" };
jest.mock("@/lib/departmentsContext", () => ({
  useDepartments: () => ({
    departments: [ECE_DEPT, MECH_DEPT],
    activeDepartments: [ECE_DEPT, MECH_DEPT],
    loading: false, error: "", refetch: jest.fn(),
  }),
}));

jest.mock("@/components/admin/BulkAccountImportModal", () => ({
  BulkAccountImportModal: ({ isOpen }: { isOpen: boolean }) =>
    isOpen ? <div role="dialog" aria-label="bulk-import-modal-stub" /> : null,
}));

import React from "react";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import api from "@/lib/api";
import ITSuperAdminsPage from "@/app/it/super-admins/page";

const SUPER_ADMIN_ROW = {
  id: "sa-1", email: "priya@test.com", name: "Priya Sharma", department: "CSE", is_active: true, created_at: "2026-08-20T00:00:00Z",
};

function mockList(rows: any[]) {
  jest.spyOn(api, "get").mockResolvedValue({ data: { data: rows } } as any);
}

beforeEach(() => {
  mockToastSuccess.mockClear();
  mockToastError.mockClear();
});

afterEach(() => {
  jest.restoreAllMocks();
});

describe("IT — Super Admins page", () => {
  it("lists super admins from /auth/super-admins/", async () => {
    const getSpy = jest.spyOn(api, "get").mockResolvedValue({ data: { data: [SUPER_ADMIN_ROW] } } as any);
    render(<ITSuperAdminsPage />);
    await waitFor(() => expect(screen.getByText("Priya Sharma")).toBeInTheDocument());
    expect(getSpy).toHaveBeenCalledWith("/auth/super-admins/");
    expect(within(screen.getByRole("table")).getByText("CSE")).toBeInTheDocument();
  });

  it("shows the empty state with an Add Super Admin action when there are none", async () => {
    mockList([]);
    render(<ITSuperAdminsPage />);
    await waitFor(() => expect(screen.getByText("No Super Admins Yet")).toBeInTheDocument());
  });

  it("creates a super admin via /auth/super-admins/ and shows it in the list", async () => {
    const user = userEvent.setup();
    mockList([]);
    const postSpy = jest.spyOn(api, "post").mockResolvedValue({
      data: { data: { id: "sa-2", email: "new-sa@test.com", name: "New Super Admin", department: "ECE", is_active: true, created_at: "2026-08-20T00:00:00Z" } },
    } as any);
    render(<ITSuperAdminsPage />);
    await waitFor(() => expect(screen.getByText("No Super Admins Yet")).toBeInTheDocument());

    await user.click(screen.getAllByText("Add Super Admin")[0]);
    await user.type(screen.getByPlaceholderText("superadmin@institution.edu"), "new-sa@test.com");
    await user.type(screen.getByPlaceholderText(/Rajan Kumar/), "New Super Admin");
    await user.selectOptions(screen.getByLabelText("Department"), "ECE");
    await user.click(screen.getByRole("button", { name: "Create Super Admin" }));

    await waitFor(() => expect(postSpy).toHaveBeenCalledWith("/auth/super-admins/", { name: "New Super Admin", email: "new-sa@test.com", department: "ECE" }));
    await waitFor(() => expect(screen.getByText("New Super Admin")).toBeInTheDocument());
    expect(mockToastSuccess).toHaveBeenCalledWith("Super admin account created.");
  });

  it("edits a super admin's name and department via the per-row action", async () => {
    const user = userEvent.setup();
    mockList([SUPER_ADMIN_ROW]);
    const patchSpy = jest.spyOn(api, "patch").mockResolvedValue({
      data: { data: { ...SUPER_ADMIN_ROW, name: "Priya Renamed", department: "MECH" } },
    } as any);
    render(<ITSuperAdminsPage />);
    await waitFor(() => expect(screen.getByText("Priya Sharma")).toBeInTheDocument());

    await user.click(screen.getByLabelText("Edit"));
    const nameInput = within(screen.getByRole("dialog")).getByPlaceholderText(/Rajan Kumar/);
    await user.clear(nameInput);
    await user.type(nameInput, "Priya Renamed");
    await user.selectOptions(within(screen.getByRole("dialog")).getByLabelText("Department"), "MECH");
    await user.click(screen.getByRole("button", { name: "Save" }));

    await waitFor(() => expect(patchSpy).toHaveBeenCalledWith("/auth/super-admins/sa-1/", { name: "Priya Renamed", department: "MECH" }));
    await waitFor(() => expect(screen.getByText("Priya Renamed")).toBeInTheDocument());
  });

  it("resets a super admin's password to default via the per-row action", async () => {
    const user = userEvent.setup();
    mockList([SUPER_ADMIN_ROW]);
    const postSpy = jest.spyOn(api, "post").mockResolvedValue({ data: {} } as any);
    render(<ITSuperAdminsPage />);
    await waitFor(() => expect(screen.getByText("Priya Sharma")).toBeInTheDocument());

    await user.click(screen.getByLabelText("Reset to Default Password"));
    await user.click(screen.getByRole("button", { name: "Reset to Default" }));

    await waitFor(() => expect(postSpy).toHaveBeenCalledWith("/auth/super-admins/sa-1/reset-default-password/"));
    expect(mockToastSuccess).toHaveBeenCalledWith("Password reset to default for Priya Sharma.");
  });

  it("deactivates an active super admin", async () => {
    const user = userEvent.setup();
    mockList([SUPER_ADMIN_ROW]);
    const patchSpy = jest.spyOn(api, "patch").mockResolvedValue({
      data: { data: { ...SUPER_ADMIN_ROW, is_active: false } },
    } as any);
    render(<ITSuperAdminsPage />);
    await waitFor(() => expect(screen.getByText("Priya Sharma")).toBeInTheDocument());

    await user.click(screen.getByLabelText("Deactivate"));
    await user.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Deactivate" }));

    await waitFor(() => expect(patchSpy).toHaveBeenCalledWith("/auth/super-admins/sa-1/", { is_active: false }));
    await waitFor(() => expect(within(screen.getByRole("table")).getByText("Inactive")).toBeInTheDocument());
  });

  it("deletes a super admin only after typing DELETE to confirm", async () => {
    const user = userEvent.setup();
    mockList([SUPER_ADMIN_ROW]);
    const deleteSpy = jest.spyOn(api, "delete").mockResolvedValue({ data: {} } as any);
    render(<ITSuperAdminsPage />);
    await waitFor(() => expect(screen.getByText("Priya Sharma")).toBeInTheDocument());

    await user.click(screen.getByLabelText("Delete Super Admin"));
    const confirmButton = screen.getByRole("button", { name: "Permanently Delete" });
    expect(confirmButton).toBeDisabled();

    await user.type(screen.getByPlaceholderText("Type DELETE to confirm"), "DELETE");
    expect(confirmButton).toBeEnabled();
    await user.click(confirmButton);

    await waitFor(() => expect(deleteSpy).toHaveBeenCalledWith("/auth/super-admins/sa-1/"));
    await waitFor(() => expect(screen.queryByText("Priya Sharma")).not.toBeInTheDocument());
  });

  it("shows a page-level error with retry when the list fails to load", async () => {
    jest.spyOn(api, "get").mockRejectedValue(new Error("network error"));
    render(<ITSuperAdminsPage />);
    await waitFor(() => expect(screen.getByText("Retry")).toBeInTheDocument());
  });

  it("opens the bulk import modal via Import CSV", async () => {
    const user = userEvent.setup();
    mockList([]);
    render(<ITSuperAdminsPage />);
    await waitFor(() => expect(screen.getByText("No Super Admins Yet")).toBeInTheDocument());

    expect(screen.queryByLabelText("bulk-import-modal-stub")).not.toBeInTheDocument();
    await user.click(screen.getByText("Import CSV"));
    expect(screen.getByLabelText("bulk-import-modal-stub")).toBeInTheDocument();
  });
});
