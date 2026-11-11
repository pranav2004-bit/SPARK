/**
 * @jest-environment jsdom
 *
 * Content bank (LIVETRACKER4 Phase I): node page shows topics under a subject
 * and questions under a topic, with validated create forms and reorder.
 */

const mockParams = { node_id: "n1" };
jest.mock("next/navigation", () => ({
  useParams: () => mockParams,
  useRouter: () => ({ push: jest.fn(), back: jest.fn() }),
}));

// Stub: renders one confirm button only while open (see the question editor test).
jest.mock("@/components/ui/ConfirmDialog", () => ({
  ConfirmDialog: (props: { isOpen: boolean; onConfirm: () => void; confirmLabel?: string }) =>
    props.isOpen ? <button onClick={props.onConfirm}>{`Confirm ${props.confirmLabel ?? ""}`}</button> : null,
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
import AdminContentNodePage from "@/app/admin/content/nodes/[node_id]/page";

const SUBJECT = { id: "s1", parent_id: null, name: "Maths", display_order: 1, status: "published", child_count: 2, question_count: 0 };
const TOPIC_NODE = { id: "n1", parent_id: "s1", name: "Algebra", display_order: 1, status: "draft", child_count: 0, question_count: 1 };
const SUBJECT_NODE = { ...SUBJECT, id: "n1", name: "Maths" };
const QUESTION = {
  id: "q1", node_id: "n1", display_order: 1, status: "draft", current_version_no: 1, published_version_no: null,
  editable_version: { version_no: 1, state: "draft", question_text: "What is 1+1?", explanation: "", image_key: "", image_url: "", image_alt_text: "", options: [] },
};

function envelope(data: unknown) {
  return { data: { success: true, data }, headers: { etag: '"e1"' } } as any;
}

function page<T>(results: T[]) {
  return { count: results.length, total_pages: 1, current_page: 1, next: null, previous: null, results };
}

function mockTopic() {
  jest.spyOn(api, "get").mockImplementation((url: string) => {
    if (url === "/practice/content/nodes/n1/") return Promise.resolve(envelope(TOPIC_NODE));
    if (url === "/practice/content/nodes/s1/") return Promise.resolve(envelope(SUBJECT));
    if (url.startsWith("/practice/content/questions/?node_id=n1")) return Promise.resolve(envelope(page([QUESTION])));
    return Promise.reject(new Error(`unexpected GET ${url}`));
  });
}

function mockSubject() {
  jest.spyOn(api, "get").mockImplementation((url: string) => {
    if (url === "/practice/content/nodes/n1/") return Promise.resolve(envelope(SUBJECT_NODE));
    if (url.startsWith("/practice/content/nodes/?parent_id=n1")) {
      return Promise.resolve(envelope(page([TOPIC_NODE])));
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

describe("Content node page: topic level", () => {
  it("lists the topic's questions with their status", async () => {
    mockTopic();
    render(<AdminContentNodePage />);
    expect(await screen.findByText(/What is 1\+1\?/)).toBeInTheDocument();
    expect(screen.getByText("Draft")).toBeInTheDocument();
  });

  it("saves a question as a draft with the marked option as correct", async () => {
    mockTopic();
    const post = jest.spyOn(api, "post").mockResolvedValue(envelope(QUESTION));
    render(<AdminContentNodePage />);
    await screen.findByText(/What is 1\+1\?/);

    await userEvent.type(screen.getByLabelText("Question text"), "What is 2+2?");
    await userEvent.type(screen.getByLabelText("Option A text"), "3");
    await userEvent.type(screen.getByLabelText("Option B text"), "4");
    await userEvent.click(screen.getByLabelText("Option B is correct"));
    await userEvent.click(screen.getByRole("button", { name: "Save as draft" }));

    await waitFor(() => expect(post).toHaveBeenCalledTimes(1));
    const [url, body] = post.mock.calls[0] as [string, any];
    expect(url).toBe("/practice/content/questions/");
    expect(body.node_id).toBe("n1");
    expect(body.text).toBe("What is 2+2?");
    expect(body.options).toEqual([
      expect.objectContaining({ option_text: "3", is_correct: false }),
      expect.objectContaining({ option_text: "4", is_correct: true }),
    ]);
  });

  it("refuses a question with no text", async () => {
    mockTopic();
    const post = jest.spyOn(api, "post");
    render(<AdminContentNodePage />);
    await screen.findByText(/What is 1\+1\?/);
    await userEvent.click(screen.getByRole("button", { name: "Save as draft" }));
    expect(await screen.findByText("Enter the question text.")).toBeInTheDocument();
    expect(post).not.toHaveBeenCalled();
  });

  it("reorders questions by posting the new id order", async () => {
    const second = { ...QUESTION, id: "q2", display_order: 2, editable_version: { ...QUESTION.editable_version!, question_text: "Second" } };
    jest.spyOn(api, "get").mockImplementation((url: string) => {
      if (url === "/practice/content/nodes/n1/") return Promise.resolve(envelope(TOPIC_NODE));
      if (url === "/practice/content/nodes/s1/") return Promise.resolve(envelope(SUBJECT));
      if (url.startsWith("/practice/content/questions/?node_id=n1")) return Promise.resolve(envelope(page([QUESTION, second])));
      return Promise.reject(new Error(`unexpected GET ${url}`));
    });
    const post = jest.spyOn(api, "post").mockResolvedValue(envelope(null));
    render(<AdminContentNodePage />);
    await screen.findByText(/Second/);
    await userEvent.click(screen.getByRole("button", { name: "Move question 2 up" }));
    await waitFor(() =>
      expect(post).toHaveBeenCalledWith("/practice/content/questions/reorder/", { node_id: "n1", question_ids: ["q2", "q1"] }),
    );
  });
});

describe("Content node page: subject level", () => {
  it("lists topics and creates a new topic under the subject", async () => {
    mockSubject();
    const post = jest.spyOn(api, "post").mockResolvedValue(envelope(TOPIC_NODE));
    render(<AdminContentNodePage />);
    expect(await screen.findByText("Algebra", { exact: false })).toBeInTheDocument();

    await userEvent.type(screen.getByLabelText("New topic name"), "Geometry");
    await userEvent.click(screen.getByRole("button", { name: "Add topic" }));
    await waitFor(() =>
      expect(post).toHaveBeenCalledWith("/practice/content/nodes/", { name: "Geometry", parent_id: "n1" }),
    );
  });

  it("reorders topics by posting the parent and the new id order", async () => {
    const topicB = { ...TOPIC_NODE, id: "t2", name: "Calculus", display_order: 2 };
    jest.spyOn(api, "get").mockImplementation((url: string) => {
      if (url === "/practice/content/nodes/n1/") return Promise.resolve(envelope(SUBJECT_NODE));
      if (url.startsWith("/practice/content/nodes/?parent_id=n1")) return Promise.resolve(envelope(page([TOPIC_NODE, topicB])));
      return Promise.reject(new Error(`unexpected GET ${url}`));
    });
    const post = jest.spyOn(api, "post").mockResolvedValue(envelope(null));
    render(<AdminContentNodePage />);
    await screen.findByText("Calculus", { exact: false });
    await userEvent.click(screen.getByRole("button", { name: "Move Calculus up" }));
    await waitFor(() =>
      expect(post).toHaveBeenCalledWith("/practice/content/nodes/reorder/", { parent_id: "n1", node_ids: ["t2", "n1"] }),
    );
  });
});

describe("Content node page: rename and delete", () => {
  it("renames the node and shows the new name", async () => {
    mockSubject();
    const patch = jest.spyOn(api, "patch").mockResolvedValue(envelope({ ...SUBJECT_NODE, name: "Physics" }));
    render(<AdminContentNodePage />);
    await screen.findByRole("heading", { name: "Maths" });

    await userEvent.click(screen.getByRole("button", { name: "Rename" }));
    const input = screen.getByLabelText("Name");
    await userEvent.clear(input);
    await userEvent.type(input, "Physics");
    await userEvent.click(screen.getByRole("button", { name: "Save name" }));

    await waitFor(() => expect(patch).toHaveBeenCalledWith("/practice/content/nodes/n1/", { name: "Physics" }));
    expect(await screen.findByRole("heading", { name: "Physics" })).toBeInTheDocument();
  });

  it("shows the server's reason when a non-empty node is deleted", async () => {
    mockSubject();
    jest.spyOn(api, "delete").mockRejectedValue({
      response: { status: 409, data: { success: false, code: "node_not_empty", message: "x", errors: {} } },
    });
    render(<AdminContentNodePage />);
    await screen.findByRole("heading", { name: "Maths" });

    await userEvent.click(screen.getByRole("button", { name: "Delete" }));
    await userEvent.click(screen.getByRole("button", { name: "Confirm Delete" }));
    await waitFor(() =>
      expect(mockToastError).toHaveBeenCalledWith(
        "This still has topics or questions. Remove or move them first, then try again.",
      ),
    );
  });
});
