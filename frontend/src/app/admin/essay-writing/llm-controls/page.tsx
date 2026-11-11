"use client";

import { useEffect, useState, useCallback } from "react";
import { Bot, Sparkles, Hash, TrendingUp, AlertTriangle, RefreshCcw } from "lucide-react";
import { AdminLayout } from "@/components/layout/AdminLayout";
import { PageWrapper } from "@/components/layout/PageWrapper";
import { PageHeader } from "@/components/layout/PageHeader";
import { Skeleton } from "@/components/ui/Skeleton";
import { useToast } from "@/components/ui/Toast";
import api, { getErrorMessage } from "@/lib/api";
import type { ApiSuccess, EssayLLMAnalytics } from "@/types";

function StatTile({ icon: Icon, label, value, bg, color }: {
  icon: typeof Bot; label: string; value: React.ReactNode; bg: string; color: string;
}) {
  return (
    <div className="rounded-[var(--radius-lg)] px-4 py-4" style={{ background: "var(--color-surface)", border: "1px solid var(--color-border)" }}>
      <div className="flex items-center gap-2 mb-2">
        <div className="w-7 h-7 rounded-md flex items-center justify-center shrink-0" style={{ background: bg }}>
          <Icon size={14} style={{ color }} />
        </div>
        <p className="text-xs font-medium" style={{ color: "var(--color-text-subtle)" }}>{label}</p>
      </div>
      <p className="text-2xl font-bold" style={{ color: "var(--color-text)" }}>{value}</p>
    </div>
  );
}

export default function AdminLLMControlsPage() {
  const toast = useToast();
  const [data, setData] = useState<EssayLLMAnalytics | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState(false);

  const load = useCallback(() => {
    setLoading(true);
    setLoadError(false);
    api.get<ApiSuccess<EssayLLMAnalytics>>("/essay/admin/llm-controls/analytics/")
      .then(res => setData(res.data.data))
      .catch(err => { toast.error(getErrorMessage(err)); setLoadError(true); })
      .finally(() => setLoading(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(load, [load]);

  return (
    <AdminLayout>
      <PageWrapper>
        <div className="flex items-start justify-between gap-3 mb-5">
          <PageHeader
            title="LLM Controls"
            subtitle="Evaluation pipeline analytics — provider, model, and outcomes."
          />
          <button
            onClick={load}
            className="flex items-center gap-1.5 text-sm px-3 py-1.5 rounded-[var(--radius-md)] cursor-pointer"
            style={{ color: "var(--color-text-subtle)", border: "1px solid var(--color-border)" }}
          >
            <RefreshCcw size={13} /> Refresh
          </button>
        </div>

        {loading ? (
          <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
            {Array.from({ length: 6 }).map((_, i) => <Skeleton key={i} className="h-24 w-full" />)}
          </div>
        ) : loadError || !data ? (
          <p className="text-sm" style={{ color: "var(--color-text-subtle)" }}>Couldn&apos;t load LLM analytics. Please try again.</p>
        ) : (
          <>
            <div className="rounded-[var(--radius-lg)] px-4 py-3 mb-4 flex items-center gap-2 text-sm" style={{ background: "var(--color-surface-subtle)", border: "1px solid var(--color-border)" }}>
              <Bot size={14} style={{ color: "var(--color-text-subtle)" }} />
              <span style={{ color: "var(--color-text-subtle)" }}>Provider:</span>
              <span className="font-semibold" style={{ color: "var(--color-text)" }}>{data.provider}</span>
              <span style={{ color: "var(--color-border-strong)" }}>·</span>
              <span style={{ color: "var(--color-text-subtle)" }}>Model:</span>
              <span className="font-semibold" style={{ color: "var(--color-text)" }}>{data.model}</span>
            </div>

            <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
              <StatTile
                icon={Sparkles} label="Evaluations" value={data.evaluation_count}
                bg="#EFF6FF" color="#2563EB"
              />
              <StatTile
                icon={TrendingUp} label="Average score"
                value={data.average_score !== null ? `${data.average_score}/10` : "—"}
                bg="#F0FDF4" color="#16A34A"
              />
              <StatTile
                icon={AlertTriangle} label="Malformed-response DLQ" value={data.malformed_response_dlq_count}
                bg="#FEF2F2" color="#DC2626"
              />
              <StatTile
                icon={Hash} label="Retrigger requests" value={data.retrigger_count}
                bg="#FFF4E6" color="#E8820C"
              />
            </div>

            <p className="text-xs mt-4" style={{ color: "var(--color-text-subtle)" }}>
              Per-submission retrigger, LLM trace/debug, and manual score override live on each submission&apos;s own detail page under Submissions.
            </p>
          </>
        )}
      </PageWrapper>
    </AdminLayout>
  );
}
