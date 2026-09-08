/**
 * @jest-environment jsdom
 *
 * Coverage for the exam notification added to the student home page
 * (2026-08-27): the moment a student lands on /students/home, a live or
 * upcoming exam surfaces as a card instead of requiring them to think to
 * check the Assessments tab. LIVE takes priority over SCHEDULED when both
 * exist. Also covers the "Assessments" step in the preparation-path map,
 * unlocked in the same change — it was previously mislabeled "locked, v2"
 * even though the feature has been live for a while, which would have sat
 * confusingly right below this new notification.
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

jest.mock("@/lib/auth-store", () => ({
  useAuthStore: () => ({ user: { role: "student", fullname: "Alice", student_id: "LT001" } }),
}));

import React from "react";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import api from "@/lib/api";
import StudentHomePage from "@/app/students/home/page";

const PROFILE_RESPONSE = { data: { data: { fullname: "Alice", batch_name: "2023-27", department: "CSE" } } };
const COMPANIES_RESPONSE = { data: { count: 3, results: [] } };

function mockApi({ assignments = [] }: { assignments?: any[] } = {}) {
  return jest.spyOn(api, "get").mockImplementation((url: string) => {
    if (url === "/users/me/") return Promise.resolve(PROFILE_RESPONSE) as any;
    if (url === "/resources/student/companies/") return Promise.resolve(COMPANIES_RESPONSE) as any;
    if (url === "/assessments/student/assignments/") return Promise.resolve({ data: { data: assignments } }) as any;
    return Promise.reject(new Error(`unexpected GET ${url}`));
  });
}

const LIVE_NOT_STARTED = {
  assignment_id: "a-1", paper_title: "Aptitude Round 1", paper_instructions: "",
  status: "LIVE", exam_duration_minutes: 60, global_start_time: null,
  global_expire_time: "2026-09-01T12:00:00Z", session_status: null,
};

const LIVE_IN_PROGRESS = {
  ...LIVE_NOT_STARTED, assignment_id: "a-2", session_status: "IN_PROGRESS",
};

const LIVE_COMPLETED = {
  ...LIVE_NOT_STARTED, assignment_id: "a-3", session_status: "SUBMITTED",
};

const SCHEDULED = {
  assignment_id: "a-4", paper_title: "Technical Round", paper_instructions: "",
  status: "SCHEDULED", exam_duration_minutes: 45,
  global_start_time: "2026-09-02T09:00:00Z", global_expire_time: "2026-09-02T11:00:00Z",
  session_status: null,
};

afterEach(() => {
  jest.restoreAllMocks();
  mockPush.mockClear();
});

describe("Student home page — exam notification", () => {
  it("shows nothing when there are no live or scheduled exams", async () => {
    mockApi({ assignments: [LIVE_COMPLETED] });
    render(<StudentHomePage />);

    await screen.findByText("Alice");
    expect(screen.queryByText("Exam live now")).not.toBeInTheDocument();
    expect(screen.queryByText("Upcoming exam")).not.toBeInTheDocument();
  });

  it("shows a live-now card for a not-yet-started live exam", async () => {
    mockApi({ assignments: [LIVE_NOT_STARTED] });
    render(<StudentHomePage />);

    expect(await screen.findByText("Exam live now")).toBeInTheDocument();
    expect(screen.getByText("Aptitude Round 1")).toBeInTheDocument();
  });

  it("shows 'in progress' wording for a resumable session", async () => {
    mockApi({ assignments: [LIVE_IN_PROGRESS] });
    render(<StudentHomePage />);

    expect(await screen.findByText("Exam in progress")).toBeInTheDocument();
  });

  it("shows an upcoming-exam card when only a scheduled exam exists", async () => {
    mockApi({ assignments: [SCHEDULED] });
    render(<StudentHomePage />);

    expect(await screen.findByText("Upcoming exam")).toBeInTheDocument();
    expect(screen.getByText("Technical Round")).toBeInTheDocument();
  });

  it("prioritizes a live exam over a scheduled one when both exist", async () => {
    mockApi({ assignments: [SCHEDULED, LIVE_NOT_STARTED] });
    render(<StudentHomePage />);

    expect(await screen.findByText("Exam live now")).toBeInTheDocument();
    expect(screen.queryByText("Upcoming exam")).not.toBeInTheDocument();
  });

  it("does not count a completed live exam as actionable", async () => {
    mockApi({ assignments: [LIVE_COMPLETED, SCHEDULED] });
    render(<StudentHomePage />);

    // The completed one shouldn't produce a "live" card; the scheduled one
    // should still surface since there's no ACTIONABLE live exam.
    expect(await screen.findByText("Upcoming exam")).toBeInTheDocument();
    expect(screen.queryByText("Exam live now")).not.toBeInTheDocument();
  });

  it("clicking the notification card navigates to the assessments list", async () => {
    mockApi({ assignments: [LIVE_NOT_STARTED] });
    const user = userEvent.setup();
    render(<StudentHomePage />);

    await user.click(await screen.findByText("Aptitude Round 1"));
    expect(mockPush).toHaveBeenCalledWith("/students/assessments");
  });
});

describe("Student home page — Assessments step unlocked", () => {
  it("no longer shows a 'v2' locked badge next to Assessments", async () => {
    mockApi();
    render(<StudentHomePage />);

    await screen.findByText("Alice");
    // "Assessments" now appears twice — desktop and mobile variants of the
    // same active step — both must be real, clickable buttons.
    const assessmentsLabels = screen.getAllByText("Assessments");
    expect(assessmentsLabels.length).toBeGreaterThanOrEqual(2);
    assessmentsLabels.forEach(label => {
      expect(label.closest("button")).not.toBeNull();
    });
  });

  it("Compete & rank is still locked, v2 — unaffected by this change", async () => {
    mockApi();
    render(<StudentHomePage />);

    await screen.findByText("Alice");
    const competeLabels = screen.getAllByText("Compete & rank");
    competeLabels.forEach(label => {
      expect(label.closest("button")).toBeNull();
    });
    expect(screen.getAllByText("v2").length).toBeGreaterThan(0);
  });

  it("clicking the Assessments step navigates to /students/assessments", async () => {
    mockApi();
    const user = userEvent.setup();
    render(<StudentHomePage />);

    await screen.findByText("Alice");
    const [firstAssessmentsButton] = screen.getAllByText("Assessments");
    await user.click(firstAssessmentsButton);

    expect(mockPush).toHaveBeenCalledWith("/students/assessments");
  });
});
