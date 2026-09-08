/**
 * @jest-environment jsdom
 *
 * Regression tests for the 2026-08-18 analytics-page audit fixes:
 * data-driven KPI colors (not fixed brand colors), completed/allocated
 * ratio, small-sample-size caveat, hardest-first question sorting with
 * outlier badges, set-fairness/malpractice-breakdown panels that hide
 * themselves when there's nothing to compare, and the "View flagged
 * students" deep link into the results page.
 */

const mockPush = jest.fn();
jest.mock("next/navigation", () => ({
  useParams: () => ({ assignment_id: "11111111-1111-1111-1111-111111111111" }),
  useRouter: () => ({ push: mockPush }),
}));

jest.mock("@/components/layout/AdminLayout", () => ({
  AdminLayout: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}));

const mockToastError = jest.fn();
jest.mock("@/components/ui/Toast", () => ({
  useToast: () => ({ error: mockToastError, success: jest.fn() }),
}));

import React from "react";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import api from "@/lib/api";
import AdminAssessmentAnalyticsPage from "@/app/admin/assessments/analytics/[assignment_id]/page";

const METRIC_DEFINITIONS = {
  score_distribution: "def1", average_score_percentage: "def2", pass_rate_percentage: "def3",
  percentage_correct: "def4", average_seconds_spent: "def5", average_percentage: "def6",
  set_comparison: "def7", malpractice_rate_percentage: "def8", malpractice_breakdown: "def9",
};

function baseData(overrides: Record<string, unknown> = {}) {
  return {
    assignment_id: "11111111-1111-1111-1111-111111111111",
    generated_at: "2026-08-18T10:00:00Z",
    total_completed: 20,
    total_allocated: 25,
    average_score_percentage: 62.5,
    average_completion_time_seconds: 2280,
    exam_duration_minutes: 45,
    score_distribution: [{ bucket: "0-10%", count: 0 }],
    pass_fail: { pass_count: 12, fail_count: 8, pass_rate_percentage: 60, cutoff_percentage: 40 },
    question_difficulty: [
      { question_id: "q1", question_number: 1, set_label: "Set A", total_answered: 20, correct_count: 15, percentage_correct: 75, average_seconds_spent: 30 },
      { question_id: "q2", question_number: 2, set_label: "Set A", total_answered: 20, correct_count: 2, percentage_correct: 10, average_seconds_spent: 90 },
      { question_id: "q3", question_number: 3, set_label: "Set A", total_answered: 20, correct_count: 20, percentage_correct: 100, average_seconds_spent: 5 },
      { question_id: "q4", question_number: 4, set_label: "Set A", total_answered: 0, correct_count: 0, percentage_correct: null, average_seconds_spent: null },
    ],
    department_comparison: [{ department: "CSE", student_count: 20, average_percentage: 62.5 }],
    set_comparison: [{ set_label: "Set A", student_count: 20, average_percentage: 62.5 }],
    malpractice_rate: { flagged_count: 0, total_count: 20, rate_percentage: 0 },
    malpractice_breakdown: [],
    metric_definitions: METRIC_DEFINITIONS,
    ...overrides,
  };
}

function mockAnalytics(data: unknown) {
  jest.spyOn(api, "get").mockImplementation((url: string) => {
    if (url.includes("/analytics/export/")) return Promise.resolve({ data: new Blob() } as any);
    return Promise.resolve({ data: { data } } as any);
  });
}

beforeEach(() => {
  mockPush.mockClear();
  mockToastError.mockClear();
});

afterEach(() => {
  jest.restoreAllMocks();
});

