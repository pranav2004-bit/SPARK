/**
 * @jest-environment jsdom
 *
 * Production-readiness audit (2026-11-15): before not-found.tsx/error.tsx
 * existed, a genuinely unmatched route or an unhandled render crash fell
 * through to Next.js's own bare, unstyled default page — no SPARK branding
 * at all, the only unbranded error state in an app whose other one
 * (public/offline.html) was already properly designed. These two files are
 * this app's own branded replacements.
 */

const pushMock = jest.fn();
jest.mock("next/navigation", () => ({
  useRouter: () => ({ push: pushMock }),
}));

import React from "react";
import { render, screen, fireEvent } from "@testing-library/react";
import NotFound from "@/app/not-found";
import ErrorBoundary from "@/app/error";

afterEach(() => {
  jest.restoreAllMocks();
  pushMock.mockClear();
});

describe("not-found.tsx", () => {
  it("shows the branded message, not Next's default bare text", () => {
    render(<NotFound />);
    expect(screen.getByText("Page not found")).toBeInTheDocument();
    expect(screen.queryByText("This page could not be found.")).not.toBeInTheDocument();
  });

  it("\"Go to Homepage\" navigates to \"/\"", () => {
    render(<NotFound />);
    fireEvent.click(screen.getByText("Go to Homepage"));
    expect(pushMock).toHaveBeenCalledWith("/");
  });
});

describe("error.tsx", () => {
  const error = Object.assign(new Error("boom"), { digest: "abc123" });

  it("shows a clean message, never the raw error's own message/stack", () => {
    render(<ErrorBoundary error={error} reset={jest.fn()} />);
    expect(screen.getByText("Something went wrong")).toBeInTheDocument();
    expect(screen.queryByText("boom")).not.toBeInTheDocument();
    expect(screen.queryByText(/abc123/)).not.toBeInTheDocument();
  });

  it("\"Try Again\" calls the provided reset()", () => {
    const reset = jest.fn();
    render(<ErrorBoundary error={error} reset={reset} />);
    fireEvent.click(screen.getByText("Try Again"));
    expect(reset).toHaveBeenCalledTimes(1);
  });

  it("\"Go to Homepage\" navigates to \"/\"", () => {
    render(<ErrorBoundary error={error} reset={jest.fn()} />);
    fireEvent.click(screen.getByText("Go to Homepage"));
    expect(pushMock).toHaveBeenCalledWith("/");
  });
});
