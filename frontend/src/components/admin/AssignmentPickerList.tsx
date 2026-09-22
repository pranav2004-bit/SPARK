"use client";

import { useEffect, useState, useCallback } from "react";
import { useRouter } from "next/navigation";
import { ChevronRight, Clock, AlertTriangle, type LucideIcon } from "lucide-react";
import { AdminLayout } from "@/components/layout/AdminLayout";
import { PageWrapper } from "@/components/layout/PageWrapper";
import { PageHeader } from "@/components/layout/PageHeader";
import { EmptyState } from "@/components/ui/EmptyState";
import { Skeleton } from "@/components/ui/Skeleton";
import { useToast } from "@/components/ui/Toast";
import api, { getErrorMessage } from "@/lib/api";
import type { Batch, BatchAssignment, ApiSuccess, PaginatedResponse } from "@/types";

// Same card-colour palette as admin/assessments/papers/page.tsx — kept in
// sync deliberately so every centralised list under Assessments (papers,
// results, analytics, dashboard) reads as one family.
const PALETTE = [
  { bg: "#EFF6FF", color: "#2563EB" },
  { bg: "#F0FDF4", color: "#16A34A" },
  { bg: "#FDF4FF", color: "#9333EA" },
  { bg: "#FFF4E6", color: "#E8820C" },
  { bg: "#FFF1F2", color: "#E11D48" },
  { bg: "#F0FDFA", color: "#0D9488" },
];
const palette = (i: number) => PALETTE[i % PALETTE.length];

// Same status-badge convention as the old admin/assessments/assignments/page.tsx.
const STATUS_STYLES: Record<string, { bg: string; color: string; label: string }> = {
  SCHEDULED: { bg: "#FFF4E6", color: "#E8820C", label: "Scheduled" },
  LIVE:      { bg: "#F0FDF4", color: "#16A34A", label: "Live" },
  CLOSED:    { bg: "#F3F4F6", color: "#6B7280", label: "Closed" },
};

interface AssignmentPickerListProps {
  title: string;
  subtitle: string;
  /** Card click navigates to `${basePath}/${assignment.id}` */
  basePath: string;
  icon: LucideIcon;
  emptyTitle: string;
  emptySubtitle: string;
}

/**
 * Shared centralised list — one assignment per card, click-through to a
 * per-assignment detail page. Backs the Results, Analytics, and Dashboard
 * sections (each a thin page.tsx passing its own basePath/icon/copy), the
 * same way admin/assessments/papers/page.tsx centralises question papers.
 */
export function AssignmentPickerList({ title, subtitle, basePath, icon: Icon, emptyTitle, emptySubtitle }: AssignmentPickerListProps) {
  const router = useRouter();
  const toast = useToast();

  const [assignments, setAssignments] = useState<BatchAssignment[]>([]);
  const [batches, setBatches] = useState<Batch[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState(false);

  // On failure this must not just toast and fall through to the
  // caller-provided "empty" copy below (e.g. "No assignments yet") — that
  // reads as "there's genuinely nothing here," not "this failed to load."
  // Shared by every AssignmentPickerList caller (Results, Analytics,
  // Dashboard), so fixing it here fixes all three at once.
  const load = useCallback(() => {
    setLoading(true);
    setLoadError(false);
    Promise.all([
      api.get<PaginatedResponse<BatchAssignment>>("/assessments/admin/assignments/"),
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
        <PageHeader title={title} subtitle={subtitle} backHref="/admin/assessments" />

        {loading ? (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {[1, 2, 3].map(i => <Skeleton key={i} className="h-[124px] rounded-[var(--radius-xl)]" />)}
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
            {assignments.map((a, i) => {
              const { bg, color } = palette(i);
              const status = STATUS_STYLES[a.status] ?? STATUS_STYLES.SCHEDULED;
              return (
                <button
                  key={a.id}
                  onClick={() => router.push(`${basePath}/${a.id}`)}
                  className="text-left rounded-[var(--radius-xl)] overflow-hidden transition-shadow duration-150 hover:shadow-[var(--shadow-md)] cursor-pointer group px-5 pt-5 pb-5"
                  style={{ background: "var(--color-surface)", border: "1px solid var(--color-border)", boxShadow: "var(--shadow-sm)" }}
                >
                  <div className="flex items-start justify-between gap-3">
                    <div className="w-11 h-11 rounded-[var(--radius-lg)] flex items-center justify-center shrink-0" style={{ background: bg }}>
                      <Icon size={20} style={{ color }} />
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
                  <div className="flex items-center gap-2 mt-3 flex-wrap">
                    <span
                      className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold"
                      style={{ background: status.bg, color: status.color }}
                    >
                      <span className="w-1.5 h-1.5 rounded-full" style={{ background: status.color }} />
                      {status.label}
                    </span>
                    <span className="text-xs flex items-center gap-1" style={{ color: "var(--color-text-subtle)" }}>
                      <Clock size={11} /> {a.exam_duration_minutes} min
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
