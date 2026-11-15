"use client";

import { useEffect } from "react";

// Next.js App Router convention — fires only when the ROOT layout itself
// throws (ToastProvider/DepartmentsProvider setup, etc.), the one case
// error.tsx can't catch (error.tsx is rendered INSIDE the root layout, so
// it's gone too if the layout itself is what crashed). Replaces the entire
// document, so this can't assume globals.css, the shared Button/ErrorScreen
// components, or any provider are still available — it renders its own
// <html>/<body> with fully inline styles, the same self-sufficiency
// public/offline.html already needs as a static file outside the Next.js
// build entirely. This is the last line of defense: if this file itself
// ever throws, there's nothing left to catch it.
export default function GlobalError({ error }: { error: Error & { digest?: string }; reset: () => void }) {
  useEffect(() => {
    if (process.env.NODE_ENV === "development") {
      console.error("[global-error.tsx] Root layout crashed:", error);
    }
  }, [error]);

  return (
    <html lang="en">
      <body style={{ margin: 0 }}>
        <div
          style={{
            minHeight: "100vh",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            padding: "24px",
            fontFamily:
              '"Inter", -apple-system, BlinkMacSystemFont, "Segoe UI", system-ui, sans-serif',
            background:
              "radial-gradient(ellipse at 50% 48%, #ffffff 0%, #f7f5f2 45%, #ece8e3 100%)",
          }}
        >
          <div style={{ display: "flex", flexDirection: "column", alignItems: "center", textAlign: "center", maxWidth: 360 }}>
            <div
              style={{
                width: 72,
                height: 72,
                borderRadius: "50%",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                background: "#fff4e6",
              }}
            >
              <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="#FF8C00" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                <path d="m21.73 18-8-14a2 2 0 0 0-3.46 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3Z" />
                <path d="M12 9v4" />
                <path d="M12 17h.01" />
              </svg>
            </div>
            <h1 style={{ marginTop: 24, fontSize: 24, fontWeight: 700, letterSpacing: "-0.03em", color: "#1A3150" }}>
              Something went wrong
            </h1>
            <p style={{ marginTop: 12, fontSize: 15, lineHeight: 1.55, color: "#5c6e82" }}>
              The app hit an unexpected error. Reloading usually fixes it.
            </p>
            <button
              onClick={() => window.location.reload()}
              style={{
                marginTop: 32,
                padding: "13px 30px",
                borderRadius: 10,
                border: "none",
                cursor: "pointer",
                background: "#FF8C00",
                color: "#ffffff",
                fontFamily: "inherit",
                fontSize: 14,
                fontWeight: 600,
                boxShadow: "0 2px 12px rgba(255,140,0,0.30)",
              }}
            >
              Reload
            </button>
            <div style={{ marginTop: 40, width: 36, height: 1, background: "#e6e3df" }} />
            <p style={{ marginTop: 16, fontSize: 11, fontWeight: 600, letterSpacing: "0.28em", color: "#b0bec8", textTransform: "uppercase" }}>
              SPARK
            </p>
          </div>
        </div>
      </body>
    </html>
  );
}
