"use client";

import { useEffect, useState, useRef, useCallback } from "react";
import { useRouter } from "next/navigation";
import { ExternalLink } from "lucide-react";
import api from "@/lib/api";
import { saveScrollRedirect } from "@/lib/scrollRedirect";
import type { StudentScrollResponse, ScrollUpdate } from "@/types";

// ── Context ───────────────────────────────────────────────────────────────────
// public  — landing page / login pages. Unauthenticated user.
//           Clicking a same-origin student link → save + redirect to login.
//           External links → open in new tab as normal.
// student — authenticated student module.
//           Student links → navigate directly.
//           Admin / unknown links → silently blocked (students can't access admin).
//           External links → new tab.
// admin   — authenticated admin module.
//           Any same-origin link → navigate directly.
//           External links → new tab.
export type ScrollContext = "public" | "student" | "admin";

interface Props {
  /** Which part of the app this bar is rendered in. Controls click behaviour. */
  context?: ScrollContext;
  /**
   * CSS top value for `position: sticky`.
   * 0  → pages where the bar itself defines the top edge
   * 56 → pages with a 56px fixed header (admin, student modules)
   */
  stickyTop?: number;
  /**
   * When true, renders as `position: relative` instead of sticky.
   * Use this when a parent element handles the sticky behaviour (e.g.
   * the landing-page wrapper that groups the bar + nav together).
   */
  disableSticky?: boolean;
}

// ── URL helpers ───────────────────────────────────────────────────────────────

function isSameOrigin(url: string): boolean {
  if (typeof window === "undefined") return false;
  try {
    return new URL(url, window.location.origin).origin === window.location.origin;
  } catch {
    // Relative path → same origin
    return true;
  }
}

function getPathname(url: string): string {
  try {
    return new URL(url, window.location.origin).pathname;
  } catch {
    return url.startsWith("/") ? url : `/${url}`;
  }
}

function isStudentPath(pathname: string): boolean {
  return pathname.startsWith("/students/") && !pathname.startsWith("/students/login");
}

function isAdminPath(pathname: string): boolean {
  return pathname.startsWith("/admin/");
}

// ── Duration ──────────────────────────────────────────────────────────────────
// Target: roughly one full-screen slot (100vw) every N seconds.
// We repeat items enough times so "half" the track definitely exceeds the
// widest realistic monitor (4K ≈ 3840px). Average item ~300px → 13 items fills 4K.
const SECONDS_PER_ITEM = 5;

function buildTrack(items: ScrollUpdate[]): ScrollUpdate[] {
  const repeatCount = Math.max(2, Math.ceil(15 / items.length));
  // Keep total repetitions even for seamless −50% loop
  const even = repeatCount % 2 === 0 ? repeatCount : repeatCount + 1;
  return Array.from({ length: even }, () => items).flat();
}

// ── Component ─────────────────────────────────────────────────────────────────

