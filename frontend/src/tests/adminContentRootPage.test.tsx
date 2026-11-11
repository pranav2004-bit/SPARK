/**
 * @jest-environment jsdom
 *
 * Content bank (LIVETRACKER4 Phase I): admin root page lists subjects,
 * creates a subject with validation, and runs publish/retire/restore.
 */

jest.mock("next/navigation", () => ({
  useRouter: () => ({ push: jest.fn(), back: jest.fn() }),
}));

jest.mock("@/components/layout/AdminLayout", () => ({
  AdminLayout: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}));

const mockToastError = jest.fn();
const mockToastSuccess = jest.fn();
// Stub: one confirm button while open, so the test drives onConfirm directly.
jest.mock("@/components/ui/ConfirmDialog", () => ({
  ConfirmDialog: (props: { isOpen: boolean; onConfirm: () => void; confirmLabel?: string }) =>
    props.isOpen ? <button onClick={props.onConfirm}>{`Confirm ${props.confirmLabel ?? ""}`}</button> : null,
}));

jest.mock("@/components/ui/Toast", () => ({
  useToast: () => ({ error: mockToastError, success: mockToastSuccess }),
}));

import React from "react";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import api from "@/lib/api";
import AdminContentRootPage from "@/app/admin/content/page";

const SUBJECT = {
  id: "s1", parent_id: null, name: "Maths", display_order: 1,
  status: "draft", child_count: 0, question_count: 0,
};

