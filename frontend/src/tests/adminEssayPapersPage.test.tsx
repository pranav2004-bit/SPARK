/**
 * @jest-environment jsdom
 *
 * Essay Writing — Question Bank list page (Phase 2, essay-service).
 * Mirrors adminPapersPage.test.tsx's load/empty/error-state coverage
 * convention, minus the ownership-lock suite — essay-service has no
 * per-paper ownership restriction (core/permissions.py's IsAdminOrSuperAdmin
 * docstring), so every card here is always fully interactive.
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
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import api from "@/lib/api";
import AdminEssayPapersPage from "@/app/admin/essay-writing/papers/page";

const PAPERS_LIST_RESPONSE = {
  data: {
    count: 1, total_pages: 1, current_page: 1, next: null, previous: null,
    results: [{
      id: "990e26ff-6012-4f91-814e-51db6a9eed16",
      title: "Persuasive Writing — Round 1",
      description: "",
      set_count: 2,
      created_by: "3512eb9e-c81e-4bc5-a401-e0816acc862c",
      created_at: "2026-09-20T14:45:44.867509Z",
      updated_at: "2026-09-20T14:45:44.875419Z",
    }],
  },
};

beforeEach(() => {
  mockPush.mockClear();
  mockToastError.mockClear();
  mockToastSuccess.mockClear();
});

afterEach(() => {
  jest.restoreAllMocks();
});

describe("Admin essay papers list — load states", () => {
  it("renders a paper from the real (unwrapped) pagination response", async () => {
    jest.spyOn(api, "get").mockResolvedValue(PAPERS_LIST_RESPONSE as any);

    render(<AdminEssayPapersPage />);

    await waitFor(() => {
      expect(screen.getByText("Persuasive Writing — Round 1")).toBeInTheDocument();
    });
    expect(screen.queryByText("No essay papers yet")).not.toBeInTheDocument();
    expect(mockToastError).not.toHaveBeenCalled();
  });

  it("shows the genuine empty state when there are zero papers", async () => {
    jest.spyOn(api, "get").mockResolvedValue({
      data: { count: 0, total_pages: 1, current_page: 1, next: null, previous: null, results: [] },
    } as any);

    render(<AdminEssayPapersPage />);

    await waitFor(() => {
      expect(screen.getByText("No essay papers yet")).toBeInTheDocument();
    });
    expect(mockToastError).not.toHaveBeenCalled();
  });

  it("shows a distinct error state (not the empty state) when the fetch fails", async () => {
    jest.spyOn(api, "get").mockRejectedValue(new Error("network error"));

    render(<AdminEssayPapersPage />);

    await waitFor(() => {
      expect(screen.getByText("Couldn't load essay papers")).toBeInTheDocument();
    });
    expect(screen.queryByText("No essay papers yet")).not.toBeInTheDocument();
    expect(mockToastError).toHaveBeenCalledWith("Failed to load essay papers.");
  });

  it("retrying after a failure re-fetches and renders the data on success", async () => {
    const getSpy = jest.spyOn(api, "get")
      .mockRejectedValueOnce(new Error("network error"))
      .mockResolvedValueOnce(PAPERS_LIST_RESPONSE as any);
    const user = userEvent.setup({ delay: null });

    render(<AdminEssayPapersPage />);
    await waitFor(() => expect(screen.getByText("Couldn't load essay papers")).toBeInTheDocument());

    await user.click(screen.getByRole("button", { name: "Retry" }));

    await waitFor(() => expect(screen.getByText("Persuasive Writing — Round 1")).toBeInTheDocument());
    expect(getSpy).toHaveBeenCalledTimes(2);
  });
});

describe("Admin essay papers list — navigation and creation", () => {
  it("navigates to the paper detail page on card click", async () => {
    jest.spyOn(api, "get").mockResolvedValue(PAPERS_LIST_RESPONSE as any);
    const user = userEvent.setup({ delay: null });

    render(<AdminEssayPapersPage />);
    await waitFor(() => expect(screen.getByText("Persuasive Writing — Round 1")).toBeInTheDocument());

    await user.click(screen.getByText("Persuasive Writing — Round 1"));
    expect(mockPush).toHaveBeenCalledWith("/admin/essay-writing/papers/990e26ff-6012-4f91-814e-51db6a9eed16");
  });

  it("creates a new paper via the modal and prepends it to the list", async () => {
    jest.spyOn(api, "get").mockResolvedValue({
      data: { count: 0, total_pages: 1, current_page: 1, next: null, previous: null, results: [] },
    } as any);
    const postSpy = jest.spyOn(api, "post").mockResolvedValue({
      data: {
        success: true,
        data: {
          id: "new-paper-id", title: "New Essay Paper", description: "",
          set_count: 0, created_by: "u1",
          created_at: "2026-09-20T00:00:00Z", updated_at: "2026-09-20T00:00:00Z",
        },
      },
    } as any);
    const user = userEvent.setup({ delay: null });

    render(<AdminEssayPapersPage />);
    await waitFor(() => expect(screen.getByText("No essay papers yet")).toBeInTheDocument());

    await user.click(screen.getByRole("button", { name: "+ New Paper" }));
    await user.type(screen.getByLabelText("Title"), "New Essay Paper");
    await user.click(screen.getByRole("button", { name: "Create" }));

    await waitFor(() => expect(screen.getByText("New Essay Paper")).toBeInTheDocument());
    expect(postSpy).toHaveBeenCalledWith("/essay/admin/papers/", { title: "New Essay Paper", description: "" });
    expect(mockToastSuccess).toHaveBeenCalledWith("Essay paper created.");
  });
});
