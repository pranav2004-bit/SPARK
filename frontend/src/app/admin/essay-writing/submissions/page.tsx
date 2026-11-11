"use client";

import { useEffect, useState, useCallback } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import {
  Inbox, Clock, Loader2, CheckCircle2, XCircle, ShieldAlert, Activity,
  Server, AlertTriangle,
} from "lucide-react";
import { AdminLayout } from "@/components/layout/AdminLayout";
import { PageWrapper } from "@/components/layout/PageWrapper";
import { PageHeader } from "@/components/layout/PageHeader";
import { Input } from "@/components/ui/Input";
import { SearchInput } from "@/components/ui/SearchInput";
import { Pagination } from "@/components/ui/Pagination";
import { Skeleton, TableRowSkeleton } from "@/components/ui/Skeleton";
import { EmptyState } from "@/components/ui/EmptyState";
import { useToast } from "@/components/ui/Toast";
import api, { getErrorMessage } from "@/lib/api";
import type {
  ApiSuccess, PaginatedResponse, EssaySubmissionsOverview, EssaySubmissionListRow,
  EssaySubmissionStatusBucket, EssaySubmissionsPipelineHealth,
} from "@/types";

// Client polling, not Server-Sent Events, for the pipeline-health tile —
// see AdminSubmissionsPipelineHealthView's own docstring (essays/views.py)
// for the full reasoning: this widget has at most a handful of concurrent
// institution-admin viewers, not the platform's 2,000-student target, so
// SSE's long-lived-connection cost buys nothing a 15s poll doesn't already
// deliver. Same "don't copy CLAP's SSE reflexively" instruction Task 6.1
// itself names.
const PIPELINE_HEALTH_POLL_MS = 15000;

const STATUS_BUCKETS: { key: EssaySubmissionStatusBucket; label: string; icon: typeof Clock; bg: string; color: string }[] = [
  { key: "pending",    label: "Pending",    icon: Clock,        bg: "#FFF4E6", color: "#E8820C" },
  { key: "processing", label: "Processing", icon: Loader2,      bg: "#EFF6FF", color: "#2563EB" },
  { key: "completed",  label: "Completed",  icon: CheckCircle2, bg: "#F0FDF4", color: "#16A34A" },
  { key: "failed",     label: "Failed",     icon: XCircle,      bg: "#FEF2F2", color: "#DC2626" },
];

function StatusPill({ status }: { status: EssaySubmissionListRow["status"] }) {
  const styles: Record<string, { bg: string; color: string; label: string }> = {
    PENDING:           { bg: "#FFF4E6", color: "#E8820C", label: "Pending" },
    LLM_PROCESSING:    { bg: "#EFF6FF", color: "#2563EB", label: "Processing" },
    LLM_COMPLETE:      { bg: "#F0FDF4", color: "#16A34A", label: "Complete" },
    REPORT_GENERATING: { bg: "#F0FDF4", color: "#16A34A", label: "Complete" },
    REPORT_READY:      { bg: "#F0FDF4", color: "#16A34A", label: "Complete" },
    LLM_FAILED:        { bg: "#FEF2F2", color: "#DC2626", label: "Failed" },
  };
  const s = styles[status] ?? styles.PENDING;
  return (
    <span className="text-[11px] font-semibold px-2 py-0.5 rounded-full" style={{ background: s.bg, color: s.color }}>
      {s.label}
    </span>
  );
}

function formatDateTime(iso: string): string {
  return new Date(iso).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
}

