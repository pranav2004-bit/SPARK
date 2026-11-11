/**
 * @jest-environment jsdom
 *
 * Content bank (LIVETRACKER4 Phase I): question editor saves drafts with
 * If-Match, handles stale ETags (412) by asking for a reload, and confirms
 * publish before calling the API.
 */

const mockParams = { question_id: "q1" };
jest.mock("next/navigation", () => ({
  useParams: () => mockParams,
  useRouter: () => ({ push: jest.fn(), back: jest.fn() }),
}));

jest.mock("@/components/layout/AdminLayout", () => ({
  AdminLayout: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}));

// Stub: renders a single confirm button only while open, so the test drives
// onConfirm without depending on the real dialog's markup.
jest.mock("@/components/ui/ConfirmDialog", () => ({
  ConfirmDialog: (props: { isOpen: boolean; onConfirm: () => void; confirmLabel?: string }) =>
    props.isOpen ? <button onClick={props.onConfirm}>{`Confirm ${props.confirmLabel ?? ""}`}</button> : null,
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
import AdminContentQuestionPage from "@/app/admin/content/questions/[question_id]/page";

const QUESTION = {
  id: "q1", node_id: "n1", display_order: 1, status: "draft",
  current_version_no: 1, published_version_no: null,
  editable_version: {
    version_no: 1, state: "draft", question_text: "What is 1+1?", explanation: "",
    image_key: "", image_url: "", image_alt_text: "",
    options: [
      { label: "A", option_text: "2", is_correct: true, display_order: 1 },
      { label: "B", option_text: "3", is_correct: false, display_order: 2 },
    ],
  },
};

function envelope(data: unknown, etag = '"e1"') {
  return { data: { success: true, data }, headers: { etag } } as any;
}

function conflict(code: string, status: number) {
  return { response: { status, data: { success: false, code, message: "x", errors: {} } } };
}

function mockQuestion() {
  jest.spyOn(api, "get").mockImplementation((url: string) => {
    if (url === "/practice/content/questions/q1/") return Promise.resolve(envelope(QUESTION));
    if (url === "/practice/content/questions/q1/versions/") {
      return Promise.resolve({ data: { success: true, data: [{ version_no: 1, state: "draft", published_at: null }] }, headers: {} } as any);
    }
    return Promise.reject(new Error(`unexpected GET ${url}`));
  });
}

beforeEach(() => {
  mockToastError.mockClear();
  mockToastSuccess.mockClear();
});

afterEach(() => {
  jest.restoreAllMocks();
});

describe("Content question editor", () => {
  it("loads the question into the editor fields", async () => {
    mockQuestion();
    render(<AdminContentQuestionPage />);
    expect(await screen.findByDisplayValue("What is 1+1?")).toBeInTheDocument();
    expect(screen.getByLabelText("Option A text")).toHaveValue("2");
    expect(screen.getByLabelText("Option A is correct")).toBeChecked();
  });

  it("saves the draft with the ETag in If-Match", async () => {
    mockQuestion();
    const patch = jest.spyOn(api, "patch").mockResolvedValue(envelope({ ...QUESTION }, '"e2"'));
    render(<AdminContentQuestionPage />);
    await screen.findByDisplayValue("What is 1+1?");

    await userEvent.click(screen.getByRole("button", { name: "Save draft" }));
    await waitFor(() => expect(patch).toHaveBeenCalledTimes(1));
    const [url, body, config] = patch.mock.calls[0] as [string, any, any];
    expect(url).toBe("/practice/content/questions/q1/");
    expect(body.text).toBe("What is 1+1?");
    expect(config).toEqual({ headers: { "If-Match": '"e1"' } });
    expect(mockToastSuccess).toHaveBeenCalledWith("Draft saved.");
  });

  it("shows the reload prompt when the draft changed elsewhere (412)", async () => {
    mockQuestion();
    jest.spyOn(api, "patch").mockRejectedValue(conflict("stale_version", 412));
    render(<AdminContentQuestionPage />);
    await screen.findByDisplayValue("What is 1+1?");

    await userEvent.click(screen.getByRole("button", { name: "Save draft" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("changed since you opened it");
    expect(screen.getByRole("button", { name: "Reload" })).toBeInTheDocument();
  });

  it("refuses an empty question text without calling the API", async () => {
    mockQuestion();
    const patch = jest.spyOn(api, "patch");
    render(<AdminContentQuestionPage />);
    const textInput = await screen.findByDisplayValue("What is 1+1?");
    await userEvent.clear(textInput);
    await userEvent.click(screen.getByRole("button", { name: "Save draft" }));
    expect(await screen.findByText("Enter the question text.")).toBeInTheDocument();
    expect(patch).not.toHaveBeenCalled();
  });

  it("publishes only after confirmation, sending If-Match", async () => {
    mockQuestion();
    const post = jest.spyOn(api, "post").mockResolvedValue(envelope({ ...QUESTION, status: "published" }, '"e3"'));
    render(<AdminContentQuestionPage />);
    await screen.findByDisplayValue("What is 1+1?");

    await userEvent.click(screen.getByRole("button", { name: "Publish" }));
    expect(post).not.toHaveBeenCalled();
    await userEvent.click(screen.getByRole("button", { name: "Confirm Publish" }));
    await waitFor(() => expect(post).toHaveBeenCalledTimes(1));
    expect(post.mock.calls[0][0]).toBe("/practice/content/questions/q1/publish/");
    expect(post.mock.calls[0][2]).toEqual({ headers: { "If-Match": '"e1"' } });
  });

  it("surfaces the used-question refusal when delete is attempted", async () => {
    mockQuestion();
    jest.spyOn(api, "delete").mockRejectedValue(conflict("used_question", 409));
    render(<AdminContentQuestionPage />);
    await screen.findByDisplayValue("What is 1+1?");

    await userEvent.click(screen.getByRole("button", { name: "Delete" }));
    await userEvent.click(screen.getByRole("button", { name: "Confirm Delete" }));
    await waitFor(() =>
      expect(mockToastError).toHaveBeenCalledWith("This question was used in an exam, so it can only be unpublished, not deleted."),
    );
  });
});
