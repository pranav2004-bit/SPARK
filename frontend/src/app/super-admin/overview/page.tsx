"use client";

import { useEffect, useState, useCallback } from "react";
import { Users, Layers, UserCheck, TrendingUp, RefreshCw, ArrowUp, ArrowDown, Minus } from "lucide-react";
import { PageWrapper } from "@/components/layout/PageWrapper";
import { PageHeader } from "@/components/layout/PageHeader";
import api, { getErrorMessage } from "@/lib/api";

// ── Types ──────────────────────────────────────────────────────────────────────

interface OverviewData {
  total_students: number;
  total_batches: number;
  active_admins: number;
  weekly_engagement_pct: number;
  students_change_pct?: number;
  batches_change_pct?: number;
  admins_change_pct?: number;
  engagement_change_pct?: number;
}

// ── Skeleton ───────────────────────────────────────────────────────────────────

function KpiSkeleton() {
  return (
    <div
      className="rounded-2xl p-6 animate-pulse"
      style={{ background: "#fff", border: "1px solid var(--color-border)" }}
    >
      <div className="h-4 rounded-lg w-24 mb-4" style={{ background: "var(--color-surface-secondary)" }} />
      <div className="h-9 rounded-lg w-20 mb-3" style={{ background: "var(--color-surface-secondary)" }} />
      <div className="h-3 rounded-lg w-32" style={{ background: "var(--color-surface-secondary)" }} />
    </div>
  );
}

// ── Trend indicator ────────────────────────────────────────────────────────────

function Trend({ value }: { value?: number }) {
  if (value == null) return null;
  if (value > 0) {
    return (
      <span className="inline-flex items-center gap-0.5 text-xs font-semibold" style={{ color: "var(--color-success)" }}>
        <ArrowUp size={11} />
        {value.toFixed(1)}% vs last week
      </span>
    );
  }
  if (value < 0) {
    return (
      <span className="inline-flex items-center gap-0.5 text-xs font-semibold" style={{ color: "var(--color-danger)" }}>
        <ArrowDown size={11} />
        {Math.abs(value).toFixed(1)}% vs last week
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-0.5 text-xs" style={{ color: "var(--color-text-subtle)" }}>
      <Minus size={11} />
      No change
    </span>
  );
}

// ── KPI Card ───────────────────────────────────────────────────────────────────

interface KpiCardProps {
  label: string;
  value: number | string;
  icon: React.ReactNode;
  trend?: number;
  accent?: boolean;
}

function KpiCard({ label, value, icon, trend, accent }: KpiCardProps) {
  return (
    <div
      className="rounded-2xl p-6 flex flex-col gap-3"
      style={{
        background: accent ? "var(--color-primary)" : "#fff",
        border: `1px solid ${accent ? "transparent" : "var(--color-border)"}`,
        boxShadow: "var(--shadow-sm)",
      }}
    >
      <div className="flex items-center justify-between">
        <span
          className="text-sm font-medium"
          style={{ color: accent ? "rgba(255,255,255,0.65)" : "var(--color-text-muted)" }}
        >
          {label}
        </span>
        <span
          className="w-9 h-9 rounded-xl flex items-center justify-center"
          style={{
            background: accent ? "rgba(255,255,255,0.12)" : "var(--color-accent-light)",
            color: accent ? "#fff" : "var(--color-accent)",
          }}
        >
          {icon}
        </span>
      </div>
      <p
        className="text-4xl font-bold tracking-tight"
        style={{ color: accent ? "#fff" : "var(--color-text)" }}
      >
        {typeof value === "number" ? value.toLocaleString() : value}
      </p>
      {trend != null && (
        <div>
          <Trend value={trend} />
        </div>
      )}
    </div>
  );
}

// ── Page ───────────────────────────────────────────────────────────────────────

export default function SuperAdminOverviewPage() {
  const [data, setData] = useState<OverviewData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const fetchData = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const res = await api.get<{ data: OverviewData }>("/analytics/super-admin/overview/");
      setData(res.data.data);
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchData(); }, [fetchData]);

  return (
    <PageWrapper>
      <PageHeader
        title="Overview"
        subtitle="Platform-wide KPIs"
        rightSlot={
          !loading && (
            <button
              onClick={fetchData}
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
          )
        }
      />

      {/* Error state */}
      {error && (
        <div
          className="rounded-2xl p-6 flex items-center justify-between mb-6"
          style={{ background: "var(--color-danger-bg)", border: "1px solid var(--color-danger)20" }}
        >
          <p className="text-sm" style={{ color: "var(--color-danger)" }}>
            {error}
          </p>
          <button
            onClick={fetchData}
            className="text-sm font-semibold px-4 py-2 rounded-lg transition-all"
            style={{ background: "var(--color-danger)", color: "#fff" }}
          >
            Retry
          </button>
        </div>
      )}

      {/* KPI Grid */}
      <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-5">
        {loading ? (
          <>
            <KpiSkeleton />
            <KpiSkeleton />
            <KpiSkeleton />
            <KpiSkeleton />
          </>
        ) : data ? (
          <>
            <KpiCard
              label="Total Students"
              value={data.total_students ?? 0}
              icon={<Users size={18} />}
              trend={data.students_change_pct}
              accent
            />
            <KpiCard
              label="Total Batches"
              value={data.total_batches ?? 0}
              icon={<Layers size={18} />}
              trend={data.batches_change_pct}
            />
            <KpiCard
              label="Active Admins"
              value={data.active_admins ?? 0}
              icon={<UserCheck size={18} />}
              trend={data.admins_change_pct}
            />
            <KpiCard
              label="Platform Engagement"
              value={`${(data.weekly_engagement_pct ?? 0).toFixed(1)}%`}
              icon={<TrendingUp size={18} />}
              trend={data.engagement_change_pct}
            />
          </>
        ) : !error ? (
          <div className="col-span-4 py-16 text-center" style={{ color: "var(--color-text-muted)" }}>
            No overview data available yet.
          </div>
        ) : null}
      </div>
    </PageWrapper>
  );
}
