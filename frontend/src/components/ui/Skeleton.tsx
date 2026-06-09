"use client";

interface SkeletonProps {
  className?: string;
}

export function Skeleton({ className = "" }: SkeletonProps) {
  return (
    <div
      className={[
        "animate-pulse bg-[var(--color-border)] rounded-[var(--radius-sm)]",
        className,
      ].join(" ")}
      aria-hidden="true"
    />
  );
}

export function TableRowSkeleton({ cols = 5 }: { cols?: number }) {
  return (
    <tr>
      {Array.from({ length: cols }).map((_, i) => (
        <td key={i} className="px-4 py-3">
          <Skeleton className="h-4 w-full" />
        </td>
      ))}
    </tr>
  );
}

/** Generic card skeleton — use only when a page has no specific skeleton */
export function CardSkeleton() {
  return (
    <div className="bg-white border border-[var(--color-border)] rounded-[var(--radius-lg)] p-5 space-y-3">
      <Skeleton className="h-5 w-2/3" />
      <Skeleton className="h-4 w-1/3" />
      <div className="flex gap-2 pt-2">
        <Skeleton className="h-7 w-16" />
        <Skeleton className="h-7 w-16" />
      </div>
    </div>
  );
}

/**
 * CompanyCardSkeleton — pixel-matches the real company card structure.
 * Icon circle · company name · section count · badge · edit/delete →
 * coloured footer: publish button + view-sections row.
 * Transition from skeleton → card causes zero layout shift.
 */
export function CompanyCardSkeleton() {
  return (
    <div className="bg-white border border-[var(--color-border)] rounded-xl overflow-hidden">
      {/* Card body — mirrors p-5 layout */}
      <div className="p-5">
        <div className="flex items-start justify-between gap-3">
          {/* Left: icon circle + name + section count */}
          <div className="flex items-start gap-3 min-w-0">
            <Skeleton className="w-10 h-10 rounded-lg shrink-0" />
            <div className="min-w-0 pt-0.5 flex-1 space-y-2">
              <Skeleton className="h-4 w-36" />
              <Skeleton className="h-3 w-20" />
            </div>
          </div>
          {/* Right: badge + action icons */}
          <div className="flex items-center gap-1.5 shrink-0">
            <Skeleton className="h-5 w-16 rounded-full" />
            <Skeleton className="h-7 w-7 rounded-md" />
            <Skeleton className="h-7 w-7 rounded-md" />
          </div>
        </div>
      </div>
      {/* Footer — mirrors the accent-tinted footer row */}
      <div
        className="px-5 py-2.5 flex items-center justify-between"
        style={{ borderTop: "1px solid var(--color-border)", background: "var(--color-primary-light)" }}
      >
        <Skeleton className="h-7 w-24 rounded-md" />
        <Skeleton className="h-4 w-24" />
      </div>
    </div>
  );
}

/**
 * SectionCardSkeleton — pixel-matches the real section card structure.
 * Icon · section name · upload count → coloured footer: copy-link + view-uploads.
 * Transition from skeleton → card causes zero layout shift.
 */
export function SectionCardSkeleton() {
  return (
    <div className="bg-white border border-[var(--color-border)] rounded-xl overflow-hidden">
      {/* Card body — mirrors p-5 layout */}
      <div className="p-5">
        <div className="flex items-start justify-between gap-3">
          {/* Left: icon + name + upload count */}
          <div className="flex items-start gap-3 min-w-0">
            <Skeleton className="w-10 h-10 rounded-lg shrink-0" />
            <div className="min-w-0 pt-0.5 flex-1 space-y-2">
              <Skeleton className="h-4 w-32" />
              <Skeleton className="h-3 w-20" />
            </div>
          </div>
          {/* Right: edit + delete icon buttons */}
          <div className="flex items-center gap-1.5 shrink-0">
            <Skeleton className="h-7 w-7 rounded-md" />
            <Skeleton className="h-7 w-7 rounded-md" />
          </div>
        </div>
      </div>
      {/* Footer — mirrors the accent-tinted footer row */}
      <div
        className="px-5 py-2.5 flex items-center justify-between"
        style={{ borderTop: "1px solid var(--color-border)", background: "var(--color-primary-light)" }}
      >
        <Skeleton className="h-4 w-20" />
        <Skeleton className="h-4 w-24" />
      </div>
    </div>
  );
}

/**
 * UploadListSkeleton — pixel-matches the real upload list structure.
 * White card containing N rows: icon bg · name · badge+size · 4 action icons.
 * Transition from skeleton → list causes zero layout shift.
 */