describe("Admin analytics — no duplicated KPIs with the Dashboard page", () => {
  it("mentions completed/allocated as page context, not a headline KPI tile", async () => {
    mockAnalytics(baseData({ total_completed: 20, total_allocated: 25 }));
    render(<AdminAssessmentAnalyticsPage />);
    await waitFor(() => expect(screen.getByText(/based on 20 of 25 allocated students/)).toBeInTheDocument());
    // Dashboard owns the "X / Y" headline framing — Analytics must not
    // duplicate it as its own tile (2026-08-18 KPI-overlap audit).
    expect(screen.queryByText("20 / 25")).not.toBeInTheDocument();
  });

  it("shows Avg Completion Time — a metric Dashboard doesn't have at all", async () => {
    mockAnalytics(baseData({ average_completion_time_seconds: 2280, exam_duration_minutes: 45 }));
    render(<AdminAssessmentAnalyticsPage />);
    await waitFor(() => expect(screen.getByText("Avg Completion Time")).toBeInTheDocument());
    expect(screen.getByText("38.0 min")).toBeInTheDocument(); // 2280s
    expect(screen.getByText("of 45 min allowed")).toBeInTheDocument();
  });

  it("shows a dash for average completion time when there's no data yet", async () => {
    mockAnalytics(baseData({ average_completion_time_seconds: null }));
    render(<AdminAssessmentAnalyticsPage />);
    await waitFor(() => expect(screen.getByText("Avg Completion Time")).toBeInTheDocument());
    const tile = screen.getByText("Avg Completion Time").closest("div")?.parentElement;
    expect(tile).toHaveTextContent("—");
  });

  it("does not restate the raw flagged count on the Malpractice Rate tile — Dashboard owns that number", async () => {
    mockAnalytics(baseData({ malpractice_rate: { flagged_count: 2, total_count: 20, rate_percentage: 10 } }));
    render(<AdminAssessmentAnalyticsPage />);
    await waitFor(() => expect(screen.getByText("Malpractice Rate")).toBeInTheDocument());
    expect(screen.queryByText("2 flagged")).not.toBeInTheDocument();
  });
});

describe("Admin analytics — KPI tiles are data-driven, not decorative", () => {
  it("renders a low pass rate in red, not the fixed success green", async () => {
    mockAnalytics(baseData({ pass_fail: { pass_count: 1, fail_count: 19, pass_rate_percentage: 5, cutoff_percentage: 40 } }));
    render(<AdminAssessmentAnalyticsPage />);
    await waitFor(() => expect(screen.getByText("5%")).toBeInTheDocument());
    const icon = screen.getByText("5%").closest("div")?.querySelector("svg");
    expect(icon).toHaveStyle({ color: "#DC2626" });
  });

  it("renders a high pass rate in green", async () => {
    mockAnalytics(baseData({ pass_fail: { pass_count: 19, fail_count: 1, pass_rate_percentage: 95, cutoff_percentage: 40 } }));
    render(<AdminAssessmentAnalyticsPage />);
    await waitFor(() => expect(screen.getByText("95%")).toBeInTheDocument());
    const icon = screen.getByText("95%").closest("div")?.querySelector("svg");
    expect(icon).toHaveStyle({ color: "#16A34A" });
  });

  it("renders a high malpractice rate in red", async () => {
    mockAnalytics(baseData({ malpractice_rate: { flagged_count: 5, total_count: 20, rate_percentage: 25 } }));
    render(<AdminAssessmentAnalyticsPage />);
    await waitFor(() => expect(screen.getByText("25%")).toBeInTheDocument());
    const icon = screen.getByText("25%").closest("div")?.querySelector("svg");
    expect(icon).toHaveStyle({ color: "#DC2626" });
  });
});

describe("Admin analytics — small sample size caveat", () => {
  it("shows the caveat banner below the threshold", async () => {
    mockAnalytics(baseData({ total_completed: 3 }));
    render(<AdminAssessmentAnalyticsPage />);
    await waitFor(() => expect(screen.getByText(/Only 3 sessions have completed so far/)).toBeInTheDocument());
  });

  it("does not show the caveat once enough sessions have completed", async () => {
    mockAnalytics(baseData({ total_completed: 20 }));
    render(<AdminAssessmentAnalyticsPage />);
    await waitFor(() => expect(screen.getByText("Pass Rate")).toBeInTheDocument());
    expect(screen.queryByText(/have completed so far/)).not.toBeInTheDocument();
  });
});

describe("Admin analytics — per-question difficulty table", () => {
  it("sorts hardest-first, with never-attempted questions last", async () => {
    mockAnalytics(baseData());
    render(<AdminAssessmentAnalyticsPage />);
    await waitFor(() => expect(screen.getByText("Per-Question Difficulty")).toBeInTheDocument());

    const rows = screen.getAllByRole("row").slice(1); // skip header row
    const questionNumbers = rows.map(r => r.querySelectorAll("td")[1]?.textContent);
    // q2 (10%) hardest, q1 (75%), q3 (100%), q4 (null) last
    expect(questionNumbers).toEqual(["2", "1", "3", "4"]);
  });

  it("badges a very-hard question", async () => {
    mockAnalytics(baseData());
    render(<AdminAssessmentAnalyticsPage />);
    await waitFor(() => expect(screen.getByText("Very hard")).toBeInTheDocument());
  });

  it("badges a very-easy question", async () => {
    mockAnalytics(baseData());
    render(<AdminAssessmentAnalyticsPage />);
    await waitFor(() => expect(screen.getByText("Very easy")).toBeInTheDocument());
  });

  it("shows formatted average time per question, and a dash for no data", async () => {
    mockAnalytics(baseData());
    render(<AdminAssessmentAnalyticsPage />);
    await waitFor(() => expect(screen.getByText("30s")).toBeInTheDocument());
    expect(screen.getByText("1.5 min")).toBeInTheDocument(); // 90s
    expect(screen.getAllByText("—").length).toBeGreaterThan(0); // q4's null time (and possibly its % correct)
  });
});

