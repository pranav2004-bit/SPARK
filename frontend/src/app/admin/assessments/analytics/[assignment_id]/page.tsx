"use client";

import { useEffect, useState, useCallback, useMemo } from "react";
import { useParams, useRouter } from "next/navigation";
import {
  Download, CheckCircle2, XCircle, ShieldAlert, TrendingUp, AlertTriangle, RefreshCw, Info, ArrowRight, Clock, Users,
} from "lucide-react";
import { AdminLayout } from "@/components/layout/AdminLayout";
import { PageWrapper } from "@/components/layout/PageWrapper";
import { PageHeader } from "@/components/layout/PageHeader";
import { Button } from "@/components/ui/Button";
import { Select } from "@/components/ui/Select";
import { Modal } from "@/components/ui/Modal";
import { Pagination } from "@/components/ui/Pagination";
import { Skeleton } from "@/components/ui/Skeleton";
import { EmptyState } from "@/components/ui/EmptyState";
import { useToast } from "@/components/ui/Toast";
import api, { getErrorMessage } from "@/lib/api";
import type { ApiSuccess, AdminQuestionResponsesData } from "@/types";

interface AnalyticsData {
  assignment_id: string;
  generated_at: string;
  total_completed: number;
  total_allocated: number;
  average_score_percentage: number | null;
  average_completion_time_seconds: number | null;
  exam_duration_minutes: number;
  score_distribution: { bucket: string; count: number }[];
  pass_fail: { pass_count: number; fail_count: number; pass_rate_percentage: number; cutoff_percentage: number };
  question_difficulty: {
    question_id: string; question_number: number; set_label: string;
    total_answered: number; correct_count: number; percentage_correct: number | null;
    average_seconds_spent: number | null;
  }[];
  department_comparison: { department: string; student_count: number; average_percentage: number }[];
  set_comparison: { set_label: string; student_count: number; average_percentage: number }[];
  malpractice_rate: { flagged_count: number; total_count: number; rate_percentage: number };
  malpractice_breakdown: { reason: string; count: number }[];
  metric_definitions: Record<string, string>;
}

// Below this many completed sessions, a percentage or average is one or two
// students away from swinging wildly — not wrong, just not yet statistically
// meaningful. 10 is a common floor for "worth trusting at a glance" without
// being so high it hides the warning on every small pilot batch.
const SMALL_SAMPLE_THRESHOLD = 10;

const MALPRACTICE_REASON_LABELS: Record<string, string> = {
  tab_switch: "Excessive tab switching",
  fullscreen_exit: "Excessive fullscreen exits",
  cadence: "Suspiciously fast answering",
};

function formatSeconds(seconds: number | null): string {
  if (seconds === null) return "—";
  if (seconds < 60) return `${seconds}s`;
  return `${(seconds / 60).toFixed(1)} min`;
}

// Every color below is a function of the actual number, not a fixed brand
// color — a 5% pass rate must not render with the same "success green" as
// a 95% one (audited live, 2026-08-18: it previously did).
function passRateColor(pct: number): string {
  if (pct < 50) return "#DC2626";
  if (pct < 80) return "#E8820C";
  return "#16A34A";
}
function malpracticeColor(pct: number): string {
  if (pct > 15) return "#DC2626";
  if (pct > 5) return "#E8820C";
  return "#16A34A";
}
function averageScoreColor(pct: number | null): string {
  if (pct === null) return "#94A3B8";
  if (pct < 50) return "#DC2626";
  if (pct < 75) return "#E8820C";
  return "#16A34A";
}

function difficultyBadge(pct: number | null): { label: string; color: string; bg: string } | null {
  if (pct === null) return null;
  if (pct < 20) return { label: "Very hard", color: "#DC2626", bg: "#FEF2F2" };
  if (pct >= 95) return { label: "Very easy", color: "#B45309", bg: "#FFF4E6" };
  return null;
}

