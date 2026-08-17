/**
 * @jest-environment jsdom
 *
 * Regression test for a real bug found live (2026-08-13): the admin papers
 * list page parsed its fetch response as `res.data.data.results`, assuming
 * the `{success, data: {...}}` wrapper every other admin endpoint in this
 * codebase uses. `GET /assessments/admin/papers/` actually returns DRF's
 * raw pagination shape directly — `{count, results, ...}`, no wrapper (same
 * shape as the admin results page, which already parses it correctly as
 * `res.data.results`). `res.data.data` was therefore always `undefined`,
 * `.results` on it threw, the catch handler fired, and the page silently
 * rendered "No question papers yet" even when papers genuinely existed —
 * confirmed live: the real API returned a real paper while the UI showed
 * none. This test locks in the fix by asserting against the *real* response
 * shape, not the wrapped one the old code wrongly assumed.
 */

const mockPush = jest.fn();
jest.mock("next/navigation", () => ({
  useRouter: () => ({ push: mockPush }),
}));

// AdminLayout pulls in useAuth/auth-store/its own API calls — all
// irrelevant to this page's own fetch-and-render logic being tested here.
jest.mock("@/components/layout/AdminLayout", () => ({
  AdminLayout: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}));

const mockToastError = jest.fn();
jest.mock("@/components/ui/Toast", () => ({
  useToast: () => ({ error: mockToastError, success: jest.fn() }),
}));

// The page itself (not just AdminLayout) now calls useAuth() directly, to
// decide which paper cards are locked (faculty-privacy restriction — a
// paper's creator or a super admin can open it, no one else). Mutate
// mockAuthStore.user per test to control that.
const mockAuthStore: { user: { id: string; role: string } | null } = { user: null };
jest.mock("@/lib/auth-store", () => ({
  useAuthStore: Object.assign(
    jest.fn(() => mockAuthStore),
    { getState: jest.fn(() => mockAuthStore) },
  ),
}));

import React from "react";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import api from "@/lib/api";
import AdminAssessmentPapersPage from "@/app/admin/assessments/papers/page";

// The real, live-confirmed shape of GET /assessments/admin/papers/ — flat
// DRF pagination, no {success, data} wrapper.
const REAL_PAPERS_LIST_RESPONSE = {
  data: {
    count: 1,
    total_pages: 1,
    current_page: 1,
    next: null,
    previous: null,
    results: [
      {
        id: "990e26ff-6012-4f91-814e-51db6a9eed16",
        title: "MOCK TEST 1",
        description: "this is the trial run",
        is_published: false,
        set_count: 0,
        created_by: "3512eb9e-c81e-4bc5-a401-e0816acc862c",
        created_at: "2026-08-13T14:45:44.867509Z",
        updated_at: "2026-08-13T14:45:44.875419Z",
      },
    ],
  },
};

beforeEach(() => {
  mockPush.mockClear();
  mockToastError.mockClear();
  mockAuthStore.user = { id: "owner-user-id", role: "admin" };
});

afterEach(() => {
  jest.restoreAllMocks();
});

describe("Admin papers list — real API response shape", () => {
  it("renders a paper returned in the real (unwrapped) pagination response", async () => {
    jest.spyOn(api, "get").mockResolvedValue(REAL_PAPERS_LIST_RESPONSE as any);

    render(<AdminAssessmentPapersPage />);

    await waitFor(() => {
      expect(screen.getByText("MOCK TEST 1")).toBeInTheDocument();
    });

    // The old bug's failure mode: falls through to the empty state instead.
    expect(screen.queryByText("No question papers yet")).not.toBeInTheDocument();
    // The old bug's failure mode: a swallowed exception surfaced as this toast.
    expect(mockToastError).not.toHaveBeenCalled();
  });

  it("shows the genuine empty state when there really are zero papers", async () => {
    jest.spyOn(api, "get").mockResolvedValue({
      data: { count: 0, total_pages: 1, current_page: 1, next: null, previous: null, results: [] },
    } as any);

    render(<AdminAssessmentPapersPage />);

    await waitFor(() => {
      expect(screen.getByText("No question papers yet")).toBeInTheDocument();
    });
    expect(mockToastError).not.toHaveBeenCalled();
  });
});

