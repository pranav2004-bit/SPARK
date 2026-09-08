/**
 * @jest-environment jsdom
 *
 * Coverage for the "Final Review" checklist added to the admin Assign page
 * (frontend/src/app/admin/assessments/assign/page.tsx): once a question
 * paper is selected, a 10-item checklist renders live values for its
 * sets/sections/questions/marks plus the current form state (batch,
 * departments, duration, global timer, cutoff, results visibility). The
 * "Create assignment" button stays disabled until every item is manually
 * ticked, and any post-review edit to a reviewed field resets every tick —
 * both are the whole point of the feature (catching human oversight before
 * an action that locks the paper and creates real student sessions), so
 * they're the two things this file is most careful to prove.
 */

const mockPush = jest.fn();
const mockSearchParams = new URLSearchParams();
jest.mock("next/navigation", () => ({
  useRouter: () => ({ push: mockPush }),
  useSearchParams: () => mockSearchParams,
}));

jest.mock("@/components/layout/AdminLayout", () => ({
  AdminLayout: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}));

const mockToastSuccess = jest.fn();
const mockToastError = jest.fn();
jest.mock("@/components/ui/Toast", () => ({
  useToast: () => ({ success: mockToastSuccess, error: mockToastError }),
}));

jest.mock("@/lib/departmentsContext", () => ({
  useDepartments: () => ({
    departments: [], activeDepartments: [], loading: false, error: "", refetch: jest.fn(),
  }),
}));

jest.mock("@/hooks/useAuth", () => ({
  useAuth: () => ({ user: { id: "admin-1", role: "admin" }, isSuperAdmin: false }),
}));

import React from "react";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import api from "@/lib/api";
import AdminAssessmentAssignPage from "@/app/admin/assessments/assign/page";

const PAPER = {
  id: "paper-1", title: "MOCK TEST 2", description: "", instructions: "",
  set_count: 1, created_by: "admin-1", created_by_name: "", created_by_email: "",
  created_at: "2026-01-01T00:00:00Z", updated_at: "2026-01-01T00:00:00Z",
};

const BATCH = { id: "batch-1", batch_name: "2023-27", student_count: 13, created_at: "", updated_at: "" };

const PAPER_DETAIL_RESPONSE = {
  data: {
    data: {
      paper: PAPER,
      sets: [
        { id: "set-1", paper: "paper-1", label: "SET A", order: 1, question_count: 2, total_marks: 2, section_count: 1 },
      ],
    },
  },
};

function mockApiGet() {
  return jest.spyOn(api, "get").mockImplementation((url: string) => {
    if (url === "/assessments/admin/papers/") {
      return Promise.resolve({ data: { count: 1, results: [PAPER] } }) as any;
    }
    if (url === "/users/batches/") {
      return Promise.resolve({ data: { data: [BATCH] } }) as any;
    }
    if (url.startsWith("/assessments/admin/papers/paper-1/")) {
      return Promise.resolve(PAPER_DETAIL_RESPONSE) as any;
    }
    if (url.startsWith("/assessments/admin/assignments/")) {
      return Promise.resolve({ data: { count: 0, results: [] } }) as any;
    }
    return Promise.reject(new Error(`unexpected GET ${url}`));
  });
}

async function selectPaperAndBatch(user: ReturnType<typeof userEvent.setup>) {
  await user.click(screen.getByText("Create Assessment"));
  await user.selectOptions(await screen.findByLabelText("Question paper"), "paper-1");
  await user.selectOptions(screen.getByLabelText("Batch"), "batch-1");
}

beforeEach(() => {
  mockPush.mockClear();
  mockToastSuccess.mockClear();
  mockToastError.mockClear();
});

afterEach(() => {
  jest.restoreAllMocks();
});

