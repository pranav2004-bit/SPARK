"use client";

/**
 * GlobalLoader — Premium full-screen loading state for SPARK.
 *
 * Features:
 *  • Studio-lighting radial gradient background (pure white centre → warm off-white edges)
 *  • 4-pointed SPARK star in SVG with a "chasing" stroke that races around its perimeter
 *  • Silky levitation animation with a reactive floor shadow (shrinks/blurs as star rises)
 *  • Pulsing "LOADING" text synchronised to the levitation rhythm
 *  • Fully mobile-first; all sizes driven by clamp() so the composition scales
 *    beautifully from 320 px phones up to 4 K monitors without a single breakpoint
 *
 * Usage:
 *  • Drop <GlobalLoader /> wherever a full-screen loading state is needed.
 *  • For automatic Next.js route transitions add it to app/loading.tsx (already done).
 */

export function GlobalLoader() {
  return (
    <>
      {/* ── Keyframe definitions ─────────────────────────────────────────────── */}
      <style>{`
        /* Silky buoyant float — eases in/out like a breath, not a bounce */
        @keyframes spark-levitate {
          0%   { transform: translateY(0px);   }
          50%  { transform: translateY(-20px);  }
          100% { transform: translateY(0px);   }
        }

        /* Floor shadow reacts inversely to levitation height */
        @keyframes spark-shadow {
          0%   { transform: scaleX(1);    opacity: 0.22; filter: blur(5px);  }
          50%  { transform: scaleX(0.45); opacity: 0.07; filter: blur(12px); }
          100% { transform: scaleX(1);    opacity: 0.22; filter: blur(5px);  }
        }

        /* Stroke races continuously around the star's perimeter */
        @keyframes spark-chase {
          from { stroke-dashoffset: 0;    }
          to   { stroke-dashoffset: -340; }
        }

        /* Text pulses in sync with the levitation — same duration, same easing */
        @keyframes spark-text {
          0%   { opacity: 0.55; }
          50%  { opacity: 0.20; }
          100% { opacity: 0.55; }
        }
      `}</style>

      {/* ── Full-screen backdrop ──────────────────────────────────────────────── */}
      <div
        role="status"
        aria-label="Loading"
        style={{
          position: "fixed",
          inset: 0,
          zIndex: 9999,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          /* Studio lighting: pure white core fading to premium warm off-white */
          background:
            "radial-gradient(ellipse at 50% 48%, #ffffff 0%, #f7f5f2 45%, #ece8e3 100%)",
        }}
      >
        {/* ── Composition column ─────────────────────────────────────────────── */}
        <div
          style={{
            display: "flex",
            flexDirection: "column",
            alignItems: "center",
          }}
        >

          {/* ── Star (levitating) ──────────────────────────────────────────────
               The entire SVG moves; the shadow sibling stays fixed, so the
               visual gap between them grows exactly as the star rises.          */}
          <div
            style={{
              animation:
                "spark-levitate 2.8s cubic-bezier(0.45, 0, 0.55, 1) infinite",
            }}
          >
            <svg
              viewBox="0 0 100 100"
              fill="none"
              xmlns="http://www.w3.org/2000/svg"
              aria-hidden="true"
              style={{
                /* Mobile-first scaling — 80 px on smallest phones → 128 px on desktop */
                width:  "clamp(80px, 16vw, 128px)",
                height: "clamp(80px, 16vw, 128px)",
                display: "block",
              }}
            >
              {/*
                4-pointed SPARK star
                  Outer radius 48 → points at (50,2) (98,50) (50,98) (2,50)
                  Inner radius ~8.5 → notches at (56,44) (56,56) (44,56) (44,44)
                  Perimeter ≈ 340 units  →  dasharray "85 255" = 25% fill
              */}

              {/* Base: faint static ghost of the full star */}
              <path
                d="M 50,2 L 56,44 L 98,50 L 56,56 L 50,98 L 44,56 L 2,50 L 44,44 Z"
                stroke="#FF8C00"
                strokeWidth="2"
                strokeOpacity="0.13"
                strokeLinejoin="miter"
              />

              {/* Active: solid orange stroke that races around the perimeter */}
              <path
                d="M 50,2 L 56,44 L 98,50 L 56,56 L 50,98 L 44,56 L 2,50 L 44,44 Z"
                stroke="#FF8C00"
                strokeWidth="2.5"
                strokeLinejoin="round"
                strokeLinecap="round"
                strokeDasharray="85 255"
                style={{
                  animation: "spark-chase 1.8s linear infinite",
                }}
              />
            </svg>
          </div>

          {/* ── Floor shadow ───────────────────────────────────────────────────
               Stays fixed in the column; the star's upward movement naturally
               increases the visual distance, simulating a cast shadow.          */}
          <div
            style={{
              marginTop: "clamp(10px, 1.8vw, 16px)",
              width:      "clamp(44px, 9vw,  68px)",
              height:     "clamp(8px,  1.6vw, 12px)",
              background:
                "radial-gradient(ellipse at center, rgba(20, 30, 50, 0.55) 0%, rgba(20, 30, 50, 0) 72%)",
              borderRadius: "50%",
              transformOrigin: "center center",
              animation:
                "spark-shadow 2.8s cubic-bezier(0.45, 0, 0.55, 1) infinite",
            }}
          />

          {/* ── "LOADING" text ─────────────────────────────────────────────────
               Uppercase, wide tracking, muted slate — premium editorial feel.
               Opacity pulses in perfect sync with the levitation (same timing). */}
          <p
            style={{
              marginTop:   "clamp(20px, 3.5vw, 30px)",
              fontFamily:
                '"Inter", -apple-system, BlinkMacSystemFont, "Segoe UI", system-ui, sans-serif',
              fontSize:    "clamp(9px, 1.6vw, 11px)",
              fontWeight:  600,
              letterSpacing: "0.32em",
              color:       "#8B9BAD",
              textTransform: "uppercase",
              userSelect:  "none",
              animation:
                "spark-text 2.8s cubic-bezier(0.45, 0, 0.55, 1) infinite",
            }}
          >
            LOADING
          </p>

        </div>
      </div>
    </>
  );
}
