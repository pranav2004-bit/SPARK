/**
 * @jest-environment jsdom
 *
 * Content bank (LIVETRACKER4 Phase I, I5): the version page is read-only and
 * shows the stored text, options and correct answer for one version.
 */

const mockParams = { question_id: "q1", version_no: "1" };
jest.mock("next/navigation", () => ({
  useParams: () => mockParams,
  useRouter: () => ({ push: jest.fn(), back: jest.fn() }),
}));

jest.mock("@/components/layout/AdminLayout", () => ({
  AdminLayout: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}));

import React from "react";
import { render, screen, waitFor } from "@testing-library/react";
import api from "@/lib/api";
import AdminContentVersionPage from "@/app/admin/content/questions/[question_id]/versions/[version_no]/page";

const VERSION = {
  version_no: 1, state: "published", question_text: "What is 1+1?", explanation: "Basic addition.",
  image_key: "", image_url: "", image_alt_text: "",
  options: [
    { label: "A", option_text: "2", is_correct: true, display_order: 1 },
    { label: "B", option_text: "3", is_correct: false, display_order: 2 },
  ],
};

afterEach(() => {
  jest.restoreAllMocks();
});

describe("Content version page", () => {
  it("shows the stored version read-only, with the correct option marked", async () => {
    jest.spyOn(api, "get").mockImplementation((url: string) => {
      if (url === "/practice/content/questions/q1/versions/1/") {
        return Promise.resolve({ data: { success: true, data: VERSION }, headers: {} } as any);
      }
      return Promise.reject(new Error(`unexpected GET ${url}`));
    });
    render(<AdminContentVersionPage />);

    expect(await screen.findByText("What is 1+1?")).toBeInTheDocument();
    expect(screen.getByText("Basic addition.")).toBeInTheDocument();
    expect(screen.getByText(/A\. 2/)).toHaveTextContent("(correct)");
    expect(screen.getByText(/read only/)).toBeInTheDocument();
    // No editing controls on a stored version.
    expect(screen.queryByRole("button", { name: "Save draft" })).not.toBeInTheDocument();
    expect(screen.queryByRole("textbox")).not.toBeInTheDocument();
  });

  it("requests the version number from the URL as a number", async () => {
    const get = jest.spyOn(api, "get").mockResolvedValue({ data: { success: true, data: VERSION }, headers: {} } as any);
    render(<AdminContentVersionPage />);
    await waitFor(() => expect(get).toHaveBeenCalledWith("/practice/content/questions/q1/versions/1/"));
  });
});
