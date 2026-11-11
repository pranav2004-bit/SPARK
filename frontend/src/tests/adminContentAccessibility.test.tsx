/**
 * @jest-environment jsdom
 *
 * Content bank (LIVETRACKER4 I9): axe-core scan of the content screens. Any
 * serious or critical violation fails the test. Colour contrast is not checked
 * in jsdom (no layout), so contrast stays a manual review item.
 */

const mockParams = { node_id: "n1", question_id: "q1" };
jest.mock("next/navigation", () => ({
  useParams: () => mockParams,
  useRouter: () => ({ push: jest.fn(), back: jest.fn() }),
}));

jest.mock("@/components/layout/AdminLayout", () => ({
  AdminLayout: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}));

jest.mock("@/components/ui/Toast", () => ({
  useToast: () => ({ error: jest.fn(), success: jest.fn() }),
}));

import React from "react";
import { render, screen } from "@testing-library/react";
import axe from "axe-core";
import api from "@/lib/api";
import AdminContentRootPage from "@/app/admin/content/page";
import AdminContentNodePage from "@/app/admin/content/nodes/[node_id]/page";
import AdminContentQuestionPage from "@/app/admin/content/questions/[question_id]/page";

const SUBJECT = { id: "s1", parent_id: null, name: "Maths", display_order: 1, status: "draft", child_count: 0, question_count: 0 };
const TOPIC = { id: "n1", parent_id: "s1", name: "Algebra", display_order: 1, status: "draft", child_count: 0, question_count: 1 };
const QUESTION = {
  id: "q1", node_id: "n1", display_order: 1, status: "draft", current_version_no: 1, published_version_no: null,
  editable_version: {
    version_no: 1, state: "draft", question_text: "What is 1+1?", explanation: "", image_key: "", image_url: "", image_alt_text: "",
    options: [
      { label: "A", option_text: "2", is_correct: true, display_order: 1 },
      { label: "B", option_text: "3", is_correct: false, display_order: 2 },
    ],
  },
};

function envelope(data: unknown) {
  return { data: { success: true, data }, headers: { etag: '"e1"' } } as any;
}
function page<T>(results: T[]) {
  return { count: results.length, total_pages: 1, current_page: 1, next: null, previous: null, results };
}

function mockApi() {
  jest.spyOn(api, "get").mockImplementation((url: string) => {
    if (url.startsWith("/practice/content/nodes/?parent_id=null")) return Promise.resolve(envelope(page([SUBJECT])));
    if (url === "/practice/content/nodes/n1/") return Promise.resolve(envelope(TOPIC));
    if (url === "/practice/content/nodes/s1/") return Promise.resolve(envelope(SUBJECT));
    if (url.startsWith("/practice/content/questions/?node_id=n1")) return Promise.resolve(envelope(page([QUESTION])));
    if (url === "/practice/content/questions/q1/") return Promise.resolve(envelope(QUESTION));
    if (url === "/practice/content/questions/q1/versions/") {
      return Promise.resolve({ data: { success: true, data: [] }, headers: {} } as any);
    }
    return Promise.reject(new Error(`unexpected GET ${url}`));
  });
}

async function serious(container: HTMLElement) {
  const results = await axe.run(container, {
    rules: { "color-contrast": { enabled: false } },
  });
  return results.violations
    .filter((v) => v.impact === "serious" || v.impact === "critical")
    .map((v) => `${v.id} (${v.impact}): ${v.nodes.length} node(s)`);
}

afterEach(() => {
  jest.restoreAllMocks();
});

describe("Content screens accessibility (axe-core)", () => {
  it("root page has no serious or critical violations", async () => {
    mockApi();
    const { container } = render(<AdminContentRootPage />);
    await screen.findByText("Maths");
    expect(await serious(container)).toEqual([]);
  });

  it("topic node page has no serious or critical violations", async () => {
    mockApi();
    const { container } = render(<AdminContentNodePage />);
    await screen.findByText(/What is 1\+1\?/);
    expect(await serious(container)).toEqual([]);
  });

  it("question editor has no serious or critical violations", async () => {
    mockApi();
    const { container } = render(<AdminContentQuestionPage />);
    await screen.findByDisplayValue("What is 1+1?");
    expect(await serious(container)).toEqual([]);
  });
});

describe("axe-core negative control", () => {
  it("flags an image without alt text, so the scan is not vacuous", async () => {
    const { container } = render(<main><img src="/x.png" alt="" /><img src="/y.png" /></main>);
    const found = await serious(container);
    expect(found.some((line) => line.startsWith("image-alt"))).toBe(true);
  });
});
