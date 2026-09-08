/**
 * @jest-environment jsdom
 *
 * Coverage for the Super Admin "Scrollbar" page (2026-08-20) — mirrors
 * admin/scroll/page.tsx exactly, using the same /users/scroll/config/,
 * /users/scroll/updates/, and /users/scroll/reorder/ endpoints (opened to
 * Super Admin the same day). No layout mock needed — super-admin/* pages
 * are chrome-free (Pattern B, file-based layout.tsx provides chrome).
 */

jest.mock("@/components/ui/Toast", () => ({
  useToast: () => ({
    showToast: jest.fn(),
    success: jest.fn(),
    error: jest.fn(),
    warning: jest.fn(),
  }),
}));

import React from "react";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import api from "@/lib/api";
import SuperAdminScrollPage from "@/app/super-admin/scroll/page";

const CONFIG = { is_enabled: false, direction: "left" };

const UPDATE_1 = { id: "u-1", text: "First update", link: "", show_new_badge: false, order: 1 };
const UPDATE_2 = { id: "u-2", text: "Second update", link: "", show_new_badge: false, order: 2 };

function mockLoad(config = CONFIG, updates: any[] = []) {
  jest.spyOn(api, "get").mockImplementation((url: string) => {
    if (url === "/users/scroll/config/") return Promise.resolve({ data: { data: config } } as any);
    if (url === "/users/scroll/updates/") return Promise.resolve({ data: { data: updates } } as any);
    return Promise.reject(new Error(`unexpected GET ${url}`));
  });
}

afterEach(() => {
  jest.restoreAllMocks();
});

describe("Super Admin — Scrollbar page", () => {
  it("loads config and updates from the scroll endpoints", async () => {
    mockLoad(CONFIG, [UPDATE_1]);
    render(<SuperAdminScrollPage />);
    await waitFor(() => expect(screen.getByText("First update")).toBeInTheDocument());
    expect(screen.getByText("Scrolling Updates")).toBeInTheDocument();
  });

  it("toggles the enable switch via PATCH /users/scroll/config/", async () => {
    const user = userEvent.setup();
    mockLoad(CONFIG, []);
    const patchSpy = jest.spyOn(api, "patch").mockResolvedValue({
      data: { data: { ...CONFIG, is_enabled: true } },
    } as any);
    render(<SuperAdminScrollPage />);
    await waitFor(() => expect(screen.getByText("Show scrolling bar")).toBeInTheDocument());

    // The Toggle component has no accessible name/text — it exposes
    // aria-pressed, which Testing Library's byRole can match on directly.
    await user.click(screen.getByRole("button", { pressed: false }));
    await waitFor(() => expect(patchSpy).toHaveBeenCalledWith("/users/scroll/config/", { is_enabled: true }));
  });

  it("adds a new update via POST /users/scroll/updates/", async () => {
    const user = userEvent.setup();
    mockLoad(CONFIG, []);
    const postSpy = jest.spyOn(api, "post").mockResolvedValue({
      data: { data: { id: "u-new", text: "Brand new update", link: "", show_new_badge: false, order: 1 } },
    } as any);
    render(<SuperAdminScrollPage />);
    await waitFor(() => expect(screen.getByText("No updates yet")).toBeInTheDocument());

    await user.click(screen.getByText("Add Update"));
    await user.type(screen.getByPlaceholderText(/Update text/), "Brand new update");
    await user.click(screen.getByText("Add"));

    await waitFor(() => expect(postSpy).toHaveBeenCalledWith("/users/scroll/updates/", {
      text: "Brand new update",
      link: "",
      show_new_badge: false,
    }));
    await waitFor(() => expect(screen.getByText("Brand new update")).toBeInTheDocument());
  });

  it("edits an existing update via PATCH /users/scroll/updates/<id>/", async () => {
    const user = userEvent.setup();
    mockLoad(CONFIG, [UPDATE_1]);
    const patchSpy = jest.spyOn(api, "patch").mockResolvedValue({
      data: { data: { ...UPDATE_1, text: "Edited update" } },
    } as any);
    render(<SuperAdminScrollPage />);
    await waitFor(() => expect(screen.getByText("First update")).toBeInTheDocument());

    await user.click(screen.getByTitle("Edit"));
    const textarea = screen.getByDisplayValue("First update");
    await user.clear(textarea);
    await user.type(textarea, "Edited update");
    await user.click(screen.getByText("Save"));

    await waitFor(() => expect(patchSpy).toHaveBeenCalledWith("/users/scroll/updates/u-1/", {
      text: "Edited update",
      link: "",
      show_new_badge: false,
    }));
    await waitFor(() => expect(screen.getByText("Edited update")).toBeInTheDocument());
  });

  it("deletes an update via DELETE /users/scroll/updates/<id>/", async () => {
    const user = userEvent.setup();
    mockLoad(CONFIG, [UPDATE_1]);
    const deleteSpy = jest.spyOn(api, "delete").mockResolvedValue({ data: {} } as any);
    render(<SuperAdminScrollPage />);
    await waitFor(() => expect(screen.getByText("First update")).toBeInTheDocument());

    await user.click(screen.getByTitle("Delete"));

    await waitFor(() => expect(deleteSpy).toHaveBeenCalledWith("/users/scroll/updates/u-1/"));
    await waitFor(() => expect(screen.queryByText("First update")).not.toBeInTheDocument());
  });

  it("reorders updates via POST /users/scroll/reorder/", async () => {
    const user = userEvent.setup();
    mockLoad(CONFIG, [UPDATE_1, UPDATE_2]);
    const postSpy = jest.spyOn(api, "post").mockResolvedValue({
      data: { data: [UPDATE_2, UPDATE_1] },
    } as any);
    render(<SuperAdminScrollPage />);
    await waitFor(() => expect(screen.getByText("First update")).toBeInTheDocument());

    // Order-control buttons render lucide ChevronUp/ChevronDown icons with no
    // accessible name — the direction buttons above them also contain SVGs,
    // so filter specifically on the chevron-down icon's class instead of
    // guessing an index across all icon buttons on the page.
    const downButtons = screen.getAllByRole("button").filter((b) => b.querySelector("svg.lucide-chevron-down"));
    await user.click(downButtons[0]);

    await waitFor(() => expect(postSpy).toHaveBeenCalledWith("/users/scroll/reorder/", { ids: ["u-2", "u-1"] }));
  });

  it("shows a retry option when the scroll settings fail to load", async () => {
    jest.spyOn(api, "get").mockRejectedValue(new Error("network error"));
    render(<SuperAdminScrollPage />);
    await waitFor(() => expect(screen.getByText("Retry")).toBeInTheDocument());
  });
});
