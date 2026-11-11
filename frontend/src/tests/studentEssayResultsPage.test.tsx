/**
 * @jest-environment jsdom
 *
 * Coverage for the student essay-writing "Past Results" page (Phase 14,
 * Task 14.1), mirroring the MCQ assessments results page's own load-state
 * pattern and studentEssayWritingListPage.test.tsx's own mocking
 * conventions for this module.
 */

const mockPush = jest.fn();
jest.mock("next/navigation", () => ({
  useRouter: () => ({ push: mockPush }),
}));

jest.mock("@/components/layout/StudentLayout", () => ({
  StudentLayout: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}));

const mockToastError = jest.fn();
jest.mock("@/components/ui/Toast", () => ({
  useToast: () => ({ error: mockToastError, success: jest.fn() }),
}));

import React from "react";
import { render, screen } from "@testing-library/react";
import api from "@/lib/api";
import StudentEssayResultsPage from "@/app/students/essay-writing/results/page";
import type { StudentEssayResultRow } from "@/types";

const SCORED_RESULT: StudentEssayResultRow = {
  assignment_id: "assign-1", attempt_id: "attempt-1", paper_title: "Persuasive Writing",
  set_label: "Set A", question_text: "Discuss X.", attempt_status: "SUBMITTED",
  exam_status: "completed", started_at: "2026-09-01T10:00:00Z", submitted_at: "2026-09-01T10:30:00Z",
  score: 8, max_score: 10, is_no_submission: false,
  feedback: { overall: "Strong essay.", breakdown: { clarity: { score: 4, maxScore: 5, feedback: "Clear." } } },
};

const PROCESSING_RESULT: StudentEssayResultRow = {
  ...SCORED_RESULT, assignment_id: "assign-2", attempt_id: "attempt-2", paper_title: "Argumentative Writing",
  exam_status: "processing", score: null, feedback: null, submitted_at: "2026-09-02T10:00:00Z",
};

const FAILED_RESULT: StudentEssayResultRow = {
  ...SCORED_RESULT, assignment_id: "assign-3", attempt_id: "attempt-3", paper_title: "Narrative Writing",
  exam_status: "failed", score: null, feedback: null, submitted_at: "2026-09-03T10:00:00Z",
};

function mockApi(results: StudentEssayResultRow[] = [SCORED_RESULT]) {
  return jest.spyOn(api, "get").mockResolvedValue({ data: { data: results } } as any);
}

afterEach(() => {
  jest.restoreAllMocks();
  mockToastError.mockClear();
});

describe("Student essay results page — load states", () => {
  it("shows the empty state when there are no results", async () => {
    mockApi([]);
    render(<StudentEssayResultsPage />);
    expect(await screen.findByText(/No past results yet/)).toBeInTheDocument();
  });

  it("shows an error state when the list fails to load", async () => {
    jest.spyOn(api, "get").mockRejectedValue(new Error("network error"));
    render(<StudentEssayResultsPage />);
    expect(await screen.findByText(/Couldn't load your results/)).toBeInTheDocument();
    expect(mockToastError).toHaveBeenCalled();
  });

  it("fetches from the essay-service results endpoint, not the MCQ one", async () => {
    const spy = mockApi([SCORED_RESULT]);
    render(<StudentEssayResultsPage />);
    await screen.findByText("Persuasive Writing");
    expect(spy).toHaveBeenCalledWith("/essay/student/results/");
  });
});

describe("Student essay results page — scored result", () => {
  it("renders the score, overall feedback, and breakdown", async () => {
    mockApi([SCORED_RESULT]);
    render(<StudentEssayResultsPage />);
    expect(await screen.findByText("Persuasive Writing")).toBeInTheDocument();
    expect(screen.getByText("8")).toBeInTheDocument();
    expect(screen.getByText("/10")).toBeInTheDocument();
    expect(screen.getByText("Strong essay.")).toBeInTheDocument();
    expect(screen.getByText("clarity")).toBeInTheDocument();
    expect(screen.getByText("4/5")).toBeInTheDocument();
    expect(screen.getByText("Scored")).toBeInTheDocument();
  });

  it("flags a no-submission result distinctly from a genuine low score", async () => {
    mockApi([{ ...SCORED_RESULT, score: 0, is_no_submission: true, feedback: { overall: "", breakdown: {} } }]);
    render(<StudentEssayResultsPage />);
    await screen.findByText("Persuasive Writing");
    expect(screen.getByText(/No response was submitted/)).toBeInTheDocument();
  });
});

describe("Student essay results page — still-processing result", () => {
  it("shows a neutral 'Results pending' state, never the raw 'failed' status", async () => {
    mockApi([PROCESSING_RESULT]);
    render(<StudentEssayResultsPage />);
    expect(await screen.findByText("Argumentative Writing")).toBeInTheDocument();
    expect(screen.getByText("Results pending")).toBeInTheDocument();
    expect(screen.getByText(/Still being evaluated/)).toBeInTheDocument();
    expect(screen.queryByText(/failed/i)).not.toBeInTheDocument();
  });

  it("treats the real 'pending' bucket value the same as 'processing', not a crash or blank state", async () => {
    // Found missing from the type during the fourth audit round:
    // EssaySubmission genuinely defaults to PENDING for the brief window
    // before a dispatched task picks it up — this proves that real value
    // renders sanely, not just "processing" and "failed".
    mockApi([{ ...PROCESSING_RESULT, exam_status: "pending" }]);
    render(<StudentEssayResultsPage />);
    expect(await screen.findByText("Argumentative Writing")).toBeInTheDocument();
    expect(screen.getByText("Results pending")).toBeInTheDocument();
    expect(screen.getByText(/Still being evaluated/)).toBeInTheDocument();
  });
});

describe("Student essay results page — permanently-failed evaluation", () => {
  // Found during the third audit round: this state was previously given
  // the exact same "check back soon" copy as genuine processing, which is
  // a false promise — this one is stuck in an admin-only retry queue, not
  // something that resolves on its own.
  it("shows a distinct, non-alarming message pointing to the administrator, not 'check back soon'", async () => {
    mockApi([FAILED_RESULT]);
    render(<StudentEssayResultsPage />);
    expect(await screen.findByText("Narrative Writing")).toBeInTheDocument();
    expect(screen.getByText("Results pending")).toBeInTheDocument();
    expect(screen.getByText(/contact your administrator/i)).toBeInTheDocument();
    expect(screen.queryByText(/check back soon/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/^failed$/i)).not.toBeInTheDocument();
  });
});
