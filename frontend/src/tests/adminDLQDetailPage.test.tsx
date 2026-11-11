/**
 * @jest-environment jsdom
 *
 * Essay Writing — admin DLQ detail page (Phase 12, Task 12.2): the full
 * original task payload (args, kwargs, traceback), plus retry/resolve
 * actions.
 */

const mockParams = { entry_id: "entry-1" };
jest.mock("next/navigation", () => ({
  useRouter: () => ({ push: jest.fn() }),
  useParams: () => mockParams,
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
import AdminDLQDetailPage from "@/app/admin/essay-writing/dlq/[entry_id]/page";
import type { EssayDLQEntryDetail } from "@/types";

const ENTRY: EssayDLQEntryDetail = {
  id: "entry-1", task_name: "evaluate_essay", attempts: 3, dlq_retry_count: 1,
  error: "LLM permanent error: content policy violation", resolved: false, resolved_at: null,
  created_at: "2026-09-22T10:00:00Z", task_id: "task-uuid-1",
  args: ["sub-1"], kwargs: { inline_retry_count: 2 },
  traceback: "Traceback (most recent call last):\n  ...\nRuntimeError: boom",
};

function mockDetail(overrides: Partial<EssayDLQEntryDetail> = {}) {
  jest.spyOn(api, "get").mockImplementation((url: string) => {
    if (url.includes("/essay/admin/dlq/entry-1/")) {
      return Promise.resolve({ data: { data: { ...ENTRY, ...overrides } } } as any);
    }
    return Promise.reject(new Error(`unexpected GET ${url}`));
  });
}

beforeEach(() => {
  mockToastError.mockClear();
  mockToastSuccess.mockClear();
});

afterEach(() => {
  jest.restoreAllMocks();
});

describe("DLQ detail page", () => {
  it("renders the full task payload", async () => {
    mockDetail();
    render(<AdminDLQDetailPage />);
    await waitFor(() => expect(screen.getByText("LLM permanent error: content policy violation")).toBeInTheDocument());
    expect(screen.getByText(/"sub-1"/)).toBeInTheDocument();
    expect(screen.getByText(/inline_retry_count/)).toBeInTheDocument();
    expect(screen.getByText(/RuntimeError: boom/)).toBeInTheDocument();
    expect(screen.getByText("task-uuid-1")).toBeInTheDocument();
  });

  it("disables Retry and Resolve once already resolved", async () => {
    mockDetail({ resolved: true, resolved_at: "2026-09-22T12:00:00Z" });
    render(<AdminDLQDetailPage />);
    await waitFor(() => expect(screen.getByText("LLM permanent error: content policy violation")).toBeInTheDocument());
    expect(screen.getByRole("button", { name: /Retry/ })).toBeDisabled();
    expect(screen.getByRole("button", { name: /Resolve/ })).toBeDisabled();
  });

  it("submits a retry with a reason", async () => {
    mockDetail();
    jest.spyOn(api, "post").mockResolvedValue({ data: { success: true, message: "Retry dispatched." } } as any);
    const user = userEvent.setup();
    render(<AdminDLQDetailPage />);
    await waitFor(() => expect(screen.getByText("LLM permanent error: content policy violation")).toBeInTheDocument());

    await user.click(screen.getByRole("button", { name: /^Retry/ }));
    const dialog = screen.getByRole("dialog");
    await user.type(screen.getByPlaceholderText("Why?"), "Root cause fixed.");
    await user.click(within(dialog).getByRole("button", { name: "Retry" }));

    await waitFor(() => expect(api.post).toHaveBeenCalledWith(
      "/essay/admin/dlq/entry-1/retry/", { reason: "Root cause fixed." },
    ));
  });
});
