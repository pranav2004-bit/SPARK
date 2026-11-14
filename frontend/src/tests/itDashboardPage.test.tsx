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
import { render, screen, waitFor, within } from "@testing-library/react";
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
        },
        sections_per_department: [{
          department: "CSE", section_count: 1,
          sections: [{ section: "A", total: 10, active: 9, inactive: 1 }],
        }],
        batches: [
          {
            id: "b-1", batch_name: "2023-27", total: 10, active: 9, inactive: 1,
            by_department: [{
              department: "CSE", total: 10, active: 9, inactive: 1,
              sections: [{ section: "A", total: 10, active: 9, inactive: 1 }],
            }],
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

    await waitFor(() => expect(screen.getByText("Students", { selector: "p" })).toBeInTheDocument());
    expect(screen.queryByText(/department that no longer exists/)).not.toBeInTheDocument();
  });

  it("filters the Students department breakdown by batch when a batch is selected", async () => {
    mockApiGet(
      authResponse(),
      userResponse({
        students: { total: 15, active: 14, inactive: 1, by_department: [{ department: "CSE", total: 15, active: 14, inactive: 1 }] },
        batches: [
          {
            // Two departments in this batch so the batch's own aggregate
            // (23, shown unconditionally in the Batches table below) never
            // collides with either department's individual count (6, 17).
            id: "b-1", batch_name: "2023-27", total: 23, active: 21, inactive: 2,
            by_department: [
              { department: "CSE", total: 6, active: 5, inactive: 1, sections: [{ section: "A", total: 6, active: 5, inactive: 1 }] },
              { department: "ECE", total: 17, active: 16, inactive: 1, sections: [{ section: "A", total: 17, active: 16, inactive: 1 }] },
            ],
          },
        ],
      }),
    );
    const user = userEvent.setup();
    render(<ITDashboardPage />);

    await waitFor(() => expect(screen.getByText("Students", { selector: "h2" })).toBeInTheDocument());
    const studentsCard = screen.getByText("Students", { selector: "h2" }).closest(".p-5") as HTMLElement;

    // "All batches" (default) shows the institution-wide breakdown (15),
    // not any one batch's own count (6).
    expect(within(studentsCard).getByText("15")).toBeInTheDocument();
    expect(within(studentsCard).queryByText("6")).not.toBeInTheDocument();

    await user.selectOptions(within(studentsCard).getByDisplayValue("All batches"), "b-1");

    // Picking a batch switches to THAT batch's own breakdown (6 and 17) —
    // the institution-wide total (15) no longer renders in this table.
    expect(await within(studentsCard).findByText("6")).toBeInTheDocument();
    expect(within(studentsCard).getByText("17")).toBeInTheDocument();
    expect(within(studentsCard).queryByText("15")).not.toBeInTheDocument();
  });

  it("expands a batch row on click to reveal its own by-department table", async () => {
    // "By department" already appears twice (Admins section + Students
    // section are always visible) — expanding the batch row adds its own
    // one-off "By department" table (no more flat "By section" tally).
    mockApiGet();
    const user = userEvent.setup();
    render(<ITDashboardPage />);

    // "2023-27" also appears as an <option> in the Students section's new
    // batch filter dropdown — scope to the <span> the Batches table row
    // actually renders its batch name in, to click the real row.
    await waitFor(() => expect(screen.getByText("2023-27", { selector: "span" })).toBeInTheDocument());
    expect(screen.getAllByText("By department")).toHaveLength(2);

    await user.click(screen.getByText("2023-27", { selector: "span" }));

    await waitFor(() => expect(screen.getAllByText("By department")).toHaveLength(3));
  });

  it("expanding a department row inside an expanded batch reveals that department's own sections, scoped to the batch and department", async () => {
    // Both departments have TWO sections each — so a department's own row
    // total (83 / 77) never collides with either of its own section
    // values (41+42 / 30+47), keeping the "not yet rendered" assertions
    // below unambiguous. Expanding CSE's row inside the batch panel must
    // show only CSE's own section counts, never ECE's.
    mockApiGet(
      authResponse(),
      userResponse({
        sections_per_department: [], // not the focus of this test
        batches: [
          {
            id: "b-1", batch_name: "2023-27", total: 160, active: 152, inactive: 8,
            by_department: [
              {
                department: "CSE", total: 83, active: 79, inactive: 4,
                sections: [{ section: "A", total: 41, active: 39, inactive: 2 }, { section: "B", total: 42, active: 40, inactive: 2 }],
              },
              {
                department: "ECE", total: 77, active: 73, inactive: 4,
                sections: [{ section: "A", total: 30, active: 28, inactive: 2 }, { section: "B", total: 47, active: 45, inactive: 2 }],
              },
            ],
          },
        ],
      }),
    );
    const user = userEvent.setup();
    render(<ITDashboardPage />);

    // "2023-27" also appears as an <option> in the Students section's new
    // batch filter dropdown — scope to the <span> the Batches table row
    // actually renders its batch name in, to click the real row.
    await waitFor(() => expect(screen.getByText("2023-27", { selector: "span" })).toBeInTheDocument());
    await user.click(screen.getByText("2023-27", { selector: "span" }));

    // Both departments' raw codes appear as rows in the batch's own
    // by-department table (the Admins/Students tables above always show
    // the resolved department NAME instead, so "CSE"/"ECE" here are
    // unambiguous). No section breakdown renders until a department row
    // itself is expanded.
    const cseRow = await screen.findByText("CSE").then(el => el.closest("tr"));
    expect(screen.queryByText("41")).not.toBeInTheDocument();

    await user.click(cseRow!);

    // CSE's own section counts (41, 42) appear; ECE's row stays collapsed,
    // so its own section counts (30, 47) never render.
    expect(await screen.findByText("41")).toBeInTheDocument();
    expect(screen.getByText("42")).toBeInTheDocument();
    expect(screen.queryByText("30")).not.toBeInTheDocument();
    expect(screen.queryByText("47")).not.toBeInTheDocument();
  });

  it("shows the empty state when there are no batches yet", async () => {
    mockApiGet(authResponse(), userResponse({ batches: [] }));
    render(<ITDashboardPage />);

    await waitFor(() => expect(screen.getByText("No batches created yet.")).toBeInTheDocument());
  });

});
