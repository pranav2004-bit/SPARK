/**
 * @jest-environment jsdom
 *
 * Coverage for the Super Admin "Admins" page after it was restricted to
 * read-only (2026-08-19) — admin account CRUD moved to IT (see
 * itAdminsPage.test.tsx for that side). Locks in: no Add/Edit/Reset/
 * Toggle/Delete affordances, list + search/status-filter still work.
 */

jest.mock("next/navigation", () => ({
  useRouter: () => ({ push: jest.fn() }),
}));

import React from "react";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import api from "@/lib/api";
import SuperAdminAdminsPage from "@/app/super-admin/admins/page";

const ADMIN_ROW = {
  id: "admin-1", email: "priya@test.com", name: "Priya Sharma", is_active: true, created_at: "2026-08-19T00:00:00Z",
};

function mockList(rows: any[]) {
  jest.spyOn(api, "get").mockResolvedValue({ data: { data: rows } } as any);
}

afterEach(() => {
  jest.restoreAllMocks();
});

describe("Super Admin — Admins page (read-only)", () => {
  it("lists admins and shows their data", async () => {
    mockList([ADMIN_ROW]);
    render(<SuperAdminAdminsPage />);
    await waitFor(() => expect(screen.getByText("Priya Sharma")).toBeInTheDocument());
    expect(screen.getByText("priya@test.com")).toBeInTheDocument();
    expect(within(screen.getByRole("table")).getByText("Active")).toBeInTheDocument();
  });

  it("renders no Add Admin button", async () => {
    mockList([ADMIN_ROW]);
    render(<SuperAdminAdminsPage />);
    await waitFor(() => expect(screen.getByText("Priya Sharma")).toBeInTheDocument());
    expect(screen.queryByText("Add Admin")).not.toBeInTheDocument();
  });

  it("renders no per-row edit/reset/toggle/delete actions", async () => {
    mockList([ADMIN_ROW]);
    render(<SuperAdminAdminsPage />);
    await waitFor(() => expect(screen.getByText("Priya Sharma")).toBeInTheDocument());
    expect(screen.queryByLabelText("Edit Name")).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Reset to Default Password")).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Deactivate")).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Delete Admin")).not.toBeInTheDocument();
  });

  it("still supports search filtering", async () => {
    const user = userEvent.setup();
    mockList([ADMIN_ROW, { ...ADMIN_ROW, id: "admin-2", email: "other@test.com", name: "Other Person" }]);
    render(<SuperAdminAdminsPage />);
    await waitFor(() => expect(screen.getByText("Priya Sharma")).toBeInTheDocument());

    await user.type(screen.getByPlaceholderText("Search by name or email…"), "Priya");
    await waitFor(() => expect(screen.queryByText("Other Person")).not.toBeInTheDocument());
    expect(screen.getByText("Priya Sharma")).toBeInTheDocument();
  });

  it("shows the empty state with no action button when there are no admins", async () => {
    mockList([]);
    render(<SuperAdminAdminsPage />);
    await waitFor(() => expect(screen.getByText("No Admins Yet")).toBeInTheDocument());
    expect(screen.queryByRole("button", { name: /add admin/i })).not.toBeInTheDocument();
  });

  it("shows a page-level error with retry when the list fails to load", async () => {
    jest.spyOn(api, "get").mockRejectedValue(new Error("network error"));
    render(<SuperAdminAdminsPage />);
    await waitFor(() => expect(screen.getByText("Retry")).toBeInTheDocument());
  });
});
