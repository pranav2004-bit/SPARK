/**
 * @jest-environment jsdom
 *
 * Coverage for the "Students attending this assessment" field added to the
 * admin Assign page (frontend/src/app/admin/assessments/assign/page.tsx),
 * and for the Batch dropdown option label dropping its old inline
 * "(N students)" suffix in favor of this field. The count deliberately
 * requires BOTH a batch AND at least one department picked before showing
 * a number — leaving departments empty still means "every department" for
 * the actual assignment, but this preview only populates once both choices
 * are explicit — so that gating is the main thing this file proves, backed
 * by GET /users/batches/<id>/students/?departments=<comma-separated>.
 */

const mockPush = jest.fn();
const mockSearchParams = new URLSearchParams();
jest.mock("next/navigation", () => ({
  useRouter: () => ({ push: mockPush }),
  useSearchParams: () => mockSearchParams,
}));

jest.mock("@/components/layout/AdminLayout", () => ({
  AdminLayout: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}));

jest.mock("@/components/ui/Toast", () => ({
  useToast: () => ({ success: jest.fn(), error: jest.fn() }),
}));

const DEPARTMENTS = [
  { id: "d1", code: "CSD", name: "Computer Science and Data Science", is_active: true, created_at: "", updated_at: "" },
  { id: "d2", code: "ECE", name: "Electronics and Communication Engineering", is_active: true, created_at: "", updated_at: "" },
];
jest.mock("@/lib/departmentsContext", () => ({
  useDepartments: () => ({
    departments: DEPARTMENTS, activeDepartments: DEPARTMENTS, loading: false, error: "", refetch: jest.fn(),
  }),
}));

jest.mock("@/hooks/useAuth", () => ({
  useAuth: () => ({ user: { id: "admin-1", role: "admin" }, isSuperAdmin: false }),
}));

import React from "react";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import api from "@/lib/api";
import AdminAssessmentAssignPage from "@/app/admin/assessments/assign/page";

const PAPER = {
  id: "paper-1", title: "MOCK TEST 2", description: "", instructions: "",
  set_count: 1, created_by: "admin-1", created_by_name: "", created_by_email: "",
  created_at: "2026-01-01T00:00:00Z", updated_at: "2026-01-01T00:00:00Z",
};
const BATCH = { id: "batch-1", batch_name: "2023-27", student_count: 13, created_at: "", updated_at: "" };

function mockApiGet(studentsCountByUrl?: (url: string) => number | "error") {
  return jest.spyOn(api, "get").mockImplementation((url: string) => {
    if (url === "/assessments/admin/papers/") {
      return Promise.resolve({ data: { count: 1, results: [PAPER] } }) as any;
    }
    if (url === "/users/batches/") {
      return Promise.resolve({ data: { data: [BATCH] } }) as any;
    }
    if (url.startsWith("/assessments/admin/papers/paper-1/")) {
      return Promise.resolve({ data: { data: { paper: PAPER, sets: [] } } }) as any;
    }
    if (url.startsWith("/assessments/admin/assignments/")) {
      return Promise.resolve({ data: { count: 0, results: [] } }) as any;
    }
    if (url.startsWith("/users/batches/batch-1/students/")) {
      const result = studentsCountByUrl ? studentsCountByUrl(url) : 9;
      if (result === "error") return Promise.reject(new Error("boom"));
      return Promise.resolve({ data: { count: result, total_pages: 1, current_page: 1, next: null, previous: null, results: [] } }) as any;
    }
    return Promise.reject(new Error(`unexpected GET ${url}`));
  });
}

async function openFormAndSelect(user: ReturnType<typeof userEvent.setup>, { paper = true, batch = true } = {}) {
  await user.click(screen.getByText("Create Assessment"));
  if (paper) await user.selectOptions(await screen.findByLabelText("Question paper"), "paper-1");
  if (batch) await user.selectOptions(screen.getByLabelText("Batch"), "batch-1");
}

afterEach(() => {
  jest.restoreAllMocks();
});

describe("Admin Assign page — Batch dropdown and eligible-student count", () => {
  it("Batch dropdown option no longer shows an inline student count", async () => {
    mockApiGet();
    const user = userEvent.setup();
    render(<AdminAssessmentAssignPage />);
    await user.click(screen.getByText("Create Assessment"));

    const batchSelect = await screen.findByLabelText("Batch");
    const option = Array.from(batchSelect.querySelectorAll("option")).find(o => o.textContent?.includes("2023-27"));
    expect(option?.textContent).toBe("2023-27");
    expect(option?.textContent).not.toMatch(/student/i);
  });

  it("stays empty until both a batch and a department are selected", async () => {
    mockApiGet();
    const user = userEvent.setup();
    render(<AdminAssessmentAssignPage />);

    await user.click(screen.getByText("Create Assessment"));
    expect(screen.getByText(/Select a batch and department\(s\)/)).toBeInTheDocument();

    // Batch only — still empty, no department picked yet.
    await user.selectOptions(screen.getByLabelText("Batch"), "batch-1");
    expect(screen.getByText(/Select a batch and department\(s\)/)).toBeInTheDocument();
    expect(api.get).not.toHaveBeenCalledWith(expect.stringContaining("/students/"));
  });

  it("shows the count only once both batch and department are picked", async () => {
    mockApiGet(() => 7);
    const user = userEvent.setup();
    render(<AdminAssessmentAssignPage />);

    await openFormAndSelect(user, { paper: false });
    await user.click(screen.getByRole("button", { name: /Computer Science and Data Science/ }));

    await waitFor(() => expect(api.get).toHaveBeenCalledWith(
      expect.stringMatching(/^\/users\/batches\/batch-1\/students\/\?departments=CSD&page_size=1$/)
    ));
    expect(await screen.findByText("7 students")) .toBeInTheDocument();
  });

  it("sends every selected department, comma-separated, and reverts to empty when deselected", async () => {
    mockApiGet(() => 12);
    const user = userEvent.setup();
    render(<AdminAssessmentAssignPage />);

    await openFormAndSelect(user, { paper: false });
    await user.click(screen.getByRole("button", { name: /Computer Science and Data Science/ }));
    await user.click(screen.getByRole("button", { name: /Electronics and Communication Engineering/ }));

    await waitFor(() => expect(api.get).toHaveBeenCalledWith(
      expect.stringContaining("departments=CSD%2CECE")
    ));
    expect(await screen.findByText("12 students")).toBeInTheDocument();

    // Deselect both — back to the empty prompt, not a stale number.
    await user.click(screen.getByRole("button", { name: /Computer Science and Data Science/ }));
    await user.click(screen.getByRole("button", { name: /Electronics and Communication Engineering/ }));
    expect(await screen.findByText(/Select a batch and department\(s\)/)).toBeInTheDocument();
  });

  it("shows a retry link if the count fails to load", async () => {
    mockApiGet(() => "error");
    const user = userEvent.setup();
    render(<AdminAssessmentAssignPage />);

    await openFormAndSelect(user, { paper: false });
    await user.click(screen.getByRole("button", { name: /Computer Science and Data Science/ }));

    expect(await screen.findByText(/Couldn't calculate/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "retry" })).toBeInTheDocument();
  });

  it("uses singular wording for exactly 1 student", async () => {
    mockApiGet(() => 1);
    const user = userEvent.setup();
    render(<AdminAssessmentAssignPage />);

    await openFormAndSelect(user, { paper: false });
    await user.click(screen.getByRole("button", { name: /Computer Science and Data Science/ }));

    expect(await screen.findByText("1 student")).toBeInTheDocument();
  });
});
