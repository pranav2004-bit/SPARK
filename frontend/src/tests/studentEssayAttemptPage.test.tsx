/**
 * @jest-environment jsdom
 *
 * Coverage for the student essay-writing exam-taking page (Tasks 4.1–4.3
 * combined): start/resume-or-already-done gating, the writing screen's
 * word-limit truncation and paste-block, and submit. Mirrors the mocking
 * pattern of studentExamSectionsNavigator.test.tsx (StudentLayout collapsed
 * to a passthrough, its examMode slots rendered directly so tests can find
 * the countdown/Submit button) but scoped to essay-writing's much smaller
 * single-question surface — no sections/navigator here.
 */

const mockPush = jest.fn();
jest.mock("next/navigation", () => ({
  useParams: () => ({ assignment_id: "assign-1" }),
  useRouter: () => ({ push: mockPush }),
}));

jest.mock("@/components/layout/StudentLayout", () => ({
  StudentLayout: ({ children, examCenterContent, examRightContent }: any) => (
    <>
      <div data-testid="exam-center">{examCenterContent}</div>
      <div data-testid="exam-right">{examRightContent}</div>
      {children}
    </>
  ),
}));

const mockToastError = jest.fn();
jest.mock("@/components/ui/Toast", () => ({
  useToast: () => ({ error: mockToastError, success: jest.fn() }),
}));

const mockRequestFullscreen = jest.fn().mockResolvedValue(undefined);
jest.mock("@/hooks/useEssayActivityCapture", () => ({
  useEssayActivityCapture: () => ({
    isFullscreen: false,
    requestFullscreen: mockRequestFullscreen,
    tabSwitchCount: 0,
    fullscreenExitCount: 0,
    pasteAttempts: 0,
  }),
  clearEssayViolationCounts: jest.fn(),
}));

const mockSaveDraftResilient = jest.fn().mockResolvedValue("saved");
const mockPendingDraft = jest.fn().mockReturnValue(null);
const mockFlushDraftQueue = jest.fn().mockResolvedValue(false);
jest.mock("@/lib/essayDraftQueue", () => ({
  saveDraftResilient: (...args: any[]) => mockSaveDraftResilient(...args),
  pendingDraft: (...args: any[]) => mockPendingDraft(...args),
  flushDraftQueue: (...args: any[]) => mockFlushDraftQueue(...args),
}));

