/**
 * @jest-environment jsdom
 *
 * Coverage for the student essay-writing assignment list (Task 4.4),
 * mirroring students/assessments/page.tsx's own list-page test pattern
 * (studentAssessmentsListPage.test.tsx) — load states, status pill logic,
 * and Start/Resume navigation into the exam route.
 */

const mockPush = jest.fn();
jest.mock("next/navigation", () => ({
  useRouter: () => ({ push: mockPush }),
}));

jest.mock("@/components/layout/StudentLayout", () => ({
  StudentLayout: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}));

const mockToastError = jest.fn();
jest.mock("@/components/ui/Toast", () => ({
  useToast: () => ({ error: mockToastError, success: jest.fn() }),
}));

import React from "react";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import api from "@/lib/api";
import StudentEssayWritingPage from "@/app/students/essay-writing/page";
import type { StudentEssayAssignmentListItem } from "@/types";

const LIVE_ITEM: StudentEssayAssignmentListItem = {
  assignment_id: "assign-1", paper_title: "Persuasive Writing", status: "LIVE",
  global_start_time: null, global_expire_time: "2026-09-01T12:00:00Z",
  attempt_status: null, word_limit: 500, time_limit_minutes: 45,
};

function mockApi(items: StudentEssayAssignmentListItem[] = [LIVE_ITEM]) {
  return jest.spyOn(api, "get").mockResolvedValue({ data: { data: items } } as any);
}

afterEach(() => {
  jest.restoreAllMocks();
  mockPush.mockClear();
  mockToastError.mockClear();
});

describe("Student essay-writing list — load states", () => {
  it("shows the empty state when there are no assignments", async () => {
    mockApi([]);
    render(<StudentEssayWritingPage />);
    expect(await screen.findByText(/No essay assessments yet/)).toBeInTheDocument();
  });

  it("shows an error state when the list fails to load", async () => {
    jest.spyOn(api, "get").mockRejectedValue(new Error("network error"));
    render(<StudentEssayWritingPage />);
    expect(await screen.findByText(/Couldn't load your essay assessments/)).toBeInTheDocument();
    expect(mockToastError).toHaveBeenCalled();
  });

  it("renders a live, not-yet-attempted assignment with a Start Writing button", async () => {
    mockApi([LIVE_ITEM]);
    render(<StudentEssayWritingPage />);
    expect(await screen.findByText("Persuasive Writing")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Start Writing" })).toBeInTheDocument();
  });
});

describe("Student essay-writing list — navigation", () => {
  it("clicking Start Writing navigates to the exam route for that assignment", async () => {
    mockApi([LIVE_ITEM]);
    const user = userEvent.setup();
    render(<StudentEssayWritingPage />);

    await user.click(await screen.findByRole("button", { name: "Start Writing" }));
    expect(mockPush).toHaveBeenCalledWith("/students/essay-writing/assign-1");
  });

  it("shows Resume for an in-progress attempt and navigates the same way", async () => {
    mockApi([{ ...LIVE_ITEM, attempt_status: "IN_PROGRESS" }]);
    const user = userEvent.setup();
    render(<StudentEssayWritingPage />);

    const btn = await screen.findByRole("button", { name: "Resume" });
    await user.click(btn);
    expect(mockPush).toHaveBeenCalledWith("/students/essay-writing/assign-1");
  });

  it("clicking Past Results navigates to the essay results page (Phase 14)", async () => {
    mockApi([LIVE_ITEM]);
    const user = userEvent.setup();
    render(<StudentEssayWritingPage />);

    await user.click(await screen.findByRole("button", { name: /Past Results/ }));
    expect(mockPush).toHaveBeenCalledWith("/students/essay-writing/results");
  });
});

describe("Student essay-writing list — status pill / enterability", () => {
  it("does not show an enter button for a SCHEDULED (not yet live) assignment", async () => {
    mockApi([{ ...LIVE_ITEM, status: "SCHEDULED" }]);
    render(<StudentEssayWritingPage />);
    await screen.findByText("Persuasive Writing");
    expect(screen.getByText("Not started yet")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Start Writing|Resume/ })).not.toBeInTheDocument();
  });

  it("shows Completed and no enter button once submitted", async () => {
    mockApi([{ ...LIVE_ITEM, attempt_status: "SUBMITTED" }]);
    render(<StudentEssayWritingPage />);
    await screen.findByText("Persuasive Writing");
    expect(screen.getByText("Completed")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Start Writing|Resume/ })).not.toBeInTheDocument();
  });

  it("shows Completed for an auto-submitted attempt too", async () => {
    mockApi([{ ...LIVE_ITEM, attempt_status: "AUTO_SUBMITTED" }]);
    render(<StudentEssayWritingPage />);
    await screen.findByText("Persuasive Writing");
    expect(screen.getByText("Completed")).toBeInTheDocument();
  });

  it("shows Closed and no enter button for a closed assignment", async () => {
    mockApi([{ ...LIVE_ITEM, status: "CLOSED" }]);
    render(<StudentEssayWritingPage />);
    await screen.findByText("Persuasive Writing");
    expect(screen.getByText("Closed")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Start Writing|Resume/ })).not.toBeInTheDocument();
  });
});
