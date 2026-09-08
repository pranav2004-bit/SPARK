/**
 * @jest-environment jsdom
 *
 * Coverage for BulkAccountImportModal (2026-08-20, revised same day) —
 * shared bulk-CSV-import modal for the IT Admins and Super Admins pages,
 * parameterized by `role`. The CSV is a single column of emails (source of
 * mail IDs only); department is picked once via a dropdown and applied to
 * every row — same shape as the Students bulk import's shared Department.
 */

const CSE_DEPT = { id: "d-cse", code: "CSE", name: "Computer Science and Engineering", is_active: true, created_at: "", updated_at: "" };
const ECE_DEPT = { id: "d-ece", code: "ECE", name: "Electronics and Communication Engineering", is_active: true, created_at: "", updated_at: "" };
jest.mock("@/lib/departmentsContext", () => ({
  useDepartments: () => ({
    departments: [CSE_DEPT, ECE_DEPT],
    activeDepartments: [CSE_DEPT, ECE_DEPT],
    loading: false, error: "", refetch: jest.fn(),
  }),
}));

import React from "react";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import api from "@/lib/api";
import { BulkAccountImportModal } from "@/components/admin/BulkAccountImportModal";

function makeCSVFile(content: string, name = "import.csv") {
  return new File([content], name, { type: "text/csv" });
}

async function uploadFile(user: ReturnType<typeof userEvent.setup>, content: string) {
  const file = makeCSVFile(content);
  const input = document.querySelector('input[type="file"]') as HTMLInputElement;
  await user.upload(input, file);
}

/** The parse-summary lines split their text across a <strong> and sibling
 * text nodes (e.g. "<strong>2</strong> emails ready to import"), which
 * getByText's default matcher can't see as one string. */
function bySpanText(regex: RegExp) {
  return (_content: string, element: Element | null) =>
    element?.tagName.toLowerCase() === "span" && regex.test(element.textContent || "");
}

afterEach(() => {
  jest.restoreAllMocks();
});

