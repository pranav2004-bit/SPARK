/**
 * @jest-environment jsdom
 *
 * Regression test for the Assessments landing page (4 module cards —
 * Assessments/Results/Analytics/Dashboard — added in response to a direct
 * request: the "Assessments" nav previously jumped straight to the papers
 * list with no hub page; Dashboard was added as a 4th card in a follow-up
 * request after Results/Analytics landed first). Verifies all four cards
 * render with the right labels and navigate to the right route on click,
 * so a future edit can't silently drop one or point a card at the wrong
 * destination.
 */

const mockPush = jest.fn();
jest.mock("next/navigation", () => ({
  useRouter: () => ({ push: mockPush }),
}));

jest.mock("@/components/layout/AdminLayout", () => ({
  AdminLayout: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}));

import React from "react";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import AdminAssessmentsLandingPage from "@/app/admin/assessments/page";

beforeEach(() => {
  mockPush.mockClear();
});

describe("Assessments landing page — 4 module cards", () => {
  it("renders all four cards", () => {
    render(<AdminAssessmentsLandingPage />);
    expect(screen.getByRole("button", { name: /^Question Bank/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^Results/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^Analytics/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^Dashboard/ })).toBeInTheDocument();
  });

  it("navigates to the papers list when the Question Bank card is clicked", async () => {
    const user = userEvent.setup();
    render(<AdminAssessmentsLandingPage />);
    await user.click(screen.getByRole("button", { name: /^Question Bank/ }));
    expect(mockPush).toHaveBeenCalledWith("/admin/assessments/papers");
  });

  it("navigates to the results list when the Results card is clicked", async () => {
    const user = userEvent.setup();
    render(<AdminAssessmentsLandingPage />);
    await user.click(screen.getByRole("button", { name: /^Results/ }));
    expect(mockPush).toHaveBeenCalledWith("/admin/assessments/results");
  });

  it("navigates to the analytics list when the Analytics card is clicked", async () => {
    const user = userEvent.setup();
    render(<AdminAssessmentsLandingPage />);
    await user.click(screen.getByRole("button", { name: /^Analytics/ }));
    expect(mockPush).toHaveBeenCalledWith("/admin/assessments/analytics");
  });

  it("navigates to the dashboard list when the Dashboard card is clicked", async () => {
    const user = userEvent.setup();
    render(<AdminAssessmentsLandingPage />);
    await user.click(screen.getByRole("button", { name: /^Dashboard/ }));
    expect(mockPush).toHaveBeenCalledWith("/admin/assessments/dashboard");
  });
});
