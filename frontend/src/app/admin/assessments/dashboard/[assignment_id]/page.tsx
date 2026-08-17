"use client";

import { useEffect, useState, useCallback, useRef } from "react";
import { useParams } from "next/navigation";
import { Download, Printer, Users, CheckCircle2, ShieldAlert, Percent, Radio, AlertTriangle } from "lucide-react";
import { AdminLayout } from "@/components/layout/AdminLayout";
import { PageWrapper } from "@/components/layout/PageWrapper";
import { PageHeader } from "@/components/layout/PageHeader";
import { Button } from "@/components/ui/Button";
import { Skeleton } from "@/components/ui/Skeleton";
import { EmptyState } from "@/components/ui/EmptyState";
import { useToast } from "@/components/ui/Toast";
import api, { getErrorMessage } from "@/lib/api";
import type { ApiSuccess } from "@/types";

interface DashboardData {
  assignment_id: string;
  status: string;
  student_count_total: number;
  student_count_completed: number;
  student_count_in_progress: number;
  completion_rate_percentage: number;
  average_score_percentage: number;
  malpractice_incidents: number;
  submission_breakdown: {
    on_time: number;
    auto_submitted: number;
    on_time_percentage: number;
  };
  metric_definitions: Record<string, string>;
}

// A live exam is watched, not just glanced at once — poll while the
// assignment is actually LIVE, same 8s cadence the assign-page's status
// poll uses, and stop once it's CLOSED (nothing left to change).
const LIVE_POLL_INTERVAL_MS = 8000;

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

function SplitBar({ leftLabel, leftValue, rightLabel, rightValue, leftColor, rightColor }: {
  leftLabel: string; leftValue: number; rightLabel: string; rightValue: number; leftColor: string; rightColor: string;
}) {
  const total = leftValue + rightValue;
  const leftPct = total > 0 ? (leftValue / total) * 100 : 50;
  return (
    <div>
      <div className="h-6 rounded-md overflow-hidden flex" style={{ background: "var(--color-surface-secondary)" }}>
        {total > 0 ? (
          <>
            <div style={{ width: `${leftPct}%`, background: leftColor }} />
            <div style={{ width: `${100 - leftPct}%`, background: rightColor }} />
          </>
        ) : (
          <div className="w-full flex items-center justify-center text-xs" style={{ color: "var(--color-text-subtle)" }}>No submissions yet</div>
        )}
      </div>
      <div className="flex justify-between mt-2 text-xs">
        <span className="flex items-center gap-1.5" style={{ color: "var(--color-text-muted)" }}>
          <span className="w-2.5 h-2.5 rounded-full inline-block" style={{ background: leftColor }} /> {leftLabel}: {leftValue}
        </span>
        <span className="flex items-center gap-1.5" style={{ color: "var(--color-text-muted)" }}>
          <span className="w-2.5 h-2.5 rounded-full inline-block" style={{ background: rightColor }} /> {rightLabel}: {rightValue}
        </span>
      </div>
    </div>
  );
}