describe("Admin Assign page — Final Review checklist", () => {
  it("shows all 10 review items with accurate live values once a paper is selected", async () => {
    mockApiGet();
    const user = userEvent.setup();
    render(<AdminAssessmentAssignPage />);

    await selectPaperAndBatch(user);
    await user.type(screen.getByLabelText("Global expire time"), "2026-09-01T10:00");

    expect(await screen.findByText("Final Review")).toBeInTheDocument();

    const section = screen.getByText("Final Review").closest("div") as HTMLElement;
    // Each row is `<label><input/><span>{label span}{value span}</span></label>`
    // — getByText(label) matches the inner label span, so its parent is the
    // full-line span holding both label and live value.
    const line = (label: RegExp) => within(section).getByText(label).parentElement as HTMLElement;
    expect(line(/Total number of sets:/)).toHaveTextContent("1 set");
    expect(line(/Sections per set:/)).toHaveTextContent("SET A: 1 section");
    expect(line(/Questions per set:/)).toHaveTextContent("SET A: 2 questions");
    expect(line(/Marks per set:/)).toHaveTextContent("SET A: 2 marks");
    expect(line(/Assigned batch:/)).toHaveTextContent("2023-27");
    expect(line(/Assigned department\(s\):/)).toHaveTextContent("All departments in the batch");
    expect(line(/Exam duration:/)).toHaveTextContent("60 minutes");
    // Global timer must use the same "·" separator as the per-set rows
    // above it, not a different style (was "|" — a visual inconsistency
    // flagged in review).
    expect(line(/Global timer:/)).toHaveTextContent("not set — begins immediately once you start the exam · Expire:");
    expect(line(/Pass cutoff:/)).toHaveTextContent("40%");
    expect(line(/Results visibility:/)).toHaveTextContent("Visible to students after submission");

    // 10 checkboxes, all unticked by default.
    const boxes = within(section).getAllByRole("checkbox");
    expect(boxes).toHaveLength(10);
    boxes.forEach(b => expect(b).not.toBeChecked());
  }, 20000);

  it("keeps Create assignment disabled until every item is ticked, then hides it behind the mock-test prompt until answered", async () => {
    mockApiGet();
    const user = userEvent.setup();
    render(<AdminAssessmentAssignPage />);

    await selectPaperAndBatch(user);
    await user.type(screen.getByLabelText("Global expire time"), "2026-09-01T10:00");
    await screen.findByText("Final Review");

    expect(screen.getByRole("button", { name: "Create assignment" })).toBeDisabled();

    const boxes = screen.getAllByRole("checkbox");
    for (const box of boxes.slice(0, -1)) {
      await user.click(box);
    }
    expect(screen.getByRole("button", { name: "Create assignment" })).toBeDisabled(); // one still unticked

    await user.click(boxes[boxes.length - 1]);
    // All ticked — the mock-test prompt replaces the button entirely until
    // the admin explicitly answers Yes or No.
    expect(screen.queryByRole("button", { name: "Create assignment" })).not.toBeInTheDocument();
    expect(screen.getByText(/willing to take the mock test/)).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "No" }));
    expect(screen.getByRole("button", { name: "Create assignment" })).toBeEnabled();
  }, 20000);

  it("resets every tick — and the mock-test prompt — if a reviewed field is edited after checking", async () => {
    mockApiGet();
    const user = userEvent.setup();
    render(<AdminAssessmentAssignPage />);

    await selectPaperAndBatch(user);
    await user.type(screen.getByLabelText("Global expire time"), "2026-09-01T10:00");
    await screen.findByText("Final Review");

    const boxes = screen.getAllByRole("checkbox");
    for (const box of boxes) await user.click(box);
    await user.click(screen.getByRole("button", { name: "No" }));
    expect(screen.getByRole("button", { name: "Create assignment" })).toBeEnabled();

    // Edit a reviewed field (duration) after ticking everything and answering.
    const durationInput = screen.getByLabelText("Exam duration (minutes)");
    await user.clear(durationInput);
    await user.type(durationInput, "90");

    const boxesAfter = screen.getAllByRole("checkbox");
    boxesAfter.forEach(b => expect(b).not.toBeChecked());
    expect(screen.getByRole("button", { name: "Create assignment" })).toBeDisabled();
    // The mock-test prompt must also have reset, not just the checkboxes —
    // re-ticking everything should show the prompt again, not silently
    // resume the "No" answer from before the edit.
    for (const box of boxesAfter) await user.click(box);
    expect(screen.getByText(/willing to take the mock test/)).toBeInTheDocument();
  }, 20000);

  it("shows a retry link and no checkboxes if the paper's structure fails to load", async () => {
    jest.spyOn(api, "get").mockImplementation((url: string) => {
      if (url === "/assessments/admin/papers/") {
        return Promise.resolve({ data: { count: 1, results: [PAPER] } }) as any;
      }
      if (url === "/users/batches/") {
        return Promise.resolve({ data: { data: [BATCH] } }) as any;
      }
      if (url.startsWith("/assessments/admin/papers/paper-1/")) {
        return Promise.reject(new Error("boom"));
      }
      if (url.startsWith("/assessments/admin/assignments/")) {
        return Promise.resolve({ data: { count: 0, results: [] } }) as any;
      }
      return Promise.reject(new Error(`unexpected GET ${url}`));
    });
    const user = userEvent.setup();
    render(<AdminAssessmentAssignPage />);

    await user.click(screen.getByText("Create Assessment"));
    await user.selectOptions(await screen.findByLabelText("Question paper"), "paper-1");

    expect(await screen.findByText(/Couldn't load this paper's structure/)).toBeInTheDocument();
    expect(screen.queryByRole("checkbox")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Create assignment" })).toBeDisabled();
  });

  it("warns when the paper has no sets, but still lets the admin review and tick it", async () => {
    jest.spyOn(api, "get").mockImplementation((url: string) => {
      if (url === "/assessments/admin/papers/") {
        return Promise.resolve({ data: { count: 1, results: [PAPER] } }) as any;
      }
      if (url === "/users/batches/") {
        return Promise.resolve({ data: { data: [BATCH] } }) as any;
      }
      if (url.startsWith("/assessments/admin/papers/paper-1/")) {
        return Promise.resolve({ data: { data: { paper: PAPER, sets: [] } } }) as any;
      }
      if (url.startsWith("/assessments/admin/assignments/")) {
        return Promise.resolve({ data: { count: 0, results: [] } }) as any;
      }
      return Promise.reject(new Error(`unexpected GET ${url}`));
    });
    const user = userEvent.setup();
    render(<AdminAssessmentAssignPage />);

    await selectPaperAndBatch(user);
    await screen.findByText("Final Review");

    expect(await screen.findByText(/structure looks incomplete/)).toBeInTheDocument();
    const setsLine = screen.getByText(/Total number of sets:/).parentElement as HTMLElement;
    expect(setsLine).toHaveTextContent("No sets found on this paper.");
    // Still a real, checkable item — the warning informs, it doesn't block.
    const setsCheckbox = within(setsLine.closest("label") as HTMLElement).getByRole("checkbox");
    expect(setsCheckbox).not.toBeDisabled();
  });

  it("warns on the specific set with zero questions/sections, without flagging a healthy set", async () => {
    jest.spyOn(api, "get").mockImplementation((url: string) => {
      if (url === "/assessments/admin/papers/") {
        return Promise.resolve({ data: { count: 1, results: [PAPER] } }) as any;
      }
      if (url === "/users/batches/") {
        return Promise.resolve({ data: { data: [BATCH] } }) as any;
      }
      if (url.startsWith("/assessments/admin/papers/paper-1/")) {
        return Promise.resolve({
          data: { data: { paper: PAPER, sets: [
            { id: "set-1", paper: "paper-1", label: "SET A", order: 1, question_count: 0, total_marks: 0, section_count: 0 },
            { id: "set-2", paper: "paper-1", label: "SET B", order: 2, question_count: 2, total_marks: 2, section_count: 1 },
          ] } },
        }) as any;
      }
      if (url.startsWith("/assessments/admin/assignments/")) {
        return Promise.resolve({ data: { count: 0, results: [] } }) as any;
      }
      return Promise.reject(new Error(`unexpected GET ${url}`));
    });
    const user = userEvent.setup();
    render(<AdminAssessmentAssignPage />);

    await selectPaperAndBatch(user);
    await screen.findByText("Final Review");

    expect(await screen.findByText(/structure looks incomplete/)).toBeInTheDocument();
    // "Total number of sets" itself is fine (there ARE sets) — only the
    // rows that enumerate per-set content should carry the warning color.
    const setsLine = screen.getByText(/Total number of sets:/).parentElement as HTMLElement;
    const setsValue = setsLine.querySelector("span:last-child") as HTMLElement;
    expect(setsValue.style.color).toBe("var(--color-text-subtle)");
    const questionsLine = screen.getByText(/Questions per set:/).parentElement as HTMLElement;
    expect(questionsLine).toHaveTextContent("SET A: 0 questions");
    expect(questionsLine).toHaveTextContent("SET B: 2 questions");
    const questionsValue = questionsLine.querySelector("span:last-child") as HTMLElement;
    expect(questionsValue.style.color).toBe("var(--color-danger)");
  });

  it("clicking Yes starts a trial session and opens the exam UI in a new tab, without blocking Create assignment", async () => {
    mockApiGet();
    jest.spyOn(api, "post").mockImplementation((url: string) => {
      if (url === "/assessments/admin/papers/paper-1/trial/start/") {
        return Promise.resolve({ data: { data: { session_id: "trial-sess-1" } } }) as any;
      }
      return Promise.reject(new Error(`unexpected POST ${url}`));
    });
    const openSpy = jest.spyOn(window, "open").mockImplementation(() => null);
    const user = userEvent.setup();
    render(<AdminAssessmentAssignPage />);

    await selectPaperAndBatch(user);
    await user.type(screen.getByLabelText("Global expire time"), "2026-09-01T10:00");
    await screen.findByText("Final Review");
    for (const box of screen.getAllByRole("checkbox")) await user.click(box);

    await user.click(screen.getByRole("button", { name: "Yes" }));

    await waitFor(() => expect(api.post).toHaveBeenCalledWith(
      "/assessments/admin/papers/paper-1/trial/start/",
      { duration_minutes: 60 },
    ));
    await waitFor(() => expect(openSpy).toHaveBeenCalledWith("/admin/assessments/trial/trial-sess-1", "_blank"));
    // "Yes" reveals Create assignment too — it never blocks real creation.
    expect(await screen.findByRole("button", { name: "Create assignment" })).toBeInTheDocument();
    expect(await screen.findByRole("button", { name: "Take the mock test again" })).toBeInTheDocument();

    openSpy.mockRestore();
  }, 20000);

  it("creates the assignment once every item is reviewed and required fields are filled", async () => {
    mockApiGet();
    jest.spyOn(api, "post").mockResolvedValue({
      data: { data: { id: "assign-1", paper: "paper-1", batch_id: "batch-1", status: "SCHEDULED", exam_duration_minutes: 60, pass_cutoff_percentage: 40, show_result_to_student: true, departments: [] } },
    } as any);
    const user = userEvent.setup();
    render(<AdminAssessmentAssignPage />);

    await selectPaperAndBatch(user);
    await user.type(screen.getByLabelText("Global expire time"), "2026-09-01T10:00");
    await screen.findByText("Final Review");

    for (const box of screen.getAllByRole("checkbox")) await user.click(box);
    await user.click(screen.getByRole("button", { name: "No" }));
    await user.click(screen.getByRole("button", { name: "Create assignment" }));

    await waitFor(() => expect(api.post).toHaveBeenCalledWith(
      "/assessments/admin/assignments/",
      expect.objectContaining({ paper: "paper-1", batch_id: "batch-1" }),
    ));
    await waitFor(() => expect(mockToastSuccess).toHaveBeenCalledWith("Assignment created."));
    // Optimistically prepended to the assignment history below the form.
    // "2023-27" alone now matches twice (the still-present Batch <option>
    // AND the new history card), since the option no longer carries an
    // inline "(N students)" suffix to disambiguate it — cutoff% is unique
    // to the history card.
    expect(await screen.findByText("cutoff 40%")).toBeInTheDocument();
  }, 20000);

  it("an existing assignment's Mock Test toolbar button starts a trial for that assignment's paper", async () => {
    const ASSIGNMENT = {
      id: "assign-9", paper: "paper-1", paper_title: "MOCK TEST 2", batch_id: "batch-1", institution_id: "inst-1",
      global_start_time: null, global_expire_time: "2026-09-01T10:00:00Z",
      exam_duration_minutes: 45, pass_cutoff_percentage: 40, show_result_to_student: true,
      departments: [], status: "CLOSED", created_by: "admin-1",
      created_at: "2026-01-01T00:00:00Z", updated_at: "2026-01-01T00:00:00Z",
    };
    jest.spyOn(api, "get").mockImplementation((url: string) => {
      if (url === "/assessments/admin/papers/") {
        return Promise.resolve({ data: { count: 1, results: [PAPER] } }) as any;
      }
      if (url === "/users/batches/") {
        return Promise.resolve({ data: { data: [BATCH] } }) as any;
      }
      if (url.startsWith("/assessments/admin/assignments/")) {
        return Promise.resolve({ data: { count: 1, results: [ASSIGNMENT] } }) as any;
      }
      return Promise.reject(new Error(`unexpected GET ${url}`));
    });
    jest.spyOn(api, "post").mockImplementation((url: string) => {
      if (url === "/assessments/admin/papers/paper-1/trial/start/") {
        return Promise.resolve({ data: { data: { session_id: "trial-sess-2" } } }) as any;
      }
      return Promise.reject(new Error(`unexpected POST ${url}`));
    });
    const openSpy = jest.spyOn(window, "open").mockImplementation(() => null);
    const user = userEvent.setup();
    render(<AdminAssessmentAssignPage />);

    await user.click(await screen.findByRole("button", { name: "Mock Test" }));

    await waitFor(() => expect(api.post).toHaveBeenCalledWith(
      "/assessments/admin/papers/paper-1/trial/start/",
      { duration_minutes: 45 },
    ));
    await waitFor(() => expect(openSpy).toHaveBeenCalledWith("/admin/assessments/trial/trial-sess-2", "_blank"));

    openSpy.mockRestore();
  });
});
