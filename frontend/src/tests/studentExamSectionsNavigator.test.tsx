/**
 * @jest-environment jsdom
 *
 * Coverage for the sections navigator on the student's active exam-taking
 * screen (2026-08-28) — questions are grouped by section_id/section_title
 * (now returned by the backend), a Sections column renders only when the
 * paper actually has more than one, and clicking a section jumps to its
 * first question. The rest of this screen (answer selection saving,
 * submit) already has equivalent coverage on the admin trial page's
 * identical fork (adminTrialExamPage.test.tsx) — not re-verified
 * line-for-line here; this file is scoped to the sections feature and just
 * enough of the entry gate to reach the active question screen.
 */

const mockPush = jest.fn();
jest.mock("next/navigation", () => ({
  useParams: () => ({ assignment_id: "assign-1" }),
  useRouter: () => ({ push: mockPush }),
}));

jest.mock("@/components/layout/StudentLayout", () => ({
  StudentLayout: ({ children }: { children: React.ReactNode }) => <>{children}</>,
  // The real StudentLayout provides this via a Context.Provider that wraps
  // its children — this mock renders children directly with no provider,
  // so MobileExamMenu (rendered inside the exam page's own JSX, not by
  // StudentLayout itself) needs its own default here. `open: false` means
  // it renders nothing, which is the correct behavior for every test in
  // this file — none of them are testing the mobile hamburger menu itself.
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

function assignmentItem() {
  return {
    assignment_id: "assign-1", paper_title: "MOCK TEST - 3", paper_instructions: "Read carefully.",
    status: "LIVE", exam_duration_minutes: 60, global_start_time: null,
    global_expire_time: "2026-09-01T12:00:00Z", session_status: null,
    total_marks: 3, question_count: 3,
  };
}

function question(id: string, number: number, sectionId: string, sectionTitle: string) {
  return {
    id, question_number: number, mcq_type: "single", question_content_type: "text",
    question_text: `Question ${number} text`, question_image_url: null, marks: 1,
    section_id: sectionId, section_title: sectionTitle,
    options: [
      { id: `${id}-a`, label: "A", content_type: "text", text: "Option A", image_key: "", image_url: null, order: 1 },
      { id: `${id}-b`, label: "B", content_type: "text", text: "Option B", image_key: "", image_url: null, order: 2 },
    ],
    selected_option_ids: [],
  };
}

const MULTI_SECTION_QUESTIONS = [
  question("q-1", 1, "sec-1", "Quantitative Aptitude"),
  question("q-2", 2, "sec-1", "Quantitative Aptitude"),
  question("q-3", 3, "sec-2", "Verbal Ability"),
];

const SINGLE_SECTION_QUESTIONS = [
  question("q-1", 1, "sec-1", "Section 1"),
  question("q-2", 2, "sec-1", "Section 1"),
];

function mockApi(questions: any[]) {
  return jest.spyOn(api, "get").mockImplementation((url: string) => {
    if (url === "/users/me/") return Promise.resolve(PROFILE_RESPONSE) as any;
    if (url === "/assessments/student/assignments/") return Promise.resolve({ data: { data: [assignmentItem()] } }) as any;
    if (url === "/assessments/student/sessions/sess-1/questions/") {
      return Promise.resolve({
        data: { data: { session_id: "sess-1", session_status: "IN_PROGRESS", ends_at: "2026-09-01T12:00:00Z", questions } },
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

// Clicks through the briefing gate to reach the active question screen.
async function enterExam(user: ReturnType<typeof userEvent.setup>) {
  await screen.findByRole("heading", { name: "MOCK TEST - 3" });
  await user.click(screen.getByRole("checkbox"));
  await user.click(screen.getByRole("button", { name: /Enter Fullscreen & Start Exam/ }));
}

afterEach(() => {
  jest.restoreAllMocks();
  mockPush.mockClear();
  mockRequestFullscreen.mockClear();
});

describe("Exam-taking screen — sections navigator", () => {
  // Trailing 10000 arg: this test does more async find* waiting (two
  // queries against the effect-driven Sections panel, on top of the
  // shared entry-gate flow every test here pays) than its siblings, which
  // occasionally exceeds Jest's 5000ms default.
  it("groups questions into a Sections column when the paper has more than one", async () => {
    mockApi(MULTI_SECTION_QUESTIONS);
    mockStartSession();
    const user = userEvent.setup();
    render(<StudentExamPage />);

    await enterExam(user);

    expect(await screen.findByText("Question 1 text")).toBeInTheDocument();
    // The desktop Sections panel's content renders one tick after mount
    // (it's positioned via a measured pixel width — sectionsBgWidth — set
    // by an effect that reads the panel's own DOM rect, so it's always
    // empty on the very first render). findByText/findAllByText (retries)
    // rather than getByText (one-shot) is what actually waits for that.
    // "Quantitative Aptitude" is the currently-active section, so it also
    // appears in the mobile Sections dropdown's collapsed-button label —
    // two matches, hence findAllByText; "Verbal Ability" isn't the active
    // section yet, so it appears exactly once (desktop panel only).
    expect((await screen.findAllByText("Quantitative Aptitude")).length).toBeGreaterThan(0);
    expect(await screen.findByText("Verbal Ability")).toBeInTheDocument();
    // 2 of 2 answered in the first section, 0 of 1 in the second.
    expect(screen.getByText("0/2 answered")).toBeInTheDocument();
    expect(screen.getByText("0/1 answered")).toBeInTheDocument();
  }, 10000);

  it("clicking a section jumps to that section's first question", async () => {
    mockApi(MULTI_SECTION_QUESTIONS);
    mockStartSession();
    const user = userEvent.setup();
    render(<StudentExamPage />);

    await enterExam(user);
    await screen.findByText("Question 1 text");

    // See the note in the test above — this panel populates async.
    await user.click(await screen.findByText("Verbal Ability"));

    expect(await screen.findByText("Question 3 text")).toBeInTheDocument();
    expect(screen.queryByText("Question 1 text")).not.toBeInTheDocument();
  });

  it("hides the Sections column entirely for a single-section paper", async () => {
    mockApi(SINGLE_SECTION_QUESTIONS);
    mockStartSession();
    const user = userEvent.setup();
    render(<StudentExamPage />);

    await enterExam(user);

    expect(await screen.findByText("Question 1 text")).toBeInTheDocument();
    expect(screen.queryByText("Section 1")).not.toBeInTheDocument();
  });
});
