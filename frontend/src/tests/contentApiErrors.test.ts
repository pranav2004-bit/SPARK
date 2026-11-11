/**
 * @jest-environment jsdom
 *
 * Content bank (LIVETRACKER4 I7): messages shown to users. Validation and
 * business-rule errors show plainly. Only server failures (5xx) add the
 * request reference, so support can find the request in the logs.
 */

import api from "@/lib/api";
import { contentApi, messageFor } from "@/lib/contentApi";

afterEach(() => {
  jest.restoreAllMocks();
});

describe("messageFor", () => {
  it("shows a business-rule message without a reference", async () => {
    jest.spyOn(api, "post").mockRejectedValue({
      response: { status: 409, data: { success: false, code: "node_not_empty", message: "x", errors: {}, request_id: "rid-77" } },
    });
    const err = await contentApi.nodeAction("n1", "publish").catch((e: unknown) => e);
    expect(messageFor(err)).toBe("This still has topics or questions. Remove or move them first, then try again.");
  });

  it("shows a duplicate-name message without a reference", async () => {
    jest.spyOn(api, "post").mockRejectedValue({
      response: { status: 409, data: { success: false, code: "duplicate_name", message: "x", errors: {}, request_id: "rid-78" } },
    });
    const err = await contentApi.createNode("Physics", null).catch((e: unknown) => e);
    expect(messageFor(err)).toBe("This name is already used here. Choose a different name.");
  });

  it("adds the request reference to a server failure", async () => {
    jest.spyOn(api, "post").mockRejectedValue({
      response: { status: 500, data: { success: false, code: "dependency_unavailable", message: "x", errors: {}, request_id: "rid-99" } },
    });
    const err = await contentApi.nodeAction("n1", "publish").catch((e: unknown) => e);
    expect(messageFor(err)).toBe("The service is temporarily unavailable. Please try again. (Reference: rid-99)");
  });

  it("shows the plain message when the server sent no request id", async () => {
    jest.spyOn(api, "post").mockRejectedValue({
      response: { status: 500, data: { success: false, code: "dependency_unavailable", message: "x", errors: {} } },
    });
    const err = await contentApi.nodeAction("n1", "publish").catch((e: unknown) => e);
    expect(messageFor(err)).toBe("The service is temporarily unavailable. Please try again.");
  });
});