// Matches AGENTS.md's "Chart Implementation — CSS + SVG (no Recharts)"
// convention, same visual language as super-admin/analytics/page.tsx's HBarChart.
function HBarChart({ data, valueKey, labelKey, color = "var(--color-accent)", suffix = "", onBarClick }: {
  data: Record<string, number | string>[]; valueKey: string; labelKey: string; color?: string; suffix?: string;
  // Optional per-bar drill-down (e.g. Set Fairness → filtered results for
  // that set) — when omitted, bars render as plain non-interactive rows.
  onBarClick?: (item: Record<string, number | string>) => void;
}) {
  const max = Math.max(...data.map(d => Number(d[valueKey]) || 0), 1);
  return (
    <div className="space-y-3">
      {data.map((item, i) => {
        const val = Number(item[valueKey]) || 0;
        const pct = Math.max((val / max) * 100, val > 0 ? 3 : 0);
        const rowContent = (
          <>
            {/* Wraps instead of truncating — a cut-off label ("Excessive
                tab switc...") is worse than a bar that's two lines tall
                (found live, 2026-08-18: "Excessive tab switching" was
                being clipped illegibly at a fixed single-line width). */}
            <div className="w-32 text-xs text-right shrink-0 leading-snug" style={{ color: "var(--color-text-muted)" }}>
              {String(item[labelKey])}
            </div>
            <div className="flex-1 h-6 rounded-full overflow-hidden transition-[filter]" style={{ background: "var(--color-surface-secondary)" }}>
              {/* A genuinely zero value renders no inner segment at all —
                  the padded/colored div used to render at 0% width but
                  still keep its own horizontal padding, leaving a stray
                  colored "dot" nub on every empty bucket (found live,
                  2026-08-18: the 0-10%/40-50%/90-100% score buckets each
                  showed a small orange dot with no number in it). */}
              {val > 0 && (
                <div className="h-full flex items-center px-2.5 rounded-full transition-all duration-500 ease-out group-hover:brightness-95"
                  style={{ width: `${pct}%`, background: color, minWidth: "2rem" }}>
                  <span className="text-xs font-semibold text-white truncate">{val}{suffix}</span>
                </div>
              )}
            </div>
          </>
        );
        return onBarClick ? (
          <button
            key={i}
            type="button"
            onClick={() => onBarClick(item)}
            className="flex items-center gap-3 w-full text-left cursor-pointer group bg-transparent border-0 p-0"
          >
            {rowContent}
          </button>
        ) : (
          <div key={i} className="flex items-center gap-3">
            {rowContent}
          </div>
        );
      })}
    </div>
  );
}

function StatTile({ icon: Icon, label, value, hint, color, action }: {
  icon: React.ElementType; label: string; value: string; hint?: string; color: string;
  action?: { label: string; onClick: () => void };
}) {
  return (
    <div className="rounded-[var(--radius-xl)] p-4 flex flex-col" style={{ background: "var(--color-surface)", border: "1px solid var(--color-border)" }}>
      <div className="flex items-center gap-2 mb-2">
        <div className="w-8 h-8 rounded-[var(--radius-md)] flex items-center justify-center shrink-0" style={{ background: `${color}1A` }}>
          <Icon size={15} style={{ color }} />
        </div>
        <p className="text-xs font-semibold uppercase tracking-wider" style={{ color: "var(--color-text-subtle)" }}>{label}</p>
      </div>
      <p className="text-2xl font-bold" style={{ color: "var(--color-text)" }}>{value}</p>
      {hint && <p className="text-xs mt-0.5" style={{ color: "var(--color-text-subtle)" }}>{hint}</p>}
      {action && (
        <div className="mt-2.5 pt-2.5" style={{ borderTop: "1px solid var(--color-border)" }}>
          <button
            onClick={action.onClick}
            className="text-xs font-semibold flex items-center gap-1 cursor-pointer w-fit"
            style={{ color: "var(--color-accent)" }}
            onMouseEnter={e => { e.currentTarget.style.color = "var(--color-accent-hover)"; }}
            onMouseLeave={e => { e.currentTarget.style.color = "var(--color-accent)"; }}
          >
            {action.label} <ArrowRight size={12} />
          </button>
        </div>
      )}
    </div>
  );
}

function formatGeneratedAt(iso: string): string {
  return new Date(iso).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
}

