/**
 * @jest-environment jsdom
 *
 * Coverage for the "Logs/Tracking" eye-icon column added to the admin
 * results table (2026-08-17): a plain-English, non-technical timeline of a
 * student's exam activity (start -> tab-switches/etc. -> submit), replacing
 * the old raw event_type "Logs" button. Backed by
 * GET /assessments/admin/sessions/<session_id>/timeline/.
 */

const mockPush = jest.fn();
let mockSearchParams = new URLSearchParams();
jest.mock("next/navigation", () => ({
  useParams: () => ({ assignment_id: "11111111-1111-1111-1111-111111111111" }),
  useRouter: () => ({ push: mockPush }),
  useSearchParams: () => mockSearchParams,
}));

jest.mock("@/components/layout/AdminLayout", () => ({
  AdminLayout: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}));

const mockToastError = jest.fn();
jest.mock("@/components/ui/Toast", () => ({
  useToast: () => ({ error: mockToastError, success: jest.fn() }),
}));

jest.mock("@/lib/departmentsContext", () => ({
  useDepartments: () => ({ departments: [], activeDepartments: [], loading: false, error: "", refetch: jest.fn() }),
}));

import React from "react";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import api from "@/lib/api";
import AdminAssessmentResultsPage from "@/app/admin/assessments/results/[assignment_id]/page";

const ASSIGNMENT_RESPONSE = {
  data: {
    data: {
      id: "11111111-1111-1111-1111-111111111111",
      paper_title: "Midterm Paper",
      status: "CLOSED",
      pass_cutoff_percentage: 40,
    },
  },
};

function resultsResponse(rows: any[], availableSets: string[] = ["Set A"]) {
  return { data: { count: rows.length, total_pages: 1, current_page: 1, results: rows, available_sets: availableSets } };
}

const SUBMITTED_ROW = {
  result_id: "res-1", session_id: "sess-1", student_user_id: "stu-1",
  student_roll_id: "ROLL-001", student_name: "Alice A", department: "CSE",
  set_label: "Set A", exam_status: "submitted", started_at: null, ended_at: null,
  duration_seconds: 1200, score: 5, total_marks: 5, percentage: 100,
  malpractice_flag: false,
};

const WRITING_ROW = {
  result_id: null, session_id: "sess-2", student_user_id: "stu-2",
  student_roll_id: "ROLL-002", student_name: "Bob B", department: "CSE",
  set_label: "Set A", exam_status: "writing", started_at: null, ended_at: null,
  duration_seconds: null, score: null, total_marks: null, percentage: null,
  malpractice_flag: null,
};

const PENDING_ROW = {
  result_id: null, session_id: null, student_user_id: "stu-3",
  student_roll_id: "ROLL-003", student_name: "Carol C", department: "CSE",
  set_label: "Set A", exam_status: "pending", started_at: null, ended_at: null,
  duration_seconds: null, score: null, total_marks: null, percentage: null,
  malpractice_flag: null,
};

function mockApiFor(rows: any[]) {
  jest.spyOn(api, "get").mockImplementation((url: string) => {
    if (url.includes("/results/export/")) return Promise.resolve({ data: new Blob() } as any);
    if (url.includes("/results/")) return Promise.resolve(resultsResponse(rows) as any);
    if (url.includes("/timeline/")) return Promise.reject(new Error("not stubbed for this test"));
    return Promise.resolve(ASSIGNMENT_RESPONSE as any);
  });
}

beforeEach(() => {
  mockPush.mockClear();
  mockToastError.mockClear();
  mockSearchParams = new URLSearchParams();
});

afterEach(() => {
  jest.restoreAllMocks();
});

