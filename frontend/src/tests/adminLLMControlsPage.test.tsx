/**
 * @jest-environment jsdom
 *
 * Essay Writing — admin LLM Controls page (Phase 7, Task 7.2): the
 * analytics dashboard (provider/model, evaluation count + average score,
 * malformed-response DLQ count, retrigger count).
 */

jest.mock("next/navigation", () => ({
  useRouter: () => ({ push: jest.fn() }),
}));

jest.mock("@/components/layout/AdminLayout", () => ({
  AdminLayout: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}));

const mockToastError = jest.fn();
jest.mock("@/components/ui/Toast", () => ({
  useToast: () => ({ error: mockToastError, success: jest.fn() }),
}));

import React from "react";
import { render, screen, waitFor } from "@testing-library/react";
import api from "@/lib/api";
import AdminLLMControlsPage from "@/app/admin/essay-writing/llm-controls/page";
import type { EssayLLMAnalytics } from "@/types";

const BASE_ANALYTICS: EssayLLMAnalytics = {
  provider: "OpenAI", model: "gpt-4o-mini",
  evaluation_count: 42, average_score: 7.35,
  malformed_response_dlq_count: 3, retrigger_count: 5,
};

function mockAnalytics(overrides: Partial<EssayLLMAnalytics> = {}) {
  jest.spyOn(api, "get").mockImplementation((url: string) => {
    if (url.includes("/essay/admin/llm-controls/analytics/")) {
      return Promise.resolve({ data: { data: { ...BASE_ANALYTICS, ...overrides } } } as any);
    }
    return Promise.reject(new Error(`unexpected GET ${url}`));
  });
}

beforeEach(() => {
  mockToastError.mockClear();
});

afterEach(() => {
  jest.restoreAllMocks();
});

describe("LLM Controls page", () => {
  it("renders provider, model, and all four stat tiles", async () => {
    mockAnalytics();
    render(<AdminLLMControlsPage />);
    await waitFor(() => expect(screen.getByText("OpenAI")).toBeInTheDocument());
    expect(screen.getByText("gpt-4o-mini")).toBeInTheDocument();
    expect(screen.getByText("42")).toBeInTheDocument();
    expect(screen.getByText("7.35/10")).toBeInTheDocument();
    expect(screen.getByText("3")).toBeInTheDocument();
    expect(screen.getByText("5")).toBeInTheDocument();
  });

  it("shows an em-dash for average score when there have been no evaluations yet", async () => {
    mockAnalytics({ evaluation_count: 0, average_score: null });
    render(<AdminLLMControlsPage />);
    await waitFor(() => expect(screen.getByText("OpenAI")).toBeInTheDocument());
    expect(screen.getByText("—")).toBeInTheDocument();
  });

  it("shows an error message when analytics fail to load", async () => {
    jest.spyOn(api, "get").mockRejectedValue(new Error("network error"));
    render(<AdminLLMControlsPage />);
    await waitFor(() => expect(screen.getByText(/Couldn't load LLM analytics/)).toBeInTheDocument());
  });
});
