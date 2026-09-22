"use client";

import { usePathname } from "next/navigation";

export function GlobalFooter() {
  const pathname = usePathname();
  // Hidden on mobile for student routes in general (screen space is tight
  // on data-dense student pages), except the login page, which is shown on
  // mobile too since it's not a data-dense screen.
  const hideOnMobile = pathname.startsWith("/students") && pathname !== "/students/login";

  return (
    <footer
      className={[
        "fixed bottom-0 inset-x-0 z-50",
        "px-5",
        hideOnMobile ? "hidden sm:grid" : "grid",
      ].join(" ")}
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
