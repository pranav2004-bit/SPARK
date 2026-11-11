/**
 * @jest-environment jsdom
 *
 * Essay Writing — Assessments Assigning page (Phase 3, essay-service).
 * Single-step create form (unlike assessment-service's multi-step wizard —
 * essay-service's EssayAssignment has no exam_duration_minutes/pass_cutoff
 * to configure). Covers load states, create, and the start/close/resync
 * lifecycle actions.
 */

const mockPush = jest.fn();
jest.mock("next/navigation", () => ({
  useRouter: () => ({ push: mockPush }),
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
import AdminEssayAssignPage from "@/app/admin/essay-writing/assign/page";
import type { EssayAssignment, PaginatedResponse } from "@/types";

type AssignmentsResponse = { data: PaginatedResponse<EssayAssignment> };

const PAPERS_RESPONSE = {
  data: {
    count: 1, total_pages: 1, current_page: 1, next: null, previous: null,
    results: [{ id: "paper-1", title: "Persuasive Writing", description: "", set_count: 2, created_by: "u1", created_at: "t", updated_at: "t" }],
  },
};

const BATCHES_RESPONSE = {
  data: { success: true, data: [{ id: "batch-1", batch_name: "CSE 2026", created_at: "t", updated_at: "t" }] },
};

const ASSIGNMENTS_EMPTY: AssignmentsResponse = {
  data: { count: 0, total_pages: 1, current_page: 1, next: null, previous: null, results: [] },
};

function mockOptionsAndAssignments(assignmentsResponse: AssignmentsResponse = ASSIGNMENTS_EMPTY) {
  jest.spyOn(api, "get").mockImplementation((url: string) => {
    if (url === "/essay/admin/papers/") return Promise.resolve(PAPERS_RESPONSE as any);
    if (url === "/users/batches/") return Promise.resolve(BATCHES_RESPONSE as any);
    if (url === "/essay/admin/assignments/") return Promise.resolve(assignmentsResponse as any);
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

describe("Assign page — load states", () => {
  it("shows the empty state when there are no assignments", async () => {
    mockOptionsAndAssignments();
    render(<AdminEssayAssignPage />);
    await waitFor(() => expect(screen.getByText(/No assignments yet/)).toBeInTheDocument());
  });

  it("shows an error state when assignments fail to load", async () => {
    jest.spyOn(api, "get").mockImplementation((url: string) => {
      if (url === "/essay/admin/papers/") return Promise.resolve(PAPERS_RESPONSE as any);
      if (url === "/users/batches/") return Promise.resolve(BATCHES_RESPONSE as any);
      if (url === "/essay/admin/assignments/") return Promise.reject(new Error("network error"));
      return Promise.reject(new Error("unexpected"));
    });
    render(<AdminEssayAssignPage />);
    await waitFor(() => expect(screen.getByText(/Couldn't load assignments/)).toBeInTheDocument());
  });
});

describe("Assign page — create flow", () => {
  it("creates an assignment via the form", async () => {
    mockOptionsAndAssignments();
    const postSpy = jest.spyOn(api, "post").mockResolvedValue({
      data: {
        data: {
          id: "assign-1", paper: "paper-1", paper_title: "Persuasive Writing",
          batch_id: "batch-1", institution_id: "inst-1", global_start_time: null,
          global_expire_time: "2027-01-01T00:00:00Z", departments: [], status: "SCHEDULED",
          created_by: "u1", created_at: "t", updated_at: "t",
        },
      },
    } as any);
    const user = userEvent.setup();

    render(<AdminEssayAssignPage />);
    await waitFor(() => expect(screen.getByText(/No assignments yet/)).toBeInTheDocument());

    await user.click(screen.getByRole("button", { name: /New Assignment/ }));
    await user.selectOptions(screen.getByLabelText("Essay paper"), "paper-1");
    await user.selectOptions(screen.getByLabelText("Batch"), "batch-1");

    const expireInput = screen.getByLabelText("Global expire time");
    await user.type(expireInput, "2027-01-01T00:00");

    await user.click(screen.getByRole("button", { name: "Create assignment" }));

    await waitFor(() => expect(postSpy).toHaveBeenCalledWith("/essay/admin/assignments/", expect.objectContaining({
      paper: "paper-1", batch_id: "batch-1",
    })));
    expect(mockToastSuccess).toHaveBeenCalledWith("Assignment created.");
  });

  it("rejects submission with missing fields before calling the API", async () => {
    mockOptionsAndAssignments();
    const postSpy = jest.spyOn(api, "post");
    const user = userEvent.setup();

    render(<AdminEssayAssignPage />);
    await waitFor(() => expect(screen.getByText(/No assignments yet/)).toBeInTheDocument());
    await user.click(screen.getByRole("button", { name: /New Assignment/ }));
    await user.click(screen.getByRole("button", { name: "Create assignment" }));

    expect(screen.getByText(/all required/)).toBeInTheDocument();
    expect(postSpy).not.toHaveBeenCalled();
  });
});

describe("Assign page — lifecycle actions", () => {
  const ASSIGNMENT: EssayAssignment = {
    id: "assign-1", paper: "paper-1", paper_title: "Persuasive Writing",
    batch_id: "batch-1", institution_id: "inst-1", global_start_time: null,
    global_expire_time: "2027-01-01T00:00:00Z", departments: [], status: "SCHEDULED",
    created_by: "u1", created_at: "t", updated_at: "t",
  };

  it("starts a SCHEDULED assignment after confirming", async () => {
    mockOptionsAndAssignments({ data: { count: 1, total_pages: 1, current_page: 1, next: null, previous: null, results: [ASSIGNMENT] } });
    const patchSpy = jest.spyOn(api, "patch").mockResolvedValue({
      data: { data: { ...ASSIGNMENT, status: "LIVE" } },
    } as any);
    const user = userEvent.setup();

    render(<AdminEssayAssignPage />);
    await waitFor(() => expect(screen.getByText("Persuasive Writing")).toBeInTheDocument());

    await user.click(screen.getByRole("button", { name: "Start" }));
    // Two "Start" buttons now exist — the row's own and the confirm
    // dialog's (confirmLabel="Start") — the dialog's is rendered last.
    const startButtons = screen.getAllByRole("button", { name: "Start" });
    await user.click(startButtons[startButtons.length - 1]);

    await waitFor(() => expect(patchSpy).toHaveBeenCalledWith("/essay/admin/assignments/assign-1/start/"));
  });

  it("does not show a Start button for a LIVE assignment", async () => {
    mockOptionsAndAssignments({
      data: { count: 1, total_pages: 1, current_page: 1, next: null, previous: null, results: [{ ...ASSIGNMENT, status: "LIVE" }] },
    });
    render(<AdminEssayAssignPage />);
    await waitFor(() => expect(screen.getByText("Persuasive Writing")).toBeInTheDocument());
    expect(screen.queryByRole("button", { name: "Start" })).not.toBeInTheDocument();
  });

  it("does not show a Close button for a CLOSED assignment", async () => {
    mockOptionsAndAssignments({
      data: { count: 1, total_pages: 1, current_page: 1, next: null, previous: null, results: [{ ...ASSIGNMENT, status: "CLOSED" }] },
    });
    render(<AdminEssayAssignPage />);
    await waitFor(() => expect(screen.getByText("Persuasive Writing")).toBeInTheDocument());
    expect(screen.queryByRole("button", { name: "Close" })).not.toBeInTheDocument();
  });

  it("resyncs the roster and shows the new-allocation count", async () => {
    mockOptionsAndAssignments({ data: { count: 1, total_pages: 1, current_page: 1, next: null, previous: null, results: [ASSIGNMENT] } });
    const postSpy = jest.spyOn(api, "post").mockResolvedValue({
      data: { data: { new_allocations: 4 } },
    } as any);
    const user = userEvent.setup();

    render(<AdminEssayAssignPage />);
    await waitFor(() => expect(screen.getByText("Persuasive Writing")).toBeInTheDocument());

    await user.click(screen.getByRole("button", { name: /Resync roster/ }));

    await waitFor(() => expect(postSpy).toHaveBeenCalledWith("/essay/admin/assignments/assign-1/resync-roster/"));
    expect(mockToastSuccess).toHaveBeenCalledWith("4 new student(s) allocated.");
  });
});
