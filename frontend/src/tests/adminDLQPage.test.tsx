/**
 * @jest-environment jsdom
 *
 * Essay Writing — admin DLQ list page (Phase 12, Task 12.2): filterable
 * list, single retry/resolve actions (mandatory reason), and bulk retry
 * (dry-run preview then explicit confirm).
 */

const mockPush = jest.fn();
jest.mock("next/navigation", () => ({
  useRouter: () => ({ push: mockPush }),
}));

jest.mock("@/components/layout/AdminLayout", () => ({
  AdminLayout: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}));

const mockToastError = jest.fn();
const mockToastSuccess = jest.fn();
jest.mock("@/components/ui/Toast", () => ({
  useToast: () => ({ error: mockToastError, success: mockToastSuccess }),
}));

import React from "react";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import api from "@/lib/api";
import AdminDLQPage from "@/app/admin/essay-writing/dlq/page";
import type { EssayDLQEntryRow } from "@/types";

const ENTRY: EssayDLQEntryRow = {
  id: "entry-1", task_name: "evaluate_essay", attempts: 3, dlq_retry_count: 0,
  error: "LLM permanent error", resolved: false, resolved_at: null, created_at: "2026-09-22T10:00:00Z",
};

const RESOLVED_ENTRY: EssayDLQEntryRow = {
  ...ENTRY, id: "entry-2", resolved: true, resolved_at: "2026-09-22T11:00:00Z",
};

function mockList(rows: EssayDLQEntryRow[] = [ENTRY]) {
  jest.spyOn(api, "get").mockImplementation((url: string) => {
    if (url.includes("/essay/admin/dlq/")) {
      return Promise.resolve({ data: { results: rows, count: rows.length, total_pages: 1 } } as any);
    }
    return Promise.reject(new Error(`unexpected GET ${url}`));
  });
}

beforeEach(() => {
  mockPush.mockClear();
  mockToastError.mockClear();
  mockToastSuccess.mockClear();
});

afterEach(() => {
  jest.restoreAllMocks();
});

describe("DLQ list page", () => {
  it("renders a DLQ entry row", async () => {
    mockList();
    render(<AdminDLQPage />);
    await waitFor(() => expect(screen.getByText("evaluate_essay")).toBeInTheDocument());
    expect(screen.getByText("LLM permanent error")).toBeInTheDocument();
    // "Unresolved" also appears as a <select> option — scope to the pill.
    expect(screen.getAllByText("Unresolved").length).toBeGreaterThan(0);
  });

  it("navigates to the detail page when a row is clicked", async () => {
    mockList();
    const user = userEvent.setup();
    render(<AdminDLQPage />);
    await waitFor(() => expect(screen.getByText("evaluate_essay")).toBeInTheDocument());
    await user.click(screen.getByText("evaluate_essay"));
    expect(mockPush).toHaveBeenCalledWith("/admin/essay-writing/dlq/entry-1");
  });

  it("disables Retry and Resolve for an already-resolved entry", async () => {
    mockList([RESOLVED_ENTRY]);
    render(<AdminDLQPage />);
    await waitFor(() => expect(screen.getByText("evaluate_essay")).toBeInTheDocument());
    expect(screen.getByRole("button", { name: /Retry/ })).toBeDisabled();
    expect(screen.getByRole("button", { name: /Resolve/ })).toBeDisabled();
  });

  it("filters by resolved state", async () => {
    mockList();
    const getSpy = jest.spyOn(api, "get");
    const user = userEvent.setup();
    render(<AdminDLQPage />);
    await waitFor(() => expect(screen.getByText("evaluate_essay")).toBeInTheDocument());

    await user.selectOptions(screen.getByRole("combobox"), "true");
    await waitFor(() => expect(getSpy).toHaveBeenLastCalledWith(expect.stringContaining("resolved=true")));
  });

  it("opens the retry modal and submits with a reason", async () => {
    mockList();
    jest.spyOn(api, "post").mockResolvedValue({ data: { success: true, message: "Retry dispatched." } } as any);
    const user = userEvent.setup();
    render(<AdminDLQPage />);
    await waitFor(() => expect(screen.getByText("evaluate_essay")).toBeInTheDocument());

    await user.click(screen.getByRole("button", { name: /Retry/ }));
    const dialog = screen.getByRole("dialog");
    const textarea = screen.getByPlaceholderText("Why?");
    await user.type(textarea, "Root cause fixed.");
    await user.click(within(dialog).getByRole("button", { name: "Retry" }));

    await waitFor(() => expect(api.post).toHaveBeenCalledWith(
      "/essay/admin/dlq/entry-1/retry/", { reason: "Root cause fixed." },
    ));
    await waitFor(() => expect(mockToastSuccess).toHaveBeenCalled());
  });

  it("rejects submitting the retry modal with a blank reason", async () => {
    mockList();
    jest.spyOn(api, "post").mockResolvedValue({ data: { success: true } } as any);
    const user = userEvent.setup();
    render(<AdminDLQPage />);
    await waitFor(() => expect(screen.getByText("evaluate_essay")).toBeInTheDocument());

    await user.click(screen.getByRole("button", { name: /Retry/ }));
    const dialog = screen.getByRole("dialog");
    await user.click(within(dialog).getByRole("button", { name: "Retry" }));

    expect(mockToastError).toHaveBeenCalledWith("A reason is required to retry a DLQ entry.");
    expect(api.post).not.toHaveBeenCalled();
  });

  it("opens the resolve modal and submits with a reason", async () => {
    mockList();
    jest.spyOn(api, "post").mockResolvedValue({ data: { success: true, message: "Entry resolved." } } as any);
    const user = userEvent.setup();
    render(<AdminDLQPage />);
    await waitFor(() => expect(screen.getByText("evaluate_essay")).toBeInTheDocument());

    await user.click(screen.getByRole("button", { name: /Resolve/ }));
    const dialog = screen.getByRole("dialog");
    await user.type(screen.getByPlaceholderText("Why?"), "Handled manually.");
    await user.click(within(dialog).getByRole("button", { name: "Resolve" }));

    await waitFor(() => expect(api.post).toHaveBeenCalledWith(
      "/essay/admin/dlq/entry-1/resolve/", { reason: "Handled manually." },
    ));
  });
});

