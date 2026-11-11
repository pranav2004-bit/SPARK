/**
 * @jest-environment jsdom
 *
 * Essay Writing — admin Submissions Module detail page (Phase 6, Task 6.1)
 * + Phase 7, Task 7.1's own per-submission LLM Controls: retrigger, the
 * trace/debug view, and the manual score override form.
 */

const mockPush = jest.fn();
const mockParams = { submission_id: "sub-1" };
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
import { render, screen, waitFor, within, fireEvent } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import api from "@/lib/api";
import AdminEssaySubmissionDetailPage from "@/app/admin/essay-writing/submissions/[submission_id]/page";
import type { EssaySubmissionDetail, EssayLLMTrace } from "@/types";

// Explicitly typed, not inferred from the object literal — an untyped
// `malpractice_reasons: []` would infer as `never[]`, and an untyped
// `score`/`feedback` wouldn't accept `null` from an override, the exact
// same class of gap Phase 4's own frontend audit already found and fixed
// once in adminEssayAssignPage.test.tsx's fixtures.
const BASE_SUBMISSION: EssaySubmissionDetail = {
  id: "sub-1", status: "LLM_COMPLETE", student_id: "student-uuid-1", attempt_id: "attempt-1",
  assignment_id: "assignment-1", batch_id: "batch-uuid-1", paper_title: "Persuasive Writing",
  question_text: "Argue for or against remote work.", draft_response: "Remote work offers flexibility...",
  malpractice_flag: false, malpractice_reasons: [],
  score: 8, feedback: { overall: "Well argued, clear structure." },
  evaluated_by: "llm", has_llm_trace: true,
  events: [
    { id: "ev-1", event_type: "STATUS_CHANGE", detail: "-> LLM_PROCESSING", worker_hostname: "worker@abc", task_id: "task-1", admin_user_id: null, reason: "", occurred_at: "2026-09-20T10:00:00Z" },
    { id: "ev-2", event_type: "STATUS_CHANGE", detail: "LLM_PROCESSING -> LLM_COMPLETE", worker_hostname: "worker@abc", task_id: "task-1", admin_user_id: null, reason: "", occurred_at: "2026-09-20T10:01:00Z" },
  ],
  created_at: "2026-09-20T09:59:00Z", updated_at: "2026-09-20T10:01:00Z",
};

const BASE_TRACE: EssayLLMTrace = {
  prompt_messages: [{ role: "system", content: "sys prompt" }, { role: "user", content: "usr prompt" }],
  raw_response: '{"score": 8, "feedback": {"overall": "Well argued, clear structure."}}',
  request_id: "chatcmpl-abc123", model_used: "gpt-4o-mini", evaluated_at: "2026-09-20T10:01:00Z",
};

