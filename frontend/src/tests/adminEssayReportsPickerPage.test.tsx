/**
 * @jest-environment jsdom
 *
 * Essay Writing — admin Reports picker page (Phase 11, Task 11.3): lists
 * essay assignments (via the shared EssayAssignmentPickerList, now a
 * fourth consumer alongside Results, Analytics, and Dashboard),
 * click-through to the per-assignment reports table.
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
import AdminEssayReportsPickerPage from "@/app/admin/essay-writing/reports/page";
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

describe("Reports picker page", () => {
  it("renders an assignment card with its paper title and batch name", async () => {
    mockLoad();
    render(<AdminEssayReportsPickerPage />);
    await waitFor(() => expect(screen.getByText("Persuasive Writing")).toBeInTheDocument());
    expect(screen.getByText("CSE 2026")).toBeInTheDocument();
  });

  it("navigates to the per-assignment reports page when a card is clicked", async () => {
    mockLoad();
    const user = userEvent.setup();
    render(<AdminEssayReportsPickerPage />);
    await waitFor(() => expect(screen.getByText("Persuasive Writing")).toBeInTheDocument());
    await user.click(screen.getByText("Persuasive Writing"));
    expect(mockPush).toHaveBeenCalledWith("/admin/essay-writing/reports/assign-1");
  });

  it("shows an empty state when there are no assignments", async () => {
    mockLoad([]);
    render(<AdminEssayReportsPickerPage />);
    await waitFor(() => expect(screen.getByText("No assignments yet")).toBeInTheDocument());
  });

  it("shows a load-error state on failure", async () => {
    jest.spyOn(api, "get").mockRejectedValue(new Error("network error"));
    render(<AdminEssayReportsPickerPage />);
    await waitFor(() => expect(screen.getByText("Couldn't load reports")).toBeInTheDocument());
  });
});
