/**
 * @jest-environment jsdom
 *
 * Essay Writing landing page — 10 module cards per LIVETRACKER3_V1.md's
 * plan, enabled phase by phase: Question Bank (Phase 2), Assessments
 * Assigning (Phase 3), Submissions (Phase 6), LLM Controls (Phase 7),
 * Results (Phase 8), Analytics (Phase 9), Dashboard (Phase 10), Reports
 * (Phase 11), DLQ (Phase 12), and Notifications (Phase 13) — as of this
 * phase, all 10 modules from the original plan are live; none remain
 * disabled. Locks in: all 10 titles render and all 10 cards navigate.
 */

const mockPush = jest.fn();
jest.mock("next/navigation", () => ({
  useRouter: () => ({ push: mockPush }),
}));

jest.mock("@/components/layout/AdminLayout", () => ({
  AdminLayout: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}));

import React from "react";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import AdminEssayWritingLandingPage from "@/app/admin/essay-writing/page";

const ALL_MODULE_TITLES = [
  "Question Bank", "Assessments Assigning", "Results", "Analytics", "Dashboard",
  "Submissions", "LLM Controls", "Reports", "DLQ", "Notifications",
];

beforeEach(() => {
  mockPush.mockClear();
});

describe("Essay Writing landing page — 10 module cards", () => {
  it("renders all 10 module titles", () => {
    render(<AdminEssayWritingLandingPage />);
    for (const title of ALL_MODULE_TITLES) {
      expect(screen.getByText(title)).toBeInTheDocument();
    }
  });

  it("navigates to the Question Bank pages when its card is clicked", async () => {
    const user = userEvent.setup();
    render(<AdminEssayWritingLandingPage />);
    await user.click(screen.getByRole("button", { name: /^Question Bank/ }));
    expect(mockPush).toHaveBeenCalledWith("/admin/essay-writing/papers");
  });

  it("navigates to the Assign page when the Assessments Assigning card is clicked", async () => {
    const user = userEvent.setup();
    render(<AdminEssayWritingLandingPage />);
    await user.click(screen.getByRole("button", { name: /^Assessments Assigning/ }));
    expect(mockPush).toHaveBeenCalledWith("/admin/essay-writing/assign");
  });

  it("navigates to the Submissions page when its card is clicked", async () => {
    const user = userEvent.setup();
    render(<AdminEssayWritingLandingPage />);
    await user.click(screen.getByRole("button", { name: /^Submissions/ }));
    expect(mockPush).toHaveBeenCalledWith("/admin/essay-writing/submissions");
  });

  it("navigates to the LLM Controls page when its card is clicked", async () => {
    const user = userEvent.setup();
    render(<AdminEssayWritingLandingPage />);
    await user.click(screen.getByRole("button", { name: /^LLM Controls/ }));
    expect(mockPush).toHaveBeenCalledWith("/admin/essay-writing/llm-controls");
  });

  it("navigates to the Results page when its card is clicked", async () => {
    const user = userEvent.setup();
    render(<AdminEssayWritingLandingPage />);
    await user.click(screen.getByRole("button", { name: /^Results/ }));
    expect(mockPush).toHaveBeenCalledWith("/admin/essay-writing/results");
  });

  it("navigates to the Analytics page when its card is clicked", async () => {
    const user = userEvent.setup();
    render(<AdminEssayWritingLandingPage />);
    await user.click(screen.getByRole("button", { name: /^Analytics/ }));
    expect(mockPush).toHaveBeenCalledWith("/admin/essay-writing/analytics");
  });

  it("navigates to the Dashboard page when its card is clicked", async () => {
    const user = userEvent.setup();
    render(<AdminEssayWritingLandingPage />);
    await user.click(screen.getByRole("button", { name: /^Dashboard/ }));
    expect(mockPush).toHaveBeenCalledWith("/admin/essay-writing/dashboard");
  });

  it("navigates to the Reports page when its card is clicked", async () => {
    const user = userEvent.setup();
    render(<AdminEssayWritingLandingPage />);
    await user.click(screen.getByRole("button", { name: /^Reports/ }));
    expect(mockPush).toHaveBeenCalledWith("/admin/essay-writing/reports");
  });

  it("navigates to the DLQ page when its card is clicked", async () => {
    const user = userEvent.setup();
    render(<AdminEssayWritingLandingPage />);
    await user.click(screen.getByRole("button", { name: /^DLQ/ }));
    expect(mockPush).toHaveBeenCalledWith("/admin/essay-writing/dlq");
  });

  it("navigates to the Notifications page when its card is clicked", async () => {
    const user = userEvent.setup();
    render(<AdminEssayWritingLandingPage />);
    await user.click(screen.getByRole("button", { name: /^Notifications/ }));
    expect(mockPush).toHaveBeenCalledWith("/admin/essay-writing/notifications");
  });

  it("shows no 'Coming soon' badges — every module is now live", () => {
    render(<AdminEssayWritingLandingPage />);
    expect(screen.queryAllByText("Coming soon")).toHaveLength(0);
  });
});
