"use client";

import { useEffect, useState } from "react";
import { X, Download } from "lucide-react";

// ── Types ─────────────────────────────────────────────────────────────────────
interface BeforeInstallPromptEvent extends Event {
  prompt: () => Promise<void>;
  userChoice: Promise<{ outcome: "accepted" | "dismissed" }>;
}

// ── Constants ─────────────────────────────────────────────────────────────────
const DISMISS_KEY      = "spark-install-dismissed";
const DISMISS_DURATION = 7 * 24 * 60 * 60 * 1000; // re-show after 7 days
const SHOW_DELAY_MS    = 2500;                       // wait before appearing

// ── Component ─────────────────────────────────────────────────────────────────
export function InstallPrompt() {
  const [prompt, setPrompt]   = useState<BeforeInstallPromptEvent | null>(null);
  const [visible, setVisible] = useState(false);
  const [leaving, setLeaving] = useState(false);

  useEffect(() => {
    // Don't show if user dismissed recently
    const ts = localStorage.getItem(DISMISS_KEY);
    if (ts && Date.now() - parseInt(ts) < DISMISS_DURATION) return;

    const handler = (e: Event) => {
      e.preventDefault();
      setPrompt(e as BeforeInstallPromptEvent);
      setTimeout(() => setVisible(true), SHOW_DELAY_MS);
    };

    window.addEventListener("beforeinstallprompt", handler);
    return () => window.removeEventListener("beforeinstallprompt", handler);
  }, []);

  // Animated exit then hide
  function dismiss() {
    setLeaving(true);
    localStorage.setItem(DISMISS_KEY, Date.now().toString());
    setTimeout(() => { setVisible(false); setLeaving(false); }, 320);
  }

  async function handleInstall() {
    if (!prompt) return;
    await prompt.prompt();
    const { outcome } = await prompt.userChoice;
    if (outcome === "accepted") dismiss();
    setPrompt(null);
  }

  if (!visible) return null;

  return (
    <>
      <style>{`
        @keyframes ip-slide-up   { from { transform: translateY(110%); opacity: 0; } to { transform: translateY(0); opacity: 1; } }
        @keyframes ip-slide-down { from { transform: translateY(0);    opacity: 1; } to { transform: translateY(110%); opacity: 0; } }
        @keyframes ip-fade-in    { from { opacity: 0; transform: translateY(12px) scale(0.97); } to { opacity: 1; transform: translateY(0) scale(1); } }
        @keyframes ip-fade-out   { from { opacity: 1; transform: translateY(0) scale(1); } to { opacity: 0; transform: translateY(12px) scale(0.97); } }
      `}</style>

      {/* ── Mobile bottom sheet ───────────────────────────────────────────────
           Slides up from the bottom on small screens.                         */}
      <div
        className="sm:hidden"
        style={{
          position: "fixed",
          bottom: 0,
          left: 0,
          right: 0,
          zIndex: 9998,
          animation: leaving
            ? "ip-slide-down 0.3s cubic-bezier(0.4,0,1,1) forwards"
            : "ip-slide-up 0.38s cubic-bezier(0,0,0.2,1) forwards",
        }}
      >
        <div
          style={{
            background: "#ffffff",
            borderTop: "1px solid #e6e3df",
            borderRadius: "20px 20px 0 0",
            padding: "20px 20px 28px",
            boxShadow: "0 -8px 40px rgba(0,0,0,0.10)",
          }}
        >
          {/* Drag handle */}
          <div style={{
            width: 36, height: 4,
            borderRadius: 99,
            background: "#e6e3df",
            margin: "0 auto 18px",
          }} />

          {/* Header row */}
          <div style={{ display: "flex", alignItems: "flex-start", gap: 14 }}>
            {/* Star icon */}
            <div style={{
              width: 48, height: 48, borderRadius: 12, flexShrink: 0,
              background: "#fff4e6",
              display: "flex", alignItems: "center", justifyContent: "center",
              border: "1px solid #fde8c4",
            }}>
              <StarIcon size={24} />
            </div>

            {/* Text */}
            <div style={{ flex: 1, minWidth: 0 }}>
              <p style={{ fontSize: 16, fontWeight: 700, color: "#1A3150", letterSpacing: "-0.02em", lineHeight: 1.2 }}>
                Install SPARK
              </p>
              <p style={{ fontSize: 13, color: "#8fa3b8", marginTop: 4, lineHeight: 1.45 }}>
                Add to your home screen for faster, offline-ready access.
              </p>
            </div>

            {/* Close */}
            <button
              onClick={dismiss}
              aria-label="Dismiss install prompt"
              style={{
                width: 30, height: 30, borderRadius: 99, border: "none",
                background: "#f3f4f6", cursor: "pointer", display: "flex",
                alignItems: "center", justifyContent: "center", flexShrink: 0,
                color: "#8fa3b8", transition: "background 0.15s",
              }}
            >
              <X size={15} />
            </button>
          </div>

          {/* Install button */}
          <button
            onClick={handleInstall}
            style={{
              marginTop: 18,
              width: "100%",
              height: 48,
              borderRadius: 12,
              border: "none",
              background: "#FF8C00",
              color: "#ffffff",
              fontSize: 14,
              fontWeight: 600,
              fontFamily: "inherit",
              letterSpacing: "0.01em",
              cursor: "pointer",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              gap: 8,
              boxShadow: "0 2px 14px rgba(255,140,0,0.28)",
              transition: "background 0.15s, transform 0.15s",
            }}
          >
            <Download size={16} />
            Install App
          </button>
        </div>
      </div>

      {/* ── Desktop floating card ─────────────────────────────────────────────
           Fades + slides in at the bottom-centre of the screen.               */}
      <div
        className="hidden sm:block"
        style={{
          position: "fixed",
          bottom: 28,
          left: "50%",
          transform: "translateX(-50%)",
          zIndex: 9998,
          width: "clamp(320px, 40vw, 420px)",
          animation: leaving
            ? "ip-fade-out 0.3s cubic-bezier(0.4,0,1,1) forwards"
            : "ip-fade-in 0.38s cubic-bezier(0,0,0.2,1) forwards",
        }}
      >
        <div
          style={{
            background: "#ffffff",
            border: "1px solid #e6e3df",
            borderRadius: 18,
            padding: "18px 20px 20px",
            boxShadow:
              "0 4px 6px rgba(0,0,0,0.04), 0 12px 40px rgba(0,0,0,0.10)",
          }}
        >
          {/* Top row: icon + text + close */}
          <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
            {/* Star icon */}
            <div style={{
              width: 44, height: 44, borderRadius: 11, flexShrink: 0,
              background: "#fff4e6",
              display: "flex", alignItems: "center", justifyContent: "center",
              border: "1px solid #fde8c4",
            }}>
              <StarIcon size={22} />
            </div>

            {/* Text */}
            <div style={{ flex: 1, minWidth: 0 }}>
              <p style={{ fontSize: 14, fontWeight: 700, color: "#1A3150", letterSpacing: "-0.02em" }}>
                Install SPARK
              </p>
              <p style={{ fontSize: 12, color: "#8fa3b8", marginTop: 3, lineHeight: 1.4 }}>
                Add to home screen for faster, offline-ready access.
              </p>
            </div>

            {/* Close */}
            <button
              onClick={dismiss}
              aria-label="Dismiss install prompt"
              style={{
                width: 28, height: 28, borderRadius: 99, border: "none",
                background: "#f3f4f6", cursor: "pointer", display: "flex",
                alignItems: "center", justifyContent: "center", flexShrink: 0,
                color: "#8fa3b8", transition: "background 0.15s",
              }}
            >
              <X size={13} />
            </button>
          </div>

          {/* Action row */}
          <div style={{ display: "flex", gap: 10, marginTop: 16 }}>
            <button
              onClick={dismiss}
              style={{
                flex: 1,
                height: 40,
                borderRadius: 10,
                border: "1px solid #e6e3df",
                background: "transparent",
                color: "#5c6e82",
                fontSize: 13,
                fontWeight: 500,
                fontFamily: "inherit",
                cursor: "pointer",
                transition: "background 0.15s",
              }}
            >
              Not now
            </button>
            <button
              onClick={handleInstall}
              style={{
                flex: 2,
                height: 40,
                borderRadius: 10,
                border: "none",
                background: "#FF8C00",
                color: "#ffffff",
                fontSize: 13,
                fontWeight: 600,
                fontFamily: "inherit",
                cursor: "pointer",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                gap: 7,
                boxShadow: "0 2px 10px rgba(255,140,0,0.26)",
                transition: "background 0.15s",
              }}
            >
              <Download size={14} />
              Install
            </button>
          </div>
        </div>
      </div>
    </>
  );
}

// ── Inline SPARK star SVG ─────────────────────────────────────────────────────
function StarIcon({ size }: { size: number }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 100 100"
      fill="none"
      aria-hidden="true"
    >
      <path
        d="M 50,2 L 56,44 L 98,50 L 56,56 L 50,98 L 44,56 L 2,50 L 44,44 Z"
        fill="#FF8C00"
      />
    </svg>
  );
}
