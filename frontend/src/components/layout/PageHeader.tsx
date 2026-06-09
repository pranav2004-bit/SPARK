"use client";

import { useRouter } from "next/navigation";
import { ArrowLeft, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/Button";

interface PageHeaderProps {
  title: string;
  subtitle?: string;
  /** Pass backHref for simple navigation, or onBack for custom handler */
  backHref?: string;
  onBack?: () => void;
  backLoading?: boolean;
  rightSlot?: React.ReactNode;
  centerSlot?: React.ReactNode;
  breadcrumb?: React.ReactNode;
  /** Render a skeleton shimmer in place of the title (e.g. while data loads) */
  titleSkeleton?: React.ReactNode;
}

export function PageHeader({
  title,
  subtitle,
  backHref,
  onBack,
  backLoading = false,
  rightSlot,
  centerSlot,
  breadcrumb,
  titleSkeleton,
}: PageHeaderProps) {
  const router = useRouter();

  const hasBack = !!(backHref || onBack);
  const handleBack = () => {
    if (onBack) { onBack(); return; }
    if (backHref) router.push(backHref);
  };

  return (
    <div className="flex items-center pb-4 sm:pb-5 mb-5 sm:mb-6 border-b border-[var(--color-border)] gap-4">

      {/* Left — back + title */}
      <div className="flex items-center gap-3 min-w-0 flex-1">
        {hasBack && (
          <Button
            variant="ghost"
            size="sm"
            onClick={handleBack}
            disabled={backLoading}
            aria-label="Go back"
            className="px-2 shrink-0 disabled:opacity-60"
          >
            {backLoading
              ? <Loader2 size={16} className="animate-spin" />
              : <ArrowLeft size={16} />
            }
          </Button>
        )}
        <div className="min-w-0">
          {/* Breadcrumb — desktop only. On mobile the back button is sufficient;
              showing the full path adds noise and redundancy with the title. */}
          {breadcrumb && (
            <div className="hidden sm:block text-xs text-[var(--color-text-muted)] mb-1 truncate">
              {breadcrumb}
            </div>
          )}
          {titleSkeleton ?? (
            <h1
              className={[
                "font-bold text-[var(--color-text)] tracking-tight truncate",
                centerSlot ? "text-xl" : "text-2xl",
              ].join(" ")}
            >
              {title}
            </h1>
          )}
          {subtitle && (
            <p className="text-sm text-[var(--color-text-muted)] mt-0.5">{subtitle}</p>
          )}
        </div>
      </div>

      {/* Center — search or other inline content */}
      {centerSlot && (
        <div className="flex-1 flex justify-center min-w-0 px-2">{centerSlot}</div>
      )}

      {/* Right — actions */}
      {rightSlot && (
        <div className={["flex items-center gap-2 shrink-0", !centerSlot ? "ml-auto" : ""].join(" ")}>
          {rightSlot}
        </div>
      )}

    </div>
  );
}
