"use client";

import { useEffect, useState, useCallback } from "react";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import {
  Download, FileText, ShieldAlert, CheckCircle2, XCircle, Clock, Hourglass, PenLine, Target, RefreshCw, AlertTriangle, Eye, Info, Loader2, FlaskConical,
} from "lucide-react";
import { AdminLayout } from "@/components/layout/AdminLayout";
import { PageWrapper } from "@/components/layout/PageWrapper";
import { PageHeader } from "@/components/layout/PageHeader";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { SearchInput } from "@/components/ui/SearchInput";
import { Select } from "@/components/ui/Select";
import { Modal } from "@/components/ui/Modal";
import { Pagination } from "@/components/ui/Pagination";
import { Skeleton, TableRowSkeleton } from "@/components/ui/Skeleton";
import { EmptyState } from "@/components/ui/EmptyState";
import { useToast } from "@/components/ui/Toast";
import api, { getErrorMessage } from "@/lib/api";
import { useDepartments } from "@/lib/departmentsContext";
import type {
  ApiSuccess, AdminResultsPage, AdminResultRow, AdminResultResponsesData, AdminSessionTimelineData, BatchAssignment,
  AdminTrialResultRow,
} from "@/types";

function formatDateTime(iso: string | null): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
}

function formatDuration(seconds: number | null): string {
  if (seconds === null) return "—";
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return `${m}m ${s}s`;
}

// A static minutes-elapsed number, not a live-ticking clock — recomputed
// whenever the component happens to re-render (a data refresh, a filter
// change, etc.), with no dedicated interval driving it.
function formatRelativeTime(date: Date | null): string {
  if (!date) return "never";
  const minutes = Math.floor((Date.now() - date.getTime()) / 60000);
  if (minutes < 1) return "just now";
  return `${minutes} min ago`;
}

// Same cadence as admin/assessments/dashboard/[assignment_id]/page.tsx's
// live poll — a single platform-wide convention for "how often do we
// re-check a LIVE assignment," not a value invented separately per page.
const LIVE_POLL_INTERVAL_MS = 8000;

