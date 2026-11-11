/**
 * @jest-environment jsdom
 *
 * Essay Writing — admin per-assignment live Dashboard page (Phase 10,
 * Task 10.2): KPI tiles, the LIVE badge + 8s polling (only while the
 * assignment is actually LIVE), and the submission-throughput sparkline.
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
jest.mock("@/components/ui/Toast", () => ({
  useToast: () => ({ error: mockToastError, success: jest.fn() }),
}));

import React from "react";
import { render, screen, waitFor, act } from "@testing-library/react";
import api from "@/lib/api";
import AdminEssayDashboardPage from "@/app/admin/essay-writing/dashboard/[assignment_id]/page";
import type { EssayAssignment, EssayAssignmentDashboard } from "@/types";

const LIVE_ASSIGNMENT: EssayAssignment = {
  id: "assign-1", paper: "paper-1", paper_title: "Persuasive Writing", batch_id: "batch-1",
  institution_id: "inst-1", global_start_time: null, global_expire_time: "2026-09-25T10:00:00Z",
  departments: [], status: "LIVE", created_by: "admin-1",
  created_at: "2026-09-20T00:00:00Z", updated_at: "2026-09-20T00:00:00Z",
};

const BASE_DASHBOARD: EssayAssignmentDashboard = {
  assignment_id: "assign-1", assignment_status: "LIVE", generated_at: "2026-09-21T10:00:00Z",
  time_remaining_seconds: 600,
  // in_progress_count deliberately NOT 0/1 and not matching the
  // throughput bucket's own count value below — StatTile values and the
  // sparkline's own per-bar count labels are sibling text nodes on the
  // same page, so two unrelated figures happening to read the same
  // (e.g. both "2") makes getByText genuinely ambiguous, not a real
  // rendering bug (the same class of fixture collision already found
  // and fixed once for the Results/Analytics pages' own tests).
  total_allocated: 10, in_progress_count: 4, total_submitted: 5,
  completion_rate_percentage: 50.0, total_scored: 3, average_score: 7.33,
  pending_evaluation_count: 1, dlq_backlog_count: 1,
  submission_throughput: Array.from({ length: 6 }, (_, i) => ({ bucket_start: "2026-09-21T09:30:00Z", count: i === 5 ? 9 : 0 })),
};

function mockLoad(dashboardOverrides: Partial<EssayAssignmentDashboard> = {}, assignment: EssayAssignment = LIVE_ASSIGNMENT) {
  jest.spyOn(api, "get").mockImplementation((url: string) => {
    if (url.includes("/dashboard/")) {
      return Promise.resolve({ data: { data: { ...BASE_DASHBOARD, ...dashboardOverrides } } } as any);
    }
    if (url.includes("/essay/admin/assignments/assign-1/")) {
      return Promise.resolve({ data: { data: assignment } } as any);
    }
    return Promise.reject(new Error(`unexpected GET ${url}`));
  });
}

beforeEach(() => {
  mockToastError.mockClear();
});

afterEach(() => {
  jest.restoreAllMocks();
});

describe("Dashboard page", () => {
  it("renders the KPI tiles", async () => {
    mockLoad();
    render(<AdminEssayDashboardPage />);
    await waitFor(() => expect(screen.getByText("Persuasive Writing")).toBeInTheDocument());
    expect(screen.getByText("50%")).toBeInTheDocument();
    expect(screen.getByText("5/10 submitted")).toBeInTheDocument();
    expect(screen.getByText("4")).toBeInTheDocument(); // in progress
    expect(screen.getByText("7.33/10")).toBeInTheDocument();
  });

  it("shows the LIVE badge with time remaining only while status is LIVE", async () => {
    mockLoad();
    render(<AdminEssayDashboardPage />);
    await waitFor(() => expect(screen.getByText(/Live — refreshing every/)).toBeInTheDocument());
    expect(screen.getByText("10m left")).toBeInTheDocument();
  });

  it("hides the LIVE badge when the assignment is CLOSED", async () => {
    mockLoad({ assignment_status: "CLOSED", time_remaining_seconds: null }, { ...LIVE_ASSIGNMENT, status: "CLOSED" });
    render(<AdminEssayDashboardPage />);
    await waitFor(() => expect(screen.getByText("Persuasive Writing")).toBeInTheDocument());
    expect(screen.queryByText(/Live — refreshing every/)).not.toBeInTheDocument();
  });

  it("polls every 8 seconds while LIVE, and stops once the assignment closes", async () => {
    jest.useFakeTimers({ advanceTimers: true });
    mockLoad();
    render(<AdminEssayDashboardPage />);
    await waitFor(() => expect(screen.getByText("Persuasive Writing")).toBeInTheDocument());

    const callsAfterInitialLoad = (api.get as jest.Mock).mock.calls.length;

    await act(async () => { jest.advanceTimersByTime(8000); });
    await waitFor(() => expect((api.get as jest.Mock).mock.calls.length).toBeGreaterThan(callsAfterInitialLoad));

    // Now the assignment closes — the next poll response says CLOSED.
    mockLoad({ assignment_status: "CLOSED", time_remaining_seconds: null }, { ...LIVE_ASSIGNMENT, status: "CLOSED" });
    await act(async () => { jest.advanceTimersByTime(8000); });
    await waitFor(() => expect(screen.queryByText(/Live — refreshing every/)).not.toBeInTheDocument());

    const callsAfterClose = (api.get as jest.Mock).mock.calls.length;
    await act(async () => { jest.advanceTimersByTime(16000); });
    expect((api.get as jest.Mock).mock.calls.length).toBe(callsAfterClose); // no further polling

    jest.useRealTimers();
  });

  it("renders the submission throughput sparkline", async () => {
    mockLoad();
    render(<AdminEssayDashboardPage />);
    await waitFor(() => expect(screen.getByText("Submission throughput (last 30 minutes)")).toBeInTheDocument());
  });

  it("shows an error state when the dashboard fails to load", async () => {
    jest.spyOn(api, "get").mockImplementation((url: string) => {
      if (url.includes("/dashboard/")) return Promise.reject(new Error("network error"));
      return Promise.resolve({ data: { data: LIVE_ASSIGNMENT } } as any);
    });
    render(<AdminEssayDashboardPage />);
    await waitFor(() => expect(screen.getByText("Couldn't load dashboard")).toBeInTheDocument());
  });
});