describe("Admin results — Logs/Tracking eye icon", () => {
  it("shows an eye icon for a submitted student and a writing student, but not a pending one", async () => {
    mockApiFor([SUBMITTED_ROW, WRITING_ROW, PENDING_ROW]);

    render(<AdminAssessmentResultsPage />);

    await waitFor(() => expect(screen.getByText("Alice A")).toBeInTheDocument());

    expect(screen.getByLabelText("View Alice A's exam activity timeline")).toBeInTheDocument();
    expect(screen.getByLabelText("View Bob B's exam activity timeline")).toBeInTheDocument();
    expect(screen.queryByLabelText("View Carol C's exam activity timeline")).not.toBeInTheDocument();
  });

  it("clicking the eye icon opens the plain-English timeline with the retention notice", async () => {
    const user = userEvent.setup();
    mockApiFor([SUBMITTED_ROW]);
    jest.spyOn(api, "get").mockImplementation((url: string) => {
      if (url === "/assessments/admin/sessions/sess-1/timeline/") {
        return Promise.resolve({
          data: {
            data: {
              session_id: "sess-1", exam_status: "submitted",
              malpractice_flag: true, malpractice_reasons: ["tab_switch"],
              total_event_count: 2, truncated: false, retention_days: 15,
              events: [
                { description: "Started the exam", occurred_at: "2026-08-17T10:00:00Z" },
                { description: "Switched away to another browser tab", occurred_at: "2026-08-17T10:05:00Z" },
                { description: "Submitted the exam", occurred_at: "2026-08-17T10:30:00Z" },
              ],
            },
          },
        } as any);
      }
      if (url.includes("/results/export/")) return Promise.resolve({ data: new Blob() } as any);
      if (url.includes("/results/")) return Promise.resolve(resultsResponse([SUBMITTED_ROW]) as any);
      return Promise.resolve(ASSIGNMENT_RESPONSE as any);
    });

    render(<AdminAssessmentResultsPage />);
    await waitFor(() => expect(screen.getByText("Alice A")).toBeInTheDocument());

    await user.click(screen.getByLabelText("View Alice A's exam activity timeline"));

    await waitFor(() => expect(screen.getByText("Student Activity Timeline")).toBeInTheDocument());
    expect(screen.getByText("Started the exam")).toBeInTheDocument();
    expect(screen.getByText("Switched away to another browser tab")).toBeInTheDocument();
    expect(screen.getByText("Submitted the exam")).toBeInTheDocument();
    // No raw technical event_type strings leak into the popup.
    expect(screen.queryByText(/tab_switch/)).not.toBeInTheDocument();
    // The 15-day auto-erase notice, using the server-provided retention_days.
    expect(screen.getByText(/automatically and permanently erased 15 days/)).toBeInTheDocument();
    expect(screen.getByText("Flagged for review")).toBeInTheDocument();
  });

  it("a writing (mid-exam) student's timeline has no closing event yet", async () => {
    const user = userEvent.setup();
    jest.spyOn(api, "get").mockImplementation((url: string) => {
      if (url === "/assessments/admin/sessions/sess-2/timeline/") {
        return Promise.resolve({
          data: {
            data: {
              session_id: "sess-2", exam_status: "writing",
              malpractice_flag: false, malpractice_reasons: [],
              total_event_count: 0, truncated: false, retention_days: 15,
              events: [{ description: "Started the exam", occurred_at: "2026-08-17T10:00:00Z" }],
            },
          },
        } as any);
      }
      if (url.includes("/results/export/")) return Promise.resolve({ data: new Blob() } as any);
      if (url.includes("/results/")) return Promise.resolve(resultsResponse([WRITING_ROW]) as any);
      return Promise.resolve(ASSIGNMENT_RESPONSE as any);
    });

    render(<AdminAssessmentResultsPage />);
    await waitFor(() => expect(screen.getByText("Bob B")).toBeInTheDocument());

    await user.click(screen.getByLabelText("View Bob B's exam activity timeline"));

    await waitFor(() => expect(screen.getByText("Student Activity Timeline")).toBeInTheDocument());
    expect(screen.getByText("Started the exam")).toBeInTheDocument();
    expect(screen.queryByText("Submitted the exam")).not.toBeInTheDocument();
    expect(screen.queryByText("Flagged for review")).not.toBeInTheDocument();
  });

  it("shows a truncation note when the timeline was capped server-side", async () => {
    // Rendering 2000 timeline rows in jsdom is slower than the default 5s
    // per-test budget — this is a jsdom rendering-cost artifact of the
    // fixture size, not a real slowdown in the app itself.
    const user = userEvent.setup();
    mockApiFor([SUBMITTED_ROW]);
    jest.spyOn(api, "get").mockImplementation((url: string) => {
      if (url === "/assessments/admin/sessions/sess-1/timeline/") {
        return Promise.resolve({
          data: {
            data: {
              session_id: "sess-1", exam_status: "submitted",
              malpractice_flag: false, malpractice_reasons: [],
              total_event_count: 2005, truncated: true, retention_days: 15,
              events: [
                { description: "Started the exam", occurred_at: "2026-08-17T10:00:00Z" },
                ...Array.from({ length: 2000 }, () => ({ description: "Copied text from the exam page", occurred_at: "2026-08-17T10:05:00Z" })),
                { description: "Submitted the exam", occurred_at: "2026-08-17T10:30:00Z" },
              ],
            },
          },
        } as any);
      }
      if (url.includes("/results/export/")) return Promise.resolve({ data: new Blob() } as any);
      if (url.includes("/results/")) return Promise.resolve(resultsResponse([SUBMITTED_ROW]) as any);
      return Promise.resolve(ASSIGNMENT_RESPONSE as any);
    });

    render(<AdminAssessmentResultsPage />);
    await waitFor(() => expect(screen.getByText("Alice A")).toBeInTheDocument());
    await user.click(screen.getByLabelText("View Alice A's exam activity timeline"));

    await waitFor(() => {
      expect(screen.getByText(/Showing the first 2000 of 2005 recorded events\./)).toBeInTheDocument();
    }, { timeout: 15000 });
  }, 20000);

  it("shows an error toast and does not open the modal if the timeline fetch fails", async () => {
    const user = userEvent.setup();
    mockApiFor([SUBMITTED_ROW]);

    render(<AdminAssessmentResultsPage />);
    await waitFor(() => expect(screen.getByText("Alice A")).toBeInTheDocument());

    await user.click(screen.getByLabelText("View Alice A's exam activity timeline"));

    await waitFor(() => expect(mockToastError).toHaveBeenCalled());
    expect(screen.queryByText("Student Activity Timeline")).not.toBeInTheDocument();
  });
});