export default function AdminAssessmentDashboardPage() {
  const { assignment_id } = useParams<{ assignment_id: string }>();
  const toast = useToast();

  const [data, setData] = useState<DashboardData | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState(false);
  const [exporting, setExporting] = useState(false);
  const statusRef = useRef<string | undefined>(undefined);

  // On failure this must set a visible error state, not just toast — the
  // "!data" branch below used to render a bare page header with nothing
  // else on any failure, which looks broken/suspicious rather than
  // communicating "this couldn't load, try again."
  const load = useCallback((silent = false) => {
    if (!silent) { setLoading(true); setLoadError(false); }
    api.get<ApiSuccess<DashboardData>>(`/assessments/admin/assignments/${assignment_id}/dashboard/`)
      .then(res => {
        setData(res.data.data);
        statusRef.current = res.data.data.status;
        setLoadError(false);
      })
      .catch(err => { if (!silent) { toast.error(getErrorMessage(err)); setLoadError(true); } })
      .finally(() => { if (!silent) setLoading(false); });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [assignment_id]);

  useEffect(() => load(), [load]);

  // Live polling — only while the assignment is LIVE. Re-evaluated after
  // every load() so it stops the moment the exam closes.
  useEffect(() => {
    if (data?.status !== "LIVE") return;
    const interval = setInterval(() => load(true), LIVE_POLL_INTERVAL_MS);
    return () => clearInterval(interval);
  }, [data?.status, load]);

  async function handleExportCsv() {
    setExporting(true);
    try {
      const res = await api.get(`/assessments/admin/assignments/${assignment_id}/dashboard/export/`, { responseType: "blob" });
      const blob = new Blob([res.data], { type: "text/csv;charset=utf-8;" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `dashboard_${assignment_id}.csv`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    } catch (err) {
      toast.error(getErrorMessage(err));
    } finally {
      setExporting(false);
    }
  }

  // Image/PDF export: rendered client-side via the browser's native
  // print-to-PDF, not a new server-side (WeasyPrint) or client-side
  // (jsPDF/html2canvas) dependency — see AdminAssignmentDashboardExportView's
  // docstring in the backend for the full documented rationale (Task 9.1).
  function handlePrint() {
    window.print();
  }

  if (loading) {
    return (
      <AdminLayout>
        <PageWrapper className="max-w-5xl">
          <Skeleton className="h-8 w-64 mb-6" />
          <div className="grid grid-cols-2 sm:grid-cols-3 gap-4 mb-6">
            {[1, 2, 3, 4, 5, 6].map(i => <Skeleton key={i} className="h-24 rounded-[var(--radius-xl)]" />)}
          </div>
          <Skeleton className="h-40 rounded-[var(--radius-xl)]" />
        </PageWrapper>
      </AdminLayout>
    );
  }

  if (!data) {
    return (
      <AdminLayout>
        <PageWrapper className="max-w-5xl">
          <PageHeader title="Dashboard" backHref="/admin/assessments/dashboard" />
          {loadError && (
            <EmptyState
              icon={AlertTriangle}
              title="Couldn't load this dashboard"
              subtitle="Something went wrong fetching this data — it may be temporary. Try again in a moment."
              action={{ label: "Retry", onClick: () => load() }}
            />
          )}
        </PageWrapper>
      </AdminLayout>
    );
  }

  const { submission_breakdown: sb } = data;
  const isLive = data.status === "LIVE";

  return (
    <AdminLayout>
      {/* Print-only styling: hides everything except #dashboard-printable
          (the sidebar/nav from AdminLayout, action buttons, etc.), matching
          Task 9.1's documented "client-side window.print() for image/PDF
          export" decision. */}
      <style>{`
        @media print {
          body * { visibility: hidden; }
          #dashboard-printable, #dashboard-printable * { visibility: visible; }
          #dashboard-printable { position: absolute; left: 0; top: 0; width: 100%; }
          .no-print { display: none !important; }
        }
      `}</style>

      <PageWrapper className="max-w-5xl">
        <div id="dashboard-printable">
          <PageHeader
            title="Dashboard"
            subtitle="At-a-glance KPI rollup for this assignment."
            backHref="/admin/assessments/dashboard"
            rightSlot={
              <div className="flex items-center gap-2 no-print">
                <Button variant="secondary" leftIcon={<Printer size={14} />} onClick={handlePrint}>
                  Print / Save PDF
                </Button>
                <Button variant="secondary" leftIcon={<Download size={14} />} loading={exporting} onClick={handleExportCsv}>
                  Export CSV
                </Button>
              </div>
            }
          />

          {isLive && (
            <div className="flex items-center gap-2 mb-5 px-3 py-2 rounded-[var(--radius-lg)] w-fit" style={{ background: "#F0FDF4", border: "1px solid #BBF7D0" }}>
              <Radio size={13} className="animate-pulse" style={{ color: "#16A34A" }} />
              <span className="text-xs font-semibold" style={{ color: "#16A34A" }}>Live — refreshing every {LIVE_POLL_INTERVAL_MS / 1000}s</span>
            </div>
          )}

          {/* KPI tiles — mobile-first: 2 cols at the smallest breakpoint, 3 from sm up */}
          <div className="grid grid-cols-2 sm:grid-cols-3 gap-4 mb-6">
            <StatTile icon={Users} label="Total Students" value={String(data.student_count_total)} color="#2563EB" />
            <StatTile icon={CheckCircle2} label="Completed" value={String(data.student_count_completed)}
              hint={`${data.student_count_in_progress} in progress`} color="#16A34A" />
            <StatTile icon={Percent} label="Completion Rate" value={`${data.completion_rate_percentage}%`} color="#9333EA" />
            <StatTile icon={CheckCircle2} label="Average Score" value={`${data.average_score_percentage}%`} color="#E8820C" />
            <StatTile icon={ShieldAlert} label="Malpractice" value={String(data.malpractice_incidents)}
              hint="flagged sessions" color="#DC2626" />
            <StatTile icon={Percent} label="On-Time Rate" value={`${sb.on_time_percentage}%`}
              hint="of completed sessions" color="#0891B2" />
          </div>

          {/* Submission breakdown */}
          <div className="rounded-[var(--radius-xl)] p-5" style={{ background: "var(--color-surface)", border: "1px solid var(--color-border)" }}>
            <h3 className="text-sm font-semibold mb-1" style={{ color: "var(--color-text)" }}>Submission Breakdown</h3>
            <p className="text-xs mb-4" style={{ color: "var(--color-text-subtle)" }}>{data.metric_definitions.submission_breakdown}</p>
            <SplitBar
              leftLabel="On Time" leftValue={sb.on_time} leftColor="var(--color-accent)"
              rightLabel="Auto-Submitted" rightValue={sb.auto_submitted} rightColor="#E8820C"
            />
          </div>
        </div>
      </PageWrapper>
    </AdminLayout>
  );
}
