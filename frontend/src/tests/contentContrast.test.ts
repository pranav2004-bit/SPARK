/**
 * @jest-environment node
 *
 * Content bank (LIVETRACKER4 I9): static WCAG AA contrast check for the colour
 * tokens the content screens use. Reads the real token values from globals.css,
 * so the check follows the stylesheet. Normal text needs a ratio of at least 4.5:1.
 * Live rendering is not needed for this check; a visual pass is still recommended.
 */

import fs from "fs";
import path from "path";

const CSS = fs.readFileSync(path.resolve(__dirname, "../app/globals.css"), "utf-8");
const CONTENT_DIR = path.resolve(__dirname, "../app/admin/content");

function token(name: string): string {
  // First declaration of the token is the light-theme value in :root.
  const match = CSS.match(new RegExp(`--${name}:\\s*(#[0-9a-fA-F]{6})\\s*;`));
  if (!match) throw new Error(`token --${name} not found in globals.css`);
  return match[1];
}

function luminance(hex: string): number {
  const channels = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16) / 255);
  const [r, g, b] = channels.map((v) => (v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4)));
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

function ratio(fg: string, bg: string): number {
  const a = luminance(fg);
  const b = luminance(bg);
  return (Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05);
}

function contentSources(dir: string): string[] {
  return fs.readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) return contentSources(full);
    return entry.name.endsWith(".tsx") ? [full] : [];
  });
}

describe("content screen colour contrast (WCAG AA, normal text)", () => {
  const backgrounds = ["color-surface", "color-surface-secondary"];
  const texts = ["color-text", "color-text-muted", "color-danger"];

  it.each(texts.flatMap((t) => backgrounds.map((bg) => [t, bg])))(
    "--%s on --%s meets 4.5:1",
    (text, bg) => {
      expect(ratio(token(text), token(bg))).toBeGreaterThanOrEqual(4.5);
    },
  );

  it("content screens do not use the low-contrast tokens", () => {
    const offenders = contentSources(CONTENT_DIR)
      // Text colours only: borders and backgrounds may use the accent colour.
      .filter((file) => /color:\s*"var\(--color-(text-subtle|success|accent)\)"/.test(fs.readFileSync(file, "utf-8")))
      .map((file) => path.relative(CONTENT_DIR, file));
    expect(offenders).toEqual([]);
  });
});
