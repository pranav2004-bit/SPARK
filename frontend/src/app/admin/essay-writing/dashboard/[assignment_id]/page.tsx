"use client";

import { useEffect, useState, useCallback, useRef } from "react";
import { useParams } from "next/navigation";
import { Users, Loader2, CheckCircle2, Target, AlertTriangle, Radio, Clock, TrendingUp } from "lucide-react";
import { AdminLayout } from "@/components/layout/AdminLayout";
import { PageWrapper } from "@/components/layout/PageWrapper";
import { PageHeader } from "@/components/layout/PageHeader";
import { Skeleton } from "@/components/ui/Skeleton";
import { EmptyState } from "@/components/ui/EmptyState";
import { useToast } from "@/components/ui/Toast";
import api, { getErrorMessage } from "@/lib/api";
import type { ApiSuccess, EssayAssignment, EssayAssignmentDashboard } from "@/types";

// Same 8s live-polling cadence as assessment-service's own Dashboard page
// (frontend/src/app/admin/assessments/dashboard/[assignment_id]/page.tsx)
// — a live exam is watched, not just glanced at once. Polling stops the
// instant assignment_status flips off "LIVE" (re-evaluated after every load).
const LIVE_POLL_INTERVAL_MS = 8000;

function formatTimeRemaining(seconds: number | null | undefined): string {
  if (seconds == null || !Number.isFinite(seconds)) return "—";
  if (seconds <= 0) return "Ending now";
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  return h > 0 ? `${h}h ${m}m left` : `${m}m left`;
}

function StatTile({ icon: Icon, label, value, hint, color }: {
  icon: React.ElementType; label: string; value: string; hint?: string; color: string;
}) {
  return (
    <div className="rounded-[var(--radius-xl)] p-4" style={{ background: "var(--color-surface)", border: "1px solid var(--color-border)" }}>
      <div className="flex items-center gap-2 mb-2">
        <div className="w-8 h-8 rounded-[var(--radius-md)] flex items-center justify-center shrink-0" style={{ background: `${color}1A` }}>
          <Icon size={15} style={{ color }} />
        </div>
        <p className="text-xs font-semibold uppercase tracking-wider truncate" style={{ color: "var(--color-text-subtle)" }}>{label}</p>
      </div>
      <p className="text-2xl font-bold" style={{ color: "var(--color-text)" }}>{value}</p>
      {hint && <p className="text-xs mt-0.5" style={{ color: "var(--color-text-subtle)" }}>{hint}</p>}
    </div>
  );
}

// A minimal vertical-bar sparkline — this platform's own no-Recharts, hand-
// rolled-CSS chart convention (see frontend/AGENTS.md), scaled down for a
// compact "is anyone still submitting" time-series signal.
function ThroughputSparkline({ buckets }: { buckets: EssayAssignmentDashboard["submission_throughput"] }) {
  const max = Math.max(...buckets.map(b => b.count), 1);
  return (
    <div className="flex items-end gap-1.5 h-16">
      {buckets.map((b, i) => (
        <div key={i} className="flex-1 flex flex-col items-center gap-1">
          <div
            className="w-full rounded-t-sm transition-all duration-300"
            style={{
              height: `${Math.max((b.count / max) * 100, b.count > 0 ? 8 : 2)}%`,
              background: b.count > 0 ? "var(--color-accent)" : "var(--color-surface-secondary)",
              minHeight: "2px",
            }}
          />
          <span className="text-[10px]" style={{ color: "var(--color-text-subtle)" }}>{b.count}</span>
        </div>
      ))}
    </div>
  );
}

