/**
 * @jest-environment jsdom
 *
 * GlobalFooter is mounted once, unconditionally, in the root layout
 * (src/app/layout.tsx) — it used to render on every single route in the
 * app. Restricted (2026-11-14, user decision) to the application's own
 * home page ("/") only, since it's branding for the public landing page,
 * not something that belongs on every authenticated admin/student/
 * super-admin/IT screen.
 */

let mockPathname = "/";
jest.mock("next/navigation", () => ({
  usePathname: () => mockPathname,
}));

import React from "react";
import { render, screen } from "@testing-library/react";
import { GlobalFooter } from "@/components/layout/GlobalFooter";

describe("GlobalFooter — shown only on the application home page", () => {
  it("renders on the home page (\"/\")", () => {
    mockPathname = "/";
    const { container } = render(<GlobalFooter />);
    expect(container.querySelector("footer")).not.toBeNull();
    expect(screen.getByText("SANJIVO")).toBeInTheDocument();
    expect(screen.getByText("AuraTech-Vision")).toBeInTheDocument();
  });

  it("does not render on an admin portal page", () => {
    mockPathname = "/admin/assessments/papers";
    const { container } = render(<GlobalFooter />);
    expect(container).toBeEmptyDOMElement();
  });

  it("does not render on a student portal page", () => {
    mockPathname = "/students/home";
    const { container } = render(<GlobalFooter />);
    expect(container).toBeEmptyDOMElement();
  });

  it("does not render on a marketing/info page other than the home page", () => {
    mockPathname = "/about";
    const { container } = render(<GlobalFooter />);
    expect(container).toBeEmptyDOMElement();
  });
});
