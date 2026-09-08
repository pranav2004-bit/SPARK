/**
 * @jest-environment jsdom
 *
 * Coverage for the "Real tests / Mock tests" toggle added to the admin
 * Results page (2026-08-27): mock attempts are the admin's own dry runs on
 * this assignment's paper (see the admin mock-test feature), deliberately
 * paper-scoped rather than assignment-scoped, and must never mix with the
 * real, assignment-scoped student results table that's the page's default
 * view.
 */

const mockPush = jest.fn();
const mockSearchParams = new URLSearchParams();
jest.mock("next/navigation", () => ({
  useParams: () => ({ assignment_id: "assign-1" }),
  useRouter: () => ({ push: mockPush }),
  useSearchParams: () => mockSearchParams,
}));

jest.mock("@/components/layout/AdminLayout", () => ({
  AdminLayout: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}));

const mockToastError = jest.fn();
jest.mock("@/components/ui/Toast", () => ({
  useToast: () => ({ error: mockToastError, success: jest.fn() }),
}));

jest.mock("@/lib/departmentsContext", () => ({
  useDepartments: () => ({ departments: [], activeDepartments: [], loading: false, error: "", refetch: jest.fn() }),
}));

import React from "react";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import api from "@/lib/api";
import AdminAssessmentResultsPage from "@/app/admin/assessments/results/[assignment_id]/page";

const ASSIGNMENT_RESPONSE = {
  data: { data: { id: "assign-1", paper: "paper-1", paper_title: "Midterm Paper", status: "CLOSED", pass_cutoff_percentage: 40 } },
};

const REAL_RESULTS_RESPONSE = {
  data: {
    count: 1, total_pages: 1, current_page: 1, available_sets: ["Set A"],
    results: [{
      result_id: "res-1", session_id: "sess-1", student_user_id: "stu-1",
      student_roll_id: "ROLL-001", student_name: "Alice A", department: "CSE",
      set_label: "Set A", exam_status: "submitted", started_at: null, ended_at: null,
      duration_seconds: 1200, score: 5, total_marks: 5, percentage: 100, malpractice_flag: false,
    }],
  },
};

const MOCK_RESULTS_RESPONSE = {
  data: {
    data: [{
      id: "trial-res-1", set_label: "Set A", score: 8, total_marks: 10, percentage: 80,
      duration_seconds: 300, ended_at: "2026-08-27T09:00:00Z",
      attempted_by_name: "Lohit Admin", attempted_by_email: "lohit@example.com",
    }],
  },
};

function mockApiFor({ real = REAL_RESULTS_RESPONSE, mock = MOCK_RESULTS_RESPONSE }: { real?: any; mock?: any } = {}) {
  return jest.spyOn(api, "get").mockImplementation((url: string) => {
    if (url.includes("/trial-results/")) {
      return mock instanceof Error ? Promise.reject(mock) : Promise.resolve(mock as any);
    }
    if (url.includes("/results/")) return Promise.resolve(real as any);
    return Promise.resolve(ASSIGNMENT_RESPONSE as any);
  });
}

beforeEach(() => {
  mockPush.mockClear();
  mockToastError.mockClear();
});

afterEach(() => {
  jest.restoreAllMocks();
});

describe("Admin Results page — Real / Mock toggle", () => {
  it("defaults to Real tests and shows the real student row", async () => {
    mockApiFor();
    render(<AdminAssessmentResultsPage />);

    expect(await screen.findByText("Alice A")).toBeInTheDocument();
    expect(screen.queryByText("Lohit Admin")).not.toBeInTheDocument();
  });

  it("switching to Mock tests fetches paper-scoped trial results and hides the real table", async () => {
    mockApiFor();
    const user = userEvent.setup();
    render(<AdminAssessmentResultsPage />);
    await screen.findByText("Alice A");

    await user.click(screen.getByRole("button", { name: "Mock tests" }));

    expect(await screen.findByText("Lohit Admin")).toBeInTheDocument();
    expect(screen.getByText("8/10")).toBeInTheDocument();
    expect(screen.getByText("80%")).toBeInTheDocument();
    expect(screen.queryByText("Alice A")).not.toBeInTheDocument();
    await waitFor(() => expect(api.get).toHaveBeenCalledWith("/assessments/admin/papers/paper-1/trial-results/"));
  });

  it("shows an empty state on the Mock tab when there are no trial attempts", async () => {
    mockApiFor({ mock: { data: { data: [] } } });
    const user = userEvent.setup();
    render(<AdminAssessmentResultsPage />);
    await screen.findByText("Alice A");

    await user.click(screen.getByRole("button", { name: "Mock tests" }));

    expect(await screen.findByText("No mock test attempts yet")).toBeInTheDocument();
  });

  it("shows a retry option if the trial-results fetch fails", async () => {
    mockApiFor({ mock: new Error("boom") });
    const user = userEvent.setup();
    render(<AdminAssessmentResultsPage />);
    await screen.findByText("Alice A");

    await user.click(screen.getByRole("button", { name: "Mock tests" }));

    expect(await screen.findByText("Couldn't load mock test attempts")).toBeInTheDocument();
  });

  it("switching back to Real tests still shows the real table untouched", async () => {
    mockApiFor();
    const user = userEvent.setup();
    render(<AdminAssessmentResultsPage />);
    await screen.findByText("Alice A");

    await user.click(screen.getByRole("button", { name: "Mock tests" }));
    await screen.findByText("Lohit Admin");
    await user.click(screen.getByRole("button", { name: "Real tests" }));

    expect(await screen.findByText("Alice A")).toBeInTheDocument();
    expect(screen.queryByText("Lohit Admin")).not.toBeInTheDocument();
  });
});