function ExamStatusBadge({ status }: { status: AdminResultRow["exam_status"] }) {
  if (status === "submitted") {
    return (
      <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold" style={{ background: "#F0FDF4", color: "#16A34A" }}>
        <CheckCircle2 size={11} /> Submitted
      </span>
    );
  }
  if (status === "writing") {
    return (
      <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold" style={{ background: "#EFF6FF", color: "#2563EB" }}>
        <PenLine size={11} /> Writing
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold" style={{ background: "#FFF4E6", color: "#E8820C" }}>
      <Hourglass size={11} /> Pending
    </span>
  );
}

export default function AdminAssessmentResultsPage() {
  const { assignment_id } = useParams<{ assignment_id: string }>();
  const router = useRouter();
  const searchParams = useSearchParams();
  const toast = useToast();
  const { departments } = useDepartments();

  const [rows, setRows] = useState<AdminResultRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState(false);
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  const [totalCount, setTotalCount] = useState(0);

  const [rollSearch, setRollSearch] = useState("");
  const [department, setDepartment] = useState("");
  const [examStatus, setExamStatus] = useState("");
  // Deep-linkable from the Analytics page's "View flagged students" link
  // (?flagged=true) — read once at mount via the lazy useState initializer,
  // same one-way "seed initial state from the URL" pattern as any other
  // link-driven filter; the URL itself is never kept in sync afterward
  // (this page has never round-tripped filters through the URL for any of
  // its other filters either).
  const [flagged, setFlagged] = useState(() => (searchParams.get("flagged") === "true" ? "true" : ""));
  // Same pattern, for the Analytics page's Set Fairness bars (?set=<label>).
  const [set, setSet] = useState(() => searchParams.get("set") ?? "");
  const [availableSets, setAvailableSets] = useState<string[]>([]);
  const [passed, setPassed] = useState("");
  // "above"/"between" use pctX as the (exclusive) lower bound,
  // "below"/"between" use pctY as the (inclusive) upper bound.
  const [pctMode, setPctMode] = useState<"" | "above" | "below" | "between">("");
  const [pctX, setPctX] = useState("");
  const [pctY, setPctY] = useState("");
  const [sort, setSort] = useState("-ended_at");

  const [assignment, setAssignment] = useState<BatchAssignment | null>(null);
  const [lastRefreshedAt, setLastRefreshedAt] = useState<Date | null>(null);

  const [responsesModal, setResponsesModal] = useState<AdminResultResponsesData | null>(null);
  const [timelineModal, setTimelineModal] = useState<AdminSessionTimelineData | null>(null);
  const [detailLoading, setDetailLoading] = useState<string | null>(null);
  const [extendTarget, setExtendTarget] = useState<{ sessionId: string; studentName: string } | null>(null);
  const [extendMinutes, setExtendMinutes] = useState("15");
  const [extending, setExtending] = useState(false);
  const [exporting, setExporting] = useState(false);

  const buildParams = useCallback(() => {
    const params = new URLSearchParams({ page: String(page), sort });
    const trimmedRollSearch = rollSearch.trim();
    if (trimmedRollSearch) params.set("student_roll_id", trimmedRollSearch);
    if (department) params.set("department", department);
    if (examStatus) params.set("exam_status", examStatus);
    if (flagged) params.set("flagged", flagged);
    if (set) params.set("set", set);
    if (passed) params.set("passed", passed);
    if ((pctMode === "above" || pctMode === "between") && pctX !== "") params.set("min_percentage", pctX);
    if ((pctMode === "below" || pctMode === "between") && pctY !== "") params.set("max_percentage", pctY);
    return params;
  }, [page, sort, rollSearch, department, examStatus, flagged, set, passed, pctMode, pctX, pctY]);

  // silent=true (background poll) skips the full-table skeleton and stays
  // quiet on failure — a transient blip shouldn't flash the table or spam
  // an error toast every 8s; the next tick just tries again. silent=false
  // (initial load, a filter/sort/page change, or the manual refresh button)
  // behaves exactly as before: skeleton while loading, toast on failure.
  const load = useCallback((silent = false) => {
    if (!silent) setLoading(true);
    api.get<AdminResultsPage>(
      `/assessments/admin/assignments/${assignment_id}/results/?${buildParams()}`
    )
      .then(res => {
        setRows(res.data.results);
        setTotalPages(res.data.total_pages);
        setTotalCount(res.data.count);
        setAvailableSets(res.data.available_sets ?? []);
        setLastRefreshedAt(new Date());
        setLoadError(false);
      })
      // Silent background polls stay quiet on failure (see comment above) —
      // but a *non-silent* failure (initial load, filter change, manual
      // refresh) must not just toast and fall through to rendering an empty
      // table with all its headers and zero rows, which reads as "there's
      // genuinely nothing here" rather than "this failed to load."
      .catch(err => { if (!silent) { toast.error(getErrorMessage(err)); setLoadError(true); } })
      .finally(() => { if (!silent) setLoading(false); });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [assignment_id, buildParams]);

  useEffect(() => load(), [load]);

  useEffect(() => { setPage(1); }, [rollSearch, department, examStatus, flagged, set, passed, pctMode, pctX, pctY, sort]);

  // Independent of the (filterable/paginated) results table — this is just
  // the assignment's own stored pass_cutoff_percentage and paper_title,
  // plus (below) its status, which gates whether the live poll runs at all.
  const loadAssignment = useCallback((silent = false) => {
    api.get<ApiSuccess<BatchAssignment>>(`/assessments/admin/assignments/${assignment_id}/`)
      .then(res => setAssignment(res.data.data))
      .catch(err => { if (!silent) toast.error(getErrorMessage(err)); });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [assignment_id]);

  useEffect(() => { loadAssignment(); }, [loadAssignment]);

  // Mock tests tab (added 2026-08-27) — deliberately paper-scoped, not
  // assignment-scoped: an admin's mock attempts on this paper can predate
  // this specific assignment (taken from the assign form's Final Review
  // step) or come from a completely different assignment of the same
  // paper, so "this assignment's results" isn't the right frame for them.
  // Loaded lazily (only once the tab is actually opened, and only once the
  // assignment's own paper id is known) rather than alongside the real
  // results on every page load.
  const [resultsMode, setResultsMode] = useState<"real" | "mock">("real");
  const [mockRows, setMockRows] = useState<AdminTrialResultRow[]>([]);
  const [loadingMock, setLoadingMock] = useState(false);
  const [mockLoadError, setMockLoadError] = useState(false);

  const loadMockResults = useCallback(() => {
    if (!assignment) return;
    setLoadingMock(true);
    setMockLoadError(false);
    api.get<ApiSuccess<AdminTrialResultRow[]>>(`/assessments/admin/papers/${assignment.paper}/trial-results/`)
      .then(res => setMockRows(res.data.data))
      .catch(err => { toast.error(getErrorMessage(err)); setMockLoadError(true); })
      .finally(() => setLoadingMock(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [assignment]);

  useEffect(() => {
    if (resultsMode === "mock" && assignment) loadMockResults();
  }, [resultsMode, assignment, loadMockResults]);

  // Live auto-refresh — only while the assignment is actually LIVE
  // (students still submitting, so the table can genuinely change).
  // SCHEDULED: nothing has happened yet, nothing to refresh. CLOSED:
  // results are final, sessions are already finalized — polling forever
  // would just be wasted load for zero benefit. Re-checks assignment.status
  // itself on every tick too, so once the exam is closed (by this admin,
  // another admin, or the automatic sweep job) the *next* tick's status
  // fetch flips this effect's own dependency and the interval self-stops —
  // no separate "did it just close" plumbing needed.
  useEffect(() => {
    if (assignment?.status !== "LIVE") return;
    const interval = setInterval(() => {
      load(true);
      loadAssignment(true);
    }, LIVE_POLL_INTERVAL_MS);
    return () => clearInterval(interval);
  }, [assignment?.status, load, loadAssignment]);

  async function openResponses(resultId: string) {
    setDetailLoading(resultId + ":responses");
    try {
      const res = await api.get<ApiSuccess<AdminResultResponsesData>>(`/assessments/admin/results/${resultId}/responses/`);
      setResponsesModal(res.data.data);
    } catch (err) {
      toast.error(getErrorMessage(err));
    } finally {
      setDetailLoading(null);
    }
  }

  async function openTimeline(sessionId: string) {
    setDetailLoading(sessionId + ":timeline");
    try {
      const res = await api.get<ApiSuccess<AdminSessionTimelineData>>(`/assessments/admin/sessions/${sessionId}/timeline/`);
      setTimelineModal(res.data.data);
    } catch (err) {
      toast.error(getErrorMessage(err));
    } finally {
      setDetailLoading(null);
    }
  }

  // The student's client picks this up on its next server-time poll
  // (every ~20s, ADR 001 — no push channel exists) and both updates its
  // countdown and shows its own notification then, not instantly.
  async function handleExtend() {
    if (!extendTarget) return;
    const minutes = Number(extendMinutes);
    if (!Number.isInteger(minutes) || minutes <= 0) {
      toast.error("Enter a positive whole number of minutes.");
      return;
    }
    setExtending(true);
    try {
      await api.patch(
        `/assessments/admin/assignments/${assignment_id}/sessions/${extendTarget.sessionId}/extend/`,
        { extend_minutes: minutes },
      );
      toast.success(`Extended ${extendTarget.studentName}'s time by ${minutes} minute${minutes === 1 ? "" : "s"}.`);
      setExtendTarget(null);
      load(true);
    } catch (err) {
      toast.error(getErrorMessage(err));
    } finally {
      setExtending(false);
    }
  }

  async function handleExport() {
    setExporting(true);
    try {
      const res = await api.get(`/assessments/admin/assignments/${assignment_id}/results/export/?${buildParams()}`, {
        responseType: "blob",
      });
      const blob = new Blob([res.data], { type: "text/csv;charset=utf-8;" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `results_${assignment_id}.csv`;
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

  const isEmpty = !loading && rows.length === 0;
  const hasActiveFilters = !!(
    rollSearch.trim() || department || examStatus || flagged || set || passed || pctMode
  );

  return (
    <AdminLayout>
      <PageWrapper>
        <PageHeader
          title={assignment ? `${assignment.paper_title} - Results` : "Results"}
          titleSkeleton={!assignment ? <Skeleton className="h-8 w-64" /> : undefined}
          subtitle="Review submitted responses, activity logs, and export data for this assessment."
          backHref="/admin/assessments/results"
          rightSlot={
            <div className="flex items-center gap-3 flex-wrap justify-end">
              <div className="flex items-center gap-1.5">
                <button
                  onClick={() => load()}
                  disabled={loading}
                  className="p-1.5 rounded-[var(--radius-md)] transition-colors disabled:opacity-60 disabled:cursor-not-allowed cursor-pointer"
                  style={{ color: "var(--color-text-subtle)" }}
                  onMouseEnter={e => { if (!loading) { e.currentTarget.style.background = "var(--color-surface-hover)"; e.currentTarget.style.color = "var(--color-text)"; } }}
                  onMouseLeave={e => { e.currentTarget.style.background = "transparent"; e.currentTarget.style.color = "var(--color-text-subtle)"; }}
                  aria-label="Refresh results"
                  title={assignment?.status === "LIVE" ? "Refresh now (also auto-refreshes every 8s while live)" : "Refresh now"}
                >
                  <RefreshCw size={14} className={loading ? "animate-spin" : ""} />
                </button>
                <span className="text-xs whitespace-nowrap" style={{ color: "var(--color-text-subtle)" }}>
                  Refreshed {formatRelativeTime(lastRefreshedAt)}
                </span>
              </div>
              {assignment && (
                <span
                  className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-semibold whitespace-nowrap"
                  style={{ background: "var(--color-accent-light)", color: "var(--color-accent)" }}
                  title="The pass cutoff set for this assignment"
                >
                  <Target size={12} /> Pass cutoff: {assignment.pass_cutoff_percentage}%
                </span>
              )}
              <Button variant="secondary" leftIcon={<Download size={14} />} loading={exporting} onClick={handleExport}>
                Export CSV
              </Button>
            </div>
          }
        />

        {/* Real / Mock toggle (added 2026-08-27) — mock attempts are the
            admin's own dry runs on this paper, kept entirely separate from
            real student data everywhere else in this platform; this tab is
            the one place they're ever surfaced. */}
        <div className="flex gap-2 mb-5">
          {(["real", "mock"] as const).map(mode => (
            <button
              key={mode}
              type="button"
              onClick={() => setResultsMode(mode)}
              className="px-3.5 py-1.5 rounded-full text-xs font-semibold cursor-pointer transition-colors"
              style={resultsMode === mode
                ? { background: "var(--color-accent)", color: "#fff" }
                : { background: "var(--color-surface)", color: "var(--color-text-muted)", border: "1px solid var(--color-border)" }
              }
            >
              {mode === "real" ? "Real tests" : "Mock tests"}
            </button>
          ))}
        </div>

        {resultsMode === "mock" ? (
          <div className="rounded-[var(--radius-xl)] overflow-hidden" style={{ border: "1px solid var(--color-border)", background: "var(--color-surface)" }}>
            {mockLoadError ? (
              <EmptyState
                icon={AlertTriangle}
                title="Couldn't load mock test attempts"
                subtitle="Something went wrong fetching this data — it may be temporary. Try again in a moment."
                action={{ label: "Retry", onClick: loadMockResults }}
              />
            ) : loadingMock ? (
              <table className="w-full text-sm"><tbody>
                {Array.from({ length: 3 }).map((_, i) => <TableRowSkeleton key={i} cols={6} />)}
              </tbody></table>
            ) : mockRows.length === 0 ? (
              <EmptyState
                icon={FlaskConical}
                title="No mock test attempts yet"
                subtitle="Attempts taken via the assign form's Final Review step or this assignment's Mock Test button will show up here."
              />
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr style={{ borderBottom: "1px solid var(--color-border)" }}>
                      {["Attempted by", "Set", "Score", "%", "Duration", "When"].map(h => (
                        <th key={h} className="text-left px-4 py-3 text-xs font-semibold uppercase tracking-wider whitespace-nowrap"
                          style={{ color: "var(--color-text-subtle)" }}>{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {mockRows.map(row => (
                      <tr key={row.id} style={{ borderBottom: "1px solid var(--color-border)" }}>
                        <td className="px-4 py-3 whitespace-nowrap" style={{ color: "var(--color-text)" }}>
                          {row.attempted_by_name || row.attempted_by_email || "—"}
                        </td>
                        <td className="px-4 py-3 whitespace-nowrap">{row.set_label}</td>
                        <td className="px-4 py-3 whitespace-nowrap">{row.score}/{row.total_marks}</td>
                        <td className="px-4 py-3 whitespace-nowrap font-semibold">{row.percentage}%</td>
                        <td className="px-4 py-3 whitespace-nowrap">
                          <span className="inline-flex items-center gap-1"><Clock size={11} />{formatDuration(row.duration_seconds)}</span>
                        </td>
                        <td className="px-4 py-3 whitespace-nowrap">{formatDateTime(row.ended_at)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        ) : (
        <>
        {/* Filters — bordered toolbar (same treatment as admin/students) so
            wrapping onto a second line on narrower screens reads as a
            contained, designed group instead of stray floating controls. */}
        <div
          className="flex flex-wrap items-end gap-3 rounded-xl px-4 py-3 mb-5"
          style={{ background: "var(--color-surface)", border: "1px solid var(--color-border)", boxShadow: "var(--shadow-sm)" }}
        >
          <div className="w-full sm:w-48 flex flex-col gap-1.5">
            <label className="text-sm font-medium" style={{ color: "var(--color-text)" }}>Student ID</label>
            <SearchInput
              value={rollSearch}
              onChange={setRollSearch}
              placeholder="Search roll number..."
            />
            <p className="text-xs min-h-[16px]" />
          </div>
          <div className="w-full sm:w-48">
            <Select
              label="Department"
              value={department}
              onChange={e => setDepartment(e.target.value)}
              options={[{ value: "", label: "All departments" }, ...departments.map(d => ({ value: d.code, label: d.name || d.code }))]}
            />
          </div>
          <div className="w-full sm:w-48">
            <Select
              label="Sort by"
              value={sort}
              onChange={e => setSort(e.target.value)}
              options={[
                { value: "-ended_at", label: "Most recent" },
                { value: "-percentage", label: "Highest score" },
                { value: "percentage", label: "Lowest score" },
                { value: "-duration_seconds", label: "Longest duration" },
                { value: "duration_seconds", label: "Shortest duration" },
              ]}
            />
          </div>
          <div className="w-full sm:w-44">
            <Select
              label="Exam status"
              value={examStatus}
              onChange={e => setExamStatus(e.target.value)}
              options={[
                { value: "", label: "All statuses" },
                { value: "pending", label: "Pending" },
                { value: "writing", label: "Writing" },
                { value: "submitted", label: "Submitted" },
              ]}
            />
          </div>
          <div className="w-full sm:w-44">
            <Select
              label="Result"
              value={passed}
              onChange={e => setPassed(e.target.value)}
              options={[
                { value: "", label: "All results" },
                { value: "true", label: "Passed" },
                { value: "false", label: "Failed" },
              ]}
            />
          </div>
          <div className="w-full sm:w-44">
            <Select
              label="Flagged"
              value={flagged}
              onChange={e => setFlagged(e.target.value)}
              options={[
                { value: "", label: "All students" },
                { value: "true", label: "Flagged only" },
                { value: "false", label: "Not flagged" },
              ]}
            />
          </div>
          {availableSets.length > 1 && (
            <div className="w-full sm:w-44">
              <Select
                label="Set"
                value={set}
                onChange={e => setSet(e.target.value)}
                options={[
                  { value: "", label: "All sets" },
                  ...availableSets.map(s => ({ value: s, label: s })),
                ]}
              />
            </div>
          )}
          <div className="w-full sm:w-44">
            <Select
              label="Percentage"
              value={pctMode}
              onChange={e => { setPctMode(e.target.value as typeof pctMode); setPctX(""); setPctY(""); }}
              options={[
                { value: "", label: "Any percentage" },
                { value: "above", label: "Above x%" },
                { value: "below", label: "Below y%" },
                { value: "between", label: "Between x and y" },
              ]}
            />
          </div>
          {(pctMode === "above" || pctMode === "between") && (
            <div className="w-full sm:w-32">
              <Input
                label={pctMode === "between" ? "Above x%" : "Above %"}
                type="number" min={0} max={100} step="any"
                placeholder="x"
                value={pctX}
                onChange={e => setPctX(e.target.value)}
              />
            </div>
          )}
          {(pctMode === "below" || pctMode === "between") && (
            <div className="w-full sm:w-32">
              <Input
                label={pctMode === "between" ? "Up to y%" : "Up to %"}
                type="number" min={0} max={100} step="any"
                placeholder="y"
                value={pctY}
                onChange={e => setPctY(e.target.value)}
              />
            </div>
          )}
        </div>

        {/* Table */}
        <div className="rounded-[var(--radius-xl)] overflow-hidden" style={{ border: "1px solid var(--color-border)", background: "var(--color-surface)" }}>
          {loadError ? (
            <EmptyState
              icon={AlertTriangle}
              title="Couldn't load results"
              subtitle="Something went wrong fetching this data — it may be temporary. Try again in a moment."
              action={{ label: "Retry", onClick: () => load() }}
            />
          ) : (
          <>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr style={{ borderBottom: "1px solid var(--color-border)" }}>
                  {["Student", "Dept", "Set", "Status", "Duration", "Score", "%", "Flagged", "Logs/Tracking", ""].map(h => (
                    <th key={h} className="text-left px-4 py-3 text-xs font-semibold uppercase tracking-wider whitespace-nowrap"
                      style={{ color: "var(--color-text-subtle)" }}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {loading ? (
                  Array.from({ length: 5 }).map((_, i) => <TableRowSkeleton key={i} cols={10} />)
                ) : rows.map(r => (
                  <tr key={r.student_user_id} style={{ borderBottom: "1px solid var(--color-border)" }}>
                    <td className="px-4 py-3 whitespace-nowrap">
                      <p className="font-medium" style={{ color: "var(--color-text)" }}>{r.student_name}</p>
                      <p className="text-xs" style={{ color: "var(--color-text-subtle)" }}>{r.student_roll_id}</p>
                    </td>
                    <td className="px-4 py-3 whitespace-nowrap">{r.department}</td>
                    <td className="px-4 py-3 whitespace-nowrap">{r.set_label}</td>
                    <td className="px-4 py-3 whitespace-nowrap"><ExamStatusBadge status={r.exam_status} /></td>
                    <td className="px-4 py-3 whitespace-nowrap">
                      <span className="inline-flex items-center gap-1"><Clock size={11} />{formatDuration(r.duration_seconds)}</span>
                    </td>
                    <td className="px-4 py-3 whitespace-nowrap">{r.score !== null ? `${r.score}/${r.total_marks}` : "—"}</td>
                    <td className="px-4 py-3 whitespace-nowrap font-semibold">{r.percentage !== null ? `${r.percentage}%` : "—"}</td>
                    <td className="px-4 py-3 whitespace-nowrap">
                      {r.exam_status !== "submitted" ? (
                        <span style={{ color: "var(--color-text-subtle)" }}>—</span>
                      ) : r.malpractice_flag ? (
                        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-semibold"
                          style={{ background: "#FEF2F2", color: "#DC2626" }}>
                          <ShieldAlert size={11} /> Flagged
                        </span>
                      ) : (
                        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-semibold"
                          style={{ background: "#F0FDF4", color: "#16A34A" }}>
                          <CheckCircle2 size={11} /> Clean
                        </span>
                      )}
                    </td>
                    <td className="px-4 py-3 whitespace-nowrap">
                      {r.session_id ? (
                        <button
                          onClick={() => openTimeline(r.session_id!)}
                          disabled={detailLoading === r.session_id + ":timeline"}
                          className="p-1.5 rounded-[var(--radius-md)] transition-colors disabled:opacity-60 disabled:cursor-wait cursor-pointer"
                          style={{ color: "var(--color-text-subtle)" }}
                          onMouseEnter={e => { if (detailLoading !== r.session_id + ":timeline") { e.currentTarget.style.background = "var(--color-surface-hover)"; e.currentTarget.style.color = "var(--color-text)"; } }}
                          onMouseLeave={e => { e.currentTarget.style.background = "transparent"; e.currentTarget.style.color = "var(--color-text-subtle)"; }}
                          aria-label={`View ${r.student_name}'s exam activity timeline`}
                          title="View exam activity timeline"
                        >
                          {detailLoading === r.session_id + ":timeline" ? (
                            <Loader2 size={16} className="animate-spin" />
                          ) : (
                            <Eye size={16} />
                          )}
                        </button>
                      ) : (
                        <span className="text-xs" style={{ color: "var(--color-text-subtle)" }}>—</span>
                      )}
                    </td>
                    <td className="px-4 py-3 whitespace-nowrap">
                      {r.result_id ? (
                        <Button variant="ghost" size="sm" loading={detailLoading === r.result_id + ":responses"}
                          onClick={() => openResponses(r.result_id!)}>
                          Responses
                        </Button>
                      ) : r.exam_status === "writing" && r.session_id ? (
                        <Button
                          variant="ghost" size="sm" leftIcon={<Clock size={13} />}
                          onClick={() => { setExtendTarget({ sessionId: r.session_id!, studentName: r.student_name }); setExtendMinutes("15"); }}
                        >
                          Extend Time
                        </Button>
                      ) : (
                        <span className="text-xs" style={{ color: "var(--color-text-subtle)" }}>Not submitted</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {isEmpty && hasActiveFilters && (
            <EmptyState
              icon={FileText}
              title="No students match these filters"
              subtitle="Try adjusting or clearing the filters above."
              action={{
                label: "Clear filters",
                onClick: () => {
                  setRollSearch(""); setDepartment(""); setExamStatus("");
                  setFlagged(""); setSet(""); setPassed(""); setPctMode(""); setPctX(""); setPctY("");
                },
              }}
            />
          )}
          {isEmpty && !hasActiveFilters && (
            <EmptyState icon={FileText} title="No students allocated yet" subtitle="Assign this paper to a batch to see the roster here." />
          )}

          {!isEmpty && (
            <Pagination page={page} totalPages={totalPages} totalCount={totalCount} onPageChange={setPage} />
          )}
          </>
          )}
        </div>
        </>
        )}
      </PageWrapper>

      {/* Responses modal */}
      <Modal isOpen={!!responsesModal} onClose={() => setResponsesModal(null)} title="Submitted Responses" maxWidth="lg">
        <div className="space-y-4 max-h-[60vh] overflow-y-auto">
          {responsesModal?.questions.map(q => (
            <div key={q.question_id} className="rounded-[var(--radius-lg)] p-4" style={{ border: "1px solid var(--color-border)" }}>
              <p className="text-xs font-semibold uppercase tracking-wider mb-2" style={{ color: "var(--color-text-subtle)" }}>
                Question {q.question_number} · {q.marks_awarded}/{q.marks} marks
              </p>
              <p className="text-sm mb-3" style={{ color: "var(--color-text)" }}>{q.question_text}</p>
              {!q.answered && (
                <p className="text-xs italic mb-2" style={{ color: "var(--color-text-subtle)" }}>Not answered</p>
              )}
              <div className="space-y-1.5">
                {q.options.map(opt => {
                  const selected = q.selected_option_ids.includes(opt.id);
                  const style = opt.is_correct
                    ? { background: "#F0FDF4", border: "1px solid #BBF7D0", color: "#166534" }
                    : selected
                      ? { background: "#FEF2F2", border: "1px solid #FECACA", color: "#991B1B" }
                      : { background: "#fff", border: "1px solid var(--color-border)", color: "var(--color-text-muted)" };
                  return (
                    <div key={opt.id} className="flex items-center gap-2 px-3 py-2 rounded-[var(--radius-md)] text-sm" style={style}>
                      {opt.is_correct ? <CheckCircle2 size={13} /> : selected ? <XCircle size={13} /> : null}
                      <span className="font-semibold">{opt.label}.</span> {opt.text}
                      {selected && <span className="text-xs ml-auto">(selected)</span>}
                    </div>
                  );
                })}
              </div>
            </div>
          ))}
        </div>
      </Modal>

      {/* Activity timeline modal — plain-English, non-technical event log
          for the "eye icon" Logs/Tracking column. Deliberately not the
          raw event_type/metadata dump the old Logs button showed: every
          event here reads as a short sentence anyone can understand. */}
      <Modal isOpen={!!timelineModal} onClose={() => setTimelineModal(null)} title="Student Activity Timeline" maxWidth="md">
        <div>
          <div className="flex items-start gap-2 px-4 py-3 rounded-[var(--radius-lg)] mb-4"
            style={{ background: "#FFF4E6", border: "1px solid #FDE0B0" }}>
            <Info size={16} style={{ color: "#B45309", flexShrink: 0, marginTop: 1 }} />
            <p className="text-xs leading-relaxed" style={{ color: "#92400E" }}>
              This activity data is automatically and permanently erased {timelineModal?.retention_days ?? 15} days
              after the exam to save storage — it does not affect the student&apos;s score or result, which are kept permanently.
            </p>
          </div>

          {timelineModal?.malpractice_flag && (
            <div className="flex items-start gap-2 px-4 py-3 rounded-[var(--radius-lg)] mb-4"
              style={{ background: "#FEF2F2", border: "1px solid #FECACA" }}>
              <ShieldAlert size={16} style={{ color: "#DC2626", flexShrink: 0, marginTop: 1 }} />
              <p className="text-sm font-semibold" style={{ color: "#991B1B" }}>Flagged for review</p>
            </div>
          )}

          <div className="space-y-2 max-h-[50vh] overflow-y-auto">
            {timelineModal?.events.map((event, i) => (
              <div key={i} className="flex items-center gap-3 px-3 py-2 rounded-[var(--radius-md)]" style={{ background: "var(--color-surface-secondary)" }}>
                <span className="flex items-center justify-center rounded-full text-xs font-semibold flex-shrink-0"
                  style={{ width: 20, height: 20, background: "var(--color-accent-light)", color: "var(--color-accent)" }}>
                  {i + 1}
                </span>
                <span className="text-sm" style={{ color: "var(--color-text)" }}>{event.description}</span>
                <span className="text-xs ml-auto whitespace-nowrap" style={{ color: "var(--color-text-subtle)" }}>{formatDateTime(event.occurred_at)}</span>
              </div>
            ))}
          </div>
          {timelineModal?.truncated && (
            <p className="text-xs mt-3 italic" style={{ color: "var(--color-text-subtle)" }}>
              Showing the first {timelineModal.events.length - (timelineModal.exam_status === "writing" ? 1 : 2)} of {timelineModal.total_event_count} recorded events.
            </p>
          )}
        </div>
      </Modal>

      {/* Extend-time modal — the student's own client picks this up on its
          next server-time poll (every ~20s), not instantly; see the
          hint text below. */}
      <Modal isOpen={!!extendTarget} onClose={() => setExtendTarget(null)} title="Extend exam time" maxWidth="sm">
        <p className="text-sm mb-4 leading-relaxed" style={{ color: "var(--color-text-muted)" }}>
          Give <strong>{extendTarget?.studentName}</strong> more time on this exam. Their countdown
          updates and they get a notification within about 20 seconds — not instantly.
        </p>
        <Input
          label="Extend by (minutes)"
          type="number" min={1} max={1440}
          value={extendMinutes}
          onChange={e => setExtendMinutes(e.target.value)}
        />
        <div className="flex justify-end gap-3 mt-5">
          <Button variant="secondary" onClick={() => setExtendTarget(null)}>Cancel</Button>
          <Button variant="primary" loading={extending} onClick={handleExtend}>Extend</Button>
        </div>
      </Modal>
    </AdminLayout>
  );
}