describe("BulkAccountImportModal — role=admin", () => {
  const baseProps = {
    isOpen: true,
    onClose: jest.fn(),
    onImportComplete: jest.fn(),
    role: "admin" as const,
  };

  it("renders the Admins-specific title", () => {
    render(<BulkAccountImportModal {...baseProps} />);
    expect(screen.getByRole("heading", { name: "Import Admins" })).toBeInTheDocument();
  });

  it("parses a valid single-column CSV of emails", async () => {
    const user = userEvent.setup();
    render(<BulkAccountImportModal {...baseProps} />);

    await uploadFile(user, "email\nfaculty1@test.com\nfaculty2@test.com\n");

    await waitFor(() => expect(screen.getByText(bySpanText(/2 emails ready to import/))).toBeInTheDocument());
  });

  it("does not enable Import until a department is selected", async () => {
    const user = userEvent.setup();
    render(<BulkAccountImportModal {...baseProps} />);

    await uploadFile(user, "email\nfaculty1@test.com\n");
    await waitFor(() => expect(screen.getByText(bySpanText(/1 email ready to import/))).toBeInTheDocument());

    expect(screen.getByRole("button", { name: /Import 1 Admins/ })).toBeDisabled();

    await user.selectOptions(screen.getByLabelText(/Department/), "CSE");
    expect(screen.getByRole("button", { name: /Import 1 Admins/ })).toBeEnabled();
  });

  it("skips rows with an invalid email format", async () => {
    const user = userEvent.setup();
    render(<BulkAccountImportModal {...baseProps} />);

    await uploadFile(user, "email\nnot-an-email\nvalid@test.com\n");

    await waitFor(() => expect(screen.getByText(bySpanText(/1 email ready to import/))).toBeInTheDocument());
    expect(screen.getByText(bySpanText(/1 row skipped/))).toBeInTheDocument();
  });

  it("dedupes rows with the same email (case-insensitive)", async () => {
    const user = userEvent.setup();
    render(<BulkAccountImportModal {...baseProps} />);

    await uploadFile(user, "email\ndup@test.com\nDUP@test.com\n");

    await waitFor(() => expect(screen.getByText(bySpanText(/1 email ready to import/))).toBeInTheDocument());
    expect(screen.getByText(bySpanText(/1 duplicate removed/))).toBeInTheDocument();
  });

  it("submits the emails and department to /auth/admins/import/", async () => {
    const user = userEvent.setup();
    const postSpy = jest.spyOn(api, "post").mockResolvedValue({
      data: { data: { total: 1, created: 1, rejected: 0, results: [{ email: "faculty1@test.com", status: "created" }] } },
    } as any);
    render(<BulkAccountImportModal {...baseProps} />);

    await uploadFile(user, "email\nfaculty1@test.com\n");
    await waitFor(() => expect(screen.getByText(bySpanText(/1 email ready to import/))).toBeInTheDocument());
    await user.selectOptions(screen.getByLabelText(/Department/), "CSE");
    await user.click(screen.getByRole("button", { name: /Import 1 Admins/ }));

    await waitFor(() => expect(postSpy).toHaveBeenCalledWith("/auth/admins/import/", {
      emails: ["faculty1@test.com"],
      department: "CSE",
    }));
    await waitFor(() => expect(screen.getByText("All 1 admins created successfully!")).toBeInTheDocument());
  });

  it("shows rejected rows with reasons after a partial import", async () => {
    const user = userEvent.setup();
    jest.spyOn(api, "post").mockResolvedValue({
      data: {
        data: {
          total: 2, created: 1, rejected: 1,
          results: [
            { email: "ok@test.com", status: "created" },
            { email: "taken@test.com", status: "rejected", reason: "An account with this email already exists." },
          ],
        },
      },
    } as any);
    render(<BulkAccountImportModal {...baseProps} />);

    await uploadFile(user, "email\nok@test.com\ntaken@test.com\n");
    await waitFor(() => expect(screen.getByText(bySpanText(/2 emails ready to import/))).toBeInTheDocument());
    await user.selectOptions(screen.getByLabelText(/Department/), "CSE");
    await user.click(screen.getByRole("button", { name: /Import 2 Admins/ }));

    await waitFor(() => expect(screen.getByText("taken@test.com")).toBeInTheDocument());
    expect(screen.getByText("An account with this email already exists.")).toBeInTheDocument();
  });

  it("calls onImportComplete only when at least one account was created, on close", async () => {
    const user = userEvent.setup();
    const onImportComplete = jest.fn();
    jest.spyOn(api, "post").mockResolvedValue({
      data: { data: { total: 1, created: 1, rejected: 0, results: [{ email: "a@test.com", status: "created" }] } },
    } as any);
    render(<BulkAccountImportModal {...baseProps} onImportComplete={onImportComplete} />);

    await uploadFile(user, "email\na@test.com\n");
    await waitFor(() => expect(screen.getByText(bySpanText(/1 email ready to import/))).toBeInTheDocument());
    await user.selectOptions(screen.getByLabelText(/Department/), "CSE");
    await user.click(screen.getByRole("button", { name: /Import 1 Admins/ }));
    await waitFor(() => expect(screen.getByText("Done")).toBeInTheDocument());

    await user.click(screen.getByText("Done"));
    expect(onImportComplete).toHaveBeenCalled();
  });
});

describe("BulkAccountImportModal — role=super_admin", () => {
  const baseProps = {
    isOpen: true,
    onClose: jest.fn(),
    onImportComplete: jest.fn(),
    role: "super_admin" as const,
  };

  it("renders the Super Admins-specific title and posts to /auth/super-admins/import/", async () => {
    const user = userEvent.setup();
    const postSpy = jest.spyOn(api, "post").mockResolvedValue({
      data: { data: { total: 1, created: 1, rejected: 0, results: [{ email: "sa@test.com", status: "created" }] } },
    } as any);
    render(<BulkAccountImportModal {...baseProps} />);

    expect(screen.getByRole("heading", { name: "Import Super Admins" })).toBeInTheDocument();

    await uploadFile(user, "email\nsa@test.com\n");
    await waitFor(() => expect(screen.getByText(bySpanText(/1 email ready to import/))).toBeInTheDocument());
    await user.selectOptions(screen.getByLabelText(/Department/), "ECE");
    await user.click(screen.getByRole("button", { name: /Import 1 Super Admins/ }));

    await waitFor(() => expect(postSpy).toHaveBeenCalledWith("/auth/super-admins/import/", {
      emails: ["sa@test.com"],
      department: "ECE",
    }));
  });
});