describe("Admin analytics — set comparison panel visibility", () => {
  it("hides the panel when there's only one set (nothing to compare)", async () => {
    mockAnalytics(baseData({ set_comparison: [{ set_label: "Set A", student_count: 20, average_percentage: 62.5 }] }));
    render(<AdminAssessmentAnalyticsPage />);
    await waitFor(() => expect(screen.getByText("Pass Rate")).toBeInTheDocument());
    expect(screen.queryByText("Set Fairness Comparison")).not.toBeInTheDocument();
  });

  it("shows the panel with two or more sets", async () => {
    mockAnalytics(baseData({
      set_comparison: [
        { set_label: "Set A", student_count: 10, average_percentage: 70 },
        { set_label: "Set B", student_count: 10, average_percentage: 55 },
      ],
    }));
    render(<AdminAssessmentAnalyticsPage />);
    await waitFor(() => expect(screen.getByText("Set Fairness Comparison")).toBeInTheDocument());
    expect(screen.getByText("Set A (10)")).toBeInTheDocument();
    expect(screen.getByText("Set B (10)")).toBeInTheDocument();
  });
});

describe("Admin analytics — Set Fairness drill-down", () => {
  it("clicking a set's bar navigates to the results page pre-filtered to that set", async () => {
    const user = userEvent.setup();
    mockAnalytics(baseData({
      set_comparison: [
        { set_label: "Set A", student_count: 10, average_percentage: 70 },
        { set_label: "Set B", student_count: 10, average_percentage: 55 },
      ],
    }));
    render(<AdminAssessmentAnalyticsPage />);
    await waitFor(() => expect(screen.getByText("Set B (10)")).toBeInTheDocument());

    await user.click(screen.getByText("Set B (10)"));
    expect(mockPush).toHaveBeenCalledWith("/admin/assessments/results/11111111-1111-1111-1111-111111111111?set=Set%20B");
  });
});

const QUESTION_RESPONSES_FIXTURE = {
  question_id: "q2", question_number: 2, set_label: "Set A",
  question_text: "What is 2+2?", question_image_url: null, marks: 5,
  options: [
    { id: "optA", label: "A", content_type: "text", text: "3", image_key: "", image_url: null, is_correct: false, order: 1 },
    { id: "optB", label: "B", content_type: "text", text: "4", image_key: "", image_url: null, is_correct: true, order: 2 },
  ],
  count: 3, total_pages: 1, current_page: 1,
  students: [
    { student_user_id: "s1", student_roll_id: "ROLL-001", student_name: "Alice A", department: "CSE", exam_status: "submitted", selected_option_ids: ["optB"], is_correct: true, answered: true },
    { student_user_id: "s2", student_roll_id: "ROLL-002", student_name: "Bob B", department: "CSE", exam_status: "submitted", selected_option_ids: ["optA"], is_correct: false, answered: true },
    { student_user_id: "s3", student_roll_id: "ROLL-003", student_name: "Carol C", department: "ECE", exam_status: "writing", selected_option_ids: [], is_correct: false, answered: false },
  ],
};

