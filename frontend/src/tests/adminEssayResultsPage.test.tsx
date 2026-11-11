/**
 * @jest-environment jsdom
 *
 * Essay Writing — admin per-assignment Results table (Phase 8, Task 8.2):
 * columns, filters, export button, and row click-through to the
 * submission detail page.
 */

const mockPush = jest.fn();
const mockParams = { assignment_id: "assign-1" };
jest.mock("next/navigation", () => ({
  useRouter: () => ({ push: mockPush }),
  useParams: () => mockParams,
}));

jest.mock("@/components/layout/AdminLayout", () => ({
  AdminLayout: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}));

const mockToastError = jest.fn();
const mockToastSuccess = jest.fn();
jest.mock("@/components/ui/Toast", () => ({
  useToast: () => ({ error: mockToastError, success: mockToastSuccess }),
}));

import React from "react";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import api from "@/lib/api";
import AdminEssayResultsPage from "@/app/admin/essay-writing/results/[assignment_id]/page";
import type { EssayAssignment, EssayResultRow } from "@/types";

const ASSIGNMENT: EssayAssignment = {
  id: "assign-1", paper: "paper-1", paper_title: "Persuasive Writing", batch_id: "batch-1",
  institution_id: "inst-1", global_start_time: null, global_expire_time: "2026-09-25T10:00:00Z",
  departments: [], status: "LIVE", created_by: "admin-1",
  created_at: "2026-09-20T00:00:00Z", updated_at: "2026-09-20T00:00:00Z",
};

const SCORED_ROW: EssayResultRow = {
  student_user_id: "student-1", student_roll_id: "R001", student_name: "Alice Student",
  department: "CSE", set_label: "Set A", question_text: "Argue for or against remote work.",
  attempt_id: "attempt-1", submission_id: "sub-1", exam_status: "completed",
  submitted_at: "2026-09-20T10:00:00Z", score: 8,
  feedback: { overall: "Well argued." }, evaluated_by: "llm",
  malpractice_flag: false, malpractice_reasons: [], plagiarism_flag: false,
};

const PENDING_ROW: EssayResultRow = {
  student_user_id: "student-2", student_roll_id: "R002", student_name: "Bob Student",
  department: "ECE", set_label: "Set A", question_text: "Argue for or against remote work.",
  attempt_id: null, submission_id: null, exam_status: "pending",
  submitted_at: null, score: null, feedback: null, evaluated_by: null,
  malpractice_flag: false, malpractice_reasons: [], plagiarism_flag: false,
};

function mockList(rows: EssayResultRow[] = [SCORED_ROW, PENDING_ROW]) {
  jest.spyOn(api, "get").mockImplementation((url: string) => {
    if (url.includes("/results/")) {
      return Promise.resolve({ data: { results: rows, count: rows.length, total_pages: 1 } } as any);
    }
    if (url.includes("/essay/admin/assignments/assign-1/")) {
      return Promise.resolve({ data: { data: ASSIGNMENT } } as any);
    }
    return Promise.reject(new Error(`unexpected GET ${url}`));
  });
}

beforeEach(() => {
  mockPush.mockClear();
  mockToastError.mockClear();
});

afterEach(() => {
  jest.restoreAllMocks();
});

describe("Results table page", () => {
  it("renders both a scored row and a not-yet-started row", async () => {
    mockList();
    render(<AdminEssayResultsPage />);
    await waitFor(() => expect(screen.getByText("Alice Student")).toBeInTheDocument());
    expect(screen.getByText("8/10")).toBeInTheDocument();
    expect(screen.getByText("Bob Student")).toBeInTheDocument();
    expect(screen.getByText("Not started")).toBeInTheDocument();
  });

  it("navigates to the submission detail page when a scored row is clicked", async () => {
    mockList();
    const user = userEvent.setup();
    render(<AdminEssayResultsPage />);
    await waitFor(() => expect(screen.getByText("Alice Student")).toBeInTheDocument());
    await user.click(screen.getByText("Alice Student"));
    expect(mockPush).toHaveBeenCalledWith("/admin/essay-writing/submissions/sub-1");
  });

  it("does not navigate when a not-yet-submitted row (no submission_id) is clicked", async () => {
    mockList();
    const user = userEvent.setup();
    render(<AdminEssayResultsPage />);
    await waitFor(() => expect(screen.getByText("Bob Student")).toBeInTheDocument());
    await user.click(screen.getByText("Bob Student"));
    expect(mockPush).not.toHaveBeenCalled();
  });

  it("downloads a CSV when Export CSV is clicked", async () => {
    mockList();
    const blobSpy = jest.spyOn(api, "get");
    const user = userEvent.setup();

    // Real browser blob/anchor APIs don't exist in jsdom — stub them the
    // same way this platform's existing exports (assessment-service's own
    // results/[assignment_id]/page.tsx) are already covered elsewhere.
    const createObjectURL = jest.fn().mockReturnValue("blob:mock-url");
    const revokeObjectURL = jest.fn();
    (global.URL as any).createObjectURL = createObjectURL;
    (global.URL as any).revokeObjectURL = revokeObjectURL;

    render(<AdminEssayResultsPage />);
    await waitFor(() => expect(screen.getByText("Alice Student")).toBeInTheDocument());

    blobSpy.mockResolvedValueOnce({ data: new Blob(["csv,data"]) } as any);
    await user.click(screen.getByRole("button", { name: /Export CSV/ }));

    await waitFor(() => expect(createObjectURL).toHaveBeenCalled());
    expect(blobSpy).toHaveBeenCalledWith(
      expect.stringContaining("/essay/admin/assignments/assign-1/results/export/"),
      expect.objectContaining({ responseType: "blob" }),
    );
  });

  it("filters the table by department", async () => {
    mockList();
    const user = userEvent.setup();
    render(<AdminEssayResultsPage />);
    await waitFor(() => expect(screen.getByText("Alice Student")).toBeInTheDocument());

    mockList([SCORED_ROW]);
    await user.type(screen.getByPlaceholderText("Department..."), "CSE");
    await waitFor(() => expect(api.get).toHaveBeenCalledWith(expect.stringContaining("department=CSE")));
  });

  it("shows an error state when the table fails to load", async () => {
    jest.spyOn(api, "get").mockRejectedValue(new Error("network error"));
    render(<AdminEssayResultsPage />);
    await waitFor(() => expect(screen.getByText("Couldn't load results")).toBeInTheDocument());
  });
});
