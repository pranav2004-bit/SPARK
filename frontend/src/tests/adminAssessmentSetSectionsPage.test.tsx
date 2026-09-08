/**
 * @jest-environment jsdom
 *
 * Regression test for the Set → Sections page (frontend/src/app/admin/
 * assessments/papers/[paper_id]/sets/[set_id]/page.tsx). This page used to
 * show the set's questions directly with a "+ Add Question" button; it now
 * shows a grid of section cards with a "+ Section" button, and clicking a
 * card opens that section's own question list on a separate page. Covers
 * the list render, empty state, create flow, navigation on card click, and
 * the delete flow (including the question-count-aware confirmation
 * message).
 */

const mockPush = jest.fn();
jest.mock("next/navigation", () => ({
  useParams: () => ({ paper_id: "paper-1", set_id: "set-1" }),
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
import AdminAssessmentSetSectionsPage from "@/app/admin/assessments/papers/[paper_id]/sets/[set_id]/page";

const SET_SECTIONS_RESPONSE = {
  data: {
    data: {
      set: { id: "set-1", paper: "paper-1", label: "Set A", order: 1, question_count: 3, total_marks: 3 },
      paper: { id: "paper-1", title: "Demo Paper" },
      sections: [
        { id: "sec-1", set: "set-1", title: "Quantitative Aptitude", order: 1, question_count: 2 },
        { id: "sec-2", set: "set-1", title: "Logical Reasoning", order: 2, question_count: 1 },
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

describe("Admin Set Sections page", () => {
  it("renders each section card with its title and question count", async () => {
    jest.spyOn(api, "get").mockResolvedValue(SET_SECTIONS_RESPONSE as any);
    render(<AdminAssessmentSetSectionsPage />);

    expect(await screen.findByText("Quantitative Aptitude")).toBeInTheDocument();
    expect(screen.getByText("2 questions")).toBeInTheDocument();
    expect(screen.getByText("Logical Reasoning")).toBeInTheDocument();
    expect(screen.getByText("1 question")).toBeInTheDocument();
  });

  it("shows an empty state when the set has no sections yet", async () => {
    jest.spyOn(api, "get").mockResolvedValue({
      data: { data: { ...SET_SECTIONS_RESPONSE.data.data, sections: [] } },
    } as any);
    render(<AdminAssessmentSetSectionsPage />);

    expect(await screen.findByText("No sections yet")).toBeInTheDocument();
  });

  it("navigates to the section's question list when a card is clicked", async () => {
    jest.spyOn(api, "get").mockResolvedValue(SET_SECTIONS_RESPONSE as any);
    const user = userEvent.setup();
    render(<AdminAssessmentSetSectionsPage />);

    await user.click(await screen.findByText("Quantitative Aptitude"));
    expect(mockPush).toHaveBeenCalledWith("/admin/assessments/papers/paper-1/sets/set-1/sections/sec-1");
  });

  it("creates a new section and adds it to the list", async () => {
    jest.spyOn(api, "get").mockResolvedValue(SET_SECTIONS_RESPONSE as any);
    jest.spyOn(api, "post").mockResolvedValue({
      data: { data: { id: "sec-3", set: "set-1", title: "Verbal Ability", order: 3, question_count: 0 } },
    } as any);
    const user = userEvent.setup();
    render(<AdminAssessmentSetSectionsPage />);

    await user.click(await screen.findByRole("button", { name: "+ Section" }));
    await user.type(screen.getByPlaceholderText(/Quantitative Aptitude/), "Verbal Ability");
    await user.click(screen.getByRole("button", { name: "Create Section" }));

    await waitFor(() => expect(api.post).toHaveBeenCalledWith(
      "/assessments/admin/sets/set-1/sections/",
      { title: "Verbal Ability" },
    ));
    expect(await screen.findByText("Verbal Ability")).toBeInTheDocument();
  });

  it("delete confirmation states how many questions will be removed with the section", async () => {
    jest.spyOn(api, "get").mockResolvedValue(SET_SECTIONS_RESPONSE as any);
    const user = userEvent.setup();
    render(<AdminAssessmentSetSectionsPage />);

    await screen.findByText("Quantitative Aptitude");
    await user.click(screen.getAllByLabelText("Delete section")[0]);

    expect(await screen.findByText(/Quantitative Aptitude.*and its 2 questions will be permanently removed/)).toBeInTheDocument();
  });

  it("deletes a section on confirm and removes it from the list", async () => {
    jest.spyOn(api, "get").mockResolvedValue(SET_SECTIONS_RESPONSE as any);
    jest.spyOn(api, "delete").mockResolvedValue({} as any);
    const user = userEvent.setup();
    render(<AdminAssessmentSetSectionsPage />);

    await screen.findByText("Quantitative Aptitude");
    await user.click(screen.getAllByLabelText("Delete section")[0]);
    await user.click(screen.getByRole("button", { name: "Delete" }));

    await waitFor(() => expect(api.delete).toHaveBeenCalledWith("/assessments/admin/sections/sec-1/"));
    await waitFor(() => expect(screen.queryByText("Quantitative Aptitude")).not.toBeInTheDocument());
  });
});
