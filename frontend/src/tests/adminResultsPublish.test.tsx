/**
 * @jest-environment jsdom
 *
 * Coverage for the "Publish Results" action on the admin results detail
 * page — for an assignment created with show_result_to_student=false, lets
 * the admin make results visible to students afterward.
 */

jest.mock("next/navigation", () => ({
  useParams: () => ({ assignment_id: "11111111-1111-1111-1111-111111111111" }),
  useRouter: () => ({ push: jest.fn() }),
  useSearchParams: () => new URLSearchParams(),
}));

jest.mock("@/components/layout/AdminLayout", () => ({
  AdminLayout: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}));

const mockToastSuccess = jest.fn();
const mockToastError = jest.fn();
jest.mock("@/components/ui/Toast", () => ({
  useToast: () => ({ error: mockToastError, success: mockToastSuccess }),
}));

jest.mock("@/lib/departmentsContext", () => ({
  useDepartments: () => ({ departments: [], activeDepartments: [], loading: false, error: "", refetch: jest.fn() }),
}));

import React from "react";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import api from "@/lib/api";
import AdminAssessmentResultsPage from "@/app/admin/assessments/results/[assignment_id]/page";

const HIDDEN_ASSIGNMENT = {
  data: {
    data: {
      id: "11111111-1111-1111-1111-111111111111",
      paper_title: "Midterm Paper",
      status: "CLOSED",
      pass_cutoff_percentage: 40,
      show_result_to_student: false,
      results_published_at: null,
    },
  },
};

const PUBLISHED_ASSIGNMENT = {
  data: {
    data: {
      ...HIDDEN_ASSIGNMENT.data.data,
      show_result_to_student: true,
      results_published_at: "2026-11-12T10:00:00Z",
    },
  },
};

function emptyResultsResponse() {
  return { data: { count: 0, total_pages: 1, current_page: 1, results: [], available_sets: [] } };
}

function mockApiFor(assignmentResponse: any) {
  jest.spyOn(api, "get").mockImplementation((url: string) => {
    if (url.includes("/results/export/")) return Promise.resolve({ data: new Blob() } as any);
    if (url.includes("/results/")) return Promise.resolve(emptyResultsResponse() as any);
    return Promise.resolve(assignmentResponse as any);
  });
}

beforeEach(() => {
  mockToastSuccess.mockClear();
  mockToastError.mockClear();
});

afterEach(() => {
  jest.restoreAllMocks();
});

describe("Admin results page — Publish Results", () => {
  it("shows a Publish Results button when results are hidden", async () => {
    mockApiFor(HIDDEN_ASSIGNMENT);
    render(<AdminAssessmentResultsPage />);
    await waitFor(() => expect(screen.getByRole("button", { name: /publish results/i })).toBeInTheDocument());
    expect(screen.queryByText(/results visible to students/i)).not.toBeInTheDocument();
  });

  it("shows a read-only badge instead of a button once results are already visible", async () => {
    mockApiFor(PUBLISHED_ASSIGNMENT);
    render(<AdminAssessmentResultsPage />);
    await waitFor(() => expect(screen.getByText(/results visible to students/i)).toBeInTheDocument());
    expect(screen.queryByRole("button", { name: /publish results/i })).not.toBeInTheDocument();
  });

  it("requires confirmation before publishing, then calls the publish endpoint", async () => {
    mockApiFor(HIDDEN_ASSIGNMENT);
    const patchSpy = jest.spyOn(api, "patch").mockResolvedValue(PUBLISHED_ASSIGNMENT as any);
    const user = userEvent.setup();

    render(<AdminAssessmentResultsPage />);
    await waitFor(() => expect(screen.getByRole("button", { name: /publish results/i })).toBeInTheDocument());

    await user.click(screen.getByRole("button", { name: /publish results/i }));
    // Confirmation modal — the action must not fire on the first click alone.
    expect(patchSpy).not.toHaveBeenCalled();
    const dialog = screen.getByRole("dialog");
    expect(within(dialog).getByText(/publish results to students\?/i)).toBeInTheDocument();

    await user.click(within(dialog).getByRole("button", { name: /^publish results$/i }));
    await waitFor(() =>
      expect(patchSpy).toHaveBeenCalledWith(
        "/assessments/admin/assignments/11111111-1111-1111-1111-111111111111/publish-results/",
      ),
    );
    await waitFor(() => expect(mockToastSuccess).toHaveBeenCalled());
    // Button is replaced by the visible badge once the response lands.
    await waitFor(() => expect(screen.getByText(/results visible to students/i)).toBeInTheDocument());
  });

  it("cancelling the confirmation modal does not call the publish endpoint", async () => {
    mockApiFor(HIDDEN_ASSIGNMENT);
    const patchSpy = jest.spyOn(api, "patch");
    const user = userEvent.setup();

    render(<AdminAssessmentResultsPage />);
    await waitFor(() => expect(screen.getByRole("button", { name: /publish results/i })).toBeInTheDocument());
    await user.click(screen.getByRole("button", { name: /publish results/i }));
    await user.click(screen.getByRole("button", { name: /cancel/i }));

    expect(patchSpy).not.toHaveBeenCalled();
    expect(screen.queryByText(/publish results to students\?/i)).not.toBeInTheDocument();
  });

  it("shows an error toast and keeps the button if publishing fails", async () => {
    mockApiFor(HIDDEN_ASSIGNMENT);
    jest.spyOn(api, "patch").mockRejectedValue({ response: { data: { message: "Server error" } } });
    const user = userEvent.setup();

    render(<AdminAssessmentResultsPage />);
    await waitFor(() => expect(screen.getByRole("button", { name: /publish results/i })).toBeInTheDocument());
    await user.click(screen.getByRole("button", { name: /publish results/i }));
    const dialog = screen.getByRole("dialog");
    await user.click(within(dialog).getByRole("button", { name: /^publish results$/i }));

    await waitFor(() => expect(mockToastError).toHaveBeenCalled());
    // Modal deliberately stays open on failure (only closes on success) so
    // the admin can see the error and retry without re-opening it.
    expect(screen.getByRole("dialog")).toBeInTheDocument();
  });
});
