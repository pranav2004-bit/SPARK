/**
 * @jest-environment jsdom
 *
 * Essay Writing — admin Submissions Module list page (Phase 6, Task 6.1).
 * Covers overview tile counts, the pipeline-health tile, status-bucket
 * filtering (click-through from a tile), and load/error/empty states.
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

const mockToastError = jest.fn();
const mockToastSuccess = jest.fn();
jest.mock("@/components/ui/Toast", () => ({
  useToast: () => ({ error: mockToastError, success: mockToastSuccess }),
}));

import React from "react";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import api from "@/lib/api";
import AdminEssaySubmissionsPage from "@/app/admin/essay-writing/submissions/page";

const OVERVIEW_RESPONSE = {
  data: { data: { pending: 2, processing: 1, completed: 5, failed: 1, total: 9 } },
};

const HEALTH_RESPONSE = {
  data: {
    data: {
      redis_ok: true, queue_depth: 3, celery_workers_online: 2,
      unresolved_dlq_count: 1, oldest_unresolved_dlq_age_seconds: 930,
      undispatched_submission_count: 0, oldest_undispatched_submission_age_seconds: null,
    },
  },
};

const LIST_ROW = {
  id: "sub-1", status: "LLM_COMPLETE", student_id: "student-uuid-1", attempt_id: "attempt-1",
  assignment_id: "assignment-1", batch_id: "batch-uuid-1", paper_title: "Persuasive Writing",
  malpractice_flag: false, score: 8, created_at: "2026-09-20T10:00:00Z", updated_at: "2026-09-20T10:05:00Z",
};

const LIST_EMPTY = { data: { count: 0, total_pages: 1, current_page: 1, next: null, previous: null, results: [] } };
const LIST_ONE = { data: { count: 1, total_pages: 1, current_page: 1, next: null, previous: null, results: [LIST_ROW] } };

function mockAll({ list = LIST_EMPTY, overview = OVERVIEW_RESPONSE, health = HEALTH_RESPONSE }: any = {}) {
  jest.spyOn(api, "get").mockImplementation((url: string) => {
    if (url.includes("/essay/admin/submissions/overview/")) return Promise.resolve(overview as any);
    if (url.includes("/essay/admin/submissions/pipeline-health/")) return Promise.resolve(health as any);
    if (url.startsWith("/essay/admin/submissions/")) return Promise.resolve(list as any);
    return Promise.reject(new Error(`unexpected GET ${url}`));
  });
}

beforeEach(() => {
  mockPush.mockClear();
  mockToastError.mockClear();
  mockToastSuccess.mockClear();
});

afterEach(() => {
  jest.restoreAllMocks();
});

describe("Submissions list page — overview and health tiles", () => {
  it("renders the 4 bucket counts from the overview endpoint", async () => {
    mockAll();
    render(<AdminEssaySubmissionsPage />);
    await waitFor(() => expect(screen.getByText("2")).toBeInTheDocument()); // pending
    expect(screen.getByText("5")).toBeInTheDocument(); // completed
    expect(screen.getByText("Pending")).toBeInTheDocument();
    expect(screen.getByText("Completed")).toBeInTheDocument();
  });

  it("renders the pipeline health tile from a real (mocked) health response", async () => {
    mockAll();
    render(<AdminEssaySubmissionsPage />);
    await waitFor(() => expect(screen.getByText(/Redis reachable/)).toBeInTheDocument());
    expect(screen.getByText(/2 workers online/)).toBeInTheDocument();
    expect(screen.getByText(/1 unresolved failure/)).toBeInTheDocument();
    expect(screen.getByText(/0 undispatched/)).toBeInTheDocument();
  });

  it("shows Redis unreachable when the health endpoint reports it", async () => {
    mockAll({
      health: {
        data: {
          data: {
            redis_ok: false, queue_depth: null, celery_workers_online: 0,
            unresolved_dlq_count: 0, oldest_unresolved_dlq_age_seconds: null,
            undispatched_submission_count: 0, oldest_undispatched_submission_age_seconds: null,
          },
        },
      },
    });
    render(<AdminEssaySubmissionsPage />);
    await waitFor(() => expect(screen.getByText(/Redis unreachable/)).toBeInTheDocument());
  });

  it("surfaces undispatched submissions found post-Task 18.2 — a different failure mode from the DLQ", async () => {
    // Real gap this session found and fixed: a submission whose dispatch
    // never reached the broker at all never gets an EssayFailedJob row
    // either, so the DLQ count alone would show 0 while essays are
    // genuinely stuck. This is the one place an admin can now see that.
    mockAll({
      health: {
        data: {
          data: {
            redis_ok: true, queue_depth: 0, celery_workers_online: 2,
            unresolved_dlq_count: 0, oldest_unresolved_dlq_age_seconds: null,
            undispatched_submission_count: 3, oldest_undispatched_submission_age_seconds: 610,
          },
        },
      },
    });
    render(<AdminEssaySubmissionsPage />);
    await waitFor(() => expect(screen.getByText(/3 undispatched/)).toBeInTheDocument());
    expect(screen.getByText(/oldest/)).toBeInTheDocument();
  });
});

describe("Submissions list page — table states", () => {
  it("shows the empty state when there are no submissions", async () => {
    mockAll();
    render(<AdminEssaySubmissionsPage />);
    await waitFor(() => expect(screen.getByText(/No submissions found/)).toBeInTheDocument());
  });

  it("shows an error state when the list fails to load", async () => {
    jest.spyOn(api, "get").mockImplementation((url: string) => {
      if (url.includes("/essay/admin/submissions/overview/")) return Promise.resolve(OVERVIEW_RESPONSE as any);
      if (url.includes("/essay/admin/submissions/pipeline-health/")) return Promise.resolve(HEALTH_RESPONSE as any);
      return Promise.reject(new Error("network error"));
    });
    render(<AdminEssaySubmissionsPage />);
    await waitFor(() => expect(screen.getByText(/Couldn't load submissions/)).toBeInTheDocument());
  });

  it("renders a submission row with its paper title, status, and score", async () => {
    mockAll({ list: LIST_ONE });
    render(<AdminEssaySubmissionsPage />);
    await waitFor(() => expect(screen.getByText("Persuasive Writing")).toBeInTheDocument());
    expect(screen.getByText("Complete")).toBeInTheDocument();
    expect(screen.getByText("8/10")).toBeInTheDocument();
  });

  it("navigates to the detail page when a row is clicked", async () => {
    mockAll({ list: LIST_ONE });
    const user = userEvent.setup();
    render(<AdminEssaySubmissionsPage />);
    await waitFor(() => expect(screen.getByText("Persuasive Writing")).toBeInTheDocument());
    await user.click(screen.getByText("Persuasive Writing"));
    expect(mockPush).toHaveBeenCalledWith("/admin/essay-writing/submissions/sub-1");
  });

  it("clicking a status tile filters the list by that bucket", async () => {
    mockAll({ list: LIST_ONE });
    const user = userEvent.setup();
    render(<AdminEssaySubmissionsPage />);
    await waitFor(() => expect(screen.getByText("Persuasive Writing")).toBeInTheDocument());

    (api.get as jest.Mock).mockClear();
    await user.click(screen.getByText("Completed"));

    await waitFor(() => {
      const calls = (api.get as jest.Mock).mock.calls.map((c: any[]) => c[0]);
      expect(calls.some((url: string) => url.includes("status=completed"))).toBe(true);
    });
  });
});
