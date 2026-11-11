"use client";

import { useEffect, useState, useCallback } from "react";
import { Send, AlertTriangle, CheckCircle2, Inbox, Clock, XCircle } from "lucide-react";
import { AdminLayout } from "@/components/layout/AdminLayout";
import { PageWrapper } from "@/components/layout/PageWrapper";
import { PageHeader } from "@/components/layout/PageHeader";
import { Button } from "@/components/ui/Button";
import { Select } from "@/components/ui/Select";
import { Skeleton } from "@/components/ui/Skeleton";
import { EmptyState } from "@/components/ui/EmptyState";
import { useToast } from "@/components/ui/Toast";
import api, { getErrorMessage } from "@/lib/api";
import type { ApiSuccess, EssayPipelineHealthSummary, EssayPipelineAlert } from "@/types";

const WINDOW_OPTIONS = [
  { value: "24", label: "Last 24 hours" },
  { value: "48", label: "Last 48 hours" },
  { value: "168", label: "Last 7 days" },
];

const TIER_STYLES: Record<string, { bg: string; border: string; color: string; label: string }> = {
  P1: { bg: "#FEF2F2", border: "#FECACA", color: "#DC2626", label: "P1 Critical" },
  P2: { bg: "#FFF4E6", border: "#FED7AA", color: "#D97706", label: "P2 Warning" },
};

function AlertCard({ alert }: { alert: EssayPipelineAlert }) {
  const s = TIER_STYLES[alert.tier] ?? TIER_STYLES.P2;
  return (
    <div className="rounded-[var(--radius-lg)] p-4 flex items-start gap-3" style={{ background: s.bg, border: `1px solid ${s.border}` }}>
      <AlertTriangle size={16} style={{ color: s.color, marginTop: 2, flexShrink: 0 }} />
      <div>
        <p className="text-xs font-semibold uppercase tracking-wide" style={{ color: s.color }}>{s.label}</p>
        <p className="text-sm mt-0.5" style={{ color: "var(--color-text)" }}>{alert.message}</p>
      </div>
    </div>
  );
}

function StatTile({ icon: Icon, label, value, color }: {
  icon: React.ElementType; label: string; value: string; color: string;
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
    </div>
  );
}

function formatAge(seconds: number | null): string {
  if (seconds === null) return "—";
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return `${minutes}m`;
  return `${Math.round(minutes / 60)}h`;
}

export default function AdminNotificationsPage() {
  const toast = useToast();

  const [windowHours, setWindowHours] = useState("24");
  const [summary, setSummary] = useState<EssayPipelineHealthSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState(false);
  const [sending, setSending] = useState(false);

  const load = useCallback(() => {
    setLoading(true);
    setLoadError(false);
    api.get<ApiSuccess<EssayPipelineHealthSummary>>(
      `/essay/admin/notifications/summary/?window_hours=${windowHours}`,
    )
      .then(res => setSummary(res.data.data))
      .catch(err => { toast.error(getErrorMessage(err)); setLoadError(true); })
      .finally(() => setLoading(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [windowHours]);

  useEffect(load, [load]);

  async function sendNow() {
    setSending(true);
    try {
      const res = await api.post<ApiSuccess<null>>("/essay/admin/notifications/send-summary/");
      toast.success(res.data.message ?? "Daily summary dispatched.");
    } catch (err) {
      toast.error(getErrorMessage(err));
    } finally {
      setSending(false);
    }
  }

  return (
    <AdminLayout>
      <PageWrapper>
        <PageHeader
          title="Notifications"
          subtitle="Pipeline-health alerts and the underlying operational numbers."
          backHref="/admin/essay-writing"
          rightSlot={
            <div className="flex items-center gap-2">
              <div className="w-40">
                <Select value={windowHours} onChange={e => setWindowHours(e.target.value)} options={WINDOW_OPTIONS} />
              </div>
              <Button variant="secondary" leftIcon={<Send size={14} />} loading={sending} onClick={sendNow}>
                Send daily summary now
              </Button>
            </div>
          }
        />

        {loading ? (
          <div className="space-y-4">
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              {Array.from({ length: 4 }).map((_, i) => <Skeleton key={i} className="h-24 w-full" />)}
            </div>
            <Skeleton className="h-24 w-full" />
          </div>
        ) : loadError || !summary ? (
          <EmptyState icon={AlertTriangle} title="Couldn't load the pipeline summary" subtitle="Please try again." />
        ) : (
          <>
            <div className="mb-5">
              {summary.alerts.length === 0 ? (
                <div className="rounded-[var(--radius-lg)] p-4 flex items-center gap-2" style={{ background: "#F0FDF4", border: "1px solid #BBF7D0" }}>
                  <CheckCircle2 size={16} style={{ color: "#16A34A" }} />
                  <p className="text-sm font-semibold" style={{ color: "#16A34A" }}>No active alerts — pipeline looks healthy.</p>
                </div>
              ) : (
                <div className="space-y-2">
                  {summary.alerts.map((a, i) => <AlertCard key={i} alert={a} />)}
                </div>
              )}
            </div>

            <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-5">
              <StatTile icon={Inbox} label="Submissions" value={String(summary.total_submissions)} color="#2563EB" />
              <StatTile icon={CheckCircle2} label="Completed" value={String(summary.completed_submissions)} color="#16A34A" />
              <StatTile icon={XCircle} label="Failed" value={String(summary.failed_submissions)} color="#DC2626" />
              <StatTile
                icon={AlertTriangle} label="Unresolved DLQ" color={summary.unresolved_dlq_count > 0 ? "#D97706" : "#16A34A"}
                value={String(summary.unresolved_dlq_count)}
              />
              <StatTile
                icon={AlertTriangle} label="Undispatched" color={summary.undispatched_submission_count > 0 ? "#D97706" : "#16A34A"}
                value={String(summary.undispatched_submission_count)}
              />
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-3 mb-5">
              <div className="rounded-[var(--radius-xl)] p-5" style={{ background: "var(--color-surface)", border: "1px solid var(--color-border)" }}>
                <p className="text-sm font-semibold mb-3 flex items-center gap-1.5" style={{ color: "var(--color-text)" }}>
                  <Clock size={14} /> Oldest unresolved DLQ entry
                </p>
                <p className="text-2xl font-bold" style={{ color: "var(--color-text)" }}>
                  {formatAge(summary.oldest_unresolved_dlq_age_seconds)}
                </p>
                <p className="text-xs mt-3" style={{ color: "var(--color-text-subtle)" }}>
                  {summary.recent_failure_event_count} failure-shaped event(s) in the last {summary.window_hours}h
                </p>
              </div>
              <div className="rounded-[var(--radius-xl)] p-5" style={{ background: "var(--color-surface)", border: "1px solid var(--color-border)" }}>
                <p className="text-sm font-semibold mb-3 flex items-center gap-1.5" style={{ color: "var(--color-text)" }}>
                  <Clock size={14} /> Oldest undispatched submission
                </p>
                <p className="text-2xl font-bold" style={{ color: "var(--color-text)" }}>
                  {formatAge(summary.oldest_undispatched_submission_age_seconds)}
                </p>
                <p className="text-xs mt-3" style={{ color: "var(--color-text-subtle)" }}>
                  A submission whose dispatch never reached a worker at all — self-heals automatically once the broker recovers.
                </p>
              </div>
            </div>
          </>
        )}
      </PageWrapper>
    </AdminLayout>
  );
}
