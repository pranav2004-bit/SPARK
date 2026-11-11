/**
 * @jest-environment jsdom
 *
 * Essay Writing — admin Reports detail page (Phase 11, Task 11.3):
 * generation state + delivery state in one table, regenerate (mandatory
 * reason), single resend, bulk resend (dry-run preview then confirm), and
 * bulk download (ZIP blob).
 */

const mockParams = { assignment_id: "assign-1" };
jest.mock("next/navigation", () => ({
  useRouter: () => ({ push: jest.fn() }),
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
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import api from "@/lib/api";
import AdminEssayReportsPage from "@/app/admin/essay-writing/reports/[assignment_id]/page";
import type { EssayAssignment, EssayReportRow } from "@/types";

const ASSIGNMENT: EssayAssignment = {
  id: "assign-1", paper: "paper-1", paper_title: "Persuasive Writing", batch_id: "batch-1",
  institution_id: "inst-1", global_start_time: null, global_expire_time: "2026-09-25T10:00:00Z",
  departments: [], status: "LIVE", created_by: "admin-1",
  created_at: "2026-09-20T00:00:00Z", updated_at: "2026-09-20T00:00:00Z",
};

const READY_ROW: EssayReportRow = {
  submission_id: "sub-1", student_user_id: "student-1", student_roll_id: "R001",
  student_name: "Alice Student", student_email: "alice@example.com", department: "CSE",
  status: "REPORT_READY", has_report: true, score: 8, email_sent_at: null,
  delivery_status: "pending", updated_at: "2026-09-20T10:00:00Z",
};

const NOT_READY_ROW: EssayReportRow = {
  submission_id: "sub-2", student_user_id: "student-2", student_roll_id: "R002",
  student_name: "Bob Student", student_email: "bob@example.com", department: "ECE",
  status: "LLM_COMPLETE", has_report: false, score: 6, email_sent_at: null,
  delivery_status: "pending", updated_at: "2026-09-20T10:00:00Z",
};

function mockList(rows: EssayReportRow[] = [READY_ROW]) {
  jest.spyOn(api, "get").mockImplementation((url: string) => {
    if (url.includes("/essay/admin/assignments/assign-1/reports/")) {
      return Promise.resolve({ data: { results: rows, count: rows.length, total_pages: 1 } } as any);
    }
    if (url.includes("/essay/admin/assignments/assign-1/")) {
      return Promise.resolve({ data: { data: ASSIGNMENT } } as any);
    }
    return Promise.reject(new Error(`unexpected GET ${url}`));
  });
}

beforeEach(() => {
  mockToastError.mockClear();
  mockToastSuccess.mockClear();
});

afterEach(() => {
  jest.restoreAllMocks();
});

describe("Reports detail page — list", () => {
  it("renders a report row with student, score, and delivery status", async () => {
    mockList();
    render(<AdminEssayReportsPage />);
    await waitFor(() => expect(screen.getByText("Alice Student")).toBeInTheDocument());
    expect(screen.getByText("alice@example.com")).toBeInTheDocument();
    expect(screen.getByText("8/10")).toBeInTheDocument();
    expect(screen.getByText("Not sent")).toBeInTheDocument();
  });

  it("disables Regenerate for a submission that has no ready report yet", async () => {
    mockList([NOT_READY_ROW]);
    render(<AdminEssayReportsPage />);
    await waitFor(() => expect(screen.getByText("Bob Student")).toBeInTheDocument());
    expect(screen.getByRole("button", { name: /Regenerate/ })).toBeDisabled();
    expect(screen.getByRole("button", { name: /Resend/ })).toBeDisabled();
  });

  it("enables Regenerate and Resend once a report is ready", async () => {
    mockList([READY_ROW]);
    render(<AdminEssayReportsPage />);
    await waitFor(() => expect(screen.getByText("Alice Student")).toBeInTheDocument());
    expect(screen.getByRole("button", { name: /Regenerate/ })).toBeEnabled();
    expect(screen.getByRole("button", { name: /Resend/ })).toBeEnabled();
  });
});

describe("Reports detail page — regenerate", () => {
  it("opens the regenerate modal and submits with a reason", async () => {
    mockList();
    jest.spyOn(api, "post").mockResolvedValue({ data: { success: true } } as any);
    const user = userEvent.setup({ delay: null });
    render(<AdminEssayReportsPage />);
    await waitFor(() => expect(screen.getByText("Alice Student")).toBeInTheDocument());

    await user.click(screen.getByRole("button", { name: /Regenerate/ }));
    const dialog = screen.getByRole("dialog");
    const textarea = screen.getByPlaceholderText("Why is this report being regenerated?");
    await user.type(textarea, "Score was corrected.");
    await user.click(within(dialog).getByRole("button", { name: "Regenerate" }));

    await waitFor(() => expect(api.post).toHaveBeenCalledWith(
      "/essay/admin/submissions/sub-1/regenerate-report/", { reason: "Score was corrected." },
    ));
    await waitFor(() => expect(mockToastSuccess).toHaveBeenCalled());
  });

  it("rejects submitting the regenerate modal with a blank reason", async () => {
    mockList();
    jest.spyOn(api, "post").mockResolvedValue({ data: { success: true } } as any);
    const user = userEvent.setup({ delay: null });
    render(<AdminEssayReportsPage />);
    await waitFor(() => expect(screen.getByText("Alice Student")).toBeInTheDocument());

    await user.click(screen.getByRole("button", { name: /Regenerate/ }));
    const dialog = screen.getByRole("dialog");
    await user.click(within(dialog).getByRole("button", { name: "Regenerate" }));

    expect(mockToastError).toHaveBeenCalledWith("A reason is required to regenerate a report.");
    expect(api.post).not.toHaveBeenCalled();
  });
});

describe("Reports detail page — resend", () => {
  it("dispatches a single resend and shows a success toast", async () => {
    mockList();
    jest.spyOn(api, "post").mockResolvedValue({ data: { success: true, message: "Report email dispatched to alice@example.com." } } as any);
    const user = userEvent.setup({ delay: null });
    render(<AdminEssayReportsPage />);
    await waitFor(() => expect(screen.getByText("Alice Student")).toBeInTheDocument());

    await user.click(screen.getByRole("button", { name: /Resend/ }));
    await waitFor(() => expect(api.post).toHaveBeenCalledWith("/essay/admin/submissions/sub-1/resend-report/"));
    await waitFor(() => expect(mockToastSuccess).toHaveBeenCalledWith("Report email dispatched to alice@example.com."));
  });
});

describe("Reports detail page — bulk resend", () => {
  it("shows a dry-run preview before sending anything", async () => {
    mockList();
    const postSpy = jest.spyOn(api, "post").mockResolvedValue({
      data: { success: true, data: { dry_run: true, would_dispatch_count: 1, total_matching: 1, capped: false, sample: [{ submission_id: "sub-1", student_email: "alice@example.com" }] } },
    } as any);
    const user = userEvent.setup({ delay: null });
    render(<AdminEssayReportsPage />);
    await waitFor(() => expect(screen.getByText("Alice Student")).toBeInTheDocument());

    await user.click(screen.getByRole("button", { name: /Bulk resend/ }));
    await waitFor(() => expect(postSpy).toHaveBeenCalledWith(
      expect.stringContaining("/essay/admin/assignments/assign-1/reports/bulk-resend/"),
      { dry_run: true },
    ));
    await waitFor(() => expect(screen.getByText(/will send/)).toBeInTheDocument());
    const dialog = screen.getByRole("dialog");
    expect(within(dialog).getByText("alice@example.com")).toBeInTheDocument();
  });

  it("confirming the bulk-resend preview actually dispatches with dry_run=false", async () => {
    mockList();
    const postSpy = jest.spyOn(api, "post")
      .mockResolvedValueOnce({
        data: { success: true, data: { dry_run: true, would_dispatch_count: 1, total_matching: 1, capped: false, sample: [] } },
      } as any)
      .mockResolvedValueOnce({
        data: { success: true, data: { dry_run: false, dispatched_count: 1, total_matching: 1, capped: false } },
      } as any);
    const user = userEvent.setup({ delay: null });
    render(<AdminEssayReportsPage />);
    await waitFor(() => expect(screen.getByText("Alice Student")).toBeInTheDocument());

    await user.click(screen.getByRole("button", { name: /Bulk resend/ }));
    await waitFor(() => expect(screen.getByText(/will send/)).toBeInTheDocument());

    const dialog = screen.getByRole("dialog");
    await user.click(within(dialog).getByRole("button", { name: /Send 1 email/ }));

    await waitFor(() => expect(postSpy).toHaveBeenLastCalledWith(
      expect.stringContaining("/essay/admin/assignments/assign-1/reports/bulk-resend/"),
      { dry_run: false },
    ));
    await waitFor(() => expect(mockToastSuccess).toHaveBeenCalledWith("Dispatched 1 report email(s)."));
  });
});

describe("Reports detail page — bulk download", () => {
  it("downloads a ZIP when Bulk download is clicked", async () => {
    mockList();
    const getSpy = jest.spyOn(api, "get");

    // Real browser blob/anchor APIs don't exist in jsdom — stub them the
    // same way this platform's existing exports (Results' own CSV export)
    // are already covered elsewhere.
    const createObjectURL = jest.fn().mockReturnValue("blob:mock-url");
    const revokeObjectURL = jest.fn();
    (global.URL as any).createObjectURL = createObjectURL;
    (global.URL as any).revokeObjectURL = revokeObjectURL;

    const user = userEvent.setup({ delay: null });
    render(<AdminEssayReportsPage />);
    await waitFor(() => expect(screen.getByText("Alice Student")).toBeInTheDocument());

    getSpy.mockResolvedValueOnce({ data: new Blob(["zip-bytes"]) } as any);
    await user.click(screen.getByRole("button", { name: /Bulk download/ }));

    await waitFor(() => expect(createObjectURL).toHaveBeenCalled());
    expect(getSpy).toHaveBeenCalledWith(
      expect.stringContaining("/essay/admin/assignments/assign-1/reports/bulk-download/"),
      expect.objectContaining({ responseType: "blob" }),
    );
  });
});
