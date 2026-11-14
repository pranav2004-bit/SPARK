"use client";

import { usePathname } from "next/navigation";

export function GlobalFooter() {
  const pathname = usePathname();
  // Restricted to the application's own home page only (2026-11-14, user
  // decision) — every other route (every admin/student/super-admin/IT
  // portal screen) used to show this unconditionally since it's mounted
  // once in the root layout; it's branding for the public landing page,
  // not something that belongs on every data-dense authenticated screen.
  if (pathname !== "/") return null;

  return (
    <footer
      className="fixed bottom-0 inset-x-0 z-50 px-5 grid"
      style={{
        background: "var(--color-surface-secondary)",
        borderTop: "1px solid var(--color-border)",
        fontSize: "12px",
        color: "var(--color-text-subtle)",
        gridTemplateColumns: "1fr 1fr 1fr",
        alignItems: "center",
        // Row itself stays the original ~32px tall; the safe-area inset is
        // added as extra padding below it (same convention as
        // StudentLayout's bottom nav) so the footer's own background fills
        // the gesture-bar strip instead of leaving it blank.
        paddingTop: "8px",
        paddingBottom: "calc(8px + env(safe-area-inset-bottom))",
      }}
    >
      {/* Left — empty */}
      <span />

      {/* Center */}
      <span style={{ textAlign: "center", whiteSpace: "nowrap", letterSpacing: "0.05em", fontWeight: 400 }}>
        A{" "}
        <strong style={{ color: "var(--color-accent)", fontWeight: 700, letterSpacing: "0.08em" }}>
          SANJIVO
        </strong>{" "}
        Product
      </span>

      {/* Right — hidden on mobile */}
      <span className="hidden sm:block" style={{ textAlign: "right", whiteSpace: "nowrap", letterSpacing: "0.04em", fontWeight: 400 }}>
        Co-partnered by{" "}
        <strong style={{ color: "var(--color-accent)", fontWeight: 700, letterSpacing: "0.06em" }}>
          AuraTech-Vision
        </strong>
      </span>
    </footer>
  );
}
