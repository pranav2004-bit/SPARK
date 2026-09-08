/**
 * @jest-environment jsdom
 *
 * Regression tests for the 2026-08-18 Dashboard/Analytics KPI-overlap
 * audit: Average Score removed from Dashboard (Analytics' job — a live
 * partial average of whoever's finished first isn't a meaningful
 * operational signal), a new Time Remaining tile added (genuinely
 * Dashboard-exclusive — meaningless once the exam is closed), and
 * data-driven coloring on the metrics that actually have a "good or bad"
 * direction (Time Remaining, On-Time Rate).
 */

jest.mock("next/navigation", () => ({
  useParams: () => ({ assignment_id: "11111111-1111-1111-1111-111111111111" }),
  useRouter: () => ({ push: jest.fn(), back: jest.fn() }),
}));

jest.mock("@/components/layout/AdminLayout", () => ({
  AdminLayout: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}));

const mockToastError = jest.fn();
jest.mock("@/components/ui/Toast", () => ({
  useToast: () => ({ error: mockToastError, success: jest.fn() }),
}));

import React from "react";
import { render, screen, waitFor } from "@testing-library/react";
import api from "@/lib/api";
import AdminAssessmentDashboardPage from "@/app/admin/assessments/dashboard/[assignment_id]/page";

function baseData(overrides: Record<string, unknown> = {}) {
  return {
    assignment_id: "11111111-1111-1111-1111-111111111111",
    status: "LIVE",
    student_count_total: 25,
    student_count_completed: 20,
    student_count_in_progress: 3,
    completion_rate_percentage: 80,
    time_remaining_seconds: 1800, // 30 min
    exam_duration_minutes: 60,
    malpractice_incidents: 2,
    submission_breakdown: { on_time: 17, auto_submitted: 3, on_time_percentage: 85 },
    metric_definitions: {
      completion_rate_percentage: "def1", malpractice_incidents: "def2",
      submission_breakdown: "def3", time_remaining_seconds: "def4",
    },
    ...overrides,
  };
}

function mockDashboard(data: unknown) {
  jest.spyOn(api, "get").mockImplementation((url: string) => {
    if (url.includes("/dashboard/export/")) return Promise.resolve({ data: new Blob() } as any);
    return Promise.resolve({ data: { data } } as any);
  });
}

beforeEach(() => {
  mockToastError.mockClear();
});

afterEach(() => {
  jest.restoreAllMocks();
  jest.useRealTimers();
});

describe("Dashboard — no duplicated KPIs with the Analytics page", () => {
  it("never renders an Average Score tile — that's Analytics' job now", async () => {
    mockDashboard(baseData());
    render(<AdminAssessmentDashboardPage />);
    await waitFor(() => expect(screen.getByText("Progress")).toBeInTheDocument());
    expect(screen.queryByText("Average Score")).not.toBeInTheDocument();
  });

  it("shows Time Remaining — a metric Analytics doesn't have at all", async () => {
    mockDashboard(baseData({ time_remaining_seconds: 1800 }));
    render(<AdminAssessmentDashboardPage />);
    await waitFor(() => expect(screen.getByText("Time Remaining")).toBeInTheDocument());
    expect(screen.getByText("30m left")).toBeInTheDocument();
  });
});

describe("Dashboard — Progress tile", () => {
  it("shows completed/total as one combined ratio with in-progress as a hint", async () => {
    mockDashboard(baseData({ student_count_completed: 20, student_count_total: 25, student_count_in_progress: 3 }));
    render(<AdminAssessmentDashboardPage />);
    await waitFor(() => expect(screen.getByText("20 / 25")).toBeInTheDocument());
    expect(screen.getByText("3 in progress")).toBeInTheDocument();
  });
});

