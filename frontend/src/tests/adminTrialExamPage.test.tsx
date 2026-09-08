/**
 * @jest-environment jsdom
 *
 * Coverage for the admin mock-test exam-taking page (frontend/src/app/
 * admin/assessments/trial/[session_id]/page.tsx) — a fork of the real
 * student exam page (which has no dedicated test file of its own in this
 * codebase) with all anti-cheat/fullscreen machinery deliberately removed.
 * Scoped to the core flow this page exists for: load questions, select an
 * answer, submit, see the score — not a line-by-line re-verification of
 * the student page's own already-covered-elsewhere UI details.
 */

const mockPush = jest.fn();
jest.mock("next/navigation", () => ({
  useParams: () => ({ session_id: "trial-sess-1" }),
  useRouter: () => ({ push: mockPush }),
}));

jest.mock("@/components/layout/AdminLayout", () => ({
  AdminLayout: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}));

const mockToastError = jest.fn();
jest.mock("@/components/ui/Toast", () => ({
  useToast: () => ({ error: mockToastError, success: jest.fn() }),
}));

// useServerTimeSync polls on an interval — mocked to a fixed, non-expiring
// value so this file doesn't need fake timers just to render the page.
jest.mock("@/hooks/useServerTimeSync", () => ({
  useServerTimeSync: () => ({ secondsRemaining: 1800, isSyncFailing: false, lastExtension: null }),
}));

import React from "react";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import api from "@/lib/api";
import AdminTrialExamPage from "@/app/admin/assessments/trial/[session_id]/page";

const QUESTIONS_RESPONSE = {
  data: {
    data: {
      session_id: "trial-sess-1",
      session_status: "IN_PROGRESS",
      ends_at: "2026-09-01T11:00:00Z",
      questions: [
        {
          id: "q-1", question_number: 1, mcq_type: "single", question_content_type: "text",
          question_text: "2 + 2 = ?", question_image_url: null, marks: 2,
          section_id: "sec-1", section_title: "Section 1",
          options: [
            { id: "opt-a", label: "A", content_type: "text", text: "3", image_key: "", image_url: null, order: 1 },
            { id: "opt-b", label: "B", content_type: "text", text: "4", image_key: "", image_url: null, order: 2 },
          ],
          selected_option_ids: [],
        },
      ],
    },
  },
};

beforeEach(() => {
  mockPush.mockClear();
  mockToastError.mockClear();
});

afterEach(() => {
  jest.restoreAllMocks();
});

describe("Admin trial exam page", () => {
  it("loads the trial session's questions and renders the first one", async () => {
    jest.spyOn(api, "get").mockResolvedValue(QUESTIONS_RESPONSE as any);
    render(<AdminTrialExamPage />);

    expect(await screen.findByText("2 + 2 = ?")).toBeInTheDocument();
    expect(screen.getByText(/Mock test/)).toBeInTheDocument();
    expect(screen.getByText("0/1 answered")).toBeInTheDocument();
  });

  it("selecting an option saves the answer via the trial answer endpoint", async () => {
    jest.spyOn(api, "get").mockResolvedValue(QUESTIONS_RESPONSE as any);
    jest.spyOn(api, "put").mockResolvedValue({ data: { data: {} } } as any);
    const user = userEvent.setup();
    render(<AdminTrialExamPage />);

    await screen.findByText("2 + 2 = ?");
    await user.click(screen.getByText("4"));

    await waitFor(() => expect(api.put).toHaveBeenCalledWith(
      "/assessments/admin/trial/sessions/trial-sess-1/questions/q-1/answer/",
      { selected_option_ids: ["opt-b"] },
    ));
    expect(await screen.findByText("1/1 answered")).toBeInTheDocument();
  });

  it("submitting shows the score unconditionally, no results-visibility gate", async () => {
    jest.spyOn(api, "get").mockResolvedValue(QUESTIONS_RESPONSE as any);
    jest.spyOn(api, "post").mockResolvedValue({
      data: { data: { session_id: "trial-sess-1", status: "SUBMITTED", score: 2, total_marks: 2 } },
    } as any);
    const user = userEvent.setup();
    render(<AdminTrialExamPage />);

    await screen.findByText("2 + 2 = ?");
    await user.click(screen.getByRole("button", { name: "Submit Mock Test" }));
    await user.click(screen.getByRole("button", { name: "Submit" }));

    expect(await screen.findByText("Mock test submitted")).toBeInTheDocument();
    expect(screen.getByText((_, node) => node?.textContent === "You scored 2 out of 2.")).toBeInTheDocument();
  });

  it("redirects to Assessments if the trial session fails to load", async () => {
    jest.spyOn(api, "get").mockRejectedValue(new Error("boom"));
    render(<AdminTrialExamPage />);

    await waitFor(() => expect(mockPush).toHaveBeenCalledWith("/admin/assessments"));
  });
});
