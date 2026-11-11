/**
 * @jest-environment jsdom
 *
 * Essay Writing — admin per-assignment Analytics page (Phase 9, Task 9.2):
 * stat tiles, score-distribution chart, word-count-vs-score chart, and the
 * weakest-rubric-criterion callout.
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
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import api from "@/lib/api";
import AdminEssayAnalyticsPage from "@/app/admin/essay-writing/analytics/[assignment_id]/page";
import type { EssayAssignment, EssayAssignmentAnalytics } from "@/types";

const ASSIGNMENT: EssayAssignment = {
  id: "assign-1", paper: "paper-1", paper_title: "Persuasive Writing", batch_id: "batch-1",
  institution_id: "inst-1", global_start_time: null, global_expire_time: "2026-09-25T10:00:00Z",
  departments: [], status: "LIVE", created_by: "admin-1",
  created_at: "2026-09-20T00:00:00Z", updated_at: "2026-09-20T00:00:00Z",
};

const BASE_ANALYTICS: EssayAssignmentAnalytics = {
  assignment_id: "assign-1", generated_at: "2026-09-21T10:00:00Z",
  // 13/17, deliberately not matching any 0-10 score value — the Submitted
  // stat tile ("N/M") and the score-distribution/word-count charts'
  // own "score/10" bar labels render as sibling text nodes, so a
  // total_submitted/total_allocated pair that happens to read like a
  // real score bucket (e.g. 8/10) makes getByText genuinely ambiguous
  // across unrelated parts of the page, not a real rendering bug.
  total_allocated: 17, total_submitted: 13, total_scored: 6,
  average_score: 7.5,
  score_distribution: Array.from({ length: 11 }, (_, i) => ({ score: i, count: i === 7 ? 3 : i === 8 ? 3 : 0 })),
  word_count_vs_score: [
    { score: 7, average_word_count: 250, count: 3 },
    { score: 8, average_word_count: 320, count: 3 },
  ],
  weakest_criterion: { name: "Clarity", weak_count: 4, total_count: 6, weak_rate_percentage: 66.67 },
  plagiarism_flag_rate_percentage: 12.5,
  llm_failure_rate_percentage: 5.0,
  metric_definitions: { weakest_criterion: "Among every rubric criterion..." },
};

function mockLoad(overrides: Partial<EssayAssignmentAnalytics> = {}) {
  jest.spyOn(api, "get").mockImplementation((url: string) => {
    if (url.includes("/analytics/")) {
      return Promise.resolve({ data: { data: { ...BASE_ANALYTICS, ...overrides } } } as any);
    }
    if (url.includes("/essay/admin/assignments/assign-1/")) {
      return Promise.resolve({ data: { data: ASSIGNMENT } } as any);
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

describe("Analytics page", () => {
  it("renders the stat tiles and score distribution", async () => {
    mockLoad();
    render(<AdminEssayAnalyticsPage />);
    await waitFor(() => expect(screen.getByText("Persuasive Writing")).toBeInTheDocument());
    expect(screen.getByText("7.5/10")).toBeInTheDocument();
    expect(screen.getByText("13/17")).toBeInTheDocument(); // "Submitted" tile
    expect(screen.getByText("12.5%")).toBeInTheDocument();
    expect(screen.getByText("5%")).toBeInTheDocument();
  });

  it("the Refresh button explicitly bypasses the backend cache", async () => {
    // Real gap found by this phase's own second final-audit round: a
    // plain reload of this endpoint could silently re-serve the exact
    // same stale (60s-cached) data with no indication — inconsistent
    // with the LLM Controls page's own always-fresh Refresh button. The
    // initial mount must NOT pass ?refresh=true (it should still get to
    // benefit from the cache); only the explicit button click should.
    mockLoad();
    const user = userEvent.setup();
    render(<AdminEssayAnalyticsPage />);
    await waitFor(() => expect(screen.getByText("Persuasive Writing")).toBeInTheDocument());

    expect(api.get).toHaveBeenCalledWith(expect.stringMatching(/\/analytics\/$/));
    expect(api.get).not.toHaveBeenCalledWith(expect.stringContaining("refresh=true"));

    await user.click(screen.getByRole("button", { name: /Refresh/ }));
    await waitFor(() => expect(api.get).toHaveBeenCalledWith(expect.stringContaining("/analytics/?refresh=true")));
  });

  it("renders the weakest criterion callout", async () => {
    mockLoad();
    render(<AdminEssayAnalyticsPage />);
    await waitFor(() => expect(screen.getByText("Clarity")).toBeInTheDocument());
    expect(screen.getByText("66.67%")).toBeInTheDocument();
    expect(screen.getByText(/4 of 6 appearances/)).toBeInTheDocument();
  });

  it("shows a friendly message when no criterion is weak", async () => {
    mockLoad({ weakest_criterion: null });
    render(<AdminEssayAnalyticsPage />);
    await waitFor(() => expect(screen.getByText("Persuasive Writing")).toBeInTheDocument());
    expect(screen.getByText(/No single criterion is standing out/)).toBeInTheDocument();
  });

  it("shows an empty state when nothing has been scored yet", async () => {
    mockLoad({ total_scored: 0, total_submitted: 2, total_allocated: 10, average_score: null, score_distribution: [], word_count_vs_score: [], weakest_criterion: null });
    render(<AdminEssayAnalyticsPage />);
    await waitFor(() => expect(screen.getByText("No scored submissions yet")).toBeInTheDocument());
    expect(screen.getByText(/2 of 10 student/)).toBeInTheDocument();
  });

  it("shows an error state when analytics fail to load", async () => {
    jest.spyOn(api, "get").mockImplementation((url: string) => {
      if (url.includes("/analytics/")) return Promise.reject(new Error("network error"));
      return Promise.resolve({ data: { data: ASSIGNMENT } } as any);
    });
    render(<AdminEssayAnalyticsPage />);
    await waitFor(() => expect(screen.getByText("Couldn't load analytics")).toBeInTheDocument());
  });
});