describe("Admin analytics — per-question drill-down", () => {
  it("opens a modal listing every student's answer when 'Students' is clicked on a question row", async () => {
    const user = userEvent.setup();
    mockAnalytics(baseData());
    jest.spyOn(api, "get").mockImplementation((url: string) => {
      if (url.includes("/analytics/export/")) return Promise.resolve({ data: new Blob() } as any);
      if (url.includes("/questions/")) return Promise.resolve({ data: QUESTION_RESPONSES_FIXTURE } as any);
      return Promise.resolve({ data: { data: baseData() } } as any);
    });
    render(<AdminAssessmentAnalyticsPage />);
    await waitFor(() => expect(screen.getByText("Per-Question Difficulty")).toBeInTheDocument());

    const firstRow = screen.getAllByRole("row")[1]; // header + first data row (q2, hardest-first)
    await user.click(within(firstRow).getByText("Students"));

    await waitFor(() => expect(screen.getByText("What is 2+2?")).toBeInTheDocument());
    expect(screen.getByText("Alice A")).toBeInTheDocument();
    expect(screen.getByText("Bob B")).toBeInTheDocument();
    expect(screen.getByText("Carol C")).toBeInTheDocument();
    expect(screen.getByText("Not answered")).toBeInTheDocument();
  });

  it("shows an error toast and does not open the modal if the fetch fails", async () => {
    const user = userEvent.setup();
    mockAnalytics(baseData());
    jest.spyOn(api, "get").mockImplementation((url: string) => {
      if (url.includes("/analytics/export/")) return Promise.resolve({ data: new Blob() } as any);
      if (url.includes("/questions/")) return Promise.reject(new Error("network error"));
      return Promise.resolve({ data: { data: baseData() } } as any);
    });
    render(<AdminAssessmentAnalyticsPage />);
    await waitFor(() => expect(screen.getByText("Per-Question Difficulty")).toBeInTheDocument());

    const firstRow = screen.getAllByRole("row")[1];
    await user.click(within(firstRow).getByText("Students"));

    await waitFor(() => expect(mockToastError).toHaveBeenCalled());
    expect(screen.queryByText("What is 2+2?")).not.toBeInTheDocument();
  });
});

describe("Admin analytics — malpractice breakdown panel visibility", () => {
  it("hides the panel when nothing is flagged", async () => {
    mockAnalytics(baseData({ malpractice_breakdown: [] }));
    render(<AdminAssessmentAnalyticsPage />);
    await waitFor(() => expect(screen.getByText("Pass Rate")).toBeInTheDocument());
    expect(screen.queryByText("Malpractice Breakdown")).not.toBeInTheDocument();
  });

  it("shows plain-English reason labels, not raw codes, when something is flagged", async () => {
    mockAnalytics(baseData({ malpractice_breakdown: [{ reason: "tab_switch", count: 3 }, { reason: "cadence", count: 1 }] }));
    render(<AdminAssessmentAnalyticsPage />);
    await waitFor(() => expect(screen.getByText("Malpractice Breakdown")).toBeInTheDocument());
    expect(screen.getByText("Excessive tab switching")).toBeInTheDocument();
    expect(screen.getByText("Suspiciously fast answering")).toBeInTheDocument();
    expect(screen.queryByText("tab_switch")).not.toBeInTheDocument();
  });
});

describe("Admin analytics — View flagged students deep link", () => {
  it("navigates to the results page pre-filtered to flagged students", async () => {
    const user = userEvent.setup();
    mockAnalytics(baseData({ malpractice_rate: { flagged_count: 4, total_count: 20, rate_percentage: 20 } }));
    render(<AdminAssessmentAnalyticsPage />);
    await waitFor(() => expect(screen.getByText("Review 4 flagged students")).toBeInTheDocument());

    await user.click(screen.getByText("Review 4 flagged students"));
    expect(mockPush).toHaveBeenCalledWith("/admin/assessments/results/11111111-1111-1111-1111-111111111111?flagged=true");
  });

  it("singular phrasing for exactly one flagged student", async () => {
    mockAnalytics(baseData({ malpractice_rate: { flagged_count: 1, total_count: 20, rate_percentage: 5 } }));
    render(<AdminAssessmentAnalyticsPage />);
    await waitFor(() => expect(screen.getByText("Review 1 flagged student")).toBeInTheDocument());
  });

  it("shows no action at all when nothing is flagged, rather than a disabled one", async () => {
    mockAnalytics(baseData({ malpractice_rate: { flagged_count: 0, total_count: 20, rate_percentage: 0 } }));
    render(<AdminAssessmentAnalyticsPage />);
    await waitFor(() => expect(screen.getByText("Malpractice Rate")).toBeInTheDocument());
    expect(screen.queryByText(/Review .* flagged student/)).not.toBeInTheDocument();
  });
});

describe("Admin analytics — load failure vs genuine emptiness", () => {
  it("shows a distinct error state on failure, not the empty state", async () => {
    jest.spyOn(api, "get").mockRejectedValue(new Error("network error"));
    render(<AdminAssessmentAnalyticsPage />);
    await waitFor(() => expect(screen.getByText("Couldn't load analytics")).toBeInTheDocument());
    expect(screen.queryByText("No completed sessions yet")).not.toBeInTheDocument();
  });

  it("shows the genuine empty state when there are truly zero completions", async () => {
    mockAnalytics(baseData({ total_completed: 0 }));
    render(<AdminAssessmentAnalyticsPage />);
    await waitFor(() => expect(screen.getByText("No completed sessions yet")).toBeInTheDocument());
  });
});

