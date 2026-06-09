"use client";

import type { LucideIcon } from "lucide-react";
import { Button } from "./Button";

interface EmptyStateProps {
  icon: LucideIcon;
  title: string;
  subtitle?: string;
  action?: {
    label: string;
    onClick: () => void;
    icon?: LucideIcon;
  };
}

export function EmptyState({ icon: Icon, title, subtitle, action }: EmptyStateProps) {
  const ActionIcon = action?.icon;
  return (
    <div className="flex flex-col items-center justify-center py-20 px-6 text-center gap-0">
      {/* Icon container — accent-tinted, brand-anchored */}
      <div
        className="w-14 h-14 rounded-2xl flex items-center justify-center mb-5"
        style={{
          background: "var(--color-accent-light)",
        }}
      >
        <Icon size={24} style={{ color: "var(--color-accent)" }} />
      </div>

      <h3 className="text-base font-semibold mb-1.5" style={{ color: "var(--color-text)" }}>
        {title}
      </h3>

      {subtitle && (
        <p className="text-sm max-w-xs mb-6" style={{ color: "var(--color-text-muted)" }}>
          {subtitle}
        </p>
      )}

      {action && !subtitle && <div className="mb-6" />}

      {action && (
        <Button
          variant="primary"
          onClick={action.onClick}
          leftIcon={ActionIcon ? <ActionIcon size={14} /> : undefined}
        >
          {action.label}
        </Button>
      )}
    </div>
  );
}
