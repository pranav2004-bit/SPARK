"use client";

import { useEffect, useState, useCallback } from "react";
import { BarChart2, TrendingUp, Award, AlertTriangle, RefreshCw, Calendar } from "lucide-react";
import { PageWrapper } from "@/components/layout/PageWrapper";
import { PageHeader } from "@/components/layout/PageHeader";
import api, { getErrorMessage } from "@/lib/api";

// ── Types ──────────────────────────────────────────────────────────────────────

interface DepartmentStat {
  department: string;
  student_count: number;
  avg_accuracy_pct: number;
  completion_pct: number;
}

interface OverviewData {
  total_students: number;
  weekly_engagement_pct: number;
  resource_views_this_week: number;
  practice_attempts_this_week: number;
  top_performers: TopPerformer[];
  weak_topics: WeakTopic[];
  resource_trend: TrendPoint[];
  practice_trend: TrendPoint[];
}

interface TopPerformer {
  rank: number;
  student_id: string;
  fullname: string;
  accuracy_pct: number;
  attempts: number;
}

interface WeakTopic {
  topic: string;
  avg_accuracy_pct: number;
  attempt_count: number;
}

interface TrendPoint {
  label: string;
  value: number;
}

// ── Chart components (CSS + SVG — no external library required) ────────────────