// ── Load failure — must not be confused with genuine emptiness ──────────────
// Regression test for the 2026-08-17 fix: a failed fetch used to fall
// through to the same "No question papers yet" empty state as a genuinely
// empty list, which misleads an admin during a transient backend outage
// into thinking they have no papers at all.
describe("Admin papers list — load failure", () => {
  it("shows a distinct error state (not the empty state) when the fetch fails", async () => {
    jest.spyOn(api, "get").mockRejectedValue(new Error("network error"));

    render(<AdminAssessmentPapersPage />);

    await waitFor(() => {
      expect(screen.getByText("Couldn't load question papers")).toBeInTheDocument();
    });
    expect(screen.queryByText("No question papers yet")).not.toBeInTheDocument();
    expect(mockToastError).toHaveBeenCalledWith("Failed to load question papers.");
  });

  it("retrying after a failure re-fetches and renders the data on success", async () => {
    const getSpy = jest.spyOn(api, "get")
      .mockRejectedValueOnce(new Error("network error"))
      .mockResolvedValueOnce(REAL_PAPERS_LIST_RESPONSE as any);
    const user = userEvent.setup();

    render(<AdminAssessmentPapersPage />);
    await waitFor(() => expect(screen.getByText("Couldn't load question papers")).toBeInTheDocument());

    await user.click(screen.getByRole("button", { name: "Retry" }));

    await waitFor(() => expect(screen.getByText("MOCK TEST 1")).toBeInTheDocument());
    expect(screen.queryByText("Couldn't load question papers")).not.toBeInTheDocument();
    expect(getSpy).toHaveBeenCalledTimes(2);
  });
});

// ── Faculty-privacy restriction — locked cards for non-creator admins ────────
describe("Admin papers list — ownership lock", () => {
  function paperResponse(created_by: string) {
    return {
      data: {
        count: 1, total_pages: 1, current_page: 1, next: null, previous: null,
        results: [{
          id: "990e26ff-6012-4f91-814e-51db6a9eed16",
          title: "MOCK TEST 1",
          description: "",
          set_count: 2,
          created_by,
          created_by_name: "Someone Else",
          created_by_email: "someone@test.com",
          created_at: "2026-08-13T14:45:44.867509Z",
          updated_at: "2026-08-13T14:45:44.875419Z",
        }],
      },
    };
  }

  it("lets the creator open their own paper and shows edit/delete", async () => {
    mockAuthStore.user = { id: "owner-user-id", role: "admin" };
    jest.spyOn(api, "get").mockResolvedValue(paperResponse("owner-user-id") as any);
    const user = userEvent.setup();

    render(<AdminAssessmentPapersPage />);
    await waitFor(() => expect(screen.getByText("MOCK TEST 1")).toBeInTheDocument());

    expect(screen.getByLabelText("Edit")).toBeInTheDocument();
    expect(screen.getByLabelText("Delete")).toBeInTheDocument();
    expect(screen.queryByText("View only")).not.toBeInTheDocument();

    await user.click(screen.getByText("MOCK TEST 1"));
    expect(mockPush).toHaveBeenCalledWith("/admin/assessments/papers/990e26ff-6012-4f91-814e-51db6a9eed16");
  });

  it("locks another admin's paper — no navigation, no edit/delete, shows View only", async () => {
    mockAuthStore.user = { id: "owner-user-id", role: "admin" };
    jest.spyOn(api, "get").mockResolvedValue(paperResponse("someone-elses-user-id") as any);
    const user = userEvent.setup();

    render(<AdminAssessmentPapersPage />);
    await waitFor(() => expect(screen.getByText("MOCK TEST 1")).toBeInTheDocument());

    expect(screen.getByText("View only")).toBeInTheDocument();
    expect(screen.queryByLabelText("Edit")).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Delete")).not.toBeInTheDocument();

    await user.click(screen.getByText("MOCK TEST 1"));
    expect(mockPush).not.toHaveBeenCalled();
  });

  it("a super admin can always open and edit any paper, regardless of creator", async () => {
    mockAuthStore.user = { id: "some-super-admin-id", role: "super_admin" };
    jest.spyOn(api, "get").mockResolvedValue(paperResponse("someone-elses-user-id") as any);
    const user = userEvent.setup();

    render(<AdminAssessmentPapersPage />);
    await waitFor(() => expect(screen.getByText("MOCK TEST 1")).toBeInTheDocument());

    expect(screen.getByLabelText("Edit")).toBeInTheDocument();
    expect(screen.queryByText("View only")).not.toBeInTheDocument();

    await user.click(screen.getByText("MOCK TEST 1"));
    expect(mockPush).toHaveBeenCalledWith("/admin/assessments/papers/990e26ff-6012-4f91-814e-51db6a9eed16");
  });
});
