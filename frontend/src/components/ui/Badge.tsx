"use client";

type BadgeVariant =
  | "published"
  | "unpublished"
  | "active"
  | "disabled"
  | "pdf"
  | "audio"
  | "video"
  | "image"
  | "video_link"
  | "external_link"
  | "default";

interface BadgeProps {
  variant?: BadgeVariant;
  children: React.ReactNode;
  className?: string;
}

const variantStyles: Record<BadgeVariant, string> = {
  published:
    "bg-[var(--color-success-bg)] text-[var(--color-success)] border border-green-200",
  unpublished:
    "bg-[var(--color-warning-bg)] text-[var(--color-warning)] border border-amber-200",
  active:
    "bg-[var(--color-success-bg)] text-[var(--color-success)] border border-green-200",
  disabled:
    "bg-[var(--color-danger-bg)] text-[var(--color-danger)] border border-red-200",
  pdf: "bg-red-50 text-red-600 border border-red-200",
  audio: "bg-purple-50 text-purple-600 border border-purple-200",
  video: "bg-blue-50 text-blue-600 border border-blue-200",
  image: "bg-teal-50 text-teal-600 border border-teal-200",
  video_link: "bg-[var(--color-primary-light)] text-[var(--color-primary)] border border-[var(--color-primary)]/20",
  external_link: "bg-slate-100 text-slate-600 border border-slate-200",
  default: "bg-[var(--color-surface-secondary)] text-[var(--color-text-muted)] border border-[var(--color-border)]",
};

export function Badge({ variant = "default", children, className = "" }: BadgeProps) {
  return (
    <span
      className={[
        "inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium whitespace-nowrap",
        variantStyles[variant],
        className,
      ].join(" ")}
    >
      {children}
    </span>
  );
}
