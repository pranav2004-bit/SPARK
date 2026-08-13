"use client";

import { useEffect, useState, useCallback } from "react";
import { useParams } from "next/navigation";
import { Download, Users, CheckCircle2, ShieldAlert, TrendingUp } from "lucide-react";
import { AdminLayout } from "@/components/layout/AdminLayout";
import { PageWrapper } from "@/components/layout/PageWrapper";
import { PageHeader } from "@/components/layout/PageHeader";
import { Button } from "@/components/ui/Button";
import { Skeleton } from "@/components/ui/Skeleton";
import { EmptyState } from "@/components/ui/EmptyState";
import { useToast } from "@/components/ui/Toast";
import api, { getErrorMessage } from "@/lib/api";
import type { ApiSuccess } from "@/types";

interface AnalyticsData {
  assignment_id: string;
  total_completed: number;
  score_distribution: { bucket: string; count: number }[];
  pass_fail: { pass_count: number; fail_count: number; pass_rate_percentage: number; cutoff_percentage: number };
  question_difficulty: {
    question_id: string; question_number: number; set_label: string;
    total_answered: number; correct_count: number; percentage_correct: number | null;
  }[];
  department_comparison: { department: string; student_count: number; average_percentage: number }[];
  malpractice_rate: { flagged_count: number; total_count: number; rate_percentage: number };
  metric_definitions: Record<string, string>;
}