export default function AdminAssessmentAnalyticsPage() {
  const { assignment_id } = useParams<{ assignment_id: string }>();
  const router = useRouter();
  const toast = useToast();

  const [data, setData] = useState<AnalyticsData | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState(false);
  const [exporting, setExporting] = useState(false);
  // "" = All Sets. Reset on every fresh load so switching to a different
  // assignment (or a re-fetch after questions changed) never leaves a
  // filter selected for a set that may no longer exist.
  const [selectedSet, setSelectedSet] = useState("");

  // Per-question drill-down modal — every student's answer to one question,
  // opened from the Per-Question Difficulty table's "View" action.
  const [questionModal, setQuestionModal] = useState<AdminQuestionResponsesData | null>(null);
  const [questionModalLoading, setQuestionModalLoading] = useState<string | null>(null);

  // On failure this must not just toast and fall through to the "No
  // completed sessions yet" branch below — data stays null either way, and
  // that branch alone can't tell "genuinely zero completions" from "this
  // failed to load."
  const load = useCallback(() => {
    setLoading(true);
    setLoadError(false);
    setSelectedSet("");
    api.get<ApiSuccess<AnalyticsData>>(`/assessments/admin/assignments/${assignment_id}/analytics/`)
      .then(res => setData(res.data.data))
      .catch(err => { toast.error(getErrorMessage(err)); setLoadError(true); })
      .finally(() => setLoading(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [assignment_id]);

  useEffect(load, [load]);

  async function handleExport() {
    setExporting(true);
    try {
      const res = await api.get(`/assessments/admin/assignments/${assignment_id}/analytics/export/`, { responseType: "blob" });
      const blob = new Blob([res.data], { type: "text/csv;charset=utf-8;" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `analytics_${assignment_id}.csv`;
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

  async function openQuestionResponses(questionId: string, page = 1) {
    setQuestionModalLoading(questionId);
    try {
      const res = await api.get<AdminQuestionResponsesData>(
        `/assessments/admin/assignments/${assignment_id}/questions/${questionId}/responses/?page=${page}`
      );
      setQuestionModal(res.data);
    } catch (err) {
      toast.error(getErrorMessage(err));
    } finally {
      setQuestionModalLoading(null);
    }
  }

  // Set labels in the order they actually appear (paper order), for the
  // filter dropdown — not alphabetical, so "Set A, Set B, ..." reads the
  // same way it does everywhere else on this page.
  const setLabels = useMemo(() => {
    if (!data) return [];
    return Array.from(new Set(data.question_difficulty.map(q => q.set_label)));
  }, [data]);

  // Hardest-first (lowest % correct) — an admin scanning for a broken or
  // badly-taught question shouldn't have to read every row in paper order
  // to find it. Never-attempted questions (null) sort last: there's nothing
  // to act on for those the way there is for a genuinely low correct rate.
  // Filtered to the selected set first (still hardest-first within it) —
  // a paper with several sets otherwise interleaves every set's questions
  // in one long list, which is harder to scan per-set, not easier.
  const sortedQuestionDifficulty = useMemo(() => {
    if (!data) return [];
    const filtered = selectedSet ? data.question_difficulty.filter(q => q.set_label === selectedSet) : data.question_difficulty;
    return [...filtered].sort((a, b) => {
      if (a.percentage_correct === null && b.percentage_correct === null) return 0;
      if (a.percentage_correct === null) return 1;
      if (b.percentage_correct === null) return -1;
      return a.percentage_correct - b.percentage_correct;
    });
  }, [data, selectedSet]);

  if (loading) {
    return (
      <AdminLayout>
        <PageWrapper>
          <Skeleton className="h-8 w-64 mb-6" />
          <div className="grid grid-cols-2 sm:grid-cols-5 gap-4 mb-6">
            {[1, 2, 3, 4, 5].map(i => <Skeleton key={i} className="h-24 rounded-[var(--radius-xl)]" />)}
          </div>
          <Skeleton className="h-64 rounded-[var(--radius-xl)]" />
        </PageWrapper>
      </AdminLayout>
    );
  }

  if (loadError) {
    return (
      <AdminLayout>
        <PageWrapper>
          <PageHeader title="Analytics" subtitle="Institution-grade breakdown of this assessment's results." backHref="/admin/assessments/analytics" />
          <EmptyState icon={AlertTriangle} title="Couldn't load analytics"
            subtitle="Something went wrong fetching this data — it may be temporary. Try again in a moment."
            action={{ label: "Retry", onClick: load }} />
        </PageWrapper>
      </AdminLayout>
    );
  }

  if (!data || data.total_completed === 0) {
    return (
      <AdminLayout>
        <PageWrapper>
          <PageHeader title="Analytics" subtitle="Institution-grade breakdown of this assessment's results." backHref="/admin/assessments/analytics" />
          <EmptyState icon={TrendingUp} title="No completed sessions yet"
            subtitle="Analytics will populate once students submit their assessments." />
        </PageWrapper>
      </AdminLayout>
    );
  }

  const {
    pass_fail, malpractice_rate, malpractice_breakdown, department_comparison, set_comparison,
    score_distribution, average_score_percentage, average_completion_time_seconds, exam_duration_minutes,
    metric_definitions, generated_at, total_completed, total_allocated,
  } = data;
  const smallSample = total_completed < SMALL_SAMPLE_THRESHOLD;

  return (
    <AdminLayout>
      <PageWrapper>
        <PageHeader
          title="Analytics"
          subtitle={`Grading outcomes and diagnostics, based on ${total_completed} of ${total_allocated} allocated students — for live progress monitoring, see Dashboard instead.`}
          backHref="/admin/assessments/analytics"
          rightSlot={
            <div className="flex items-center gap-3 flex-wrap justify-end">
              <div className="flex items-center gap-1.5">
                <button
                  onClick={load}
                  className="p-1.5 rounded-[var(--radius-md)] transition-colors cursor-pointer"
                  style={{ color: "var(--color-text-subtle)" }}
                  onMouseEnter={e => { e.currentTarget.style.background = "var(--color-surface-hover)"; e.currentTarget.style.color = "var(--color-text)"; }}
                  onMouseLeave={e => { e.currentTarget.style.background = "transparent"; e.currentTarget.style.color = "var(--color-text-subtle)"; }}
                  aria-label="Refresh analytics"
                  title="Recompute now — figures below can be cached for up to 60s"
                >
                  <RefreshCw size={14} />
                </button>
                <span className="text-xs whitespace-nowrap" style={{ color: "var(--color-text-subtle)" }}>
                  Data as of {formatGeneratedAt(generated_at)}
                </span>
              </div>
              <Button variant="secondary" leftIcon={<Download size={14} />} loading={exporting} onClick={handleExport}>
                Export CSV
              </Button>
            </div>
          }
        />

        {smallSample && (
          <div className="flex items-start gap-2.5 px-4 py-3 rounded-[var(--radius-lg)] mb-5"
            style={{ background: "#FFF4E6", border: "1px solid #FDE0B0" }}>
            <Info size={16} style={{ color: "#B45309", flexShrink: 0, marginTop: 1 }} />
            <p className="text-xs leading-relaxed" style={{ color: "#92400E" }}>
              Only {total_completed} session{total_completed === 1 ? " has" : "s have"} completed so far — percentages
              and averages below can swing sharply with just one or two more submissions. Treat them as early signal,
              not a settled result, until more students finish.
            </p>
          </div>
        )}

        {/* KPI tiles — every color reacts to its own value, never a fixed
            brand color. Malpractice Rate carries its own "review flagged
            students" action rather than a separate, differently-styled
            card next to it — the two used to duplicate the same "N
            flagged" fact in two different visual registers, which read as
            two mismatched widgets rather than one coherent one (found
            live, 2026-08-18). No raw flagged-count hint here either — that
            absolute number is now Dashboard's job (a live alert count);
            this tile's own job is the rate and, in the reason-breakdown
            panel below, the composition. Nor is there a "Completed X/Y"
            tile — that's Dashboard's live-progress framing too; the same
            fact is still here, just as page context (the subtitle above),
            not a duplicated headline KPI (2026-08-18 KPI-overlap audit). */}
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
          <StatTile icon={TrendingUp} label="Average Score" value={average_score_percentage === null ? "—" : `${average_score_percentage}%`}
            color={averageScoreColor(average_score_percentage)} />
          <StatTile icon={Clock} label="Avg Completion Time" value={formatSeconds(average_completion_time_seconds)}
            hint={`of ${exam_duration_minutes} min allowed`} color="#0891B2" />
          <StatTile icon={CheckCircle2} label="Pass Rate" value={`${pass_fail.pass_rate_percentage}%`}
            hint={`cutoff ${pass_fail.cutoff_percentage}% · ${pass_fail.pass_count} passed / ${pass_fail.fail_count} failed`}
            color={passRateColor(pass_fail.pass_rate_percentage)} />
          <StatTile icon={ShieldAlert} label="Malpractice Rate" value={`${malpractice_rate.rate_percentage}%`}
            color={malpracticeColor(malpractice_rate.rate_percentage)}
            action={malpractice_rate.flagged_count > 0 ? {
              label: `Review ${malpractice_rate.flagged_count} flagged student${malpractice_rate.flagged_count === 1 ? "" : "s"}`,
              onClick: () => router.push(`/admin/assessments/results/${assignment_id}?flagged=true`),
            } : undefined} />
        </div>

        {/* items-start: each panel sizes to its own content — without it,
            CSS grid stretches the shorter panel (e.g. Department
            Comparison with just one department) to match its taller
            sibling, leaving a large empty gap that reads as an accident,
            not a deliberate layout (found live, 2026-08-18). */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-5 mb-5 items-start">
          {/* Score distribution */}
          <div className="rounded-[var(--radius-xl)] p-5" style={{ background: "var(--color-surface)", border: "1px solid var(--color-border)" }}>
            <h3 className="text-sm font-semibold mb-1" style={{ color: "var(--color-text)" }}>Score Distribution</h3>
            <p className="text-xs mb-4" style={{ color: "var(--color-text-subtle)" }}>{metric_definitions.score_distribution}</p>
            <HBarChart data={score_distribution} valueKey="count" labelKey="bucket" color="var(--color-accent)" />
          </div>

          {/* Department comparison — sample size shown in the label itself,
              since a 2-student average and a 40-student average aren't the
              same kind of evidence even though the bar looks identical. */}
          <div className="rounded-[var(--radius-xl)] p-5" style={{ background: "var(--color-surface)", border: "1px solid var(--color-border)" }}>
            <h3 className="text-sm font-semibold mb-1" style={{ color: "var(--color-text)" }}>Department Comparison</h3>
            <p className="text-xs mb-4" style={{ color: "var(--color-text-subtle)" }}>{metric_definitions.average_percentage}</p>
            {department_comparison.length === 0 ? (
              <p className="text-sm italic" style={{ color: "var(--color-text-subtle)" }}>No department data available.</p>
            ) : (
              <HBarChart
                data={department_comparison.map(d => ({ ...d, label: `${d.department} (${d.student_count})` }))}
                valueKey="average_percentage" labelKey="label" color="#9333EA" suffix="%"
              />
            )}
          </div>
        </div>

        {/* Set comparison — only meaningful with more than one set to
            compare; a single-set assignment has nothing to check for
            fairness against, so this panel is omitted entirely rather than
            showing a one-bar "comparison." */}
        {set_comparison.length > 1 && (
          <div className="rounded-[var(--radius-xl)] p-5 mb-5" style={{ background: "var(--color-surface)", border: "1px solid var(--color-border)" }}>
            <h3 className="text-sm font-semibold mb-1" style={{ color: "var(--color-text)" }}>Set Fairness Comparison</h3>
            <p className="text-xs mb-4" style={{ color: "var(--color-text-subtle)" }}>
              {metric_definitions.set_comparison} Click a set to see its students&apos; results.
            </p>
            <HBarChart
              data={set_comparison.map(s => ({ ...s, label: `${s.set_label} (${s.student_count})` }))}
              valueKey="average_percentage" labelKey="label" color="#0891B2" suffix="%"
              onBarClick={item => router.push(`/admin/assessments/results/${assignment_id}?set=${encodeURIComponent(String(item.set_label))}`)}
            />
          </div>
        )}

        {/* Malpractice breakdown — only rendered when there's actually
            something flagged to break down; an empty "0 of everything"
            panel would just be decoration. */}
        {malpractice_breakdown.length > 0 && (
          <div className="rounded-[var(--radius-xl)] p-5 mb-5" style={{ background: "var(--color-surface)", border: "1px solid var(--color-border)" }}>
            <h3 className="text-sm font-semibold mb-1" style={{ color: "var(--color-text)" }}>Malpractice Breakdown</h3>
            <p className="text-xs mb-4" style={{ color: "var(--color-text-subtle)" }}>{metric_definitions.malpractice_breakdown}</p>
            <HBarChart
              data={malpractice_breakdown.map(r => ({ ...r, label: MALPRACTICE_REASON_LABELS[r.reason] ?? r.reason }))}
              valueKey="count" labelKey="label" color="#DC2626"
            />
          </div>
        )}

        {/* Per-question difficulty */}
        <div className="rounded-[var(--radius-xl)] p-5 mb-5" style={{ background: "var(--color-surface)", border: "1px solid var(--color-border)" }}>
          <div className="flex items-start justify-between gap-4 flex-wrap mb-1">
            <h3 className="text-sm font-semibold" style={{ color: "var(--color-text)" }}>Per-Question Difficulty</h3>
            {setLabels.length > 1 && (
              <div className="w-full sm:w-44 -mt-1">
                <Select
                  value={selectedSet}
                  onChange={e => setSelectedSet(e.target.value)}
                  options={[{ value: "", label: "All sets" }, ...setLabels.map(s => ({ value: s, label: s }))]}
                />
              </div>
            )}
          </div>
          <p className="text-xs mb-1" style={{ color: "var(--color-text-subtle)" }}>{metric_definitions.percentage_correct}</p>
          <p className="text-xs mb-4 flex items-center gap-1.5" style={{ color: "var(--color-text-subtle)" }}>
            <Clock size={11} /> {metric_definitions.average_seconds_spent}
          </p>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr style={{ borderBottom: "1px solid var(--color-border)" }}>
                  {["Set", "Q#", "Answered", "Correct", "% Correct", "Avg Time", "", ""].map((h, i) => (
                    <th key={i} className="text-left px-3 py-3 text-xs font-semibold uppercase tracking-wider whitespace-nowrap"
                      style={{ color: "var(--color-text-subtle)" }}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {sortedQuestionDifficulty.map(q => {
                  const badge = difficultyBadge(q.percentage_correct);
                  return (
                    <tr key={q.question_id} style={{ borderBottom: "1px solid var(--color-border)" }}>
                      {/* Deliberate color hierarchy, not incidental: Set is
                          a category label (muted, least important), Q# is
                          the row's own identity (primary, semibold),
                          Answered/Correct are supporting counts (muted),
                          % Correct is the one number this whole table
                          exists to show (bold, primary) — every column
                          used to default to the same unstyled color with
                          no visual priority between them. */}
                      <td className="px-3 py-2.5 whitespace-nowrap" style={{ color: "var(--color-text-muted)" }}>{q.set_label}</td>
                      <td className="px-3 py-2.5 whitespace-nowrap font-semibold" style={{ color: "var(--color-text)" }}>{q.question_number}</td>
                      <td className="px-3 py-2.5 whitespace-nowrap" style={{ color: "var(--color-text-muted)" }}>{q.total_answered}</td>
                      <td className="px-3 py-2.5 whitespace-nowrap" style={{ color: "var(--color-text-muted)" }}>{q.correct_count}</td>
                      <td className="px-3 py-2.5 whitespace-nowrap font-bold" style={{ color: "var(--color-text)" }}>
                        {q.percentage_correct === null ? "—" : `${q.percentage_correct}%`}
                      </td>
                      <td className="px-3 py-2.5 whitespace-nowrap" style={{ color: "var(--color-text-muted)" }}>
                        {formatSeconds(q.average_seconds_spent)}
                      </td>
                      <td className="px-3 py-2.5 whitespace-nowrap">
                        {badge && (
                          <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-semibold"
                            style={{ background: badge.bg, color: badge.color }}>
                            {badge.label}
                          </span>
                        )}
                      </td>
                      <td className="px-3 py-2.5 whitespace-nowrap">
                        <Button
                          variant="ghost" size="sm" leftIcon={<Users size={13} />}
                          loading={questionModalLoading === q.question_id}
                          onClick={() => openQuestionResponses(q.question_id)}
                        >
                          Students
                        </Button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      </PageWrapper>

      {/* Per-question drill-down — one question, every student on its set.
          Cross-student counterpart to the Results page's per-student
          Responses modal: that one shows every question for one student,
          this shows every student for one question. */}
      <Modal
        isOpen={!!questionModal}
        onClose={() => setQuestionModal(null)}
        title={questionModal ? `Question ${questionModal.question_number} — ${questionModal.set_label}` : "Question Responses"}
        maxWidth="lg"
      >
        {questionModal && (
          <div>
            <div className="rounded-[var(--radius-lg)] p-4 mb-4" style={{ border: "1px solid var(--color-border)" }}>
              <p className="text-xs font-semibold uppercase tracking-wider mb-2" style={{ color: "var(--color-text-subtle)" }}>
                {questionModal.marks} mark{questionModal.marks === 1 ? "" : "s"}
              </p>
              <p className="text-sm mb-3" style={{ color: "var(--color-text)" }}>{questionModal.question_text}</p>
              <div className="space-y-1.5">
                {questionModal.options.map(opt => (
                  <div key={opt.id} className="flex items-center gap-2 px-3 py-2 rounded-[var(--radius-md)] text-sm"
                    style={opt.is_correct
                      ? { background: "#F0FDF4", border: "1px solid #BBF7D0", color: "#166534" }
                      : { background: "#fff", border: "1px solid var(--color-border)", color: "var(--color-text-muted)" }}>
                    {opt.is_correct && <CheckCircle2 size={13} />}
                    <span className="font-semibold">{opt.label}.</span> {opt.text}
                  </div>
                ))}
              </div>
            </div>

            <div className="max-h-[45vh] overflow-y-auto rounded-[var(--radius-lg)]" style={{ border: "1px solid var(--color-border)" }}>
              <table className="w-full text-sm">
                <thead>
                  <tr style={{ borderBottom: "1px solid var(--color-border)" }}>
                    {["Student", "Dept", "Status", "Answer"].map(h => (
                      <th key={h} className="text-left px-3 py-2 text-xs font-semibold uppercase tracking-wider whitespace-nowrap sticky top-0"
                        style={{ color: "var(--color-text-subtle)", background: "var(--color-surface)" }}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {questionModal.students.map(s => {
                    const selectedLabels = questionModal.options
                      .filter(o => s.selected_option_ids.includes(o.id))
                      .map(o => o.label)
                      .join(", ");
                    return (
                      <tr key={s.student_user_id} style={{ borderBottom: "1px solid var(--color-border)" }}>
                        <td className="px-3 py-2 whitespace-nowrap">
                          <p className="font-medium" style={{ color: "var(--color-text)" }}>{s.student_name}</p>
                          <p className="text-xs" style={{ color: "var(--color-text-subtle)" }}>{s.student_roll_id}</p>
                        </td>
                        <td className="px-3 py-2 whitespace-nowrap" style={{ color: "var(--color-text-muted)" }}>{s.department}</td>
                        <td className="px-3 py-2 whitespace-nowrap capitalize" style={{ color: "var(--color-text-muted)" }}>{s.exam_status}</td>
                        <td className="px-3 py-2 whitespace-nowrap">
                          {!s.answered ? (
                            <span className="text-xs italic" style={{ color: "var(--color-text-subtle)" }}>Not answered</span>
                          ) : (
                            <span className="inline-flex items-center gap-1 text-xs font-semibold" style={{ color: s.is_correct ? "#16A34A" : "#DC2626" }}>
                              {s.is_correct ? <CheckCircle2 size={13} /> : <XCircle size={13} />} {selectedLabels || "—"}
                            </span>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>

            <Pagination
              page={questionModal.current_page}
              totalPages={questionModal.total_pages}
              totalCount={questionModal.count}
              onPageChange={page => openQuestionResponses(questionModal.question_id, page)}
            />
          </div>
        )}
      </Modal>
    </AdminLayout>
  );
}
