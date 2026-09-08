/**
 * @jest-environment jsdom
 *
 * Coverage for the student assessments list page after the pre-exam
 * briefing moved off this page and onto the exam route itself (2026-08-27)
 * — Start/Resume Exam is now a plain navigation, no modal in between.
 */

const mockPush = jest.fn();
jest.mock("next/navigation", () => ({
  useRouter: () => ({ push: mockPush }),
}));

jest.mock("@/components/layout/StudentLayout", () => ({
  StudentLayout: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}));

jest.mock("@/components/ui/Toast", () => ({
  useToast: () => ({ error: jest.fn(), success: jest.fn() }),
}));

import React from "react";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import api from "@/lib/api";
import StudentAssessmentsPage from "@/app/students/assessments/page";

const LIVE_ITEM = {
  assignment_id: "assign-1", paper_title: "MOCK TEST - 3", paper_instructions: "Read carefully.",
  status: "LIVE", exam_duration_minutes: 60, global_start_time: null,
  global_expire_time: "2026-09-01T12:00:00Z", session_status: null,
  total_marks: 30, question_count: 30,
};

function mockApi(items: any[] = [LIVE_ITEM]) {
  return jest.spyOn(api, "get").mockResolvedValue({ data: { data: items } } as any);
}

afterEach(() => {
  jest.restoreAllMocks();
  mockPush.mockClear();
});

describe("Student assessments list — Start Exam navigation", () => {
  it("clicking Start Exam navigates straight to the exam route, no modal", async () => {
    mockApi();
    const user = userEvent.setup();
    render(<StudentAssessmentsPage />);

    await user.click(await screen.findByRole("button", { name: "Start Exam" }));

    expect(mockPush).toHaveBeenCalledWith("/students/assessments/assign-1");
    expect(screen.queryByText("Before you start")).not.toBeInTheDocument();
    expect(screen.queryByRole("checkbox")).not.toBeInTheDocument();
  });

  it("clicking Resume Exam navigates the same way, no separate resume gating here", async () => {
    mockApi([{ ...LIVE_ITEM, session_status: "IN_PROGRESS" }]);
    const user = userEvent.setup();
    render(<StudentAssessmentsPage />);

    await user.click(await screen.findByRole("button", { name: "Resume Exam" }));
    expect(mockPush).toHaveBeenCalledWith("/students/assessments/assign-1");
  });
});
