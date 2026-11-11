"use client";

import { useEffect, useState, useCallback } from "react";
import { useRouter } from "next/navigation";
import { ChevronRight, AlertTriangle, type LucideIcon } from "lucide-react";
import { AdminLayout } from "@/components/layout/AdminLayout";
import { PageWrapper } from "@/components/layout/PageWrapper";
import { PageHeader } from "@/components/layout/PageHeader";
import { EmptyState } from "@/components/ui/EmptyState";
import { Skeleton } from "@/components/ui/Skeleton";
import { useToast } from "@/components/ui/Toast";
import api, { getErrorMessage } from "@/lib/api";
import type { EssayAssignment, Batch, ApiSuccess, PaginatedResponse } from "@/types";

const STATUS_STYLES: Record<string, { bg: string; color: string; label: string }> = {
  SCHEDULED: { bg: "#FFF4E6", color: "#E8820C", label: "Scheduled" },
  LIVE:      { bg: "#F0FDF4", color: "#16A34A", label: "Live" },
  CLOSED:    { bg: "#F3F4F6", color: "#6B7280", label: "Closed" },
};

interface EssayAssignmentPickerListProps {
  title: string;
  subtitle: string;
  /** Card click navigates to `${basePath}/${assignment.id}` */
  basePath: string;
  icon: LucideIcon;
  iconBg: string;
  iconColor: string;
  emptyTitle: string;
  emptySubtitle: string;
}

/**
 * Essay-service's own assignment picker — extracted here in Phase 9 once
 * Analytics became a second real consumer of the exact shape Phase 8's
 * Results module already built (see that module's own page.tsx, which
 * originally kept this inline specifically because it had only one
 * caller then — "if a second essay-service module needs the identical
 * shape later, that's the point to generalize from two real call sites,
 * not guess ahead of one"). Deliberately still NOT
 * assessment-service's own <AssignmentPickerList> — that component is
 * hardcoded to assessment-service's own /assessments/admin/ endpoint and
 * BatchAssignment shape (e.g. exam_duration_minutes, which
 * EssayAssignment doesn't have), so it still can't serve this service.
 */
export function EssayAssignmentPickerList({
  title, subtitle, basePath, icon: Icon, iconBg, iconColor, emptyTitle, emptySubtitle,
}: EssayAssignmentPickerListProps) {
  const router = useRouter();
  const toast = useToast();

  const [assignments, setAssignments] = useState<EssayAssignment[]>([]);
  const [batches, setBatches] = useState<Batch[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState(false);

  const load = useCallback(() => {
    setLoading(true);
    setLoadError(false);
    Promise.all([
      api.get<PaginatedResponse<EssayAssignment>>("/essay/admin/assignments/"),
      api.get<ApiSuccess<Batch[]>>("/users/batches/"),
    ])
      .then(([assignRes, batchesRes]) => {
        setAssignments(assignRes.data.results);
        setBatches(batchesRes.data.data);
      })
      .catch(err => { toast.error(getErrorMessage(err)); setLoadError(true); })
      .finally(() => setLoading(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(load, [load]);

  const batchName = (id: string) => batches.find(b => b.id === id)?.batch_name ?? id;
  const isEmpty = !loading && assignments.length === 0;

  return (
    <AdminLayout>
      <PageWrapper>
        <PageHeader title={title} subtitle={subtitle} backHref="/admin/essay-writing" />

        {loading ? (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {[1, 2, 3].map(i => <Skeleton key={i} className="h-[110px] rounded-[var(--radius-xl)]" />)}
          </div>
        ) : loadError ? (
          <EmptyState
            icon={AlertTriangle}
            title={`Couldn't load ${title.toLowerCase()}`}
            subtitle="Something went wrong fetching this data — it may be temporary. Try again in a moment."
            action={{ label: "Retry", onClick: load }}
          />
        ) : isEmpty ? (
          <EmptyState icon={Icon} title={emptyTitle} subtitle={emptySubtitle} />
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {assignments.map(a => {
              const status = STATUS_STYLES[a.status] ?? STATUS_STYLES.SCHEDULED;
              return (
                <button
                  key={a.id}
                  onClick={() => router.push(`${basePath}/${a.id}`)}
                  className="text-left rounded-[var(--radius-xl)] overflow-hidden transition-shadow duration-150 hover:shadow-[var(--shadow-md)] cursor-pointer group px-5 pt-5 pb-5"
                  style={{ background: "var(--color-surface)", border: "1px solid var(--color-border)", boxShadow: "var(--shadow-sm)" }}
                >
                  <div className="flex items-start justify-between gap-3">
                    <div className="w-11 h-11 rounded-[var(--radius-lg)] flex items-center justify-center shrink-0" style={{ background: iconBg }}>
                      <Icon size={20} style={{ color: iconColor }} />
                    </div>
                    <ChevronRight
                      size={16}
                      style={{ color: "var(--color-text-subtle)", marginTop: 2, flexShrink: 0 }}
                      className="transition-transform duration-150 group-hover:translate-x-0.5"
                    />
                  </div>
                  <div className="mt-3">
                    <p className="text-[15px] font-semibold leading-snug truncate" style={{ color: "var(--color-text)" }}>{a.paper_title}</p>
                    <p className="text-xs mt-1" style={{ color: "var(--color-text-subtle)" }}>{batchName(a.batch_id)}</p>
                  </div>
                  <div className="mt-3">
                    <span
                      className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold"
                      style={{ background: status.bg, color: status.color }}
                    >
                      <span className="w-1.5 h-1.5 rounded-full" style={{ background: status.color }} />
                      {status.label}
                    </span>
                  </div>
                </button>
              );
            })}
          </div>
        )}
      </PageWrapper>
    </AdminLayout>
  );
}
