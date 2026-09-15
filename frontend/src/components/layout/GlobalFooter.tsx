"use client";

import { usePathname } from "next/navigation";

export function GlobalFooter() {
  const pathname = usePathname();
  const isStudentRoute = pathname.startsWith("/students");

  return (
    <footer
      className={[
        "fixed bottom-0 inset-x-0 z-50",
        "h-8 px-5",
        isStudentRoute ? "hidden sm:grid" : "grid",
      ].join(" ")}
      style={{
        background: "var(--color-surface-secondary)",
        borderTop: "1px solid var(--color-border)",
        fontSize: "12px",
        color: "var(--color-text-subtle)",
        gridTemplateColumns: "1fr 1fr 1fr",
        alignItems: "center",
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