const TWO_SET_QUESTION_DIFFICULTY = [
  { question_id: "a1", question_number: 1, set_label: "Set A", total_answered: 10, correct_count: 8, percentage_correct: 80, average_seconds_spent: 20 },
  { question_id: "a2", question_number: 2, set_label: "Set A", total_answered: 10, correct_count: 5, percentage_correct: 50, average_seconds_spent: 40 },
  { question_id: "b1", question_number: 1, set_label: "Set B", total_answered: 10, correct_count: 3, percentage_correct: 30, average_seconds_spent: 60 },
  { question_id: "b2", question_number: 2, set_label: "Set B", total_answered: 10, correct_count: 9, percentage_correct: 90, average_seconds_spent: 25 },
];

describe("Admin analytics — malpractice tile's action affordance", () => {
  it("the review-flagged action sits inside the same tile as the rate itself, not a separate mismatched card", async () => {
    mockAnalytics(baseData({ malpractice_rate: { flagged_count: 3, total_count: 20, rate_percentage: 15 } }));
    render(<AdminAssessmentAnalyticsPage />);
    await waitFor(() => expect(screen.getByText("Review 3 flagged students")).toBeInTheDocument());
    // "Malpractice Rate" (the tile's own label) and the review action share
    // a common ancestor no further up than the tile card itself — i.e.
    // they're part of one tile, not two separate cards on the page.
    const label = screen.getByText("Malpractice Rate");
    const action = screen.getByText("Review 3 flagged students");
    const tile = label.closest("div")?.parentElement;
    expect(tile).toContainElement(action);
  });
});

describe("Admin analytics — per-set filter dropdown", () => {
  it("hides the dropdown when there's only one set", async () => {
    mockAnalytics(baseData()); // base fixture is single-set (Set A only)
    render(<AdminAssessmentAnalyticsPage />);
    await waitFor(() => expect(screen.getByText("Per-Question Difficulty")).toBeInTheDocument());
    expect(screen.queryByRole("combobox")).not.toBeInTheDocument();
  });

  it("shows every set's questions by default, and narrows to one set on selection", async () => {
    const user = userEvent.setup();
    mockAnalytics(baseData({ question_difficulty: TWO_SET_QUESTION_DIFFICULTY }));
    render(<AdminAssessmentAnalyticsPage />);
    await waitFor(() => expect(screen.getAllByRole("row")).toHaveLength(5)); // header + 4 questions

    await user.selectOptions(screen.getByRole("combobox"), "Set B");

    await waitFor(() => expect(screen.getAllByRole("row")).toHaveLength(3)); // header + Set B's 2 questions
    const rows = screen.getAllByRole("row").slice(1);
    expect(rows.every(r => r.querySelectorAll("td")[0]?.textContent === "Set B")).toBe(true);
  });

  it("switching back to 'All sets' restores every set's questions", async () => {
    const user = userEvent.setup();
    mockAnalytics(baseData({ question_difficulty: TWO_SET_QUESTION_DIFFICULTY }));
    render(<AdminAssessmentAnalyticsPage />);
    await waitFor(() => expect(screen.getAllByRole("row")).toHaveLength(5));

    await user.selectOptions(screen.getByRole("combobox"), "Set A");
    await waitFor(() => expect(screen.getAllByRole("row")).toHaveLength(3));

    await user.selectOptions(screen.getByRole("combobox"), "");
    await waitFor(() => expect(screen.getAllByRole("row")).toHaveLength(5));
  });

  it("still sorts hardest-first within the selected set", async () => {
    const user = userEvent.setup();
    mockAnalytics(baseData({ question_difficulty: TWO_SET_QUESTION_DIFFICULTY }));
    render(<AdminAssessmentAnalyticsPage />);
    await waitFor(() => expect(screen.getAllByRole("row")).toHaveLength(5));

    await user.selectOptions(screen.getByRole("combobox"), "Set A");

    const rows = screen.getAllByRole("row").slice(1);
    const questionNumbers = rows.map(r => r.querySelectorAll("td")[1]?.textContent);
    expect(questionNumbers).toEqual(["2", "1"]); // Set A: q2 (50%) harder than q1 (80%)
  });
});