import React from "react";
import { render, screen, waitFor, act, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import api from "@/lib/api";
import StudentEssayAttemptPage from "@/app/students/essay-writing/[assignment_id]/page";

const START_RESPONSE = {
  data: { data: { attempt_id: "attempt-1", ends_at: "2099-01-01T00:10:00Z", status: "IN_PROGRESS" } },
};

const DETAIL_RESPONSE = {
  data: {
    data: {
      attempt_id: "attempt-1",
      ends_at: "2099-01-01T00:10:00Z",
      status: "IN_PROGRESS",
      draft_response: "",
      question: {
        id: "q-1", question_text: "Discuss the causes of climate change.",
        word_limit: 5, time_limit_minutes: 10, max_score: 10,
      },
    },
  },
};

function mockStartAndDetail(overrides: { start?: any; detail?: any } = {}) {
  jest.spyOn(api, "post").mockImplementation((url: string) => {
    if (url.includes("start-attempt")) return Promise.resolve(overrides.start ?? START_RESPONSE) as any;
    if (url.includes("/submit/")) return Promise.resolve({ data: { data: {} } }) as any;
    return Promise.reject(new Error(`unexpected POST ${url}`));
  });
  jest.spyOn(api, "get").mockImplementation((url: string) => {
    if (url.includes("/attempts/")) return Promise.resolve(overrides.detail ?? DETAIL_RESPONSE) as any;
    return Promise.reject(new Error(`unexpected GET ${url}`));
  });
}

async function enterWriting() {
  render(<StudentEssayAttemptPage />);
  const user = userEvent.setup();
  await user.click(await screen.findByRole("button", { name: "Begin Writing" }));
  await screen.findByPlaceholderText("Start writing your response…");
  return user;
}

afterEach(() => {
  jest.restoreAllMocks();
  mockPush.mockClear();
  mockToastError.mockClear();
  mockSaveDraftResilient.mockClear().mockResolvedValue("saved");
  mockPendingDraft.mockClear().mockReturnValue(null);
  mockFlushDraftQueue.mockClear().mockResolvedValue(false);
});

describe("Essay attempt page — start/resume gating", () => {
  it("shows the pre-writing gate after a successful start-attempt", async () => {
    mockStartAndDetail();
    render(<StudentEssayAttemptPage />);
    expect(await screen.findByText("Ready to begin?")).toBeInTheDocument();
  });

  it("shows an error state when start-attempt fails", async () => {
    jest.spyOn(api, "post").mockRejectedValue(new Error("not allocated"));
    render(<StudentEssayAttemptPage />);
    expect(await screen.findByText(/Couldn't load this assessment/)).toBeInTheDocument();
    expect(mockToastError).toHaveBeenCalled();
  });

  it("shows the already-submitted state without fetching attempt detail", async () => {
    const getSpy = jest.spyOn(api, "get");
    mockStartAndDetail({ start: { data: { data: { attempt_id: "attempt-1", ends_at: "2099-01-01T00:10:00Z", status: "SUBMITTED" } } } });
    render(<StudentEssayAttemptPage />);
    expect(await screen.findByText("You've already submitted this essay.")).toBeInTheDocument();
    expect(getSpy).not.toHaveBeenCalled();
  });

  it("recovers a locally-queued draft over the server's last-confirmed draft", async () => {
    mockPendingDraft.mockReturnValue("queued draft text");
    mockStartAndDetail();
    const user = await enterWriting();
    expect(screen.getByDisplayValue("queued draft text")).toBeInTheDocument();
  });

  it("resumes from the server's own draft_response on a plain refresh (nothing queued locally)", async () => {
    // The base case the "locally-queued" test above doesn't cover: no
    // offline drama, just a normal browser refresh mid-write. pendingDraft
    // returns null (its real default when localStorage has nothing for
    // this attempt), so the page must fall back to whatever the server
    // last confirmed via autosave — this is the literal "browser refresh
    // mid-write recovers the last autosaved draft" case named in
    // LIVETRACKER3_V1.md Task 4.2's own Testing checklist.
    mockStartAndDetail({
      detail: { data: { data: { ...DETAIL_RESPONSE.data.data, draft_response: "already written before the refresh" } } },
    });
    const user = await enterWriting();
    expect(screen.getByDisplayValue("already written before the refresh")).toBeInTheDocument();
  });
});

describe("Essay attempt page — writing screen", () => {
  it("renders the question text and starts the countdown after Begin Writing", async () => {
    mockStartAndDetail();
    await enterWriting();
    expect(screen.getByText("Discuss the causes of climate change.")).toBeInTheDocument();
    expect(screen.getByTestId("exam-center")).toHaveTextContent(/\d{2}:\d{2}/);
  });

  it("truncates typed text to the question's word limit instead of just flagging it", async () => {
    mockStartAndDetail();
    const user = await enterWriting();
    const textarea = screen.getByPlaceholderText("Start writing your response…");

    await user.type(textarea, "one two three four five six seven");

    expect((textarea as HTMLTextAreaElement).value.trim().split(/\s+/)).toHaveLength(5);
    expect((textarea as HTMLTextAreaElement).value.trim()).toBe("one two three four five");
  });

  it("blocks paste into the response textarea", async () => {
    mockStartAndDetail();
    await enterWriting();
    const textarea = screen.getByPlaceholderText("Start writing your response…") as HTMLTextAreaElement;

    const pasteEvent = new Event("paste", { bubbles: true, cancelable: true }) as any;
    pasteEvent.clipboardData = { getData: () => "pasted text" };
    act(() => { textarea.dispatchEvent(pasteEvent); });

    expect(pasteEvent.defaultPrevented).toBe(true);
    expect(textarea.value).toBe("");
  });

  it("schedules a debounced autosave after typing", async () => {
    jest.useFakeTimers({ advanceTimers: true });
    mockStartAndDetail();
    render(<StudentEssayAttemptPage />);
    const user = userEvent.setup({ delay: null });
    await user.click(await screen.findByRole("button", { name: "Begin Writing" }));
    const textarea = await screen.findByPlaceholderText("Start writing your response…");

    await user.type(textarea, "hello");
    await act(async () => { jest.advanceTimersByTime(2000); });

    await waitFor(() => expect(mockSaveDraftResilient).toHaveBeenCalledWith("attempt-1", "hello"));
    jest.useRealTimers();
  });
});

describe("Essay attempt page — submit", () => {
  it("submits the current draft and shows the submitted confirmation", async () => {
    mockStartAndDetail();
    const user = await enterWriting();

    await user.click(screen.getByTestId("exam-right").querySelector("button")!);
    const dialog = await screen.findByRole("dialog");
    await user.click(within(dialog).getByRole("button", { name: "Submit" }));

    expect(await screen.findByText("Your essay has been submitted.")).toBeInTheDocument();
  });

  it("exits back to the essay-writing list when leaving a terminal screen", async () => {
    mockStartAndDetail();
    const user = await enterWriting();
    await user.click(screen.getByTestId("exam-right").querySelector("button")!);
    const dialog = await screen.findByRole("dialog");
    await user.click(within(dialog).getByRole("button", { name: "Submit" }));
    await screen.findByText("Your essay has been submitted.");

    await user.click(screen.getByRole("button", { name: "Back to Essay Writing" }));
    expect(mockPush).toHaveBeenCalledWith("/students/essay-writing");
  });
});
