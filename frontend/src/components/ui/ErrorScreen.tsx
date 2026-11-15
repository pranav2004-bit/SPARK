import type { LucideIcon } from "lucide-react";
import { Button } from "./Button";

interface ErrorScreenProps {
  icon: LucideIcon;
  title: string;
  message: string;
  primaryLabel: string;
  onPrimary: () => void;
  secondaryLabel?: string;
  onSecondary?: () => void;
}

/**
 * Shared full-screen shell for this app's own branded error interfaces —
 * not-found.tsx and error.tsx (added 2026-11-15, production-readiness
 * audit: before this, a 404 or an unhandled render crash fell through to
 * Next.js's own bare, unstyled default page — "404 / This page could not
 * be found", no SPARK branding at all, the only unstyled interface left in
 * an app whose other error state (public/offline.html) was already
 * properly designed).
 *
 * Deliberately NOT used by global-error.tsx — that one replaces the root
 * layout itself when it fires, so it can't safely assume globals.css's CSS
 * variables or this component's own React tree are even available; it
 * stays fully self-contained instead, the same way offline.html (a static
 * file outside the Next.js build entirely) already has to be.
 */
export function ErrorScreen({
  icon: Icon,
  title,
  message,
  primaryLabel,
  onPrimary,
  secondaryLabel,
  onSecondary,
}: ErrorScreenProps) {
  return (
    <div
      className="min-h-screen flex items-center justify-center px-6"
      style={{
        background:
          "radial-gradient(ellipse at 50% 48%, #ffffff 0%, var(--color-surface-secondary) 45%, var(--color-border) 100%)",
      }}
    >
      <div className="flex flex-col items-center text-center max-w-sm">
        <div
          className="flex items-center justify-center rounded-full"
          style={{ width: 72, height: 72, background: "var(--color-accent-light)" }}
        >
          <Icon size={32} color="var(--color-accent)" strokeWidth={1.75} />
        </div>

        <h1
          className="mt-6 text-2xl font-bold"
          style={{ color: "var(--color-text)", letterSpacing: "-0.03em" }}
        >
          {title}
        </h1>

        <p className="mt-3 text-[15px] leading-relaxed" style={{ color: "var(--color-text-muted)" }}>
          {message}
        </p>

        <div className="mt-8 flex flex-col sm:flex-row gap-3 w-full sm:w-auto">
          <Button variant="primary" size="lg" onClick={onPrimary}>
            {primaryLabel}
          </Button>
          {secondaryLabel && onSecondary && (
            <Button variant="secondary" size="lg" onClick={onSecondary}>
              {secondaryLabel}
            </Button>
          )}
        </div>

        <div
          className="mt-10 uppercase"
          style={{
            width: 36,
            height: 1,
            background: "var(--color-border)",
          }}
        />
        <p
          // Matches public/offline.html's own brand-footer color exactly —
          // not one of globals.css's tokens (those are for borders/text,
          // not this specific muted-brand treatment).
          className="mt-4 text-[11px] font-semibold uppercase"
          style={{ color: "#b0bec8", letterSpacing: "0.28em" }}
        >
          SPARK
        </p>
      </div>
    </div>
  );
}
