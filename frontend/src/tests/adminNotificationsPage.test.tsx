/**
 * @jest-environment jsdom
 *
 * Essay Writing — admin Notifications page (Phase 13, Task 13.2): live
 * alert feed (P1/P2, tier-colored), the underlying pipeline-health
 * numbers, and a manual "send daily summary now" action.
 */

jest.mock("next/navigation", () => ({
  useRouter: () => ({ push: jest.fn() }),
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
import AdminNotificationsPage from "@/app/admin/essay-writing/notifications/page";
import type { EssayPipelineHealthSummary } from "@/types";

const HEALTHY_SUMMARY: EssayPipelineHealthSummary = {
  window_hours: 24, generated_at: "2026-09-22T10:00:00Z",
  total_submissions: 10, completed_submissions: 8, failed_submissions: 1,
  unresolved_dlq_count: 0, oldest_unresolved_dlq_age_seconds: null,
  undispatched_submission_count: 0, oldest_undispatched_submission_age_seconds: null,
  recent_failure_event_count: 0, recent_failure_events: [], alerts: [],
};

const ALERTING_SUMMARY: EssayPipelineHealthSummary = {
  ...HEALTHY_SUMMARY,
  unresolved_dlq_count: 30, oldest_unresolved_dlq_age_seconds: 200 * 60,
  alerts: [
    { tier: "P1", metric: "dlq_unresolved_count", message: "30 unresolved DLQ entries (critical threshold: 25).", value: 30, threshold: 25 },
    { tier: "P2", metric: "recent_failure_events", message: "20 failure-shaped event(s) in the last 24h (warning threshold: 15).", value: 20, threshold: 15 },
  ],
};

// Real gap found auditing this fix: generate_pipeline_alerts() (essays/
// notifications.py) only ever checked DLQ metrics — a submission stuck
// because its dispatch never reached the broker at all had no alert path,
// even though the raw count/age were exposed via the admin tile. Age-only
// (deliberately no count-based tier — see PIPELINE_ALERT_UNDISPATCHED_AGE_*
// settings' own comment for why a count-based alert would false-alarm on
// the exact expected, bounded mass-recovery scenario round 2 made safe).
const UNDISPATCHED_ALERTING_SUMMARY: EssayPipelineHealthSummary = {
  ...HEALTHY_SUMMARY,
  undispatched_submission_count: 42, oldest_undispatched_submission_age_seconds: 35 * 60,
  alerts: [
    {
      tier: "P1", metric: "undispatched_submission_oldest_age",
      message: "Oldest undispatched submission is 35 minute(s) old (critical threshold: 30) — the broker may still be unreachable.",
      value: 35 * 60, threshold: 30 * 60,
    },
  ],
};

function mockSummary(summary: EssayPipelineHealthSummary = HEALTHY_SUMMARY) {
  jest.spyOn(api, "get").mockImplementation((url: string) => {
    if (url.includes("/essay/admin/notifications/summary/")) {
      return Promise.resolve({ data: { data: summary } } as any);
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

describe("Notifications page", () => {
  it("shows a healthy state when there are no alerts", async () => {
    mockSummary();
    render(<AdminNotificationsPage />);
    await waitFor(() => expect(screen.getByText("No active alerts — pipeline looks healthy.")).toBeInTheDocument());
    expect(screen.getByText("10")).toBeInTheDocument(); // total submissions
  });

  it("renders P1 and P2 alert cards, tier-labeled", async () => {
    mockSummary(ALERTING_SUMMARY);
    render(<AdminNotificationsPage />);
    await waitFor(() => expect(screen.getByText(/30 unresolved DLQ entries/)).toBeInTheDocument());
    expect(screen.getByText("P1 Critical")).toBeInTheDocument();
    expect(screen.getByText("P2 Warning")).toBeInTheDocument();
    expect(screen.getByText(/20 failure-shaped event/)).toBeInTheDocument();
  });

  it("shows the oldest unresolved DLQ age", async () => {
    mockSummary(ALERTING_SUMMARY);
    render(<AdminNotificationsPage />);
    await waitFor(() => expect(screen.getByText(/Oldest unresolved DLQ entry/)).toBeInTheDocument());
    // 200 minutes -> rounds to 3h
    expect(screen.getByText("3h")).toBeInTheDocument();
  });

  it("renders a P1 alert and stat for a stuck undispatched submission — a different failure mode from the DLQ", async () => {
    // Real gap found and fixed this round: this failure mode (dispatch
    // never reached a worker at all, e.g. Redis down at the exact moment
    // of submit) previously had no alert path and no visible number on
    // this page — only the DLQ metrics did.
    mockSummary(UNDISPATCHED_ALERTING_SUMMARY);
    render(<AdminNotificationsPage />);
    await waitFor(() => expect(screen.getByText(/Oldest undispatched submission is 35 minute/)).toBeInTheDocument());
    expect(screen.getByText("P1 Critical")).toBeInTheDocument();
    expect(screen.getByText("42")).toBeInTheDocument(); // undispatched stat tile
    expect(screen.getByText("35m")).toBeInTheDocument(); // the detail box's own age display
  });

  it("reloads with the new window when the selector changes", async () => {
    mockSummary();
    const getSpy = jest.spyOn(api, "get");
    const user = userEvent.setup();
    render(<AdminNotificationsPage />);
    await waitFor(() => expect(screen.getByText("No active alerts — pipeline looks healthy.")).toBeInTheDocument());

    await user.selectOptions(screen.getByRole("combobox"), "168");
    await waitFor(() => expect(getSpy).toHaveBeenLastCalledWith(
      expect.stringContaining("window_hours=168"),
    ));
  });

  it("sends the daily summary now and shows a success toast", async () => {
    mockSummary();
    jest.spyOn(api, "post").mockResolvedValue({ data: { success: true, message: "Daily summary dispatched to 2 recipient(s)." } } as any);
    const user = userEvent.setup();
    render(<AdminNotificationsPage />);
    await waitFor(() => expect(screen.getByText("No active alerts — pipeline looks healthy.")).toBeInTheDocument());

    await user.click(screen.getByRole("button", { name: /Send daily summary now/ }));
    await waitFor(() => expect(api.post).toHaveBeenCalledWith("/essay/admin/notifications/send-summary/"));
    await waitFor(() => expect(mockToastSuccess).toHaveBeenCalledWith("Daily summary dispatched to 2 recipient(s)."));
  });

  it("shows an error toast when no recipients are configured", async () => {
    mockSummary();
    jest.spyOn(api, "post").mockRejectedValue({
      response: { status: 409, data: { success: false, message: "No alert email recipients configured (ALERT_EMAIL_RECIPIENTS is empty)." } },
    });
    const user = userEvent.setup();
    render(<AdminNotificationsPage />);
    await waitFor(() => expect(screen.getByText("No active alerts — pipeline looks healthy.")).toBeInTheDocument());

    await user.click(screen.getByRole("button", { name: /Send daily summary now/ }));
    await waitFor(() => expect(mockToastError).toHaveBeenCalled());
  });

  it("shows a load-error state on failure", async () => {
    jest.spyOn(api, "get").mockRejectedValue(new Error("network error"));
    render(<AdminNotificationsPage />);
    await waitFor(() => expect(screen.getByText("Couldn't load the pipeline summary")).toBeInTheDocument());
  });
});
