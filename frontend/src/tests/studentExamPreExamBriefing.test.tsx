/**
 * @jest-environment jsdom
 *
 * Coverage for the pre-exam briefing screen (2026-08-27) that replaced the
 * old "Before you start" modal on the assessments list page — now a full
 * page on the exam route itself, with assessment facts, identity
 * confirmation, admin instructions, the platform's actual enforced system
 * rules, and a readiness checklist. Scoped to the gate itself (loading,
 * error, resume, and the full first-time briefing); the question-answering
 * UI reached after the gate is unchanged and out of scope here.
 */

const mockPush = jest.fn();
jest.mock("next/navigation", () => ({
  useParams: () => ({ assignment_id: "assign-1" }),
  useRouter: () => ({ push: mockPush }),
}));

jest.mock("@/components/layout/StudentLayout", () => ({
  StudentLayout: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}));

jest.mock("@/components/ui/Toast", () => ({
  useToast: () => ({ error: jest.fn(), success: jest.fn(), warning: jest.fn() }),
}));

import React from "react";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import api from "@/lib/api";
import StudentExamPage from "@/app/students/assessments/[assignment_id]/page";

const PROFILE_RESPONSE = {
  data: {
    data: {
      student_id: "LT0083", fullname: "Adari Yaswanth", college_email_id: "x@y.com",
      department: "CSD", batch_id: "b1", batch_name: "2023-27", is_profile_completed: true,
    },
  },
};

function assignmentItem(overrides: Record<string, unknown> = {}) {
  return {
    assignment_id: "assign-1", paper_title: "MOCK TEST - 3", paper_instructions: "Read carefully.",
    status: "LIVE", exam_duration_minutes: 60, global_start_time: null,
    global_expire_time: "2026-09-01T12:00:00Z", session_status: null,
    total_marks: 45, question_count: 30,
    ...overrides,
  };
}

function mockApi(assignments: any[] = [assignmentItem()]) {
  return jest.spyOn(api, "get").mockImplementation((url: string) => {
    if (url === "/users/me/") return Promise.resolve(PROFILE_RESPONSE) as any;
    if (url === "/assessments/student/assignments/") return Promise.resolve({ data: { data: assignments } }) as any;
    return Promise.reject(new Error(`unexpected GET ${url}`));
  });
}

afterEach(() => {
  jest.restoreAllMocks();
  mockPush.mockClear();
});

