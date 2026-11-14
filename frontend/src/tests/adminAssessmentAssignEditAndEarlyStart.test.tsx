/**
 * @jest-environment jsdom
 *
 * Coverage for the assignment-scheduling feature added to the admin Assign
 * page (frontend/src/app/admin/assessments/assign/page.tsx) on 2026-11-12:
 * global_start_time became mandatory, Start Exam gained an early-override
 * confirmation flow (backed by the backend's 409 START_TIME_NOT_REACHED),
 * and SCHEDULED assignments gained an Edit panel for every field they were
 * created with.
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

const DEPARTMENTS = [
  { id: "d1", code: "CSE", name: "Computer Science", is_active: true, created_at: "", updated_at: "" },
  { id: "d2", code: "ECE", name: "Electronics", is_active: true, created_at: "", updated_at: "" },
];
jest.mock("@/lib/departmentsContext", () => ({
  useDepartments: () => ({
    departments: DEPARTMENTS, activeDepartments: DEPARTMENTS, loading: false, error: "", refetch: jest.fn(),
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

function scheduledAssignment(overrides: Record<string, unknown> = {}) {
  return {
    id: "assign-1", paper: "paper-1", paper_title: "MOCK TEST 2", batch_id: "batch-1", institution_id: "inst-1",
    global_start_time: "2026-09-01T09:00:00Z", global_expire_time: "2026-09-01T12:00:00Z",
    exam_duration_minutes: 60, pass_cutoff_percentage: 40, show_result_to_student: true,
    results_published_at: null, department_sections: [], status: "SCHEDULED", created_by: "admin-1",
    created_at: "2026-01-01T00:00:00Z", updated_at: "2026-01-01T00:00:00Z",
    ...overrides,
  };
}

function mockApiGet(assignments: unknown[]) {
  return jest.spyOn(api, "get").mockImplementation((url: string) => {
    if (url === "/assessments/admin/papers/") {
      return Promise.resolve({ data: { count: 1, results: [PAPER] } }) as any;
    }
    if (url === "/users/batches/") {
      return Promise.resolve({ data: { data: [BATCH] } }) as any;
    }
    if (url.startsWith("/assessments/admin/assignments/") && url.endsWith("/status/")) {
      return Promise.resolve({ data: { data: { status: "SCHEDULED", student_count_total: 0, student_count_completed: 0 } } }) as any;
    }
    if (url.startsWith("/assessments/admin/assignments/")) {
      return Promise.resolve({ data: { count: assignments.length, results: assignments } }) as any;
    }
    return Promise.reject(new Error(`unexpected GET ${url}`));
  });
}

afterEach(() => {
  jest.restoreAllMocks();
  mockToastSuccess.mockClear();
  mockToastError.mockClear();
});

describe("Admin Assign page — Start Exam early override", () => {
  it("shows the early-override warning on 409 and resubmits with confirm_early_start after the checkbox is ticked", async () => {
    mockApiGet([scheduledAssignment()]);
    const axiosError = Object.assign(new Error("not yet"), {
      isAxiosError: true,
      response: {
        status: 409,
        data: { success: false, message: "not yet", errors: { code: "START_TIME_NOT_REACHED", scheduled_start_time: "2026-09-01T09:00:00Z" } },
      },
    });
    const patchSpy = jest.spyOn(api, "patch")
      .mockRejectedValueOnce(axiosError)
      .mockResolvedValueOnce({ data: { data: scheduledAssignment({ status: "LIVE" }) } } as any);
    const user = userEvent.setup();
    render(<AdminAssessmentAssignPage />);

    await user.click(await screen.findByRole("button", { name: "Start Exam" }));
    const dialog = await screen.findByRole("dialog");
    await user.click(within(dialog).getByRole("button", { name: "Start Exam" }));

    expect(await screen.findByText("Start time not reached yet")).toBeInTheDocument();
    const confirmButton = screen.getByRole("button", { name: "Confirm Early Start" });
    expect(confirmButton).toBeDisabled();

    await user.click(screen.getByRole("checkbox"));
    expect(confirmButton).toBeEnabled();
    await user.click(confirmButton);

    await waitFor(() => expect(patchSpy).toHaveBeenLastCalledWith(
      "/assessments/admin/assignments/assign-1/start/",
      { confirm_early_start: true },
    ));
    await waitFor(() => expect(mockToastSuccess).toHaveBeenCalledWith("Exam started — the global timer is now live."));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("starts immediately with no override dialog when the scheduled time has already passed", async () => {
    mockApiGet([scheduledAssignment()]);
    jest.spyOn(api, "patch").mockResolvedValueOnce({ data: { data: scheduledAssignment({ status: "LIVE" }) } } as any);
    const user = userEvent.setup();
    render(<AdminAssessmentAssignPage />);

    await user.click(await screen.findByRole("button", { name: "Start Exam" }));
    const dialog = await screen.findByRole("dialog");
    await user.click(within(dialog).getByRole("button", { name: "Start Exam" }));

    await waitFor(() => expect(mockToastSuccess).toHaveBeenCalledWith("Exam started — the global timer is now live."));
    expect(screen.queryByText("Start time not reached yet")).not.toBeInTheDocument();
  });
});

describe("Admin Assign page — Edit assignment", () => {
  it("shows the Edit button only for a SCHEDULED assignment", async () => {
    mockApiGet([scheduledAssignment({ id: "assign-live", status: "LIVE" })]);
    render(<AdminAssessmentAssignPage />);

    await screen.findByRole("button", { name: "Mock Test" });
    expect(screen.queryByRole("button", { name: "Edit" })).not.toBeInTheDocument();
  });

  it("opens pre-filled from the assignment's current values and saves changes", async () => {
    mockApiGet([scheduledAssignment()]);
    const patchSpy = jest.spyOn(api, "patch").mockResolvedValueOnce({
      data: { data: scheduledAssignment({ exam_duration_minutes: 90, pass_cutoff_percentage: 50 }) },
    } as any);
    const user = userEvent.setup();
    render(<AdminAssessmentAssignPage />);

    await user.click(await screen.findByRole("button", { name: "Edit" }));
    const modal = await screen.findByRole("dialog");
    const durationInput = within(modal).getByLabelText("Exam duration (minutes)") as HTMLInputElement;
    expect(durationInput.value).toBe("60");

    await user.clear(durationInput);
    await user.type(durationInput, "90");
    await user.click(within(modal).getByRole("button", { name: "Save changes" }));

    await waitFor(() => expect(patchSpy).toHaveBeenCalledWith(
      "/assessments/admin/assignments/assign-1/",
      expect.objectContaining({ exam_duration_minutes: 90 }),
    ));
    await waitFor(() => expect(mockToastSuccess).toHaveBeenCalledWith("Assignment updated."));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("shows the new-allocations count when changing departments resyncs the roster", async () => {
    mockApiGet([scheduledAssignment()]);
    jest.spyOn(api, "patch").mockResolvedValueOnce({
      data: { data: { ...scheduledAssignment({ department_sections: [{ department: "CSE", sections: [] }] }), new_allocations: 5 } },
    } as any);
    const user = userEvent.setup();
    render(<AdminAssessmentAssignPage />);

    await user.click(await screen.findByRole("button", { name: "Edit" }));
    const modal = await screen.findByRole("dialog");
    await user.click(within(modal).getByRole("button", { name: "Computer Science" }));
    await user.click(within(modal).getByRole("button", { name: "Save changes" }));

    await waitFor(() => expect(mockToastSuccess).toHaveBeenCalledWith("Assignment updated — 5 new student(s) allocated."));
  });

  it("surfaces a server error and keeps the modal open for retry", async () => {
    mockApiGet([scheduledAssignment()]);
    jest.spyOn(api, "patch").mockRejectedValueOnce(new Error("network down"));
    const user = userEvent.setup();
    render(<AdminAssessmentAssignPage />);

    await user.click(await screen.findByRole("button", { name: "Edit" }));
    const modal = await screen.findByRole("dialog");
    await user.click(within(modal).getByRole("button", { name: "Save changes" }));

    expect(await within(modal).findByText("network down")).toBeInTheDocument();
    expect(screen.getByRole("dialog")).toBeInTheDocument();
  });
});

describe("Admin Assign page — Reopen assignment", () => {
  it("shows the Reopen button only for a CLOSED assignment", async () => {
    mockApiGet([scheduledAssignment({ status: "LIVE" })]);
    render(<AdminAssessmentAssignPage />);

    await screen.findByRole("button", { name: "Mock Test" });
    expect(screen.queryByRole("button", { name: "Reopen" })).not.toBeInTheDocument();
  });

  it("opens blank (no pre-filled times) and reopens with the newly entered times", async () => {
    mockApiGet([scheduledAssignment({ status: "CLOSED" })]);
    const patchSpy = jest.spyOn(api, "patch").mockResolvedValueOnce({
      data: { data: scheduledAssignment({ status: "SCHEDULED" }) },
    } as any);
    const user = userEvent.setup();
    render(<AdminAssessmentAssignPage />);

    await user.click(await screen.findByRole("button", { name: "Reopen" }));
    const modal = await screen.findByRole("dialog");
    const startInput = within(modal).getByLabelText("New global start time") as HTMLInputElement;
    const expireInput = within(modal).getByLabelText("New global expire time") as HTMLInputElement;
    expect(startInput.value).toBe("");
    expect(expireInput.value).toBe("");

    await user.type(startInput, "2027-01-01T09:00");
    await user.type(expireInput, "2027-01-01T12:00");
    await user.click(within(modal).getByRole("button", { name: "Reopen" }));

    await waitFor(() => expect(patchSpy).toHaveBeenCalledWith(
      "/assessments/admin/assignments/assign-1/reopen/",
      {
        global_start_time: new Date("2027-01-01T09:00").toISOString(),
        global_expire_time: new Date("2027-01-01T12:00").toISOString(),
      },
    ));
    await waitFor(() => expect(mockToastSuccess).toHaveBeenCalledWith(
      "Assignment reopened — students who haven't attempted it yet can access it again.",
    ));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("requires both times before submitting", async () => {
    mockApiGet([scheduledAssignment({ status: "CLOSED" })]);
    const patchSpy = jest.spyOn(api, "patch");
    const user = userEvent.setup();
    render(<AdminAssessmentAssignPage />);

    await user.click(await screen.findByRole("button", { name: "Reopen" }));
    const modal = await screen.findByRole("dialog");
    await user.click(within(modal).getByRole("button", { name: "Reopen" }));

    expect(await within(modal).findByText("New global start time is required.")).toBeInTheDocument();
    expect(patchSpy).not.toHaveBeenCalled();
  });

  it("surfaces a server error and keeps the modal open for retry", async () => {
    mockApiGet([scheduledAssignment({ status: "CLOSED" })]);
    jest.spyOn(api, "patch").mockRejectedValueOnce(new Error("already live elsewhere"));
    const user = userEvent.setup();
    render(<AdminAssessmentAssignPage />);

    await user.click(await screen.findByRole("button", { name: "Reopen" }));
    const modal = await screen.findByRole("dialog");
    await user.type(within(modal).getByLabelText("New global start time"), "2027-01-01T09:00");
    await user.type(within(modal).getByLabelText("New global expire time"), "2027-01-01T12:00");
    await user.click(within(modal).getByRole("button", { name: "Reopen" }));

    expect(await within(modal).findByText("already live elsewhere")).toBeInTheDocument();
    expect(screen.getByRole("dialog")).toBeInTheDocument();
  });
});