function mockDetail(overrides: Partial<EssaySubmissionDetail> = {}, traceOverrides: Partial<EssayLLMTrace> | null = BASE_TRACE) {
  jest.spyOn(api, "get").mockImplementation((url: string) => {
    if (url.includes("/trace/")) {
      return Promise.resolve({ data: traceOverrides ? { data: { ...BASE_TRACE, ...traceOverrides } } : {} } as any);
    }
    if (url.includes("/essay/admin/submissions/sub-1/")) {
      return Promise.resolve({ data: { data: { ...BASE_SUBMISSION, ...overrides } } } as any);
    }
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

describe("Submission detail page", () => {
  it("renders the question, response, and score/feedback", async () => {
    mockDetail();
    render(<AdminEssaySubmissionDetailPage />);
    await waitFor(() => expect(screen.getByText("Argue for or against remote work.")).toBeInTheDocument());
    expect(screen.getByText(/Remote work offers flexibility/)).toBeInTheDocument();
    expect(screen.getByText("8")).toBeInTheDocument();
    expect(screen.getByText("Well argued, clear structure.")).toBeInTheDocument();
  });

  it("renders the chronological event trail with worker id", async () => {
    mockDetail();
    render(<AdminEssaySubmissionDetailPage />);
    await waitFor(() => expect(screen.getByText(/LLM_PROCESSING -> LLM_COMPLETE/)).toBeInTheDocument());
    expect(screen.getAllByText(/worker@abc/).length).toBeGreaterThan(0);
  });

  it("shows the malpractice panel only when flagged", async () => {
    mockDetail({ malpractice_flag: true, malpractice_reasons: ["paste_attempt"] });
    render(<AdminEssaySubmissionDetailPage />);
    await waitFor(() => expect(screen.getByText("Flagged")).toBeInTheDocument());
    expect(screen.getByText("paste attempt")).toBeInTheDocument();
  });

  it("shows 'not yet scored' when the submission has no score", async () => {
    mockDetail({ score: null, feedback: null, evaluated_by: null });
    render(<AdminEssaySubmissionDetailPage />);
    await waitFor(() => expect(screen.getByText("Not yet scored.")).toBeInTheDocument());
  });

  it("shows an error state when the detail fails to load", async () => {
    jest.spyOn(api, "get").mockRejectedValue(new Error("network error"));
    render(<AdminEssaySubmissionDetailPage />);
    await waitFor(() => expect(screen.getByText(/Couldn't load this submission/)).toBeInTheDocument());
  });
});

describe("Submission detail page — LLM trace (Phase 7)", () => {
  it("renders the recorded trace's model and request id", async () => {
    mockDetail();
    render(<AdminEssaySubmissionDetailPage />);
    await waitFor(() => expect(screen.getByText("gpt-4o-mini")).toBeInTheDocument());
    expect(screen.getByText("chatcmpl-abc123")).toBeInTheDocument();
  });

  it("shows 'no trace recorded' when none exists", async () => {
    mockDetail({}, null);
    render(<AdminEssaySubmissionDetailPage />);
    await waitFor(() => expect(screen.getByText("No LLM trace recorded for this submission.")).toBeInTheDocument());
  });
});

describe("Submission detail page — Admin override event rendering (Phase 7)", () => {
  it("shows the admin-override badge on an admin-scored submission", async () => {
    mockDetail({ evaluated_by: "admin" });
    render(<AdminEssaySubmissionDetailPage />);
    await waitFor(() => expect(screen.getByText("Admin override")).toBeInTheDocument());
  });

  it("renders an ADMIN_OVERRIDE event with its reason quoted", async () => {
    mockDetail({
      events: [
        ...BASE_SUBMISSION.events,
        { id: "ev-3", event_type: "ADMIN_OVERRIDE", detail: "Manual score override: 7/10.", worker_hostname: "", task_id: "", admin_user_id: "admin-uuid-1", reason: "LLM kept rejecting a legitimate essay.", occurred_at: "2026-09-20T10:05:00Z" },
      ],
    });
    render(<AdminEssaySubmissionDetailPage />);
    await waitFor(() => expect(screen.getByText("Admin override")).toBeInTheDocument());
    expect(screen.getByText(/LLM kept rejecting a legitimate essay/)).toBeInTheDocument();
  });
});

describe("Submission detail page — Retrigger (Phase 7)", () => {
  it("opens the retrigger modal and submits with a reason", async () => {
    mockDetail();
    jest.spyOn(api, "post").mockResolvedValue({ data: { success: true } } as any);
    const user = userEvent.setup({ delay: null });
    render(<AdminEssaySubmissionDetailPage />);
    await waitFor(() => expect(screen.getByText("Argue for or against remote work.")).toBeInTheDocument());

    await user.click(screen.getByRole("button", { name: /Retrigger/ }));
    const dialog = screen.getByRole("dialog");
    const textarea = screen.getByPlaceholderText("Why are you retriggering this evaluation?");
    await user.type(textarea, "Score looked wrong, re-running.");
    await user.click(within(dialog).getByRole("button", { name: "Retrigger" }));

    await waitFor(() => expect(api.post).toHaveBeenCalledWith(
      "/essay/admin/submissions/sub-1/retrigger/", { reason: "Score looked wrong, re-running." },
    ));
    await waitFor(() => expect(mockToastSuccess).toHaveBeenCalled());
  });

  it("rejects submitting the retrigger modal with a blank reason", async () => {
    mockDetail();
    jest.spyOn(api, "post").mockResolvedValue({ data: { success: true } } as any);
    const user = userEvent.setup({ delay: null });
    render(<AdminEssaySubmissionDetailPage />);
    await waitFor(() => expect(screen.getByText("Argue for or against remote work.")).toBeInTheDocument());

    await user.click(screen.getByRole("button", { name: /Retrigger/ }));
    const dialog = screen.getByRole("dialog");
    await user.click(within(dialog).getByRole("button", { name: "Retrigger" }));

    expect(mockToastError).toHaveBeenCalledWith("A reason is required to retrigger evaluation.");
    expect(api.post).not.toHaveBeenCalled();
  });

  it("disables the Retrigger button while a submission is already LLM_PROCESSING", async () => {
    // Real gap found by this phase's own final-audit round: the backend
    // now rejects (409) retriggering a submission that's already
    // LLM_PROCESSING — a genuine in-flight evaluation, retriggering which
    // would dispatch a second, concurrent, separately-billed OpenAI call
    // (ET11). This button-disable is the frontend's matching
    // defense-in-depth, not a substitute for the backend guard.
    mockDetail({ status: "LLM_PROCESSING" });
    render(<AdminEssaySubmissionDetailPage />);
    await waitFor(() => expect(screen.getByText("Argue for or against remote work.")).toBeInTheDocument());

    expect(screen.getByRole("button", { name: /Retrigger/ })).toBeDisabled();
  });
});

describe("Submission detail page — Manual score override (Phase 7)", () => {
  it("shows the Override Score button only when LLM_FAILED", async () => {
    mockDetail({ status: "LLM_FAILED" }, null);
    render(<AdminEssaySubmissionDetailPage />);
    await waitFor(() => expect(screen.getByRole("button", { name: /Override Score/ })).toBeInTheDocument());
  });

  it("hides the Override Score button when not LLM_FAILED", async () => {
    mockDetail({ status: "LLM_COMPLETE" });
    render(<AdminEssaySubmissionDetailPage />);
    await waitFor(() => expect(screen.getByText("Argue for or against remote work.")).toBeInTheDocument());
    expect(screen.queryByRole("button", { name: /Override Score/ })).not.toBeInTheDocument();
  });

  it("submits a valid override with score, feedback, and reason", async () => {
    mockDetail({ status: "LLM_FAILED", score: null, feedback: null, evaluated_by: null }, null);
    jest.spyOn(api, "post").mockResolvedValue({
      data: { data: { ...BASE_SUBMISSION, status: "LLM_COMPLETE", score: 7, evaluated_by: "admin" } },
    } as any);
    const user = userEvent.setup({ delay: null });
    render(<AdminEssaySubmissionDetailPage />);
    await waitFor(() => expect(screen.getByRole("button", { name: /Override Score/ })).toBeInTheDocument());

    await user.click(screen.getByRole("button", { name: /Override Score/ }));
    await user.type(screen.getByLabelText("Score (0–10)"), "7");
    await user.type(screen.getByPlaceholderText("Overall feedback for the student."), "Solid essay, scored manually.");
    await user.type(screen.getByPlaceholderText("Why is a manual override needed here?"), "LLM rejected 3 times.");
    await user.click(screen.getByRole("button", { name: "Save Override" }));

    await waitFor(() => expect(api.post).toHaveBeenCalledWith(
      "/essay/admin/submissions/sub-1/override-score/",
      { score: 7, feedback: { overall: "Solid essay, scored manually." }, reason: "LLM rejected 3 times." },
    ));
  });

  it("rejects an out-of-range score client-side before submitting", async () => {
    mockDetail({ status: "LLM_FAILED", score: null, feedback: null, evaluated_by: null }, null);
    jest.spyOn(api, "post").mockResolvedValue({ data: { success: true } } as any);
    const user = userEvent.setup({ delay: null });
    render(<AdminEssaySubmissionDetailPage />);
    await waitFor(() => expect(screen.getByRole("button", { name: /Override Score/ })).toBeInTheDocument());

    await user.click(screen.getByRole("button", { name: /Override Score/ }));
    await user.type(screen.getByLabelText("Score (0–10)"), "11");
    await user.type(screen.getByPlaceholderText("Overall feedback for the student."), "x");
    await user.type(screen.getByPlaceholderText("Why is a manual override needed here?"), "x");
    await user.click(screen.getByRole("button", { name: "Save Override" }));

    expect(mockToastError).toHaveBeenCalledWith("Score must be a whole number between 0 and 10.");
    expect(api.post).not.toHaveBeenCalled();
  });

  it("rejects a missing reason client-side before submitting", async () => {
    mockDetail({ status: "LLM_FAILED", score: null, feedback: null, evaluated_by: null }, null);
    jest.spyOn(api, "post").mockResolvedValue({ data: { success: true } } as any);
    const user = userEvent.setup({ delay: null });
    render(<AdminEssaySubmissionDetailPage />);
    await waitFor(() => expect(screen.getByRole("button", { name: /Override Score/ })).toBeInTheDocument());

    await user.click(screen.getByRole("button", { name: /Override Score/ }));
    await user.type(screen.getByLabelText("Score (0–10)"), "7");
    await user.type(screen.getByPlaceholderText("Overall feedback for the student."), "x");
    await user.click(screen.getByRole("button", { name: "Save Override" }));

    expect(mockToastError).toHaveBeenCalledWith("A reason is required to override a score.");
    expect(api.post).not.toHaveBeenCalled();
  });
});

describe("Submission detail page — Per-criterion feedback breakdown (Phase 8)", () => {
  it("renders the rubric breakdown when the score's feedback includes one", async () => {
    mockDetail({
      feedback: {
        overall: "Well argued, clear structure.",
        breakdown: { Clarity: { score: 4, maxScore: 5, feedback: "Mostly clear." }, Argument: { score: 5, maxScore: 5, feedback: "Strong thesis." } },
      },
    });
    render(<AdminEssaySubmissionDetailPage />);
    await waitFor(() => expect(screen.getByText("Argue for or against remote work.")).toBeInTheDocument());

    expect(screen.getByText("Breakdown")).toBeInTheDocument();
    expect(screen.getByText("Clarity")).toBeInTheDocument();
    expect(screen.getByText("4/5")).toBeInTheDocument();
    expect(screen.getByText("5/5")).toBeInTheDocument();
    expect(screen.getByText("Mostly clear.")).toBeInTheDocument();
  });

  it("does not render a breakdown section when the feedback has none", async () => {
    mockDetail();
    render(<AdminEssaySubmissionDetailPage />);
    await waitFor(() => expect(screen.getByText("Argue for or against remote work.")).toBeInTheDocument());
    expect(screen.queryByText("Breakdown")).not.toBeInTheDocument();
  });
});

describe("Submission detail page — General score override (Phase 8)", () => {
  it("shows the Correct Score button once a score exists", async () => {
    mockDetail(); // BASE_SUBMISSION already has score: 8
    render(<AdminEssaySubmissionDetailPage />);
    await waitFor(() => expect(screen.getByRole("button", { name: /Correct Score/ })).toBeInTheDocument());
  });

  it("hides the Correct Score button when there is no score yet", async () => {
    mockDetail({ status: "LLM_FAILED", score: null, feedback: null, evaluated_by: null }, null);
    render(<AdminEssaySubmissionDetailPage />);
    await waitFor(() => expect(screen.getByText("Argue for or against remote work.")).toBeInTheDocument());
    expect(screen.queryByRole("button", { name: /Correct Score/ })).not.toBeInTheDocument();
  });

  it("never shows both override buttons at once (mutually exclusive by construction)", async () => {
    // LLM_FAILED never has a score, per the pipeline's own status machine
    // — so the DLQ-recovery button and the general-correction button
    // should never both be visible for the same submission.
    mockDetail({ status: "LLM_FAILED", score: null, feedback: null, evaluated_by: null }, null);
    render(<AdminEssaySubmissionDetailPage />);
    await waitFor(() => expect(screen.getByRole("button", { name: /Override Score/ })).toBeInTheDocument());
    expect(screen.queryByRole("button", { name: /Correct Score/ })).not.toBeInTheDocument();
  });

  it("submits a valid general override with score, feedback, and reason", async () => {
    mockDetail(); // score: 8
    jest.spyOn(api, "post").mockResolvedValue({
      data: { data: { ...BASE_SUBMISSION, score: 9, evaluated_by: "admin" } },
    } as any);
    const user = userEvent.setup({ delay: null });
    render(<AdminEssaySubmissionDetailPage />);
    await waitFor(() => expect(screen.getByRole("button", { name: /Correct Score/ })).toBeInTheDocument());

    await user.click(screen.getByRole("button", { name: /Correct Score/ }));
    await user.type(screen.getByLabelText("New score (0–10)"), "9");
    await user.type(screen.getByPlaceholderText("Overall feedback for the student."), "Regraded after appeal.");
    await user.type(screen.getByPlaceholderText("Why is this score being corrected?"), "Student appeal, ticket #42.");
    await user.click(screen.getByRole("button", { name: "Save Correction" }));

    await waitFor(() => expect(api.post).toHaveBeenCalledWith(
      "/essay/admin/submissions/sub-1/general-override-score/",
      { score: 9, feedback: { overall: "Regraded after appeal." }, reason: "Student appeal, ticket #42." },
    ));
    await waitFor(() => expect(mockToastSuccess).toHaveBeenCalled());
  });

  it("rejects a reason over 500 characters client-side before submitting", async () => {
    mockDetail();
    jest.spyOn(api, "post").mockResolvedValue({ data: { success: true } } as any);
    const user = userEvent.setup({ delay: null });
    render(<AdminEssaySubmissionDetailPage />);
    await waitFor(() => expect(screen.getByRole("button", { name: /Correct Score/ })).toBeInTheDocument());

    await user.click(screen.getByRole("button", { name: /Correct Score/ }));
    await user.type(screen.getByLabelText("New score (0–10)"), "9");
    await user.type(screen.getByPlaceholderText("Overall feedback for the student."), "x");
    // fireEvent.change, not user.type — userEvent simulates one keystroke
    // per character, which for a 501-character string reliably exceeds
    // this test's default timeout; a bulk value-set is what the reason
    // field's own onChange handler needs to see, not a real per-key
    // interaction sequence.
    fireEvent.change(screen.getByPlaceholderText("Why is this score being corrected?"), { target: { value: "x".repeat(501) } });
    await user.click(screen.getByRole("button", { name: "Save Correction" }));

    expect(mockToastError).toHaveBeenCalledWith("Reason must be 500 characters or fewer.");
    expect(api.post).not.toHaveBeenCalled();
  });

  it("rejects a missing reason client-side before submitting", async () => {
    mockDetail();
    jest.spyOn(api, "post").mockResolvedValue({ data: { success: true } } as any);
    const user = userEvent.setup({ delay: null });
    render(<AdminEssaySubmissionDetailPage />);
    await waitFor(() => expect(screen.getByRole("button", { name: /Correct Score/ })).toBeInTheDocument());

    await user.click(screen.getByRole("button", { name: /Correct Score/ }));
    await user.type(screen.getByLabelText("New score (0–10)"), "9");
    await user.type(screen.getByPlaceholderText("Overall feedback for the student."), "x");
    await user.click(screen.getByRole("button", { name: "Save Correction" }));

    expect(mockToastError).toHaveBeenCalledWith("A reason is required to override a score.");
    expect(api.post).not.toHaveBeenCalled();
  });
});
