/**
 * @jest-environment jsdom
 *
 * Coverage for StaleAssetReloader (2026-11-16 production-readiness audit) —
 * recovers from a stale-deployment asset mismatch ("CSS is breaking, only
 * text visible" after a Vercel deploy replaces the hashed asset files a
 * still-open tab is referencing). Detects a failed <link>/<script> load or
 * a ChunkLoadError and reloads once, with a cooldown to avoid a tight
 * reload loop if the problem isn't actually fixed by reloading.
 *
 * jsdom's window.location.reload is read-only and non-configurable, so it
 * can't be mocked directly (same constraint documented in
 * usePortalGuard.test.tsx/studentMyProfilePage.test.tsx) — calling the real
 * thing surfaces as a console.error ("Not implemented: navigation"), which
 * these tests use as proof reload() was actually invoked.
 */

import React from "react";
import { render } from "@testing-library/react";
import { StaleAssetReloader } from "@/components/StaleAssetReloader";

function dispatchResourceError(tag: "link" | "script", url: string) {
  const el = document.createElement(tag);
  if (tag === "link") {
    (el as HTMLLinkElement).rel = "stylesheet";
    (el as HTMLLinkElement).href = url;
  } else {
    (el as HTMLScriptElement).src = url;
  }
  const event = new Event("error");
  Object.defineProperty(event, "target", { value: el, enumerable: true });
  window.dispatchEvent(event);
}

function dispatchChunkRejection(reason: unknown) {
  const event = new Event("unhandledrejection") as PromiseRejectionEvent & { reason?: unknown };
  Object.defineProperty(event, "reason", { value: reason, enumerable: true });
  window.dispatchEvent(event);
}

function reloadWasCalled(errorSpy: jest.SpyInstance): boolean {
  return errorSpy.mock.calls.some(args => String(args[0]).includes("Not implemented: navigation"));
}

describe("StaleAssetReloader", () => {
  let errorSpy: jest.SpyInstance;

  beforeEach(() => {
    jest.useFakeTimers({ doNotFake: ["nextTick"] });
    sessionStorage.clear();
    errorSpy = jest.spyOn(console, "error").mockImplementation(() => {});
  });

  afterEach(() => {
    errorSpy.mockRestore();
    jest.useRealTimers();
  });

  it("reloads when a Next.js static stylesheet fails to load", () => {
    render(<StaleAssetReloader />);
    dispatchResourceError("link", "https://spark.sanjivo.com/_next/static/css/app/layout-abc123.css");
    expect(reloadWasCalled(errorSpy)).toBe(true);
  });

  it("reloads when a Next.js static script fails to load", () => {
    render(<StaleAssetReloader />);
    dispatchResourceError("script", "https://spark.sanjivo.com/_next/static/chunks/123-def456.js");
    expect(reloadWasCalled(errorSpy)).toBe(true);
  });

  it("ignores a failed resource that isn't a Next.js static asset", () => {
    render(<StaleAssetReloader />);
    dispatchResourceError("link", "https://fonts.googleapis.com/css2?family=Inter");
    expect(reloadWasCalled(errorSpy)).toBe(false);
  });

  it("reloads on a ChunkLoadError-named rejection", () => {
    render(<StaleAssetReloader />);
    dispatchChunkRejection({ name: "ChunkLoadError", message: "Loading chunk 42 failed" });
    expect(reloadWasCalled(errorSpy)).toBe(true);
  });

  it("reloads on a rejection whose message mentions loading a CSS chunk, even without the ChunkLoadError name", () => {
    render(<StaleAssetReloader />);
    dispatchChunkRejection({ name: "Error", message: "Loading CSS chunk 7 failed" });
    expect(reloadWasCalled(errorSpy)).toBe(true);
  });

  it("ignores an unrelated promise rejection", () => {
    render(<StaleAssetReloader />);
    dispatchChunkRejection({ name: "TypeError", message: "Cannot read properties of undefined" });
    expect(reloadWasCalled(errorSpy)).toBe(false);
  });

  it("does not reload a second time within the cooldown window, to avoid a tight reload loop", () => {
    render(<StaleAssetReloader />);
    dispatchResourceError("link", "https://spark.sanjivo.com/_next/static/css/app/layout-abc123.css");
    expect(reloadWasCalled(errorSpy)).toBe(true);
    errorSpy.mockClear();

    dispatchResourceError("script", "https://spark.sanjivo.com/_next/static/chunks/another-chunk.js");
    expect(reloadWasCalled(errorSpy)).toBe(false);
  });

  it("allows a second reload once the cooldown window has passed — a genuinely new deploy during a long-lived tab", () => {
    render(<StaleAssetReloader />);
    dispatchResourceError("link", "https://spark.sanjivo.com/_next/static/css/app/layout-abc123.css");
    expect(reloadWasCalled(errorSpy)).toBe(true);
    errorSpy.mockClear();

    jest.advanceTimersByTime(10_001);

    dispatchResourceError("script", "https://spark.sanjivo.com/_next/static/chunks/another-chunk.js");
    expect(reloadWasCalled(errorSpy)).toBe(true);
  });
});
