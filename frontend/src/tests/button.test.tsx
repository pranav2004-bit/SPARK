/**
 * @jest-environment jsdom
 *
 * Regression tests for two live UI reports (2026-08-18) against the shared
 * Button component: (1) a "ghost" variant button (e.g. "Responses" in the
 * admin results table) read as plain inert text, not a clickable button —
 * it had no border/background AND used the same muted gray as body text.
 * (2) a loading button showed the browser's "not-allowed" (blocked) cursor
 * on top of its own spinner, reading as broken rather than "please wait."
 */

import React from "react";
import { render, screen } from "@testing-library/react";
import { Button } from "@/components/ui/Button";

describe("Button — ghost variant reads as clickable", () => {
  it("uses the accent color at rest, not the muted body-text color", () => {
    render(<Button variant="ghost">Responses</Button>);
    const button = screen.getByRole("button", { name: "Responses" });
    expect(button.className).toContain("text-[var(--color-accent)]");
    expect(button.className).not.toContain("text-[var(--color-text-muted)]");
  });
});

describe("Button — loading vs. genuinely disabled cursor", () => {
  it("loading shows a wait cursor, not the blocked/not-allowed cursor", () => {
    render(<Button loading>Responses</Button>);
    const button = screen.getByRole("button", { name: "Responses" });
    expect(button).toBeDisabled();
    expect(button.className).toContain("disabled:cursor-wait");
    expect(button.className).not.toContain("disabled:cursor-not-allowed");
  });

  it("loading swaps in a spinner in place of any leftIcon", () => {
    render(<Button loading leftIcon={<span data-testid="left-icon" />}>Responses</Button>);
    expect(screen.queryByTestId("left-icon")).not.toBeInTheDocument();
    // Loader2 renders as an <svg> — assert via the button's own child count/role instead of a brittle class lookup.
    const button = screen.getByRole("button", { name: "Responses" });
    expect(button.querySelector("svg")).toBeInTheDocument();
  });

  it("a genuinely disabled (not loading) button keeps the not-allowed cursor", () => {
    render(<Button disabled>Responses</Button>);
    const button = screen.getByRole("button", { name: "Responses" });
    expect(button).toBeDisabled();
    expect(button.className).toContain("disabled:cursor-not-allowed");
    expect(button.className).not.toContain("disabled:cursor-wait");
  });

  it("disabled AND loading together still reads as genuinely disabled, not just waiting", () => {
    render(<Button disabled loading>Responses</Button>);
    const button = screen.getByRole("button", { name: "Responses" });
    expect(button.className).toContain("disabled:cursor-not-allowed");
    expect(button.className).not.toContain("disabled:cursor-wait");
  });

  it("neither disabled nor loading — plain pointer cursor, no wait/not-allowed classes", () => {
    render(<Button>Responses</Button>);
    const button = screen.getByRole("button", { name: "Responses" });
    expect(button).not.toBeDisabled();
    expect(button.className).not.toContain("disabled:cursor-wait");
    expect(button.className).not.toContain("disabled:cursor-not-allowed");
  });
});