describe("Dashboard — Time Remaining formatting and color", () => {
  it("formats hours and minutes when more than an hour remains", async () => {
    mockDashboard(baseData({ time_remaining_seconds: 5400, exam_duration_minutes: 180 })); // 1h 30m of 3h
    render(<AdminAssessmentDashboardPage />);
    await waitFor(() => expect(screen.getByText("1h 30m left")).toBeInTheDocument());
  });

  it("shows 'Ending now' at zero seconds remaining, not '0m left'", async () => {
    mockDashboard(baseData({ time_remaining_seconds: 0 }));
    render(<AdminAssessmentDashboardPage />);
    await waitFor(() => expect(screen.getByText("Ending now")).toBeInTheDocument());
  });

  it("shows a dash and the assignment's status when not LIVE (time remaining is inapplicable)", async () => {
    mockDashboard(baseData({ status: "CLOSED", time_remaining_seconds: null }));
    render(<AdminAssessmentDashboardPage />);
    await waitFor(() => expect(screen.getByText("Time Remaining")).toBeInTheDocument());
    expect(screen.getByText("—")).toBeInTheDocument();
    expect(screen.getByText("Exam closed")).toBeInTheDocument();
  });

  it("renders red when under 10% of the exam's own duration remains", async () => {
    mockDashboard(baseData({ time_remaining_seconds: 300, exam_duration_minutes: 60 })); // 5 of 60 min = 8.3%
    render(<AdminAssessmentDashboardPage />);
    await waitFor(() => expect(screen.getByText("Time Remaining")).toBeInTheDocument());
    const icon = screen.getByText("Time Remaining").closest("div")?.querySelector("svg");
    expect(icon).toHaveStyle({ color: "#DC2626" });
  });

  it("renders green when plenty of time remains relative to the exam's duration", async () => {
    mockDashboard(baseData({ time_remaining_seconds: 3000, exam_duration_minutes: 60 })); // 50 of 60 min
    render(<AdminAssessmentDashboardPage />);
    await waitFor(() => expect(screen.getByText("Time Remaining")).toBeInTheDocument());
    const icon = screen.getByText("Time Remaining").closest("div")?.querySelector("svg");
    expect(icon).toHaveStyle({ color: "#16A34A" });
  });

  it("never renders 'NaNm left' — an absent/undefined field (not just an explicit null) also falls back to a dash", async () => {
    // Reproduces a real live report (2026-08-18): the field being missing
    // from the payload entirely (undefined), not just explicitly null,
    // must not slip past a strict `=== null` check into the arithmetic.
    const { time_remaining_seconds: _omit, ...rest } = baseData({ status: "CLOSED" });
    mockDashboard(rest);
    render(<AdminAssessmentDashboardPage />);
    await waitFor(() => expect(screen.getByText("Time Remaining")).toBeInTheDocument());
    expect(screen.queryByText(/NaN/)).not.toBeInTheDocument();
    expect(screen.getByText("—")).toBeInTheDocument();
  });
});

describe("Dashboard — On-Time Rate is data-driven, not a fixed color", () => {
  it("renders red for a low on-time rate", async () => {
    mockDashboard(baseData({ submission_breakdown: { on_time: 5, auto_submitted: 15, on_time_percentage: 25 } }));
    render(<AdminAssessmentDashboardPage />);
    await waitFor(() => expect(screen.getByText("25%")).toBeInTheDocument());
    const icon = screen.getByText("25%").closest("div")?.querySelector("svg");
    expect(icon).toHaveStyle({ color: "#DC2626" });
  });

  it("renders green for a high on-time rate", async () => {
    mockDashboard(baseData({ submission_breakdown: { on_time: 19, auto_submitted: 1, on_time_percentage: 95 } }));
    render(<AdminAssessmentDashboardPage />);
    await waitFor(() => expect(screen.getByText("95%")).toBeInTheDocument());
    const icon = screen.getByText("95%").closest("div")?.querySelector("svg");
    expect(icon).toHaveStyle({ color: "#16A34A" });
  });
});

describe("Dashboard — load failure vs genuine emptiness", () => {
  it("shows a distinct error state on failure", async () => {
    jest.spyOn(api, "get").mockRejectedValue(new Error("network error"));
    render(<AdminAssessmentDashboardPage />);
    await waitFor(() => expect(screen.getByText("Couldn't load this dashboard")).toBeInTheDocument());
  });
});