describe("Pre-exam briefing — first-time start", () => {
  it("shows the assessment's title and key facts", async () => {
    mockApi();
    render(<StudentExamPage />);

    expect(await screen.findByRole("heading", { name: "MOCK TEST - 3" })).toBeInTheDocument();
    expect(screen.getByText("60 min")).toBeInTheDocument();
    expect(screen.getByText("45")).toBeInTheDocument();
    expect(screen.getByText("30")).toBeInTheDocument();
  });

  it("shows the admin's own instructions", async () => {
    mockApi([assignmentItem({ paper_instructions: "No calculators allowed." })]);
    render(<StudentExamPage />);

    expect(await screen.findByText("No calculators allowed.")).toBeInTheDocument();
  });

  it("falls back to a placeholder when the admin left no instructions", async () => {
    mockApi([assignmentItem({ paper_instructions: "   " })]);
    render(<StudentExamPage />);

    expect(await screen.findByText("No additional instructions were provided for this assessment.")).toBeInTheDocument();
  });

  it("shows the student's identity for confirmation", async () => {
    mockApi();
    render(<StudentExamPage />);

    await screen.findByRole("heading", { name: "MOCK TEST - 3" });
    expect(screen.getByText("Adari Yaswanth")).toBeInTheDocument();
    expect(screen.getByText("LT0083")).toBeInTheDocument();
    expect(screen.getByText("2023-27")).toBeInTheDocument();
    expect(screen.getByText("CSD")).toBeInTheDocument();
  });

  it("still renders the briefing if identity lookup fails, just without that section", async () => {
    jest.spyOn(api, "get").mockImplementation((url: string) => {
      if (url === "/users/me/") return Promise.reject(new Error("boom"));
      if (url === "/assessments/student/assignments/") return Promise.resolve({ data: { data: [assignmentItem()] } }) as any;
      return Promise.reject(new Error("unexpected"));
    });
    render(<StudentExamPage />);

    expect(await screen.findByRole("heading", { name: "MOCK TEST - 3" })).toBeInTheDocument();
    expect(screen.queryByText("Confirm your identity")).not.toBeInTheDocument();
  });

  it("states the exact enforced tab-switch and fullscreen-exit limits, matching real enforcement", async () => {
    mockApi();
    render(<StudentExamPage />);

    expect(await screen.findByText(/more than 3 times auto-submits/)).toBeInTheDocument();
    expect(screen.getByText(/more than 5 times auto-submits/)).toBeInTheDocument();
  });

  it("accurately describes copy/paste as disabled and right-click/PrintScreen as monitored, not blocked", async () => {
    mockApi();
    render(<StudentExamPage />);

    expect(await screen.findByText(/Copy and paste are disabled/)).toBeInTheDocument();
    expect(screen.getByText(/Right-clicks and PrintScreen attempts are recorded and reviewed/)).toBeInTheDocument();
  });

  it("keeps Start Exam disabled until the consent checkbox is ticked", async () => {
    mockApi();
    const user = userEvent.setup();
    render(<StudentExamPage />);

    await screen.findByRole("heading", { name: "MOCK TEST - 3" });
    const startButton = screen.getByRole("button", { name: /Enter Fullscreen & Start Exam/ });
    expect(startButton).toBeDisabled();

    await user.click(screen.getByRole("checkbox"));
    expect(startButton).toBeEnabled();
  });

  it("has no Back button on the consent card — the exam-mode header's Exit Test covers leaving", async () => {
    mockApi();
    render(<StudentExamPage />);

    await screen.findByRole("heading", { name: "MOCK TEST - 3" });
    expect(screen.queryByRole("button", { name: "Back" })).not.toBeInTheDocument();
  });

  it("shows the final-glance recap of what's enforced, right above the consent action", async () => {
    mockApi();
    render(<StudentExamPage />);

    await screen.findByRole("heading", { name: "MOCK TEST - 3" });
    expect(screen.getByText("5 tab switches = auto-submit")).toBeInTheDocument();
    expect(screen.getByText("3 fullscreen exits = auto-submit")).toBeInTheDocument();
    expect(screen.getByText("Activity monitored")).toBeInTheDocument();
    expect(screen.getByText("Auto-submits at 0:00")).toBeInTheDocument();
  });
});

describe("Pre-exam gate — resume", () => {
  it("shows a lightweight resume screen instead of the full briefing", async () => {
    mockApi([assignmentItem({ session_status: "IN_PROGRESS" })]);
    render(<StudentExamPage />);

    expect(await screen.findByRole("heading", { name: "Resume MOCK TEST - 3" })).toBeInTheDocument();
    expect(screen.queryByText("Confirm your identity")).not.toBeInTheDocument();
    expect(screen.queryByRole("checkbox")).not.toBeInTheDocument();
  });
});

describe("Pre-exam gate — load failure", () => {
  it("shows an error state with a way back if the assignment can't be found", async () => {
    mockApi([]); // this assignment isn't in the list anymore
    render(<StudentExamPage />);

    expect(await screen.findByText("Couldn't load this assessment")).toBeInTheDocument();
  });

  it("shows an error state if the fetch itself fails", async () => {
    jest.spyOn(api, "get").mockImplementation((url: string) => {
      if (url === "/users/me/") return Promise.reject(new Error("boom"));
      if (url === "/assessments/student/assignments/") return Promise.reject(new Error("boom"));
      return Promise.reject(new Error("unexpected"));
    });
    render(<StudentExamPage />);

    expect(await screen.findByText("Couldn't load this assessment")).toBeInTheDocument();
  });
});
