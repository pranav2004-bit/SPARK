"use client";

/**
 * SplashScreen — Brand intro animation for SPARK.
 *
 * Sequence (total 5 s):
 *  0.0 – 1.6 s  ANITS slides in from centre; SPARK enters from centre; divider scales up
 *  2.2 – 3.2 s  "by sanjivo" drifts up into view at the bottom (1 s, delayed 2.2 s)
 *  3.2 – 4.4 s  Everything holds at full opacity
 *  4.4 – 5.0 s  Entire screen fades to transparent → component unmounts
 *
 * Session-once:  sessionStorage key "spark_splash_seen" — skipped on every
 *                subsequent visit within the same browser session.
 *
 * Pure CSS @keyframes — no JS animation loops, buttery smooth on any device.
 */

import { useEffect, useState } from "react";
import Image from "next/image";

const SPLASH_KEY  = "spark_splash_seen";
const TOTAL_MS    = 5000; // must match splash-lifecycle animation duration

export function SplashScreen() {
  // Start true — the inline script in layout.tsx already hid the body so
  // the page content is invisible until we reveal it below.
  const [visible, setVisible] = useState(true);

  useEffect(() => {
    function dismiss() {
      // Reveal body (removes the CSS visibility:hidden set by the inline script)
      document.documentElement.removeAttribute("data-splash");
      setVisible(false);
    }

    if (sessionStorage.getItem(SPLASH_KEY)) {
      // Already seen — reveal immediately, no animation
      dismiss();
      return;
    }

    // First visit — play full animation then reveal
    const t = setTimeout(() => {
      sessionStorage.setItem(SPLASH_KEY, "1");
      dismiss();
    }, TOTAL_MS);

    return () => clearTimeout(t);
  }, []);

  if (!visible) return null;

  return (
    <>
      {/* ── Keyframe definitions ──────────────────────────────────────────── */}
      <style>{`
        /* Wrapper: holds fully visible, then fades out in the last 10 % */
        @keyframes splash-lifecycle {
          0%,  88% { opacity: 1; }
          100%     { opacity: 0; }
        }

        /* ANITS: fades in at the visual centre, then glides left */
        @keyframes anits-enter {
          0%   { opacity: 0; transform: translateX(64px);  }
          14%  { opacity: 1; transform: translateX(64px);  }
          100% { opacity: 1; transform: translateX(0);     }
        }

        /* SPARK: starts at the same centre offset, delayed, then glides right */
        @keyframes spark-enter {
          0%   { opacity: 0; transform: translateX(-64px); }
          30%  { opacity: 0; transform: translateX(-64px); }
          52%  { opacity: 1; transform: translateX(-64px); }
          100% { opacity: 1; transform: translateX(0);     }
        }

        /* Vertical divider: scales up from centre after logos are in position */
        @keyframes divider-grow {
          0%,  48% { transform: scaleY(0); opacity: 0; }
          72%      { opacity: 1;           }
          100%     { transform: scaleY(1); opacity: 1; }
        }

        /* "by sanjivo": drifts up after logos settle (has its own delay) */
        @keyframes sanjivo-enter {
          0%   { opacity: 0; transform: translateY(10px); }
          100% { opacity: 1; transform: translateY(0);    }
        }
      `}</style>

      {/* ── Full-screen backdrop ──────────────────────────────────────────── */}
      <div
        aria-hidden="true"
        style={{
          position:       "fixed",
          inset:          0,
          zIndex:         9999,
          visibility:     "visible", // override html[data-splash] body { visibility:hidden }
          background:     "#1A3150",
          display:        "flex",
          flexDirection:  "column",
          alignItems:     "center",
          justifyContent: "center",
          animation:      `splash-lifecycle ${TOTAL_MS}ms cubic-bezier(0.4, 0, 0.6, 1) forwards`,
        }}
      >

        {/* ── Logo row ─────────────────────────────────────────────────────── */}
        <div style={{ display: "flex", alignItems: "center" }}>

          {/* ANITS logo card — enters at centre, slides to left */}
          <div
            style={{
              marginRight:  "clamp(20px, 3vw, 40px)",
              background:   "#ffffff",
              borderRadius: "clamp(12px, 1.4vw, 18px)",
              padding:      "clamp(14px, 1.8vw, 22px)",
              boxShadow:    "0 4px 32px rgba(0, 0, 0, 0.18)",
              display:      "flex",
              alignItems:   "center",
              justifyContent: "center",
              opacity:      0,
              animation:    `anits-enter 1.6s cubic-bezier(0.4, 0, 0.2, 1) forwards`,
            }}
          >
            <Image
              src="/institution-logo.png"
              alt="ANITS"
              width={140}
              height={140}
              priority
              style={{
                width:     "clamp(72px, 10vw, 120px)",
                height:    "clamp(72px, 10vw, 120px)",
                objectFit: "contain",
                display:   "block",
              }}
            />
          </div>

          {/* Vertical divider */}
          <div
            style={{
              width:           2,
              height:          "clamp(80px, 12vw, 140px)",
              background:      "rgba(255, 255, 255, 0.35)",
              borderRadius:    1,
              transformOrigin: "center",
              animation:       `divider-grow 1.6s cubic-bezier(0.4, 0, 0.2, 1) forwards`,
            }}
          />

          {/* SPARK logo card — enters at same centre offset, slides to right */}
          <div
            style={{
              marginLeft:   "clamp(20px, 3vw, 40px)",
              background:   "#ffffff",
              borderRadius: "clamp(12px, 1.4vw, 18px)",
              padding:      "clamp(14px, 1.8vw, 22px) clamp(18px, 2.4vw, 30px)",
              boxShadow:    "0 4px 32px rgba(0, 0, 0, 0.18)",
              display:      "flex",
              alignItems:   "center",
              justifyContent: "center",
              opacity:      0,
              animation:    `spark-enter 1.6s cubic-bezier(0.4, 0, 0.2, 1) forwards`,
            }}
          >
            <Image
              src="/spark-logo.svg"
              alt="SPARK"
              width={0}
              height={0}
              priority
              style={{
                height:  "clamp(72px, 10vw, 120px)",
                width:   "auto",
                display: "block",
              }}
            />
          </div>

        </div>

        {/* ── "by sanjivo" ─────────────────────────────────────────────────── */}
        <p
          style={{
            position:      "absolute",
            bottom:        "clamp(28px, 5vh, 48px)",
            fontFamily:    '"Inter", -apple-system, BlinkMacSystemFont, "Segoe UI", system-ui, sans-serif',
            fontSize:      "clamp(11px, 1.2vw, 14px)",
            fontWeight:    500,
            letterSpacing: "0.25em",
            color:         "rgba(255, 255, 255, 0.60)",
            userSelect:    "none",
            animation:     `sanjivo-enter 1s cubic-bezier(0.4, 0, 0.2, 1) 2.2s both`,
          }}
        >
          by sanjivo
        </p>

      </div>
    </>
  );
}
