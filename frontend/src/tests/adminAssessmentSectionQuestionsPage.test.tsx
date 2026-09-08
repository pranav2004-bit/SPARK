/**
 * @jest-environment jsdom
 *
 * Regression test for the Section → Questions page (frontend/src/app/admin/
 * assessments/papers/[paper_id]/sets/[set_id]/sections/[section_id]/
 * page.tsx) — the question-editing UI moved here from the old set-level
 * page, now scoped to one section. Covers the list render, empty state,
 * breadcrumb showing paper → set, opening the "New Question" editor, and
 * the delete-question flow. The QuestionEditorModal's own deep internals
 * (image upload, pending options, mcq-type switching) are exercised
 * indirectly through the original page's long history and aren't
 * re-asserted line-by-line here — this file's job is the section-scoped
 * page shell around it.
 */

const mockPush = jest.fn();
jest.mock("next/navigation", () => ({
  useParams: () => ({ paper_id: "paper-1", set_id: "set-1", section_id: "sec-1" }),
  useRouter: () => ({ push: mockPush }),
}));

jest.mock("@/components/layout/AdminLayout", () => ({
  AdminLayout: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}));

const mockToastSuccess = jest.fn();
const mockToastError = jest.fn();
jest.mock("@/components/ui/Toast", () => ({
  useToast: () => ({ success: mockToastSuccess, error: mockToastError }),
}));

import React from "react";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import api from "@/lib/api";
import AdminAssessmentSectionPage from "@/app/admin/assessments/papers/[paper_id]/sets/[set_id]/sections/[section_id]/page";

const SECTION_DETAIL_RESPONSE = {
  data: {
    data: {
      section: { id: "sec-1", set: "set-1", title: "Quantitative Aptitude", order: 1, question_count: 1 },
      set: { id: "set-1", paper: "paper-1", label: "Set A", order: 1, question_count: 1, total_marks: 2 },
      paper: { id: "paper-1", title: "Demo Paper" },
      questions: [
        {
          id: "q-1", set: "set-1", section: "sec-1", question_number: 1, question_type: "mcq",
          mcq_type: "single", question_content_type: "text", question_text: "2 + 2 = ?",
          question_image_key: "", question_image_url: null, question_image_size_bytes: null,
          marks: 2, created_at: "2026-01-01T00:00:00Z", updated_at: "2026-01-01T00:00:00Z",
        },
      ],
    },
  },
};

beforeEach(() => {
  mockPush.mockClear();
  mockToastSuccess.mockClear();
  mockToastError.mockClear();
});

afterEach(() => {
  jest.restoreAllMocks();
});

describe("Admin Section Questions page", () => {
  it("renders the section title as the heading and lists its questions", async () => {
    jest.spyOn(api, "get").mockResolvedValue(SECTION_DETAIL_RESPONSE as any);
    render(<AdminAssessmentSectionPage />);

    expect(await screen.findByRole("heading", { name: "Quantitative Aptitude" })).toBeInTheDocument();
    expect(screen.getByText("2 + 2 = ?")).toBeInTheDocument();
    expect(screen.getByText("Q1")).toBeInTheDocument();
  });

  it("subtitle shows the paper title and set label for context", async () => {
    jest.spyOn(api, "get").mockResolvedValue(SECTION_DETAIL_RESPONSE as any);
    render(<AdminAssessmentSectionPage />);

    expect(await screen.findByText(/Demo Paper.*Set A.*1 question/)).toBeInTheDocument();
  });

  it("shows an empty state when the section has no questions yet", async () => {
    jest.spyOn(api, "get").mockResolvedValue({
      data: { data: { ...SECTION_DETAIL_RESPONSE.data.data, questions: [] } },
    } as any);
    render(<AdminAssessmentSectionPage />);

    expect(await screen.findByText("No questions yet")).toBeInTheDocument();
  });

  it("clicking + Add Question opens the question editor modal", async () => {
    jest.spyOn(api, "get").mockResolvedValue(SECTION_DETAIL_RESPONSE as any);
    const user = userEvent.setup();
    render(<AdminAssessmentSectionPage />);

    await screen.findByText("2 + 2 = ?");
    await user.click(screen.getByRole("button", { name: "+ Add Question" }));

    expect(await screen.findByRole("heading", { name: "New Question" })).toBeInTheDocument();
  });

  it("deletes a question on confirm and removes it from the list", async () => {
    jest.spyOn(api, "get").mockResolvedValue(SECTION_DETAIL_RESPONSE as any);
    jest.spyOn(api, "delete").mockResolvedValue({} as any);
    const user = userEvent.setup();
    render(<AdminAssessmentSectionPage />);

    await screen.findByText("2 + 2 = ?");
    await user.click(screen.getByLabelText("Delete"));
    // The row's icon-only Delete button (aria-label="Delete") and the
    // ConfirmDialog's own "Delete" button share the same accessible name
    // once the dialog opens — the dialog's is the one rendered last.
    const deleteButtons = screen.getAllByRole("button", { name: "Delete" });
    await user.click(deleteButtons[deleteButtons.length - 1]);

    await waitFor(() => expect(api.delete).toHaveBeenCalledWith("/assessments/admin/questions/q-1/"));
    await waitFor(() => expect(screen.queryByText("2 + 2 = ?")).not.toBeInTheDocument());
  });

  it("navigates back to the set's sections list (not the paper page) if the section fails to load", async () => {
    jest.spyOn(api, "get").mockRejectedValue(new Error("boom"));
    render(<AdminAssessmentSectionPage />);

    await waitFor(() => expect(mockPush).toHaveBeenCalledWith("/admin/assessments/papers/paper-1/sets/set-1"));
  });
});