export default function AdminEssayDashboardPage() {
  const { assignment_id } = useParams<{ assignment_id: string }>();
  const toast = useToast();

  const [assignment, setAssignment] = useState<EssayAssignment | null>(null);
  const [data, setData] = useState<EssayAssignmentDashboard | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState(false);
  const statusRef = useRef<string | undefined>(undefined);

  useEffect(() => {
    api.get<ApiSuccess<EssayAssignment>>(`/essay/admin/assignments/${assignment_id}/`)
      .then(res => setAssignment(res.data.data))
      .catch(() => { /* header title falls back to a generic label — the KPI panel below has its own load error handling */ });
  }, [assignment_id]);

  // silent: true for background polls — must not flash the full-page
  // skeleton on every 8s refresh, only on the very first load.
  const load = useCallback((silent = false) => {
    if (!silent) { setLoading(true); setLoadError(false); }
    api.get<ApiSuccess<EssayAssignmentDashboard>>(`/essay/admin/assignments/${assignment_id}/dashboard/`)
      .then(res => {
        setData(res.data.data);
        statusRef.current = res.data.data.assignment_status;
        setLoadError(false);
      })
      .catch(err => { if (!silent) { toast.error(getErrorMessage(err)); setLoadError(true); } })
      .finally(() => { if (!silent) setLoading(false); });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [assignment_id]);

  useEffect(() => load(), [load]);

  useEffect(() => {
    if (data?.assignment_status !== "LIVE") return;
    const interval = setInterval(() => load(true), LIVE_POLL_INTERVAL_MS);
    return () => clearInterval(interval);
  }, [data?.assignment_status, load]);

  const isLive = data?.assignment_status === "LIVE";

  return (
    <AdminLayout>
      <PageWrapper>
        <PageHeader
          title={assignment?.paper_title ?? "Dashboard"}
          subtitle="Live evaluation status for this assignment."
          backHref="/admin/essay-writing/dashboard"
        />

        {loading ? (
          <div className="space-y-4">
            <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
              {Array.from({ length: 5 }).map((_, i) => <Skeleton key={i} className="h-24 w-full" />)}
            </div>
            <Skeleton className="h-32 w-full" />
          </div>
        ) : loadError || !data ? (
          <EmptyState icon={AlertTriangle} title="Couldn't load dashboard" subtitle="Please try again." />
        ) : (
          <>
            {isLive && (
              <div className="flex items-center gap-2 mb-5 px-3 py-2 rounded-[var(--radius-lg)] w-fit" style={{ background: "#F0FDF4", border: "1px solid #BBF7D0" }}>
                <Radio size={13} className="animate-pulse" style={{ color: "#16A34A" }} />
                <span className="text-xs font-semibold" style={{ color: "#16A34A" }}>Live — refreshing every {LIVE_POLL_INTERVAL_MS / 1000}s</span>
                {data.time_remaining_seconds !== null && (
                  <span className="text-xs flex items-center gap-1" style={{ color: "#16A34A" }}>
                    <Clock size={11} /> {formatTimeRemaining(data.time_remaining_seconds)}
                  </span>
                )}
              </div>
            )}

            <div className="grid grid-cols-2 md:grid-cols-5 gap-3 mb-5">
              <StatTile
                icon={Users} label="Completion" color="#2563EB"
                value={`${data.completion_rate_percentage}%`}
                hint={`${data.total_submitted}/${data.total_allocated} submitted`}
              />
              <StatTile icon={Loader2} label="In progress" color="#E8820C" value={String(data.in_progress_count)} />
              <StatTile icon={CheckCircle2} label="Pending evaluation" color="#2563EB" value={String(data.pending_evaluation_count)} />
              <StatTile
                icon={AlertTriangle} label="DLQ backlog" color={data.dlq_backlog_count > 0 ? "#DC2626" : "#16A34A"}
                value={String(data.dlq_backlog_count)}
              />
              <StatTile
                icon={Target} label="Average score" color="#9333EA"
                value={data.average_score !== null ? `${data.average_score}/10` : "—"}
                hint={`${data.total_scored} scored`}
              />
            </div>

            <div className="rounded-[var(--radius-xl)] p-5" style={{ background: "var(--color-surface)", border: "1px solid var(--color-border)" }}>
              <p className="text-sm font-semibold mb-4 flex items-center gap-1.5" style={{ color: "var(--color-text)" }}>
                <TrendingUp size={14} /> Submission throughput (last 30 minutes)
              </p>
              <ThroughputSparkline buckets={data.submission_throughput} />
            </div>
          </>
        )}
      </PageWrapper>
    </AdminLayout>
  );
}
