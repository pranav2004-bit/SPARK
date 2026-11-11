"use client";

import { useEffect, useState, useCallback } from "react";
import { useParams } from "next/navigation";
import { Target, Users, FileCheck, ShieldAlert, AlertTriangle, TrendingDown, RefreshCcw } from "lucide-react";
import { AdminLayout } from "@/components/layout/AdminLayout";
import { PageWrapper } from "@/components/layout/PageWrapper";
import { PageHeader } from "@/components/layout/PageHeader";
import { Skeleton } from "@/components/ui/Skeleton";
import { EmptyState } from "@/components/ui/EmptyState";
import { useToast } from "@/components/ui/Toast";
import api, { getErrorMessage } from "@/lib/api";
import type { ApiSuccess, EssayAssignment, EssayAssignmentAnalytics } from "@/types";

// Same hand-rolled CSS horizontal-bar-chart convention as
// admin/assessments/analytics/[assignment_id]/page.tsx's own HBarChart —
// this platform explicitly avoids Recharts (see frontend/AGENTS.md).
// Copied, not imported: that component lives page-local in
// assessment-service's own analytics page (no shared chart component
// exists in this codebase to reuse), so essay-service's own copy is
// deliberately its own local component too, kept visually identical.
function HBarChart({ data, valueKey, labelKey, color = "var(--color-accent)", suffix = "" }: {
  data: Record<string, number | string>[]; valueKey: string; labelKey: string; color?: string; suffix?: string;
}) {
  const max = Math.max(...data.map(d => Number(d[valueKey]) || 0), 1);
  return (
    <div className="space-y-3">
      {data.map((item, i) => {
        const val = Number(item[valueKey]) || 0;
        const pct = Math.max((val / max) * 100, val > 0 ? 3 : 0);
        return (
          <div key={i} className="flex items-center gap-3">
            <div className="w-16 text-xs text-right shrink-0 leading-snug" style={{ color: "var(--color-text-muted)" }}>
              {String(item[labelKey])}
            </div>
            <div className="flex-1 h-6 rounded-full overflow-hidden" style={{ background: "var(--color-surface-secondary)" }}>
              {/* A genuinely zero value renders no inner segment at all —
                  a 0%-width padded div still leaves a stray colored nub,
                  the same bug already found and fixed once in
                  assessment-service's own identical component. */}
              {val > 0 && (
                <div className="h-full flex items-center px-2.5 rounded-full transition-all duration-500 ease-out"
                  style={{ width: `${pct}%`, background: color, minWidth: "2rem" }}>
                  <span className="text-xs font-semibold text-white truncate">{val}{suffix}</span>
                </div>
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
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
        <p className="text-xs font-semibold uppercase tracking-wider" style={{ color: "var(--color-text-subtle)" }}>{label}</p>
      </div>
      <p className="text-2xl font-bold" style={{ color: "var(--color-text)" }}>{value}</p>
      {hint && <p className="text-xs mt-0.5" style={{ color: "var(--color-text-subtle)" }}>{hint}</p>}
    </div>
  );
}

export default function AdminEssayAnalyticsPage() {
  const { assignment_id } = useParams<{ assignment_id: string }>();
  const toast = useToast();

  const [assignment, setAssignment] = useState<EssayAssignment | null>(null);
  const [data, setData] = useState<EssayAssignmentAnalytics | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState(false);

  useEffect(() => {
    api.get<ApiSuccess<EssayAssignment>>(`/essay/admin/assignments/${assignment_id}/`)
      .then(res => setAssignment(res.data.data))
      .catch(() => { /* the header title just falls back to a generic label — the analytics panel below has its own load error handling */ });
  }, [assignment_id]);

  // forceRefresh: true only for an explicit "Refresh" click, not the
  // initial mount — that first load should still benefit from the cache
  // (see AdminEssayAssignmentAnalyticsView's own docstring, essays/views.py,
  // for why a plain click otherwise couldn't actually bypass it).
  const load = useCallback((forceRefresh = false) => {
    setLoading(true);
    setLoadError(false);
    const query = forceRefresh ? "?refresh=true" : "";
    api.get<ApiSuccess<EssayAssignmentAnalytics>>(`/essay/admin/assignments/${assignment_id}/analytics/${query}`)
      .then(res => setData(res.data.data))
      .catch(err => { toast.error(getErrorMessage(err)); setLoadError(true); })
      .finally(() => setLoading(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [assignment_id]);

  useEffect(() => load(), [load]);

  return (
    <AdminLayout>
      <PageWrapper>
        <PageHeader
          title={assignment?.paper_title ?? "Analytics"}
          subtitle="Score distribution and LLM evaluation metrics for this assignment."
          backHref="/admin/essay-writing/analytics"
          rightSlot={
            <button
              onClick={() => load(true)}
              className="flex items-center gap-1.5 text-sm px-3 py-1.5 rounded-[var(--radius-md)] cursor-pointer"
              style={{ color: "var(--color-text-subtle)", border: "1px solid var(--color-border)" }}
            >
              <RefreshCcw size={13} /> Refresh
            </button>
          }
        />

        {loading ? (
          <div className="space-y-4">
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              {Array.from({ length: 4 }).map((_, i) => <Skeleton key={i} className="h-24 w-full" />)}
            </div>
            <Skeleton className="h-64 w-full" />
          </div>
        ) : loadError || !data ? (
          <EmptyState icon={AlertTriangle} title="Couldn't load analytics" subtitle="Please try again." />
        ) : data.total_scored === 0 ? (
          <EmptyState
            icon={Target}
            title="No scored submissions yet"
            subtitle={`${data.total_submitted} of ${data.total_allocated} student(s) have submitted so far — analytics will fill in once the LLM finishes evaluating them.`}
          />
        ) : (
          <>
            <p className="text-xs mb-3" style={{ color: "var(--color-text-subtle)" }}>
              A snapshot from up to 60 seconds ago — generated {new Date(data.generated_at).toLocaleTimeString()}.
            </p>

            <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-5">
              <StatTile icon={Target} label="Average score" value={data.average_score !== null ? `${data.average_score}/10` : "—"} color="#2563EB" />
              <StatTile icon={Users} label="Submitted" value={`${data.total_submitted}/${data.total_allocated}`} color="#16A34A" />
              <StatTile icon={ShieldAlert} label="Plagiarism rate" value={`${data.plagiarism_flag_rate_percentage}%`} color="#D97706" />
              <StatTile icon={FileCheck} label="LLM failure rate" value={`${data.llm_failure_rate_percentage}%`} color="#DC2626" />
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
              <div className="rounded-[var(--radius-xl)] p-5" style={{ background: "var(--color-surface)", border: "1px solid var(--color-border)" }}>
                <p className="text-sm font-semibold mb-4" style={{ color: "var(--color-text)" }}>Score distribution</p>
                <HBarChart
                  data={data.score_distribution.map(b => ({ label: `${b.score}/10`, count: b.count }))}
                  valueKey="count" labelKey="label" color="#2563EB"
                />
              </div>

              <div className="rounded-[var(--radius-xl)] p-5" style={{ background: "var(--color-surface)", border: "1px solid var(--color-border)" }}>
                <p className="text-sm font-semibold mb-4" style={{ color: "var(--color-text)" }}>Average word count by score</p>
                {data.word_count_vs_score.length === 0 ? (
                  <p className="text-sm" style={{ color: "var(--color-text-subtle)" }}>No data yet.</p>
                ) : (
                  <HBarChart
                    data={data.word_count_vs_score.map(p => ({ label: `${p.score}/10`, words: p.average_word_count }))}
                    valueKey="words" labelKey="label" color="#16A34A" suffix=" words"
                  />
                )}
              </div>

              <div className="rounded-[var(--radius-xl)] p-5 lg:col-span-2" style={{ background: "var(--color-surface)", border: "1px solid var(--color-border)" }}>
                <p className="text-sm font-semibold mb-3 flex items-center gap-1.5" style={{ color: "var(--color-text)" }}>
                  <TrendingDown size={14} /> Weakest rubric criterion
                </p>
                {data.weakest_criterion === null ? (
                  <p className="text-sm" style={{ color: "var(--color-text-subtle)" }}>
                    No single criterion is standing out as weak yet — every rubric criterion scored is doing reasonably well.
                  </p>
                ) : (
                  <div className="flex items-center justify-between flex-wrap gap-3">
                    <div>
                      <p className="text-lg font-bold" style={{ color: "var(--color-text)" }}>{data.weakest_criterion.name}</p>
                      <p className="text-xs mt-0.5" style={{ color: "var(--color-text-subtle)" }}>
                        Scored under 60% of its own max in {data.weakest_criterion.weak_count} of {data.weakest_criterion.total_count} appearances.
                      </p>
                    </div>
                    <p className="text-2xl font-bold" style={{ color: "#DC2626" }}>{data.weakest_criterion.weak_rate_percentage}%</p>
                  </div>
                )}
                <p className="text-xs mt-3 pt-3" style={{ color: "var(--color-text-subtle)", borderTop: "1px solid var(--color-border)" }}>
                  {data.metric_definitions.weakest_criterion}
                </p>
              </div>
            </div>
          </>
        )}
      </PageWrapper>
    </AdminLayout>
  );
}