function HBarChart({
  data,
  valueKey = "value",
  labelKey = "label",
  color = "var(--color-accent)",
}: {
  data: Record<string, number | string>[];
  valueKey?: string;
  labelKey?: string;
  color?: string;
}) {
  const max = Math.max(...data.map((d) => Number(d[valueKey]) || 0), 1);
  return (
    <div className="space-y-3">
      {data.map((item, i) => {
        const val = Number(item[valueKey]) || 0;
        const pct = Math.max((val / max) * 100, 2);
        return (
          <div key={i} className="flex items-center gap-3">
            <div className="w-24 text-xs text-right shrink-0 truncate" style={{ color: "var(--color-text-muted)" }}>
              {String(item[labelKey])}
            </div>
            <div className="flex-1 h-7 rounded-lg overflow-hidden" style={{ background: "var(--color-surface-secondary)" }}>
              <div
                className="h-full flex items-center px-2.5 rounded-lg transition-all duration-700"
                style={{ width: `${pct}%`, background: color, minWidth: "2.5rem" }}
              >
                <span className="text-xs font-semibold text-white truncate">{val.toFixed(1)}</span>
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
}

function LineChart({
  data,
  color = "var(--color-accent)",
  unit = "",
}: {
  data: TrendPoint[];
  color?: string;
  unit?: string;
}) {
  if (!data || data.length < 2) {
    return (
      <div className="h-40 flex items-center justify-center text-sm" style={{ color: "var(--color-text-subtle)" }}>
        Not enough data to plot
      </div>
    );
  }

  const W = 560;
  const H = 160;
  const PAD_X = 8;
  const PAD_Y = 16;

  const vals = data.map((d) => d.value);
  const max = Math.max(...vals, 1);
  const min = Math.min(...vals, 0);
  const range = max - min || 1;

  const pts = data.map((d, i) => ({
    x: PAD_X + (i / (data.length - 1)) * (W - PAD_X * 2),
    y: PAD_Y + (1 - (d.value - min) / range) * (H - PAD_Y * 2),
    label: d.label,
    value: d.value,
  }));

  const linePath = pts.map((p, i) => `${i === 0 ? "M" : "L"} ${p.x} ${p.y}`).join(" ");
  const areaPath = `${linePath} L ${pts[pts.length - 1].x} ${H - PAD_Y} L ${pts[0].x} ${H - PAD_Y} Z`;

  const gradId = `grad-${color.replace(/[^a-zA-Z0-9]/g, "")}`;

  return (
    <svg viewBox={`0 0 ${W} ${H + 20}`} className="w-full" style={{ overflow: "visible" }}>
      <defs>
        <linearGradient id={gradId} x1="0" x2="0" y1="0" y2="1">
          <stop offset="0%" stopColor={color} stopOpacity="0.18" />
          <stop offset="100%" stopColor={color} stopOpacity="0.02" />
        </linearGradient>
      </defs>

      {/* Grid lines */}
      {[0, 0.33, 0.67, 1].map((t) => (
        <line
          key={t}
          x1={PAD_X}
          y1={PAD_Y + t * (H - PAD_Y * 2)}
          x2={W - PAD_X}
          y2={PAD_Y + t * (H - PAD_Y * 2)}
          stroke="var(--color-border)"
          strokeWidth="1"
          strokeDasharray="3,4"
        />
      ))}

      {/* Area */}
      <path d={areaPath} fill={`url(#${gradId})`} />

      {/* Line */}
      <path
        d={linePath}
        fill="none"
        stroke={color}
        strokeWidth="2.5"
        strokeLinejoin="round"
        strokeLinecap="round"
      />

      {/* Data points */}
      {pts.map((p, i) => (
        <g key={i}>
          <circle cx={p.x} cy={p.y} r="5" fill="white" stroke={color} strokeWidth="2.5" />
          {/* X labels */}
          <text
            x={p.x}
            y={H + 14}
            textAnchor="middle"
            fontSize="10"
            fill="var(--color-text-muted)"
          >
            {p.label}
          </text>
        </g>
      ))}
    </svg>
  );
}

// ── Skeleton ───────────────────────────────────────────────────────────────────

function ChartSkeleton({ height = "h-40" }: { height?: string }) {
  return (
    <div
      className={`${height} rounded-xl animate-pulse`}
      style={{ background: "var(--color-surface-secondary)" }}
    />
  );
}

// ── Chart card wrapper ─────────────────────────────────────────────────────────

function ChartCard({
  title,
  subtitle,
  children,
  headerRight,
}: {
  title: string;
  subtitle?: string;
  children: React.ReactNode;
  headerRight?: React.ReactNode;
}) {
  return (
    <div
      className="rounded-2xl p-6"
      style={{ background: "#fff", border: "1px solid var(--color-border)", boxShadow: "var(--shadow-sm)" }}
    >
      <div className="flex items-start justify-between mb-5">
        <div>
          <h3 className="text-sm font-semibold" style={{ color: "var(--color-text)" }}>{title}</h3>
          {subtitle && (
            <p className="text-xs mt-0.5" style={{ color: "var(--color-text-muted)" }}>{subtitle}</p>
          )}
        </div>
        {headerRight}
      </div>
      {children}
    </div>
  );
}

// ── Error state ────────────────────────────────────────────────────────────────

function ChartError({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div className="h-40 flex flex-col items-center justify-center gap-3">
      <AlertTriangle size={20} style={{ color: "var(--color-danger)" }} />
      <p className="text-xs text-center max-w-xs" style={{ color: "var(--color-text-muted)" }}>{message}</p>
      {onRetry && (
        <button
          onClick={onRetry}
          className="text-xs font-semibold px-3 py-1.5 rounded-lg transition-all"
          style={{ background: "var(--color-accent-light)", color: "var(--color-accent)" }}
        >
          Retry
        </button>
      )}
    </div>
  );
}

// ── Page ───────────────────────────────────────────────────────────────────────

export default function SuperAdminAnalyticsPage() {
  const [overview, setOverview] = useState<OverviewData | null>(null);
  const [departments, setDepartments] = useState<DepartmentStat[]>([]);
  const [loadingOverview, setLoadingOverview] = useState(true);
  const [loadingDepts, setLoadingDepts] = useState(true);
  const [errorOverview, setErrorOverview] = useState("");
  const [errorDepts, setErrorDepts] = useState("");
  const [trendPeriod, setTrendPeriod] = useState<"weekly" | "monthly">("weekly");

  const fetchOverview = useCallback(async () => {
    setLoadingOverview(true);
    setErrorOverview("");
    try {
      const res = await api.get<{ data: OverviewData }>("/analytics/super-admin/overview/");
      setOverview(res.data.data);
    } catch (err) {
      setErrorOverview(getErrorMessage(err));
    } finally {
      setLoadingOverview(false);
    }
  }, []);

  const fetchDepartments = useCallback(async () => {
    setLoadingDepts(true);
    setErrorDepts("");
    try {
      const res = await api.get<{ data: DepartmentStat[] }>("/analytics/super-admin/departments/");
      setDepartments(res.data.data ?? []);
    } catch (err) {
      setErrorDepts(getErrorMessage(err));
    } finally {
      setLoadingDepts(false);
    }
  }, []);

  useEffect(() => {
    fetchOverview();
    fetchDepartments();
  }, [fetchOverview, fetchDepartments]);

  const deptAccuracy = departments.map((d) => ({
    label: d.department,
    value: d.avg_accuracy_pct ?? 0,
  }));

  const deptStudents = departments.map((d) => ({
    label: d.department,
    value: d.student_count ?? 0,
  }));

  const trendData =
    trendPeriod === "weekly"
      ? overview?.practice_trend ?? []
      : overview?.practice_trend ?? [];

  return (
    <PageWrapper>
      <PageHeader
        title="Analytics"
        subtitle="Departmental performance and platform engagement"
        rightSlot={
          <button
            onClick={() => { fetchOverview(); fetchDepartments(); }}
            className="inline-flex items-center gap-1.5 px-3 py-2 rounded-lg text-xs font-medium transition-all"
            style={{
              background: "var(--color-surface-secondary)",
              color: "var(--color-text-muted)",
              border: "1px solid var(--color-border)",
            }}
          >
            <RefreshCw size={12} />
            Refresh
          </button>
        }
      />

      <div className="space-y-6">

        {/* Row 1 — Department performance */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">

          <ChartCard
            title="Department — Practice Accuracy"
            subtitle="Average accuracy % per department"
          >
            {loadingDepts ? (
              <ChartSkeleton />
            ) : errorDepts ? (
              <ChartError message={errorDepts} onRetry={fetchDepartments} />
            ) : deptAccuracy.length === 0 ? (
              <div className="h-40 flex items-center justify-center text-sm" style={{ color: "var(--color-text-subtle)" }}>
                No department data available
              </div>
            ) : (
              <HBarChart data={deptAccuracy} valueKey="value" labelKey="label" />
            )}
          </ChartCard>

          <ChartCard
            title="Department — Student Count"
            subtitle="Total enrolled students per department"
          >
            {loadingDepts ? (
              <ChartSkeleton />
            ) : errorDepts ? (
              <ChartError message={errorDepts} onRetry={fetchDepartments} />
            ) : deptStudents.length === 0 ? (
              <div className="h-40 flex items-center justify-center text-sm" style={{ color: "var(--color-text-subtle)" }}>
                No data available
              </div>
            ) : (
              <HBarChart
                data={deptStudents}
                valueKey="value"
                labelKey="label"
                color="var(--color-primary)"
              />
            )}
          </ChartCard>
        </div>

        {/* Row 2 — Trend charts */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">

          <ChartCard
            title="Resource Utilisation"
            subtitle="Resource views over time"
          >
            {loadingOverview ? (
              <ChartSkeleton />
            ) : errorOverview ? (
              <ChartError message={errorOverview} onRetry={fetchOverview} />
            ) : (
              <LineChart
                data={overview?.resource_trend ?? []}
                color="var(--color-primary)"
              />
            )}
          </ChartCard>

          <ChartCard
            title="Practice Engagement Trend"
            subtitle="Practice attempts over time"
            headerRight={
              <div className="flex items-center gap-1 rounded-lg overflow-hidden" style={{ border: "1px solid var(--color-border)" }}>
                {(["weekly", "monthly"] as const).map((p) => (
                  <button
                    key={p}
                    onClick={() => setTrendPeriod(p)}
                    className="px-3 py-1 text-xs font-medium transition-all capitalize"
                    style={{
                      background: trendPeriod === p ? "var(--color-primary)" : "transparent",
                      color: trendPeriod === p ? "#fff" : "var(--color-text-muted)",
                    }}
                  >
                    {p}
                  </button>
                ))}
              </div>
            }
          >
            {loadingOverview ? (
              <ChartSkeleton />
            ) : errorOverview ? (
              <ChartError message={errorOverview} onRetry={fetchOverview} />
            ) : (
              <LineChart data={trendData} color="var(--color-accent)" />
            )}
          </ChartCard>
        </div>

        {/* Row 3 — Tables */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">

          {/* Top performers */}
          <ChartCard
            title="Top Performers"
            subtitle="Top 10 students by accuracy"
          >
            {loadingOverview ? (
              <ChartSkeleton height="h-64" />
            ) : errorOverview ? (
              <ChartError message={errorOverview} onRetry={fetchOverview} />
            ) : !overview?.top_performers?.length ? (
              <div className="py-10 text-center text-sm" style={{ color: "var(--color-text-subtle)" }}>
                No performance data yet
              </div>
            ) : (
              <div className="space-y-2">
                {overview.top_performers.slice(0, 10).map((p) => (
                  <div
                    key={p.student_id}
                    className="flex items-center gap-3 px-3 py-2.5 rounded-xl"
                    style={{ background: "var(--color-surface-secondary)" }}
                  >
                    <span
                      className="flex items-center justify-center w-7 h-7 rounded-full text-xs font-bold shrink-0"
                      style={{
                        background: p.rank <= 3 ? "var(--color-accent)" : "var(--color-primary-light)",
                        color: p.rank <= 3 ? "#fff" : "var(--color-primary)",
                      }}
                    >
                      {p.rank}
                    </span>
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-semibold truncate" style={{ color: "var(--color-text)" }}>
                        {p.fullname || p.student_id}
                      </p>
                      <p className="text-xs" style={{ color: "var(--color-text-subtle)" }}>
                        {p.attempts} attempts
                      </p>
                    </div>
                    <span
                      className="text-sm font-bold shrink-0"
                      style={{ color: p.accuracy_pct >= 80 ? "var(--color-success)" : "var(--color-accent)" }}
                    >
                      {(p.accuracy_pct ?? 0).toFixed(1)}%
                    </span>
                  </div>
                ))}
              </div>
            )}
          </ChartCard>

          {/* Weak topics */}
          <ChartCard
            title="Weak Topics"
            subtitle="Topics with <50% average accuracy"
          >
            {loadingOverview ? (
              <ChartSkeleton height="h-64" />
            ) : errorOverview ? (
              <ChartError message={errorOverview} onRetry={fetchOverview} />
            ) : !overview?.weak_topics?.length ? (
              <div className="py-10 text-center">
                <Award size={28} className="mx-auto mb-2" style={{ color: "var(--color-success)" }} />
                <p className="text-sm font-semibold" style={{ color: "var(--color-success)" }}>
                  No weak topics — great job!
                </p>
                <p className="text-xs mt-1" style={{ color: "var(--color-text-subtle)" }}>
                  All topics are above 50% accuracy.
                </p>
              </div>
            ) : (
              <div className="space-y-2">
                {overview.weak_topics.map((t, i) => (
                  <div
                    key={i}
                    className="flex items-center gap-3 px-3 py-2.5 rounded-xl"
                    style={{ background: "var(--color-danger-bg)" }}
                  >
                    <AlertTriangle size={15} style={{ color: "var(--color-danger)", flexShrink: 0 }} />
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-semibold truncate" style={{ color: "var(--color-text)" }}>
                        {t.topic}
                      </p>
                      <p className="text-xs" style={{ color: "var(--color-text-subtle)" }}>
                        {t.attempt_count} attempts
                      </p>
                    </div>
                    <span
                      className="text-sm font-bold shrink-0"
                      style={{ color: "var(--color-danger)" }}
                    >
                      {(t.avg_accuracy_pct ?? 0).toFixed(1)}%
                    </span>
                  </div>
                ))}
              </div>
            )}
          </ChartCard>
        </div>

      </div>
    </PageWrapper>
  );
}
