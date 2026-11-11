/**
 * @jest-environment jsdom
 *
 * Essay Writing — admin Analytics picker page (Phase 9, Task 9.2): lists
 * essay assignments (via the shared EssayAssignmentPickerList, extracted
 * this phase once Analytics became a second real consumer of Phase 8's
 * Results picker shape), click-through to the per-assignment analytics page.
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
import AdminEssayAnalyticsPickerPage from "@/app/admin/essay-writing/analytics/page";
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

describe("Analytics picker page", () => {
  it("renders an assignment card with its paper title and batch name", async () => {
    mockLoad();
    render(<AdminEssayAnalyticsPickerPage />);
    await waitFor(() => expect(screen.getByText("Persuasive Writing")).toBeInTheDocument());
    expect(screen.getByText("CSE 2026")).toBeInTheDocument();
  });

  it("navigates to the per-assignment analytics page when a card is clicked", async () => {
    mockLoad();
    const user = userEvent.setup();
    render(<AdminEssayAnalyticsPickerPage />);
    await waitFor(() => expect(screen.getByText("Persuasive Writing")).toBeInTheDocument());
    await user.click(screen.getByText("Persuasive Writing"));
    expect(mockPush).toHaveBeenCalledWith("/admin/essay-writing/analytics/assign-1");
  });

  it("shows an empty state when there are no assignments", async () => {
    mockLoad([]);
    render(<AdminEssayAnalyticsPickerPage />);
    await waitFor(() => expect(screen.getByText("No assignments yet")).toBeInTheDocument());
  });

  it("shows a load-error state on failure", async () => {
    jest.spyOn(api, "get").mockRejectedValue(new Error("network error"));
    render(<AdminEssayAnalyticsPickerPage />);
    await waitFor(() => expect(screen.getByText("Couldn't load analytics")).toBeInTheDocument());
  });
});
