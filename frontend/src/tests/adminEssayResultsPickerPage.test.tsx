/**
 * @jest-environment jsdom
 *
 * Essay Writing — admin Results picker page (Phase 8, Task 8.2): lists
 * essay assignments, click-through to the per-assignment results table.
 */

const mockPush = jest.fn();
jest.mock("next/navigation", () => ({
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
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import api from "@/lib/api";
import AdminEssayResultsPickerPage from "@/app/admin/essay-writing/results/page";
import type { EssayAssignment, Batch } from "@/types";

const ASSIGNMENT: EssayAssignment = {
  id: "assign-1", paper: "paper-1", paper_title: "Persuasive Writing", batch_id: "batch-1",
  institution_id: "inst-1", global_start_time: null, global_expire_time: "2026-09-25T10:00:00Z",
  departments: [], status: "LIVE", created_by: "admin-1",
  created_at: "2026-09-20T00:00:00Z", updated_at: "2026-09-20T00:00:00Z",
};

const BATCH: Batch = { id: "batch-1", batch_name: "CSE 2026", created_at: "", updated_at: "" };

function mockLoad(assignments: EssayAssignment[] = [ASSIGNMENT], batches: Batch[] = [BATCH]) {
  jest.spyOn(api, "get").mockImplementation((url: string) => {
    if (url.includes("/essay/admin/assignments/")) {
      return Promise.resolve({ data: { results: assignments, count: assignments.length, total_pages: 1 } } as any);
    }
    if (url.includes("/users/batches/")) {
      return Promise.resolve({ data: { data: batches } } as any);
    }
    return Promise.reject(new Error(`unexpected GET ${url}`));
  });
}

beforeEach(() => {
  mockPush.mockClear();
  mockToastError.mockClear();
});

afterEach(() => {
  jest.restoreAllMocks();
});

describe("Results picker page", () => {
  it("renders an assignment card with its paper title and batch name", async () => {
    mockLoad();
    render(<AdminEssayResultsPickerPage />);
    await waitFor(() => expect(screen.getByText("Persuasive Writing")).toBeInTheDocument());
    expect(screen.getByText("CSE 2026")).toBeInTheDocument();
    expect(screen.getByText("Live")).toBeInTheDocument();
  });

  it("navigates to the per-assignment results page when a card is clicked", async () => {
    mockLoad();
    const user = userEvent.setup();
    render(<AdminEssayResultsPickerPage />);
    await waitFor(() => expect(screen.getByText("Persuasive Writing")).toBeInTheDocument());
    await user.click(screen.getByText("Persuasive Writing"));
    expect(mockPush).toHaveBeenCalledWith("/admin/essay-writing/results/assign-1");
  });

  it("shows an empty state when there are no assignments", async () => {
    mockLoad([]);
    render(<AdminEssayResultsPickerPage />);
    await waitFor(() => expect(screen.getByText("No assignments yet")).toBeInTheDocument());
  });

  it("shows a load-error state, distinct from the empty state, on failure", async () => {
    // Phase 9's shared EssayAssignmentPickerList derives this message
    // from the page's own title ("Couldn't load results"), a more
    // specific message than the pre-refactor page's hardcoded generic
    // "Couldn't load assignments" — an intentional improvement from
    // extracting the shared component, not a regression.
    jest.spyOn(api, "get").mockRejectedValue(new Error("network error"));
    render(<AdminEssayResultsPickerPage />);
    await waitFor(() => expect(screen.getByText("Couldn't load results")).toBeInTheDocument());
  });
});
