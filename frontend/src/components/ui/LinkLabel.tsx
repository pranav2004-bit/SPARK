"use client";

import { useLinkStatus } from "next/link";

// Renders a spinner in place of the label's leading icon while a Next.js
// <Link> navigation is pending — must be a child of that <Link>, per
// useLinkStatus()'s contract (it reads pending state from context).
export function LinkLabel({ children }: { children: React.ReactNode }) {
  const { pending } = useLinkStatus();
  return (
    <>
      {pending && (
        <span
          className="animate-spin shrink-0"
          style={{
            display: "inline-block",
            width: 14,
            height: 14,
            borderRadius: "50%",
            border: "2px solid currentColor",
            borderTopColor: "transparent",
            opacity: 0.9,
          }}
        />
      )}
      <span style={{ opacity: pending ? 0.7 : 1 }}>{children}</span>
    </>
  );
}