// Matches AGENTS.md's "Chart Implementation — CSS + SVG (no Recharts)"
// convention, same visual language as super-admin/analytics/page.tsx's HBarChart.
function HBarChart({ data, valueKey, labelKey, color = "var(--color-accent)", suffix = "" }: {
  data: Record<string, number | string>[]; valueKey: string; labelKey: string; color?: string; suffix?: string;
}) {
  const max = Math.max(...data.map(d => Number(d[valueKey]) || 0), 1);
  return (
    <div className="space-y-2.5">
      {data.map((item, i) => {
        const val = Number(item[valueKey]) || 0;
        const pct = Math.max((val / max) * 100, val > 0 ? 3 : 0);
        return (
          <div key={i} className="flex items-center gap-3">
            <div className="w-20 text-xs text-right shrink-0 truncate" style={{ color: "var(--color-text-muted)" }}>
              {String(item[labelKey])}
            </div>
            <div className="flex-1 h-6 rounded-md overflow-hidden" style={{ background: "var(--color-surface-secondary)" }}>
              <div className="h-full flex items-center px-2 rounded-md transition-all duration-500"
                style={{ width: `${pct}%`, background: color, minWidth: val > 0 ? "2rem" : 0 }}>
                {val > 0 && <span className="text-xs font-semibold text-white truncate">{val}{suffix}</span>}
              </div>
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
        <div className="w-8 h-8 rounded-[var(--radius-md)] flex items-center justify-center" style={{ background: `${color}1A` }}>
          <Icon size={15} style={{ color }} />
        </div>
        <p className="text-xs font-semibold uppercase tracking-wider" style={{ color: "var(--color-text-subtle)" }}>{label}</p>
      </div>
      <p className="text-2xl font-bold" style={{ color: "var(--color-text)" }}>{value}</p>
      {hint && <p className="text-xs mt-0.5" style={{ color: "var(--color-text-subtle)" }}>{hint}</p>}
    </div>
  );
}

export default function AdminAssessmentAnalyticsPage() {
  const { assignment_id } = useParams<{ assignment_id: string }>();
  const toast = useToast();

  const [data, setData] = useState<AnalyticsData | null>(null);
  const [loading, setLoading] = useState(true);
  const [exporting, setExporting] = useState(false);

  const load = useCallback(() => {
    setLoading(true);
    api.get<ApiSuccess<AnalyticsData>>(`/assessments/admin/assignments/${assignment_id}/analytics/`)
      .then(res => setData(res.data.data))
      .catch(err => toast.error(getErrorMessage(err)))
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

  if (loading) {
    return (
      <AdminLayout>
        <PageWrapper className="max-w-6xl">
          <Skeleton className="h-8 w-64 mb-6" />
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 mb-6">
            {[1, 2, 3, 4].map(i => <Skeleton key={i} className="h-24 rounded-[var(--radius-xl)]" />)}
          </div>
          <Skeleton className="h-64 rounded-[var(--radius-xl)]" />
        </PageWrapper>
      </AdminLayout>
    );
  }

  if (!data || data.total_completed === 0) {
    return (
      <AdminLayout>
        <PageWrapper className="max-w-6xl">
          <PageHeader title="Analytics" subtitle="Institution-grade breakdown of this assessment's results." backHref="/admin/assessments/papers" />
          <EmptyState icon={TrendingUp} title="No completed sessions yet"
            subtitle="Analytics will populate once students submit their assessments." />
        </PageWrapper>
      </AdminLayout>
    );
  }

  const { pass_fail, malpractice_rate, department_comparison, score_distribution, question_difficulty, metric_definitions } = data;

  return (
    <AdminLayout>
      <PageWrapper className="max-w-6xl">
        <PageHeader
          title="Analytics"
          subtitle="Institution-grade breakdown of this assessment's results."
          backHref="/admin/assessments/papers"
          rightSlot={
            <Button variant="secondary" leftIcon={<Download size={14} />} loading={exporting} onClick={handleExport}>
              Export CSV
            </Button>
          }
        />

        {/* KPI tiles */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 mb-6">
          <StatTile icon={Users} label="Completed" value={String(data.total_completed)} color="#2563EB" />
          <StatTile icon={CheckCircle2} label="Pass Rate" value={`${pass_fail.pass_rate_percentage}%`}
            hint={`cutoff ${pass_fail.cutoff_percentage}%`} color="#16A34A" />
          <StatTile icon={ShieldAlert} label="Malpractice Rate" value={`${malpractice_rate.rate_percentage}%`}
            hint={`${malpractice_rate.flagged_count} flagged`} color="#DC2626" />
          <StatTile icon={TrendingUp} label="Pass / Fail" value={`${pass_fail.pass_count} / ${pass_fail.fail_count}`} color="#E8820C" />
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-5 mb-5">
          {/* Score distribution */}
          <div className="rounded-[var(--radius-xl)] p-5" style={{ background: "var(--color-surface)", border: "1px solid var(--color-border)" }}>
            <h3 className="text-sm font-semibold mb-1" style={{ color: "var(--color-text)" }}>Score Distribution</h3>
            <p className="text-xs mb-4" style={{ color: "var(--color-text-subtle)" }}>{metric_definitions.score_distribution}</p>
            <HBarChart data={score_distribution} valueKey="count" labelKey="bucket" color="var(--color-accent)" />
          </div>

          {/* Department comparison */}
          <div className="rounded-[var(--radius-xl)] p-5" style={{ background: "var(--color-surface)", border: "1px solid var(--color-border)" }}>
            <h3 className="text-sm font-semibold mb-1" style={{ color: "var(--color-text)" }}>Department Comparison</h3>
            <p className="text-xs mb-4" style={{ color: "var(--color-text-subtle)" }}>{metric_definitions.average_percentage}</p>
            {department_comparison.length === 0 ? (
              <p className="text-sm italic" style={{ color: "var(--color-text-subtle)" }}>No department data available.</p>
            ) : (
              <HBarChart data={department_comparison} valueKey="average_percentage" labelKey="department" color="#9333EA" suffix="%" />
            )}
          </div>
        </div>

        {/* Per-question difficulty */}
        <div className="rounded-[var(--radius-xl)] p-5 mb-5" style={{ background: "var(--color-surface)", border: "1px solid var(--color-border)" }}>
          <h3 className="text-sm font-semibold mb-1" style={{ color: "var(--color-text)" }}>Per-Question Difficulty</h3>
          <p className="text-xs mb-4" style={{ color: "var(--color-text-subtle)" }}>{metric_definitions.percentage_correct}</p>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr style={{ borderBottom: "1px solid var(--color-border)" }}>
                  {["Set", "Q#", "Answered", "Correct", "% Correct"].map(h => (
                    <th key={h} className="text-left px-3 py-2 text-xs font-semibold uppercase tracking-wider whitespace-nowrap"
                      style={{ color: "var(--color-text-subtle)" }}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {question_difficulty.map(q => (
                  <tr key={q.question_id} style={{ borderBottom: "1px solid var(--color-border)" }}>
                    <td className="px-3 py-2 whitespace-nowrap">{q.set_label}</td>
                    <td className="px-3 py-2 whitespace-nowrap">{q.question_number}</td>
                    <td className="px-3 py-2 whitespace-nowrap">{q.total_answered}</td>
                    <td className="px-3 py-2 whitespace-nowrap">{q.correct_count}</td>
                    <td className="px-3 py-2 whitespace-nowrap font-semibold">
                      {q.percentage_correct === null ? "—" : `${q.percentage_correct}%`}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </PageWrapper>
    </AdminLayout>
  );
}