function mockSubjects(rows = [SUBJECT]) {
  jest.spyOn(api, "get").mockImplementation((url: string) => {
    if (url.startsWith("/practice/content/nodes/?parent_id=null")) {
      return Promise.resolve({
        data: { success: true, data: { count: rows.length, total_pages: 1, current_page: 1, next: null, previous: null, results: rows } },
        headers: {},
      } as any);
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

describe("Content root page", () => {
  it("lists subjects with their status and topic count", async () => {
    mockSubjects();
    render(<AdminContentRootPage />);
    expect(await screen.findByText("Maths")).toBeInTheDocument();
    expect(within(screen.getByRole("list", { name: "Subjects" })).getByText("Draft")).toBeInTheDocument();
    expect(screen.getByText("0 topics")).toBeInTheDocument();
  });

  it("shows the empty state when there are no subjects", async () => {
    mockSubjects([]);
    render(<AdminContentRootPage />);
    expect(await screen.findByText("No subjects yet")).toBeInTheDocument();
  });

  it("shows no create action until the name has text, so nothing is sent", async () => {
    mockSubjects();
    const post = jest.spyOn(api, "post");
    render(<AdminContentRootPage />);
    await screen.findByText("Maths");
    await userEvent.click(screen.getByRole("button", { name: "Add subject" }));
    expect(screen.queryByRole("button", { name: "Create subject" })).not.toBeInTheDocument();
    await userEvent.type(screen.getByLabelText("Subject name"), "   ");
    expect(screen.queryByRole("button", { name: "Create subject" })).not.toBeInTheDocument();
    expect(post).not.toHaveBeenCalled();
  });

  it("creates a subject with a trimmed name and a null parent", async () => {
    mockSubjects();
    const post = jest.spyOn(api, "post").mockResolvedValue({ data: { success: true, data: SUBJECT }, headers: {} } as any);
    render(<AdminContentRootPage />);
    await screen.findByText("Maths");
    await userEvent.click(screen.getByRole("button", { name: "Add subject" }));
    await userEvent.type(screen.getByLabelText("Subject name"), "  Physics  ");
    await userEvent.click(screen.getByRole("button", { name: "Create subject" }));
    await waitFor(() =>
      expect(post).toHaveBeenCalledWith("/practice/content/nodes/", { name: "Physics", parent_id: null }),
    );
    expect(mockToastSuccess).toHaveBeenCalledWith("Subject created.");
  });

  it("publishes a draft subject", async () => {
    mockSubjects();
    const post = jest.spyOn(api, "post").mockResolvedValue({ data: { success: true, data: { ...SUBJECT, status: "published" } }, headers: {} } as any);
    render(<AdminContentRootPage />);
    await screen.findByText("Maths");
    await userEvent.click(screen.getByRole("button", { name: "Publish" }));
    await waitFor(() => expect(post).toHaveBeenCalledWith("/practice/content/nodes/s1/publish/"));
    expect(mockToastSuccess).toHaveBeenCalledWith("Subject published.");
  });

  it("shows the mapped message when an action is refused", async () => {
    mockSubjects();
    jest.spyOn(api, "post").mockRejectedValue({
      response: { status: 409, data: { success: false, code: "node_not_empty", message: "x", errors: {} } },
    });
    render(<AdminContentRootPage />);
    await screen.findByText("Maths");
    await userEvent.click(screen.getByRole("button", { name: "Publish" }));
    await waitFor(() =>
      expect(mockToastError).toHaveBeenCalledWith(
        "This still has topics or questions. Remove or move them first, then try again.",
      ),
    );
  });
});

describe("Content root page: edit, delete, publish controls", () => {
  it("renames a subject through the edit popup", async () => {
    mockSubjects();
    const patch = jest.spyOn(api, "patch").mockResolvedValue({ data: { success: true, data: SUBJECT }, headers: {} } as any);
    render(<AdminContentRootPage />);
    await screen.findByText("Maths");
    await userEvent.click(screen.getByRole("button", { name: "Edit" }));
    const input = screen.getByLabelText("Subject name");
    await userEvent.clear(input);
    await userEvent.type(input, "Algebra");
    await userEvent.click(screen.getByRole("button", { name: "Save changes" }));
    await waitFor(() => expect(patch).toHaveBeenCalledWith("/practice/content/nodes/s1/", { name: "Algebra" }));
  });

  it("deletes a subject after confirmation", async () => {
    mockSubjects();
    const del = jest.spyOn(api, "delete").mockResolvedValue({ data: { success: true, data: null }, headers: {} } as any);
    render(<AdminContentRootPage />);
    await screen.findByText("Maths");
    await userEvent.click(screen.getByRole("button", { name: "Delete" }));
    await userEvent.click(screen.getByRole("button", { name: "Confirm Delete" }));
    await waitFor(() => expect(del).toHaveBeenCalledWith("/practice/content/nodes/s1/"));
  });

  it("shows Unpublish for a published subject and calls the retire action", async () => {
    jest.spyOn(api, "get").mockImplementation((url: string) => {
      if (url.startsWith("/practice/content/nodes/?parent_id=null")) {
        return Promise.resolve({ data: { success: true, data: { count: 1, total_pages: 1, current_page: 1, next: null, previous: null, results: [{ ...SUBJECT, status: "published" }] } }, headers: {} } as any);
      }
      return Promise.reject(new Error(`unexpected GET ${url}`));
    });
    const post = jest.spyOn(api, "post").mockResolvedValue({ data: { success: true, data: SUBJECT }, headers: {} } as any);
    render(<AdminContentRootPage />);
    await screen.findByText("Maths");
    await userEvent.click(screen.getByRole("button", { name: "Unpublish" }));
    await waitFor(() => expect(post).toHaveBeenCalledWith("/practice/content/nodes/s1/retire/"));
  });
});

describe("Content root page: search and status filter", () => {
  const LIST = [
    { ...SUBJECT, id: "a", name: "Quantitative Aptitude", status: "published" },
    { ...SUBJECT, id: "b", name: "Verbal Ability", status: "draft" },
    { ...SUBJECT, id: "c", name: "Logical Reasoning", status: "retired" },
    { ...SUBJECT, id: "d", name: "Maths (.*) [x]", status: "draft" },
  ];

  function mockList(rows = LIST) {
    jest.spyOn(api, "get").mockImplementation((url: string) => {
      if (url.startsWith("/practice/content/nodes/?parent_id=null")) {
        return Promise.resolve({ data: { success: true, data: { count: rows.length, total_pages: 1, current_page: 1, next: null, previous: null, results: rows } }, headers: {} } as any);
      }
      return Promise.reject(new Error(`unexpected GET ${url}`));
    });
  }

  it("matches the subject name case-insensitively and ignores surrounding spaces", async () => {
    mockList();
    render(<AdminContentRootPage />);
    await screen.findByText("Verbal Ability");
    await userEvent.type(screen.getByLabelText("Search subjects"), "  VERBAL  ");
    expect(screen.getByText("Verbal Ability")).toBeInTheDocument();
    expect(screen.queryByText("Quantitative Aptitude")).not.toBeInTheDocument();
  });

  it("treats regex and markup characters as plain text", async () => {
    mockList();
    render(<AdminContentRootPage />);
    await screen.findByText("Verbal Ability");
    await userEvent.type(screen.getByLabelText("Search subjects"), ".*");
    expect(screen.queryByText("Verbal Ability")).not.toBeInTheDocument();
    expect(screen.getByText("Maths (.*) [x]")).toBeInTheDocument();
  });

  it("shows a no-match state with a way to clear, and a search with nothing typed shows all", async () => {
    mockList();
    render(<AdminContentRootPage />);
    await screen.findByText("Verbal Ability");
    await userEvent.type(screen.getByLabelText("Search subjects"), "zzz-no-such");
    expect(screen.getByText("No subjects match")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Clear search and filters" }));
    expect(screen.getByText("Verbal Ability")).toBeInTheDocument();
  });

  it("filters by status and combines with the search", async () => {
    mockList();
    render(<AdminContentRootPage />);
    await screen.findByText("Verbal Ability");
    await userEvent.selectOptions(screen.getByLabelText("Filter by status"), "draft");
    expect(screen.getByText("Verbal Ability")).toBeInTheDocument();
    expect(screen.queryByText("Quantitative Aptitude")).not.toBeInTheDocument();
    await userEvent.type(screen.getByLabelText("Search subjects"), "verbal");
    expect(screen.getByText("Verbal Ability")).toBeInTheDocument();
    await userEvent.clear(screen.getByLabelText("Search subjects"));
    await userEvent.type(screen.getByLabelText("Search subjects"), "logical");
    expect(screen.getByText("No subjects match")).toBeInTheDocument();
  });

  it("loads every page of subjects before filtering", async () => {
    const get = jest.spyOn(api, "get").mockImplementation((url: string) => {
      const page = url.includes("page=2") ? 2 : 1;
      const rows = page === 1 ? [LIST[0]] : [LIST[1]];
      return Promise.resolve({ data: { success: true, data: { count: 2, total_pages: 2, current_page: page, next: page === 1 ? "next" : null, previous: null, results: rows } }, headers: {} } as any);
    });
    render(<AdminContentRootPage />);
    expect(await screen.findByText("Verbal Ability")).toBeInTheDocument();
    expect(screen.getByText("Quantitative Aptitude")).toBeInTheDocument();
    expect(get).toHaveBeenCalledTimes(2);
  });
});
