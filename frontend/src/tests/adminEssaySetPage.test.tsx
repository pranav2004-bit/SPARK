/**
 * @jest-environment jsdom
 *
 * Essay set detail page (Phase 2) — the single-prompt editor. Covers both
 * states EssayQuestion's OneToOneField creates: no prompt yet (create form)
 * and an existing prompt (edit form), since this page's behavior genuinely
 * branches on that, unlike a typical CRUD list page.
 */

const mockPush = jest.fn();
const mockParams = { paper_id: "paper-1", set_id: "set-1" };
jest.mock("next/navigation", () => ({
  useRouter: () => ({ push: mockPush }),
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
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import api from "@/lib/api";
import AdminEssaySetPage from "@/app/admin/essay-writing/papers/[paper_id]/sets/[set_id]/page";

const PAPER = { id: "paper-1", title: "Persuasive Writing", description: "", set_count: 1, created_by: "u1", created_at: "t", updated_at: "t" };

function setDetailResponse(question: any) {
  return {
    data: {
      data: {
        set: { id: "set-1", paper: "paper-1", label: "Set A", order: 1, has_question: !!question },
        paper: PAPER,
        question,
      },
    },
  };
}

beforeEach(() => {
  mockPush.mockClear();
  mockToastError.mockClear();
  mockToastSuccess.mockClear();
});

afterEach(() => {
  jest.restoreAllMocks();
});

describe("Essay set page — no prompt yet", () => {
  it("shows the empty state and a create form", async () => {
    jest.spyOn(api, "get").mockResolvedValue(setDetailResponse(null) as any);

    render(<AdminEssaySetPage />);

    await waitFor(() => expect(screen.getByText("No prompt authored yet")).toBeInTheDocument());
    expect(screen.getByRole("button", { name: "Create prompt" })).toBeInTheDocument();
  });

  it("rejects an empty prompt without calling the API", async () => {
    jest.spyOn(api, "get").mockResolvedValue(setDetailResponse(null) as any);
    const postSpy = jest.spyOn(api, "post");
    const user = userEvent.setup();

    render(<AdminEssaySetPage />);
    await waitFor(() => expect(screen.getByRole("button", { name: "Create prompt" })).toBeInTheDocument());

    await user.click(screen.getByRole("button", { name: "Create prompt" }));

    expect(screen.getByText("The essay prompt cannot be empty.")).toBeInTheDocument();
    expect(postSpy).not.toHaveBeenCalled();
  });

  it("creates a prompt with valid input", async () => {
    jest.spyOn(api, "get").mockResolvedValue(setDetailResponse(null) as any);
    const postSpy = jest.spyOn(api, "post").mockResolvedValue({
      data: {
        data: {
          id: "q1", set: "set-1", question_text: "Describe a challenge.",
          llm_rubric_prompt: "Score clarity.", word_limit: 500,
          time_limit_minutes: 30, max_score: 10, created_at: "t", updated_at: "t",
        },
      },
    } as any);
    const user = userEvent.setup();

    render(<AdminEssaySetPage />);
    await waitFor(() => expect(screen.getByRole("button", { name: "Create prompt" })).toBeInTheDocument());

    await user.type(screen.getByPlaceholderText(/Describe a time you overcame/), "Describe a challenge.");
    await user.type(screen.getByPlaceholderText(/Score for clarity, structure/), "Score clarity.");
    await user.click(screen.getByRole("button", { name: "Create prompt" }));

    await waitFor(() => expect(postSpy).toHaveBeenCalledWith("/essay/admin/sets/set-1/question/", {
      question_text: "Describe a challenge.", llm_rubric_prompt: "Score clarity.",
      word_limit: 500, time_limit_minutes: 30, max_score: 10,
    }));
    expect(mockToastSuccess).toHaveBeenCalledWith("Prompt created.");
  });
});

describe("Essay set page — existing prompt", () => {
  const EXISTING_QUESTION = {
    id: "q1", set: "set-1", question_text: "Existing prompt text",
    llm_rubric_prompt: "Existing rubric", word_limit: 400,
    time_limit_minutes: 25, max_score: 10, created_at: "t", updated_at: "t",
  };

  it("prefills the form and shows Save changes + Delete prompt", async () => {
    jest.spyOn(api, "get").mockResolvedValue(setDetailResponse(EXISTING_QUESTION) as any);

    render(<AdminEssaySetPage />);

    await waitFor(() => expect(screen.getByDisplayValue("Existing prompt text")).toBeInTheDocument());
    expect(screen.getByDisplayValue("Existing rubric")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Save changes" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Delete prompt/ })).toBeInTheDocument();
    expect(screen.queryByText("No prompt authored yet")).not.toBeInTheDocument();
  });

  it("saves an edit via PATCH", async () => {
    jest.spyOn(api, "get").mockResolvedValue(setDetailResponse(EXISTING_QUESTION) as any);
    const patchSpy = jest.spyOn(api, "patch").mockResolvedValue({
      data: { data: { ...EXISTING_QUESTION, question_text: "Updated prompt text" } },
    } as any);
    const user = userEvent.setup();

    render(<AdminEssaySetPage />);
    await waitFor(() => expect(screen.getByDisplayValue("Existing prompt text")).toBeInTheDocument());

    const textarea = screen.getByDisplayValue("Existing prompt text");
    await user.clear(textarea);
    await user.type(textarea, "Updated prompt text");
    await user.click(screen.getByRole("button", { name: "Save changes" }));

    await waitFor(() => expect(patchSpy).toHaveBeenCalledWith(
      "/essay/admin/questions/q1/",
      expect.objectContaining({ question_text: "Updated prompt text" }),
    ));
    expect(mockToastSuccess).toHaveBeenCalledWith("Prompt updated.");
  });
});
