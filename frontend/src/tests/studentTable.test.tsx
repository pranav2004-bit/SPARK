/**
 * @jest-environment jsdom
 *
 * StudentTable is shared between Admin's read-only pages and IT's full-CRUD
 * pages (2026-08-19 reversal: Admin lost all Batches/Students write access,
 * IT is now exclusive). This locks in the `readOnly` prop contract: no
 * Actions column, no edit/toggle/reset/delete affordances, and none of the
 * three write modals mount — while the default (IT) usage is unaffected.
 */

jest.mock("@/components/ui/Toast", () => ({
  useToast: () => ({ error: jest.fn(), success: jest.fn() }),
}));

const CSE_DEPT = { id: "d-cse", code: "CSE", name: "Computer Science and Engineering", is_active: true, created_at: "", updated_at: "" };
jest.mock("@/lib/departmentsContext", () => ({
  useDepartments: () => ({ departments: [CSE_DEPT], activeDepartments: [CSE_DEPT], loading: false, error: "", refetch: jest.fn() }),
}));

import React from "react";
import { render, screen } from "@testing-library/react";
import { StudentTable } from "@/components/admin/StudentTable";
import type { Student } from "@/types";

const STUDENT: Student = {
  id: "s1",
  student_id: "STU001",
  fullname: "Jane Doe",
  college_email_id: "jane@college.edu",
  department: "CSE",
  batch_id: "b1",
  batch_name: "Batch 2024",
  is_active: true,
  is_profile_completed: true,
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
};

const baseProps = {
  students: [STUDENT],
  loading: false,
  totalCount: 1,
  page: 1,
  onPageChange: jest.fn(),
  onStudentUpdated: jest.fn(),
  onStudentDeleted: jest.fn(),
};

describe("StudentTable readOnly mode (Admin, 2026-08-19)", () => {
  it("hides the Actions column header", () => {
    render(<StudentTable {...baseProps} readOnly />);
    expect(screen.queryByLabelText("Actions")).not.toBeInTheDocument();
  });

  it("renders no edit/toggle/reset/delete buttons for the row", () => {
    render(<StudentTable {...baseProps} readOnly />);
    expect(screen.queryByTitle("Edit student")).not.toBeInTheDocument();
    expect(screen.queryByTitle("Disable student")).not.toBeInTheDocument();
    expect(screen.queryByTitle("Enable student")).not.toBeInTheDocument();
    expect(screen.queryByTitle("Reset password")).not.toBeInTheDocument();
    expect(screen.queryByTitle("Delete student")).not.toBeInTheDocument();
  });

  it("still renders the student's read data", () => {
    render(<StudentTable {...baseProps} readOnly />);
    expect(screen.getByText("STU001")).toBeInTheDocument();
    expect(screen.getByText("Jane Doe")).toBeInTheDocument();
    expect(screen.getByText("Active")).toBeInTheDocument();
  });

  it("mounts no write modals/dialogs", () => {
    render(<StudentTable {...baseProps} readOnly />);
    expect(screen.queryByText("Edit Student")).not.toBeInTheDocument();
    expect(screen.queryByText("Reset Password")).not.toBeInTheDocument();
    expect(screen.queryByText("Delete Student")).not.toBeInTheDocument();
  });
});

describe("StudentTable default mode (IT, full CRUD, unaffected)", () => {
  it("renders the Actions column and all row buttons", () => {
    render(<StudentTable {...baseProps} />);
    expect(screen.getByLabelText("Actions")).toBeInTheDocument();
    expect(screen.getByTitle("Edit student")).toBeInTheDocument();
    expect(screen.getByTitle("Disable student")).toBeInTheDocument();
    expect(screen.getByTitle("Reset password")).toBeInTheDocument();
    expect(screen.getByTitle("Delete student")).toBeInTheDocument();
  });
});