function formatAge(seconds: number | null): string {
  if (seconds === null) return "—";
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m`;
  const hours = Math.floor(minutes / 60);
  return `${hours}h ${minutes % 60}m`;
}

export default function AdminEssaySubmissionsPage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const toast = useToast();

  const [overview, setOverview] = useState<EssaySubmissionsOverview | null>(null);
  const [health, setHealth] = useState<EssaySubmissionsPipelineHealth | null>(null);

  const [rows, setRows] = useState<EssaySubmissionListRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState(false);
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  const [totalCount, setTotalCount] = useState(0);

  const [status, setStatus] = useState<EssaySubmissionStatusBucket | "">(
    () => (searchParams.get("status") as EssaySubmissionStatusBucket | null) ?? ""
  );
  const [studentSearch, setStudentSearch] = useState("");
  const [department, setDepartment] = useState("");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");

  const loadOverview = useCallback(() => {
    api.get<ApiSuccess<EssaySubmissionsOverview>>("/essay/admin/submissions/overview/")
      .then(res => setOverview(res.data.data))
      .catch(() => { /* the overview tiles are a convenience, not load-bearing — a failed
                        fetch just leaves the tiles in their loading-skeleton state, the main
                        table below still loads and errors independently. */ });
  }, []);

  const loadHealth = useCallback(() => {
    api.get<ApiSuccess<EssaySubmissionsPipelineHealth>>("/essay/admin/submissions/pipeline-health/")
      .then(res => setHealth(res.data.data))
      .catch(() => { /* same reasoning as loadOverview — a transient poll miss just leaves
                        the last-known health tile in place until the next tick. */ });
  }, []);

  const buildParams = useCallback(() => {
    const params = new URLSearchParams({ page: String(page) });
    if (status) params.set("status", status);
    const trimmedSearch = studentSearch.trim();
    if (trimmedSearch) params.set("student_search", trimmedSearch);
    if (department.trim()) params.set("department", department.trim());
    if (dateFrom) params.set("date_from", dateFrom);
    if (dateTo) params.set("date_to", dateTo);
    return params;
  }, [page, status, studentSearch, department, dateFrom, dateTo]);

  const loadList = useCallback(() => {
    setLoading(true);
    setLoadError(false);
    api.get<PaginatedResponse<EssaySubmissionListRow>>(`/essay/admin/submissions/?${buildParams()}`)
      .then(res => {
        setRows(res.data.results);
        setTotalPages(res.data.total_pages);
        setTotalCount(res.data.count);
      })
      .catch(err => { toast.error(getErrorMessage(err)); setLoadError(true); })
      .finally(() => setLoading(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [buildParams]);

  useEffect(loadOverview, [loadOverview]);
  useEffect(loadList, [loadList]);

  useEffect(() => {
    loadHealth();
    const interval = setInterval(loadHealth, PIPELINE_HEALTH_POLL_MS);
    return () => clearInterval(interval);
  }, [loadHealth]);

  useEffect(() => { setPage(1); }, [status, studentSearch, department, dateFrom, dateTo]);

  return (
    <AdminLayout>
      <PageWrapper>
        <PageHeader
          title="Submissions"
          subtitle="Monitor essay submissions moving through the LLM evaluation pipeline."
        />

        {/* Overview tiles — click one to filter the table below */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-5">
          {STATUS_BUCKETS.map(b => {
            const Icon = b.icon;
            const active = status === b.key;
            return (
              <button
                key={b.key}
                onClick={() => setStatus(active ? "" : b.key)}
                className="text-left rounded-[var(--radius-lg)] px-4 py-3 transition-shadow duration-150 cursor-pointer"
                style={{
                  background: "var(--color-surface)",
                  border: active ? `1.5px solid ${b.color}` : "1px solid var(--color-border)",
                  boxShadow: active ? "var(--shadow-sm)" : "none",
                }}
              >
                <div className="flex items-center gap-2">
                  <div className="w-7 h-7 rounded-md flex items-center justify-center shrink-0" style={{ background: b.bg }}>
                    <Icon size={14} style={{ color: b.color }} />
                  </div>
                  <p className="text-xs font-medium" style={{ color: "var(--color-text-subtle)" }}>{b.label}</p>
                </div>
                <div className="text-2xl font-bold mt-2" style={{ color: "var(--color-text)" }}>
                  {overview ? overview[b.key] : <Skeleton className="h-7 w-10" />}
                </div>
              </button>
            );
          })}
        </div>

        {/* Pipeline health tile */}
        <div
          className="flex flex-wrap items-center gap-x-6 gap-y-2 rounded-[var(--radius-lg)] px-4 py-3 mb-5 text-xs"
          style={{ background: "var(--color-surface-subtle)", border: "1px solid var(--color-border)" }}
        >
          <div className="flex items-center gap-1.5 font-semibold" style={{ color: "var(--color-text)" }}>
            <Activity size={13} /> Pipeline health
          </div>
          {health ? (
            <>
              <span className="flex items-center gap-1.5" style={{ color: health.redis_ok ? "#16A34A" : "#DC2626" }}>
                <Server size={12} /> Redis {health.redis_ok ? "reachable" : "unreachable"}
              </span>
              <span style={{ color: "var(--color-text-subtle)" }}>
                {health.celery_workers_online} worker{health.celery_workers_online === 1 ? "" : "s"} online
              </span>
              <span style={{ color: "var(--color-text-subtle)" }}>
                Queue depth: {health.queue_depth ?? "—"}
              </span>
              <span
                className="flex items-center gap-1.5"
                style={{ color: health.unresolved_dlq_count > 0 ? "#D97706" : "var(--color-text-subtle)" }}
              >
                {health.unresolved_dlq_count > 0 && <AlertTriangle size={12} />}
                {health.unresolved_dlq_count} unresolved failure{health.unresolved_dlq_count === 1 ? "" : "s"}
                {health.oldest_unresolved_dlq_age_seconds !== null && ` (oldest ${formatAge(health.oldest_unresolved_dlq_age_seconds)})`}
              </span>
              <span
                className="flex items-center gap-1.5"
                style={{ color: health.undispatched_submission_count > 0 ? "#D97706" : "var(--color-text-subtle)" }}
              >
                {health.undispatched_submission_count > 0 && <AlertTriangle size={12} />}
                {health.undispatched_submission_count} undispatched
                {health.oldest_undispatched_submission_age_seconds !== null && ` (oldest ${formatAge(health.oldest_undispatched_submission_age_seconds)})`}
              </span>
            </>
          ) : (
            <Skeleton className="h-4 w-64" />
          )}
        </div>

        {/* Filters */}
        <div className="grid grid-cols-1 sm:grid-cols-4 gap-3 mb-4">
          <SearchInput
            value={studentSearch}
            onChange={setStudentSearch}
            placeholder="Search by roll number or name..."
          />
          <Input
            placeholder="Department..."
            value={department}
            onChange={e => setDepartment(e.target.value)}
          />
          <Input type="date" value={dateFrom} onChange={e => setDateFrom(e.target.value)} placeholder="From" />
          <Input type="date" value={dateTo} onChange={e => setDateTo(e.target.value)} placeholder="To" />
        </div>

        <div className="rounded-[var(--radius-xl)] overflow-hidden" style={{ background: "var(--color-surface)", border: "1px solid var(--color-border)" }}>
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b" style={{ borderColor: "var(--color-border)" }}>
                <th className="text-left px-4 py-3 font-semibold text-xs" style={{ color: "var(--color-text-subtle)" }}>Paper</th>
                <th className="text-left px-4 py-3 font-semibold text-xs" style={{ color: "var(--color-text-subtle)" }}>Batch</th>
                <th className="text-left px-4 py-3 font-semibold text-xs" style={{ color: "var(--color-text-subtle)" }}>Status</th>
                <th className="text-left px-4 py-3 font-semibold text-xs" style={{ color: "var(--color-text-subtle)" }}>Score</th>
                <th className="text-left px-4 py-3 font-semibold text-xs" style={{ color: "var(--color-text-subtle)" }}>Flagged</th>
                <th className="text-left px-4 py-3 font-semibold text-xs" style={{ color: "var(--color-text-subtle)" }}>Submitted</th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                Array.from({ length: 6 }).map((_, i) => <TableRowSkeleton key={i} cols={6} />)
              ) : rows.length === 0 && !loadError ? (
                <tr>
                  <td colSpan={6}>
                    <EmptyState icon={Inbox} title="No submissions found" subtitle="Try adjusting your filters." />
                  </td>
                </tr>
              ) : loadError ? (
                <tr>
                  <td colSpan={6}>
                    <EmptyState icon={Inbox} title="Couldn't load submissions" subtitle="Please try again." />
                  </td>
                </tr>
              ) : (
                rows.map(row => (
                  <tr
                    key={row.id}
                    onClick={() => router.push(`/admin/essay-writing/submissions/${row.id}`)}
                    className="border-b last:border-b-0 cursor-pointer hover:bg-[var(--color-surface-subtle)]"
                    style={{ borderColor: "var(--color-border)" }}
                  >
                    <td className="px-4 py-3" style={{ color: "var(--color-text)" }}>{row.paper_title}</td>
                    <td className="px-4 py-3 font-mono text-xs" style={{ color: "var(--color-text-subtle)" }}>{row.batch_id.slice(0, 8)}</td>
                    <td className="px-4 py-3"><StatusPill status={row.status} /></td>
                    <td className="px-4 py-3" style={{ color: "var(--color-text)" }}>{row.score !== null ? `${row.score}/10` : "—"}</td>
                    <td className="px-4 py-3">
                      {row.malpractice_flag && <ShieldAlert size={14} style={{ color: "#DC2626" }} />}
                    </td>
                    <td className="px-4 py-3 text-xs" style={{ color: "var(--color-text-subtle)" }}>{formatDateTime(row.created_at)}</td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
          <Pagination page={page} totalPages={totalPages} onPageChange={setPage} totalCount={totalCount} pageSize={30} />
        </div>
      </PageWrapper>
    </AdminLayout>
  );
}