export function UploadListSkeleton({ rows = 4 }: { rows?: number }) {
  return (
    <div className="bg-white border border-[var(--color-border)] rounded-[var(--radius-lg)] overflow-hidden">
      {Array.from({ length: rows }).map((_, i) => (
        <div
          key={i}
          className="flex items-center gap-4 px-5 py-4"
          style={i > 0 ? { borderTop: "1px solid var(--color-border)" } : undefined}
        >
          {/* Icon bg */}
          <Skeleton className="w-9 h-9 rounded-[var(--radius-md)] shrink-0" />
          {/* Name + badge row */}
          <div className="flex-1 min-w-0 space-y-2">
            <Skeleton className="h-4 w-48" />
            <div className="flex items-center gap-2">
              <Skeleton className="h-5 w-12 rounded-full" />
              <Skeleton className="h-3 w-16" />
            </div>
          </div>
          {/* Action icons: rename · copy · open · delete */}
          <div className="flex items-center gap-1 shrink-0">
            <Skeleton className="h-7 w-7 rounded-md" />
            <Skeleton className="h-7 w-7 rounded-md" />
            <Skeleton className="h-7 w-7 rounded-md" />
            <Skeleton className="h-7 w-7 rounded-md" />
          </div>
        </div>
      ))}
    </div>
  );
}

/**
 * ResourceItemCardSkeleton — pixel-matches the ItemCard in admin/resources/[module_id].
 * Icon circle · name · type label → footer: publish pill + 3 action icons.
 * Transition from skeleton → card causes zero layout shift.
 */
export function ResourceItemCardSkeleton() {
  return (
    <div
      className="rounded-[var(--radius-xl)] overflow-hidden"
      style={{
        background: "var(--color-surface)",
        border: "1px solid var(--color-border)",
        boxShadow: "var(--shadow-sm)",
      }}
    >
      {/* Body — mirrors px-5 pt-5 pb-4 */}
      <div className="px-5 pt-5 pb-4">
        <div className="flex items-start justify-between gap-3">
          <Skeleton className="w-11 h-11 rounded-[var(--radius-lg)] shrink-0" />
          <Skeleton className="w-4 h-4 rounded shrink-0 mt-0.5" />
        </div>
        <div className="mt-3 space-y-2">
          <Skeleton className="h-4 w-36" />
          <Skeleton className="h-3 w-20" />
        </div>
      </div>
      {/* Footer — mirrors px-4 py-3 */}
      <div
        className="px-4 py-3 flex items-center justify-between"
        style={{ borderTop: "1px solid var(--color-border)" }}
      >
        <Skeleton className="h-6 w-24 rounded-full" />
        <div className="flex items-center gap-1">
          <Skeleton className="h-8 w-8 rounded-[var(--radius-md)]" />
          <Skeleton className="h-8 w-8 rounded-[var(--radius-md)]" />
          <Skeleton className="h-8 w-8 rounded-[var(--radius-md)]" />
        </div>
      </div>
    </div>
  );
}

/**
 * QuestionCardSkeleton — pixel-matches the PracticeCard (type="question").
 * Icon circle · title · type label → footer: publish pill + 3 action icons.
 * Identical anatomy to ResourceItemCardSkeleton — zero layout shift on load.
 */
export function QuestionCardSkeleton() {
  return (
    <div
      className="rounded-[var(--radius-xl)] overflow-hidden"
      style={{
        background: "var(--color-surface)",
        border: "1px solid var(--color-border)",
        boxShadow: "var(--shadow-sm)",
      }}
    >
      <div className="px-5 pt-5 pb-4">
        <div className="flex items-start justify-between gap-3">
          <Skeleton className="w-11 h-11 rounded-[var(--radius-lg)] shrink-0" />
          <Skeleton className="w-4 h-4 rounded shrink-0 mt-0.5" />
        </div>
        <div className="mt-3 space-y-2">
          {/* Question number — e.g. #346 */}
          <Skeleton className="h-7 w-20" />
          {/* MCQ / FIB type badge */}
          <Skeleton className="h-5 w-14 rounded" />
        </div>
      </div>
      <div
        className="px-4 py-3 flex items-center justify-between"
        style={{ borderTop: "1px solid var(--color-border)" }}
      >
        <Skeleton className="h-6 w-24 rounded-full" />
        <div className="flex items-center gap-1">
          <Skeleton className="h-8 w-8 rounded-[var(--radius-md)]" />
          <Skeleton className="h-8 w-8 rounded-[var(--radius-md)]" />
          <Skeleton className="h-8 w-8 rounded-[var(--radius-md)]" />
        </div>
      </div>
    </div>
  );
}

export function LoadingSpinner({ size = 20, color }: { size?: number; color?: string }) {
  return (
    <div
      className="inline-flex items-center justify-center"
      aria-label="Loading"
      role="status"
    >
      <svg
        width={size}
        height={size}
        viewBox="0 0 24 24"
        fill="none"
        className="animate-spin"
        style={{ color: color ?? "var(--color-accent)" }}
      >
        <circle
          cx="12"
          cy="12"
          r="10"
          stroke="currentColor"
          strokeWidth="3"
          strokeLinecap="round"
          strokeDasharray="31.4"
          strokeDashoffset="10"
          opacity="0.3"
        />
        <path
          d="M12 2a10 10 0 0 1 10 10"
          stroke="currentColor"
          strokeWidth="3"
          strokeLinecap="round"
        />
      </svg>
    </div>
  );
}
