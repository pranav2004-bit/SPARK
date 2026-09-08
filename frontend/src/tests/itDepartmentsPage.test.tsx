/**
 * @jest-environment jsdom
 *
 * Coverage for the IT "Departments" management page (2026-08-20) — the
 * canonical department list every other portal/page reads from via
 * useDepartments(). CRUD here goes through /auth/departments/; on success
 * the page calls refetch() (mocked here) and broadcasts DEPARTMENTS_UPDATED
 * so every other open tab picks up the change.
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

const mockRefetch = jest.fn();
const mockBroadcast = jest.fn();
jest.mock("@/lib/adminChannel", () => ({
  ...jest.requireActual("@/lib/adminChannel"),
  broadcastAdminEvent: (event: unknown) => mockBroadcast(event),
}));

let mockDepartments: any[] = [];
jest.mock("@/lib/departmentsContext", () => ({
  useDepartments: () => ({
    departments: mockDepartments,
    activeDepartments: mockDepartments.filter((d) => d.is_active),
    loading: false,
    error: "",
    refetch: mockRefetch,
  }),
}));

import React from "react";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import api from "@/lib/api";
import ITDepartmentsPage from "@/app/it/departments/page";

const CSE_DEPT = { id: "d-1", code: "CSE", name: "Computer Science and Engineering", is_active: true, created_at: "2026-08-20T00:00:00Z", updated_at: "2026-08-20T00:00:00Z" };

beforeEach(() => {
  mockToastSuccess.mockClear();
  mockToastError.mockClear();
  mockRefetch.mockClear();
  mockBroadcast.mockClear();
  mockDepartments = [];
});

afterEach(() => {
  jest.restoreAllMocks();
});

describe("IT — Departments page", () => {
  it("lists departments from the shared context", () => {
    mockDepartments = [CSE_DEPT];
    render(<ITDepartmentsPage />);
    expect(screen.getByText("CSE")).toBeInTheDocument();
    expect(screen.getByText("Computer Science and Engineering")).toBeInTheDocument();
  });

  it("shows the empty state with an Add Department action when there are none", () => {
    render(<ITDepartmentsPage />);
    expect(screen.getByText("No Departments Yet")).toBeInTheDocument();
  });

  it("creates a department via /auth/departments/, refetches, and broadcasts the update", async () => {
    const user = userEvent.setup();
    const postSpy = jest.spyOn(api, "post").mockResolvedValue({
      data: { data: { id: "d-2", code: "ECE", name: "Electronics", is_active: true, created_at: "", updated_at: "" } },
    } as any);
    render(<ITDepartmentsPage />);

    await user.click(screen.getAllByText("Add Department")[0]);
    await user.type(screen.getByPlaceholderText("e.g. CSE"), "ece");
    await user.type(screen.getByPlaceholderText(/Computer Science and Engineering/), "Electronics");
    await user.click(screen.getByRole("button", { name: "Create Department" }));

    await waitFor(() => expect(postSpy).toHaveBeenCalledWith("/auth/departments/", { code: "ece", name: "Electronics" }));
    await waitFor(() => expect(mockRefetch).toHaveBeenCalled());
    expect(mockBroadcast).toHaveBeenCalledWith({ type: "DEPARTMENTS_UPDATED" });
    expect(mockToastSuccess).toHaveBeenCalledWith("Department created.");
  });

  it("edits a department's name via the per-row action", async () => {
    const user = userEvent.setup();
    mockDepartments = [CSE_DEPT];
    const patchSpy = jest.spyOn(api, "patch").mockResolvedValue({
      data: { data: { ...CSE_DEPT, name: "CS and Engg" } },
    } as any);
    render(<ITDepartmentsPage />);

    await user.click(screen.getByLabelText("Edit"));
    const nameInput = within(screen.getByRole("dialog")).getByPlaceholderText(/Computer Science and Engineering/);
    await user.clear(nameInput);
    await user.type(nameInput, "CS and Engg");
    await user.click(screen.getByRole("button", { name: "Save" }));

    await waitFor(() => expect(patchSpy).toHaveBeenCalledWith("/auth/departments/d-1/", { name: "CS and Engg" }));
    await waitFor(() => expect(mockRefetch).toHaveBeenCalled());
    expect(mockBroadcast).toHaveBeenCalledWith({ type: "DEPARTMENTS_UPDATED" });
  });

  it("does not offer the code field for editing", async () => {
    const user = userEvent.setup();
    mockDepartments = [CSE_DEPT];
    render(<ITDepartmentsPage />);
    await user.click(screen.getByLabelText("Edit"));
    expect(within(screen.getByRole("dialog")).queryByPlaceholderText("e.g. CSE")).not.toBeInTheDocument();
  });

  it("deactivates an active department", async () => {
    const user = userEvent.setup();
    mockDepartments = [CSE_DEPT];
    const patchSpy = jest.spyOn(api, "patch").mockResolvedValue({
      data: { data: { ...CSE_DEPT, is_active: false } },
    } as any);
    render(<ITDepartmentsPage />);

    await user.click(screen.getByLabelText("Deactivate"));
    await user.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Deactivate" }));

    await waitFor(() => expect(patchSpy).toHaveBeenCalledWith("/auth/departments/d-1/", { is_active: false }));
    await waitFor(() => expect(mockRefetch).toHaveBeenCalled());
  });

  it("deletes a department only after typing DELETE to confirm", async () => {
    const user = userEvent.setup();
    mockDepartments = [CSE_DEPT];
    const deleteSpy = jest.spyOn(api, "delete").mockResolvedValue({ data: {} } as any);
    render(<ITDepartmentsPage />);

    await user.click(screen.getByLabelText("Delete Department"));
    const confirmButton = screen.getByRole("button", { name: "Permanently Delete" });
    expect(confirmButton).toBeDisabled();

    await user.type(screen.getByPlaceholderText("Type DELETE to confirm"), "DELETE");
    expect(confirmButton).toBeEnabled();
    await user.click(confirmButton);

    await waitFor(() => expect(deleteSpy).toHaveBeenCalledWith("/auth/departments/d-1/"));
    await waitFor(() => expect(mockRefetch).toHaveBeenCalled());
    expect(mockBroadcast).toHaveBeenCalledWith({ type: "DEPARTMENTS_UPDATED" });
  });
});
