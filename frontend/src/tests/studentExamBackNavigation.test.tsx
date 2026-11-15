/**
 * @jest-environment jsdom
 *
 * Coverage for the exam page's browser back/forward handling (2026-11-16
 * production-readiness audit — the student asked specifically about
 * browser-arrow behaviour during and after an exam):
 *
 *  1. bfcache restore (pageshow, persisted) forces a full reload, so a
 *     student who submitted, left, then pressed back can never see a
 *     frozen pre-submit snapshot of the exam UI instead of the real
 *     "Submitted" screen.
 *  2. The browser back button is trapped while an exam is IN_PROGRESS —
 *     instead of silently leaving (no warning, unlike a tab close/reload,
 *     and not tracked as suspicious activity the way a tab-switch is), it
 *     shows the same "Exit without submitting?" confirm dialog the
 *     header's own Exit button already uses.
 *
 * jsdom's window.location.reload is read-only/non-configurable — same
 * constraint documented in usePortalGuard.test.tsx — calling the real thing
 * surfaces as a console.error ("Not implemented: navigation"), used here as
 * proof reload() was actually invoked.
 */

const mockPush = jest.fn();
jest.mock("next/navigation", () => ({
  useParams: () => ({ assignment_id: "assign-1" }),
  useRouter: () => ({ push: mockPush }),
}));

jest.mock("@/components/layout/StudentLayout", () => ({
  StudentLayout: ({ children }: { children: React.ReactNode }) => <>{children}</>,
  useExamMobileMenu: () => ({ open: false, setOpen: jest.fn() }),
}));

jest.mock("@/components/ui/Toast", () => ({
  useToast: () => ({ error: jest.fn(), success: jest.fn(), warning: jest.fn() }),
}));

jest.mock("@/hooks/useServerTimeSync", () => ({
  useServerTimeSync: () => ({ secondsRemaining: 1800, isSyncFailing: false, lastExtension: null }),
}));

const mockRequestFullscreen = jest.fn().mockResolvedValue(undefined);
jest.mock("@/hooks/useActivityCapture", () => ({
  useActivityCapture: () => ({
    isFullscreen: true,
    requestFullscreen: mockRequestFullscreen,
    tabSwitchCount: 0,
    fullscreenExitCount: 0,
    screenshotAttempts: 0,
    notifyActiveQuestion: jest.fn(),
  }),
  clearExamViolationCounts: jest.fn(),
}));

jest.mock("@/hooks/useOfflineAnswerQueue", () => ({
  useOfflineAnswerQueue: () => ({
    saveAnswer: jest.fn().mockResolvedValue("saved"),
    isReconnecting: false,
    pendingCount: 0,
  }),
}));

import React from "react";
import { render, screen, act } from "@testing-library/react";
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

function assignmentItem() {
  return {
    assignment_id: "assign-1", paper_title: "MOCK TEST - 3", paper_instructions: "Read carefully.",
    status: "LIVE", exam_duration_minutes: 60, global_start_time: null,
    global_expire_time: "2026-09-01T12:00:00Z", session_status: null,
    total_marks: 1, question_count: 1,
  };
}

function question() {
  return {
    id: "q-1", question_number: 1, mcq_type: "single", question_content_type: "text",
    question_text: "Question 1 text", question_image_url: null, marks: 1,
    section_id: "sec-1", section_title: "Section 1",
    options: [
      { id: "q-1-a", label: "A", content_type: "text", text: "Option A", image_key: "", image_url: null, order: 1 },
      { id: "q-1-b", label: "B", content_type: "text", text: "Option B", image_key: "", image_url: null, order: 2 },
    ],
    selected_option_ids: [],
  };
}

function mockApi() {
  return jest.spyOn(api, "get").mockImplementation((url: string) => {
    if (url === "/users/me/") return Promise.resolve(PROFILE_RESPONSE) as any;
    if (url === "/assessments/student/assignments/") return Promise.resolve({ data: { data: [assignmentItem()] } }) as any;
    if (url === "/assessments/student/sessions/sess-1/questions/") {
      return Promise.resolve({
        data: { data: { session_id: "sess-1", session_status: "IN_PROGRESS", ends_at: "2026-09-01T12:00:00Z", questions: [question()] } },
      }) as any;
    }
    return Promise.reject(new Error(`unexpected GET ${url}`));
  });
}

function mockStartSession() {
  return jest.spyOn(api, "post").mockResolvedValue({
    data: { data: { session_id: "sess-1", status: "IN_PROGRESS" } },
  } as any);
}

async function enterExam(user: ReturnType<typeof userEvent.setup>) {
  await screen.findByRole("heading", { name: "MOCK TEST - 3" });
  await user.click(screen.getByRole("checkbox"));
  await user.click(screen.getByRole("button", { name: /Enter Fullscreen & Start Exam/ }));
}

function reloadWasCalled(errorSpy: jest.SpyInstance): boolean {
  return errorSpy.mock.calls.some(args => String(args[0]).includes("Not implemented: navigation"));
}

afterEach(() => {
  jest.restoreAllMocks();
  mockPush.mockClear();
  mockRequestFullscreen.mockClear();
});

describe("Exam page — bfcache restore (pageshow)", () => {
  it("reloads the page on a persisted (bfcache) pageshow restore, even before the exam has loaded", async () => {
    mockApi();
    const errorSpy = jest.spyOn(console, "error").mockImplementation(() => {});
    render(<StudentExamPage />);
    await screen.findByRole("heading", { name: "MOCK TEST - 3" });

    act(() => { window.dispatchEvent(Object.assign(new Event("pageshow"), { persisted: true })); });

    expect(reloadWasCalled(errorSpy)).toBe(true);
  });

  it("does not reload on an ordinary (non-bfcache) pageshow", async () => {
    mockApi();
    const errorSpy = jest.spyOn(console, "error").mockImplementation(() => {});
    render(<StudentExamPage />);
    await screen.findByRole("heading", { name: "MOCK TEST - 3" });

    act(() => { window.dispatchEvent(Object.assign(new Event("pageshow"), { persisted: false })); });

    expect(reloadWasCalled(errorSpy)).toBe(false);
  });
});

describe("Exam page — back button trapped while IN_PROGRESS", () => {
  it("shows the 'Exit without submitting?' confirm dialog on a popstate while the exam is in progress, instead of silently navigating away", async () => {
    mockApi();
    mockStartSession();
    const user = userEvent.setup();
    render(<StudentExamPage />);
    await enterExam(user);
    await screen.findByText("Question 1 text");

    act(() => { window.dispatchEvent(new PopStateEvent("popstate")); });

    expect(await screen.findByText("Exit without submitting?")).toBeInTheDocument();
  });

  it("does not show the confirm dialog on a popstate before the exam has started (still on the briefing gate)", async () => {
    mockApi();
    render(<StudentExamPage />);
    await screen.findByRole("heading", { name: "MOCK TEST - 3" });

    act(() => { window.dispatchEvent(new PopStateEvent("popstate")); });

    expect(screen.queryByText("Exit without submitting?")).not.toBeInTheDocument();
  });
});
