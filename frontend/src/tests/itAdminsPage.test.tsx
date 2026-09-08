/**
 * @jest-environment jsdom
 *
 * Coverage for the IT "Admins" management page (2026-08-19, phase 1) — the
 * same /auth/admins/ endpoint and full CRUD capability Super Admin has on
 * super-admin/admins/page.tsx (which was restricted to read-only the same
 * day, phase 2 — see superAdminAdminsPage.test.tsx for that side).
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

const CSE_DEPT = { id: "d-cse", code: "CSE", name: "Computer Science and Engineering", is_active: true, created_at: "", updated_at: "" };
const MECH_DEPT = { id: "d-mech", code: "MECH", name: "Mechanical Engineering", is_active: true, created_at: "", updated_at: "" };
jest.mock("@/lib/departmentsContext", () => ({
  useDepartments: () => ({
    departments: [CSE_DEPT, MECH_DEPT],
    activeDepartments: [CSE_DEPT, MECH_DEPT],
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
import ITAdminsPage from "@/app/it/admins/page";

const ADMIN_ROW = {
  id: "admin-1", email: "priya@test.com", name: "Priya Sharma", department: "CSE", is_active: true, created_at: "2026-08-19T00:00:00Z",
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

describe("IT — Admins page", () => {
  it("lists admins from /auth/admins/", async () => {
    const getSpy = jest.spyOn(api, "get").mockResolvedValue({ data: { data: [ADMIN_ROW] } } as any);
    render(<ITAdminsPage />);
    await waitFor(() => expect(screen.getByText("Priya Sharma")).toBeInTheDocument());
    expect(getSpy).toHaveBeenCalledWith("/auth/admins/");
    expect(within(screen.getByRole("table")).getByText("CSE")).toBeInTheDocument();
  });

  it("shows the empty state with an Add Admin action when there are none", async () => {
    mockList([]);
    render(<ITAdminsPage />);
    await waitFor(() => expect(screen.getByText("No Admins Yet")).toBeInTheDocument());
  });

  it("creates an admin via /auth/admins/ and shows it in the list", async () => {
    const user = userEvent.setup();
    mockList([]);
    const postSpy = jest.spyOn(api, "post").mockResolvedValue({
      data: { data: { id: "admin-2", email: "new-admin@test.com", name: "New Admin", department: "MECH", is_active: true, created_at: "2026-08-19T00:00:00Z" } },
    } as any);
    render(<ITAdminsPage />);
    await waitFor(() => expect(screen.getByText("No Admins Yet")).toBeInTheDocument());

    await user.click(screen.getAllByText("Add Admin")[0]);
    await user.type(screen.getByPlaceholderText("admin@institution.edu"), "new-admin@test.com");
    await user.type(screen.getByPlaceholderText(/Rajan Kumar/), "New Admin");
    await user.selectOptions(screen.getByLabelText("Department"), "MECH");
    await user.click(screen.getByRole("button", { name: "Create Admin" }));

    await waitFor(() => expect(postSpy).toHaveBeenCalledWith("/auth/admins/", { name: "New Admin", email: "new-admin@test.com", department: "MECH" }));
    await waitFor(() => expect(screen.getByText("New Admin")).toBeInTheDocument());
    expect(mockToastSuccess).toHaveBeenCalledWith("Admin account created.");
  });

  it("edits an admin's name and department via the per-row action", async () => {
    const user = userEvent.setup();
    mockList([ADMIN_ROW]);
    const patchSpy = jest.spyOn(api, "patch").mockResolvedValue({
      data: { data: { ...ADMIN_ROW, name: "Priya Renamed", department: "MECH" } },
    } as any);
    render(<ITAdminsPage />);
    await waitFor(() => expect(screen.getByText("Priya Sharma")).toBeInTheDocument());

    await user.click(screen.getByLabelText("Edit"));
    const nameInput = within(screen.getByRole("dialog")).getByPlaceholderText(/Rajan Kumar/);
    await user.clear(nameInput);
    await user.type(nameInput, "Priya Renamed");
    await user.selectOptions(within(screen.getByRole("dialog")).getByLabelText("Department"), "MECH");
    await user.click(screen.getByRole("button", { name: "Save" }));

    await waitFor(() => expect(patchSpy).toHaveBeenCalledWith("/auth/admins/admin-1/", { name: "Priya Renamed", department: "MECH" }));
    await waitFor(() => expect(screen.getByText("Priya Renamed")).toBeInTheDocument());
  });

  it("resets an admin's password to default via the per-row action", async () => {
    const user = userEvent.setup();
    mockList([ADMIN_ROW]);
    const postSpy = jest.spyOn(api, "post").mockResolvedValue({ data: {} } as any);
    render(<ITAdminsPage />);
    await waitFor(() => expect(screen.getByText("Priya Sharma")).toBeInTheDocument());

    await user.click(screen.getByLabelText("Reset to Default Password"));
    await user.click(screen.getByRole("button", { name: "Reset to Default" }));

    await waitFor(() => expect(postSpy).toHaveBeenCalledWith("/auth/admins/admin-1/reset-default-password/"));
    expect(mockToastSuccess).toHaveBeenCalledWith("Password reset to default for Priya Sharma.");
  });

  it("deactivates an active admin", async () => {
    const user = userEvent.setup();
    mockList([ADMIN_ROW]);
    const patchSpy = jest.spyOn(api, "patch").mockResolvedValue({
      data: { data: { ...ADMIN_ROW, is_active: false } },
    } as any);
    render(<ITAdminsPage />);
    await waitFor(() => expect(screen.getByText("Priya Sharma")).toBeInTheDocument());

    await user.click(screen.getByLabelText("Deactivate"));
    await user.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Deactivate" }));

    await waitFor(() => expect(patchSpy).toHaveBeenCalledWith("/auth/admins/admin-1/", { is_active: false }));
    await waitFor(() => expect(within(screen.getByRole("table")).getByText("Inactive")).toBeInTheDocument());
  });

  it("deletes an admin only after typing DELETE to confirm", async () => {
    const user = userEvent.setup();
    mockList([ADMIN_ROW]);
    const deleteSpy = jest.spyOn(api, "delete").mockResolvedValue({ data: {} } as any);
    render(<ITAdminsPage />);
    await waitFor(() => expect(screen.getByText("Priya Sharma")).toBeInTheDocument());

    await user.click(screen.getByLabelText("Delete Admin"));
    const confirmButton = screen.getByRole("button", { name: "Permanently Delete" });
    expect(confirmButton).toBeDisabled();

    await user.type(screen.getByPlaceholderText("Type DELETE to confirm"), "DELETE");
    expect(confirmButton).toBeEnabled();
    await user.click(confirmButton);

    await waitFor(() => expect(deleteSpy).toHaveBeenCalledWith("/auth/admins/admin-1/"));
    await waitFor(() => expect(screen.queryByText("Priya Sharma")).not.toBeInTheDocument());
  });

  it("shows a page-level error with retry when the list fails to load", async () => {
    jest.spyOn(api, "get").mockRejectedValue(new Error("network error"));
    render(<ITAdminsPage />);
    await waitFor(() => expect(screen.getByText("Retry")).toBeInTheDocument());
  });

  it("opens the bulk import modal via Import CSV", async () => {
    const user = userEvent.setup();
    mockList([]);
    render(<ITAdminsPage />);
    await waitFor(() => expect(screen.getByText("No Admins Yet")).toBeInTheDocument());

    expect(screen.queryByLabelText("bulk-import-modal-stub")).not.toBeInTheDocument();
    await user.click(screen.getByText("Import CSV"));
    expect(screen.getByLabelText("bulk-import-modal-stub")).toBeInTheDocument();
  });
});
