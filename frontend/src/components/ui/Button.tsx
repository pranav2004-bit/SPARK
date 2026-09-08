"use client";

import { forwardRef } from "react";
import { Loader2 } from "lucide-react";

type Variant = "primary" | "secondary" | "danger" | "ghost" | "success" | "warning";
type Size = "sm" | "md" | "lg";

interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  size?: Size;
  loading?: boolean;
  fullWidth?: boolean;
  leftIcon?: React.ReactNode;
  rightIcon?: React.ReactNode;
}

const variantStyles: Record<Variant, string> = {
  primary:
    "bg-[var(--color-accent)] text-white hover:bg-[var(--color-accent-hover)] shadow-sm",
  secondary:
    "bg-white text-[var(--color-text)] border border-[var(--color-border)] hover:bg-[var(--color-surface-hover)] shadow-sm",
  danger:
    "bg-[var(--color-danger)] text-white hover:bg-[var(--color-danger-hover)] shadow-sm",
  // text-[var(--color-accent)] at rest (not --color-text-muted): a ghost
  // button has no border/background to signal "this is clickable" the way
  // every other variant's fill does — muted gray at rest reads as plain
  // body text, not an actionable button (reported live, 2026-08-18).
  // Accent color is this app's existing convention for "this is
  // interactive" (links, active states), so a ghost button now reads the
  // same way even with no border/background.
  ghost:
    "bg-transparent text-[var(--color-accent)] hover:bg-[var(--color-surface-hover)] hover:text-[var(--color-accent-hover)]",
  success:
    "bg-[var(--color-success)] text-white hover:opacity-90 shadow-sm",
  warning:
    "bg-[var(--color-warning)] text-white hover:opacity-90 shadow-sm",
};

const sizeStyles: Record<Size, string> = {
  sm: "h-7 px-3 text-xs gap-1.5",
  md: "h-9 px-4 text-sm gap-2",
  lg: "h-11 px-6 text-sm gap-2",
};

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  (
    {
      variant = "primary",
      size = "md",
      loading = false,
      fullWidth = false,
      leftIcon,
      rightIcon,
      className = "",
      disabled,
      children,
      ...props
    },
    ref
  ) => {
    return (
      <button
        ref={ref}
        disabled={disabled || loading}
        className={[
          "inline-flex items-center justify-center font-medium rounded-[var(--radius-md)]",
          "cursor-pointer select-none",
          // Both branches use the disabled: variant (not a bare
          // cursor-wait utility) so it reliably wins over the plain
          // cursor-pointer above in Tailwind's generated stylesheet —
          // variant-prefixed utilities are always ordered after their
          // unprefixed base, a bare same-layer utility isn't guaranteed to.
          // Genuinely disabled (disabled prop, not loading) keeps the
          // "you can't do this" not-allowed cursor. Loading is a
          // temporary, expected state — its own spinner already
          // communicates "working," so a "blocked" cursor on top of that
          // reads as an error rather than a wait (reported live,
          // 2026-08-18) — cursor-wait is the correct semantic cursor here.
          disabled ? "disabled:opacity-50 disabled:cursor-not-allowed" : loading ? "disabled:opacity-50 disabled:cursor-wait" : "",
          variantStyles[variant],
          sizeStyles[size],
          fullWidth ? "w-full" : "",
          className,
        ]
          .filter(Boolean)
          .join(" ")}
        {...props}
      >
        {loading ? (
          <Loader2 className="animate-spin" size={14} />
        ) : (
          leftIcon
        )}
        {children}
        {!loading && rightIcon}
      </button>
    );
  }
);

Button.displayName = "Button";