export function ScrollingUpdates({ context = "student", stickyTop = 56, disableSticky = false }: Props) {
  const [data, setData]     = useState<StudentScrollResponse | null>(null);
  const [paused, setPaused] = useState(false);
  const hasFetched          = useRef(false);
  const router              = useRouter();

  useEffect(() => {
    if (hasFetched.current) return;
    hasFetched.current = true;

    // Uses /api/students/scroll/ which is now AllowAny
    api.get("/students/scroll/").then((res) => {
      setData(res.data.data);
    }).catch(() => {
      // Not critical — silently hide on any error
    });
  }, []);

  // ── Click handler ──────────────────────────────────────────────────────────
  const handleLink = useCallback((link: string) => {
    if (!link) return;

    // External URL → always open in new tab, no auth logic needed
    if (!isSameOrigin(link)) {
      window.open(link, "_blank", "noopener,noreferrer");
      return;
    }

    const pathname = getPathname(link);

    switch (context) {
      case "public":
        // Save the target and send user to login.
        // consumeScrollRedirect() will validate it's a student path after login.
        saveScrollRedirect(pathname);
        router.push("/students/login");
        break;

      case "student":
        // Students must only navigate within /students/
        if (isStudentPath(pathname)) {
          router.push(pathname);
        }
        // Admin paths or unknown → silently ignore (security boundary)
        break;

      case "admin":
        // Admin set the link themselves — navigate wherever it points
        if (isAdminPath(pathname) || isStudentPath(pathname) || pathname.startsWith("/")) {
          router.push(pathname);
        }
        break;
    }
  }, [context, router]);

  if (!data?.is_enabled || data.updates.length === 0) return null;

  const items    = data.updates;
  const track    = buildTrack(items);
  const duration = (track.length / 2) * SECONDS_PER_ITEM;
  const animName = data.direction === "left" ? "su-scroll-left" : "su-scroll-right";

  return (
    <>
      <style>{`
        @keyframes su-scroll-left {
          from { transform: translateX(0%);   }
          to   { transform: translateX(-50%); }
        }
        @keyframes su-scroll-right {
          from { transform: translateX(-50%); }
          to   { transform: translateX(0%);   }
        }
        .su-fade-left  { width: 80px; }
        .su-fade-right { width: 80px; }
        .su-chip       { padding: 0 36px; }
        @media (max-width: 767px) {
          .su-fade-left  { width: 36px; }
          .su-fade-right { width: 36px; }
          .su-chip       { padding: 0 18px; }
        }
      `}</style>

      <div
        role="marquee"
        aria-label="Recent updates"
        style={{
          position: disableSticky ? "relative" : "sticky",
          top: disableSticky ? undefined : stickyTop,
          zIndex: disableSticky ? undefined : 39,
          overflow: "hidden",
          background: "var(--color-primary)",
          borderBottom: "1px solid rgba(255,255,255,0.08)",
          height: 38,
          display: "flex",
          alignItems: "center",
        }}
      >
        {/* Left gradient fade */}
        <div className="su-fade-left" style={{
          position: "absolute", left: 0, top: 0, bottom: 0,
          background: "linear-gradient(to right, var(--color-primary) 40%, transparent)",
          zIndex: 2, pointerEvents: "none",
        }} />

        {/* Scrolling track */}
        <div
          onMouseEnter={() => setPaused(true)}
          onMouseLeave={() => setPaused(false)}
          style={{
            display: "inline-flex",
            alignItems: "center",
            whiteSpace: "nowrap",
            animationName: animName,
            animationDuration: `${duration}s`,
            animationTimingFunction: "linear",
            animationIterationCount: "infinite",
            animationPlayState: paused ? "paused" : "running",
            willChange: "transform",
          }}
        >
          {track.map((item, i) => (
            <Chip
              key={`${item.id}-${i}`}
              item={item}
              onLinkClick={handleLink}
              ariaHidden={i >= items.length}
            />
          ))}
        </div>

        {/* Right gradient fade */}
        <div className="su-fade-right" style={{
          position: "absolute", right: 0, top: 0, bottom: 0,
          background: "linear-gradient(to left, var(--color-primary) 40%, transparent)",
          zIndex: 2, pointerEvents: "none",
        }} />
      </div>
    </>
  );
}

// ── Chip ──────────────────────────────────────────────────────────────────────

interface ChipProps {
  item: ScrollUpdate;
  onLinkClick: (link: string) => void;
  ariaHidden?: boolean;
}

function Chip({ item, onLinkClick, ariaHidden }: ChipProps) {
  const hasLink = Boolean(item.link);

  function handleClick(e: React.MouseEvent) {
    if (!hasLink) return;
    e.preventDefault();
    onLinkClick(item.link);
  }

  return (
    <span
      role={hasLink ? "button" : undefined}
      tabIndex={hasLink && !ariaHidden ? 0 : -1}
      aria-hidden={ariaHidden}
      onClick={hasLink ? handleClick : undefined}
      onKeyDown={hasLink ? (e) => { if (e.key === "Enter" || e.key === " ") handleClick(e as unknown as React.MouseEvent); } : undefined}
      className="su-chip"
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: 8,
        fontSize: 12,
        fontWeight: 500,
        color: "rgba(255,255,255,0.88)",
        letterSpacing: "0.02em",
        lineHeight: "36px",
        cursor: hasLink ? "pointer" : "default",
        transition: "color 0.15s",
        userSelect: "none",
        whiteSpace: "nowrap",
      }}
      onMouseEnter={(e) => { if (hasLink) e.currentTarget.style.color = "var(--color-accent)"; }}
      onMouseLeave={(e) => { if (hasLink) e.currentTarget.style.color = "rgba(255,255,255,0.88)"; }}
    >
      {item.show_new_badge && (
        <span style={{
          display: "inline-flex",
          alignItems: "center",
          fontSize: 9,
          fontWeight: 700,
          letterSpacing: "0.08em",
          lineHeight: 1,
          padding: "3px 7px",
          borderRadius: 99,
          background: "linear-gradient(135deg, var(--color-accent) 0%, var(--color-accent-hover) 100%)",
          color: "#fff",
          flexShrink: 0,
          textTransform: "uppercase",
        }}>
          NEW
        </span>
      )}

      {item.text}

      {hasLink && (
        <ExternalLink size={10} style={{ opacity: 0.5, flexShrink: 0 }} aria-hidden="true" />
      )}
    </span>
  );
}