describe("DLQ list page — bulk retry", () => {
  it("shows a dry-run preview before retrying anything", async () => {
    mockList();
    const postSpy = jest.spyOn(api, "post").mockResolvedValue({
      data: { success: true, data: { dry_run: true, would_dispatch_count: 2, total_matching: 2, capped: false, sample: [{ id: "e1", task_name: "evaluate_essay", error: "x" }] } },
    } as any);
    const user = userEvent.setup();
    render(<AdminDLQPage />);
    await waitFor(() => expect(screen.getByText("evaluate_essay")).toBeInTheDocument());

    await user.click(screen.getByRole("button", { name: /Bulk retry/ }));
    await waitFor(() => expect(postSpy).toHaveBeenCalledWith("/essay/admin/dlq/bulk-retry/", { dry_run: true }));
    await waitFor(() => expect(screen.getByText(/will retry/)).toBeInTheDocument());
  });

  it("confirming requires a reason before dispatching", async () => {
    mockList();
    jest.spyOn(api, "post").mockResolvedValue({
      data: { success: true, data: { dry_run: true, would_dispatch_count: 1, total_matching: 1, capped: false, sample: [] } },
    } as any);
    const user = userEvent.setup();
    render(<AdminDLQPage />);
    await waitFor(() => expect(screen.getByText("evaluate_essay")).toBeInTheDocument());

    await user.click(screen.getByRole("button", { name: /Bulk retry/ }));
    await waitFor(() => expect(screen.getByText(/will retry/)).toBeInTheDocument());
    const dialog = screen.getByRole("dialog");
    await user.click(within(dialog).getByRole("button", { name: /Retry 1 entrie/ }));

    expect(mockToastError).toHaveBeenCalledWith("A reason is required to bulk-retry DLQ entries.");
  });

  it("confirming with a reason dispatches with dry_run=false", async () => {
    mockList();
    const postSpy = jest.spyOn(api, "post")
      .mockResolvedValueOnce({
        data: { success: true, data: { dry_run: true, would_dispatch_count: 1, total_matching: 1, capped: false, sample: [] } },
      } as any)
      .mockResolvedValueOnce({
        data: { success: true, data: { dry_run: false, dispatched_count: 1, total_matching: 1, capped: false } },
      } as any);
    const user = userEvent.setup();
    render(<AdminDLQPage />);
    await waitFor(() => expect(screen.getByText("evaluate_essay")).toBeInTheDocument());

    await user.click(screen.getByRole("button", { name: /Bulk retry/ }));
    await waitFor(() => expect(screen.getByText(/will retry/)).toBeInTheDocument());
    const dialog = screen.getByRole("dialog");
    await user.type(within(dialog).getByPlaceholderText("Why are these being bulk-retried?"), "Root cause fixed.");
    await user.click(within(dialog).getByRole("button", { name: /Retry 1 entrie/ }));

    await waitFor(() => expect(postSpy).toHaveBeenLastCalledWith(
      "/essay/admin/dlq/bulk-retry/", { dry_run: false, reason: "Root cause fixed." },
    ));
    await waitFor(() => expect(mockToastSuccess).toHaveBeenCalledWith("Retried 1 entrie(s)."));
  });
});
