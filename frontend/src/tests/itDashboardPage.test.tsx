/**
 * @jest-environment jsdom
 *
 * Coverage for the IT Dashboard page (2026-11-14) — composes two services'
 * own stats endpoints (auth-service: departments/admins/super_admins;
 * user-service: students/batches/sections) and merges the department
 * breakdowns from each against auth-service's official department list.
 */

jest.mock("next/navigation", () => ({
  useRouter: () => ({ push: jest.fn() }),
}));

jest.mock("@/components/layout/ITLayout", () => ({
  ITLayout: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}));

const mockToastError = jest.fn();
jest.mock("@/components/ui/Toast", () => ({
  useToast: () => ({ success: jest.fn(), error: mockToastError }),
}));

import React from "react";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import api from "@/lib/api";
import ITDashboardPage from "@/app/it/dashboard/page";

function authResponse(overrides: Record<string, unknown> = {}) {
  return {
    data: {
      data: {
        departments: {
          total: 2, active: 2, inactive: 0,
          list: [
            { code: "CSE", name: "Computer Science", is_active: true },
            { code: "ECE", name: "Electronics", is_active: true },
          ],
        },
        admins: {
          total: 3, active: 2, inactive: 1,
          by_department: [{ department: "CSE", total: 3, active: 2, inactive: 1 }],
        },
        super_admins: { total: 1, active: 1, inactive: 0 },
        ...overrides,
      },
    },
  };
}

function userResponse(overrides: Record<string, unknown> = {}) {
  return {
    data: {
      data: {
        students: {
          total: 10, active: 9, inactive: 1,
          by_department: [{ department: "CSE", total: 10, active: 9, inactive: 1 }],
          by_section: [{ section: "A", total: 10, active: 9, inactive: 1 }],
        },
        sections_per_department: [{ department: "CSE", sections: ["A"], section_count: 1 }],
        batches: [
          {
            id: "b-1", batch_name: "2023-27", total: 10, active: 9, inactive: 1,
            by_department: [{ department: "CSE", total: 10, active: 9, inactive: 1 }],
            by_section: [{ section: "A", total: 10, active: 9, inactive: 1 }],
          },
        ],
        ...overrides,
      },
    },
  };
}

function mockApiGet(auth = authResponse(), user = userResponse()) {
  return jest.spyOn(api, "get").mockImplementation((url: string) => {
    if (url === "/auth/dashboard-stats/") return Promise.resolve(auth) as any;
    if (url === "/users/it/dashboard-stats/") return Promise.resolve(user) as any;
    return Promise.reject(new Error(`unexpected GET ${url}`));
  });
}

afterEach(() => {
  jest.restoreAllMocks();
  mockToastError.mockClear();
});

describe("IT Dashboard page", () => {
  it("renders the overview stat tiles from both services' responses", async () => {
    mockApiGet();
    render(<ITDashboardPage />);

    await waitFor(() => expect(screen.getByText("Dashboard")).toBeInTheDocument());

    // Each stat tile is its label <p> with the value <p> as its previous
    // sibling — scoping this way avoids ambiguity with the same numbers
    // appearing again in the detail tables further down the page.
    function statTileValue(label: string): string | null | undefined {
      return screen.getByText(label, { selector: "p" }).previousElementSibling?.textContent;
    }

    await waitFor(() => expect(statTileValue("Students")).toBe("10"));
    expect(statTileValue("Admins")).toBe("3");
    expect(statTileValue("Super Admins")).toBe("1");
    expect(statTileValue("Batches")).toBe("1");
    expect(statTileValue("Departments")).toBe("2");
  });

  it("shows a distinct error state (not stuck loading) when either fetch fails", async () => {
    jest.spyOn(api, "get").mockRejectedValue(new Error("network error"));
    render(<ITDashboardPage />);

    await waitFor(() => expect(screen.getByText("Couldn't load the dashboard")).toBeInTheDocument());
    expect(mockToastError).toHaveBeenCalled();
  });

  it("merges a department with zero current admins/students in as a real 0 row, not omitted", async () => {
    // ECE has no admins and no students in either breakdown, but it IS a
    // real department (in the official list) — must still appear in both
    // tables, as a 0 row, not silently dropped.
    mockApiGet();
    render(<ITDashboardPage />);

    await waitFor(() => expect(screen.getAllByText("Electronics").length).toBeGreaterThan(0));
    const eceRows = screen.getAllByText("Electronics").map(el => el.closest("tr"));
    expect(eceRows.length).toBe(2); // admins-by-department row + students-by-department row
    for (const row of eceRows) {
      expect(row).not.toBeNull();
      expect(row!.textContent).toContain("0");
    }
  });

  it("flags a department string in the breakdown that matches no real department", async () => {
    mockApiGet(
      authResponse({
        admins: {
          total: 1, active: 1, inactive: 0,
          by_department: [{ department: "MECH", total: 1, active: 1, inactive: 0 }],
        },
      }),
    );
    render(<ITDashboardPage />);

    await waitFor(() => expect(screen.getByText(/department that no longer exists/)).toBeInTheDocument());
    expect(screen.getByText(/"MECH" \(1\)/)).toBeInTheDocument();
  });

  it("does not show the data-quality warning when every breakdown entry matches a real department", async () => {
    mockApiGet();
    render(<ITDashboardPage />);

    await waitFor(() => expect(screen.getByText("Dashboard")).toBeInTheDocument());
    expect(screen.queryByText(/department that no longer exists/)).not.toBeInTheDocument();
  });

  it("expands a batch row on click to reveal its own department/section breakdown", async () => {
    // "By department" already appears twice (Admins section + Students
    // section are always visible) and "By section" once (Students only) —
    // expanding the batch row adds one MORE of each, its own nested
    // breakdown, rather than being the only place these labels exist.
    mockApiGet();
    const user = userEvent.setup();
    render(<ITDashboardPage />);

    await waitFor(() => expect(screen.getByText("2023-27")).toBeInTheDocument());
    expect(screen.getAllByText("By department")).toHaveLength(2);
    expect(screen.getAllByText("By section")).toHaveLength(1);

    await user.click(screen.getByText("2023-27"));

    await waitFor(() => expect(screen.getAllByText("By department")).toHaveLength(3));
    expect(screen.getAllByText("By section")).toHaveLength(2);
  });

  it("shows the empty state when there are no batches yet", async () => {
    mockApiGet(authResponse(), userResponse({ batches: [] }));
    render(<ITDashboardPage />);

    await waitFor(() => expect(screen.getByText("No batches created yet.")).toBeInTheDocument());
  });
});