describe("Admin results — Set filter (Analytics' Set Fairness drill-down target)", () => {
  it("hides the Set filter dropdown when the assignment only has one set", async () => {
    jest.spyOn(api, "get").mockImplementation((url: string) => {
      if (url.includes("/results/export/")) return Promise.resolve({ data: new Blob() } as any);
      if (url.includes("/results/")) return Promise.resolve(resultsResponse([SUBMITTED_ROW], ["Set A"]) as any);
      return Promise.resolve(ASSIGNMENT_RESPONSE as any);
    });
    render(<AdminAssessmentResultsPage />);
    await waitFor(() => expect(screen.getByText("Alice A")).toBeInTheDocument());
    expect(screen.queryByLabelText("Set")).not.toBeInTheDocument();
  });

  it("shows the Set filter, pre-selected from a ?set= deep link, when multiple sets exist", async () => {
    mockSearchParams = new URLSearchParams("set=Set+B");
    jest.spyOn(api, "get").mockImplementation((url: string) => {
      if (url.includes("/results/export/")) return Promise.resolve({ data: new Blob() } as any);
      if (url.includes("/results/")) return Promise.resolve(resultsResponse([SUBMITTED_ROW], ["Set A", "Set B"]) as any);
      return Promise.resolve(ASSIGNMENT_RESPONSE as any);
    });
    render(<AdminAssessmentResultsPage />);
    await waitFor(() => expect(screen.getByLabelText("Set")).toBeInTheDocument());
    expect(screen.getByLabelText("Set")).toHaveValue("Set B");
  });

  it("changing the Set filter re-fetches results scoped to that set", async () => {
    const user = userEvent.setup();
    const getSpy = jest.spyOn(api, "get").mockImplementation((url: string) => {
      if (url.includes("/results/export/")) return Promise.resolve({ data: new Blob() } as any);
      if (url.includes("/results/")) return Promise.resolve(resultsResponse([SUBMITTED_ROW], ["Set A", "Set B"]) as any);
      return Promise.resolve(ASSIGNMENT_RESPONSE as any);
    });
    render(<AdminAssessmentResultsPage />);
    await waitFor(() => expect(screen.getByLabelText("Set")).toBeInTheDocument());

    await user.selectOptions(screen.getByLabelText("Set"), "Set B");

    await waitFor(() => {
      const resultsCalls = getSpy.mock.calls.map(c => c[0]).filter((u): u is string => typeof u === "string" && u.includes("/results/") && !u.includes("export"));
      expect(resultsCalls.at(-1)).toContain("set=Set+B");
    });
  });
});
