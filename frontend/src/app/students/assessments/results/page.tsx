"use client";

import { useEffect, useState } from "react";
import { History, CheckCircle2, XCircle, Clock, AlertTriangle } from "lucide-react";
import { StudentLayout } from "@/components/layout/StudentLayout";
import { PageWrapper } from "@/components/layout/PageWrapper";
import { PageHeader } from "@/components/layout/PageHeader";
import { EmptyState } from "@/components/ui/EmptyState";
import { Skeleton } from "@/components/ui/Skeleton";
import { useToast } from "@/components/ui/Toast";
import api, { getErrorMessage } from "@/lib/api";
import type { ApiSuccess } from "@/types";

interface StudentResultRow {
  assignment_id: string;
  paper_title: string;
  results_visible: boolean;
  score: number | null;
  total_marks: number | null;
  percentage: number | null;
  status: string;
  started_at: string;
  ended_at: string;
  duration_seconds: number;
  pass_cutoff_percentage: number;
  passed: boolean | null;
}

function formatDate(iso: string): string {
  return new Date(iso).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
}

function formatDuration(seconds: number): string {
  const mins = Math.round(seconds / 60);
  if (mins < 60) return `${mins} min`;
  return `${Math.floor(mins / 60)}h ${mins % 60}m`;
}

function PassBadge({ passed }: { passed: boolean | null }) {
  if (passed === null) {
    return (
      <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold" style={{ background: "#F3F4F6", color: "#6B7280" }}>
        Result hidden
      </span>
    );
  }
  return passed ? (
    <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold" style={{ background: "#F0FDF4", color: "#16A34A" }}>
      <CheckCircle2 size={12} /> Passed
    </span>
  ) : (
    <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold" style={{ background: "#FEF2F2", color: "#DC2626" }}>
      <XCircle size={12} /> Not Passed
    </span>
  );
}

const STATUS_LABELS: Record<string, string> = {
  SUBMITTED: "Submitted on time",
  AUTO_SUBMITTED: "Auto-submitted at deadline",
};

export default function StudentPastResultsPage() {
  const toast = useToast();
  const [results, setResults] = useState<StudentResultRow[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState(false);

  // On failure this must not just toast and fall through to "No past
  // results yet" below — that reads as "you haven't completed anything,"
  // not "this failed to load."
  function load() {
    setLoading(true);
    setLoadError(false);
    api.get<ApiSuccess<StudentResultRow[]>>("/assessments/student/results/")
      .then(res => setResults(res.data.data))
      .catch(err => { toast.error(getErrorMessage(err)); setLoadError(true); })
      .finally(() => setLoading(false));
  }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(load, []);

  return (
    <StudentLayout>
      <PageWrapper className="max-w-3xl">
        <PageHeader title="Past Results" subtitle="Every assessment you've completed, with your score and outcome." backHref="/students/assessments" />

        {loading ? (
          <div className="space-y-3">
            {[1, 2, 3].map(i => <Skeleton key={i} className="h-24 w-full rounded-[var(--radius-xl)]" />)}
          </div>
        ) : loadError ? (
          <EmptyState
            icon={AlertTriangle}
            title="Couldn't load your results"
            subtitle="Something went wrong fetching this — it may be temporary. Try again in a moment."
            action={{ label: "Retry", onClick: load }}
          />
        ) : !results || results.length === 0 ? (
          <EmptyState icon={History} title="No past results yet" subtitle="Once you complete an assessment, your score will show up here." />
        ) : (
          <div className="space-y-3">
            {results.map(r => (
              <div
                key={r.assignment_id}
                className="rounded-[var(--radius-xl)] p-5"
                style={{ background: "var(--color-surface)", border: "1px solid var(--color-border)", boxShadow: "var(--shadow-sm)" }}
              >
                <div className="flex items-start justify-between gap-4 flex-wrap">
                  <div className="min-w-0">
                    <div className="mb-2"><PassBadge passed={r.passed} /></div>
                    <h3 className="text-base font-semibold truncate" style={{ color: "var(--color-text)" }}>{r.paper_title}</h3>
                    <p className="text-xs mt-1 flex items-center gap-3 flex-wrap" style={{ color: "var(--color-text-subtle)" }}>
                      <span className="flex items-center gap-1"><Clock size={11} /> {formatDate(r.ended_at)}</span>
                      <span>{STATUS_LABELS[r.status] ?? r.status}</span>
                      <span>Duration: {formatDuration(r.duration_seconds)}</span>
                    </p>
                  </div>
                  <div className="text-right shrink-0">
                    {r.results_visible ? (
                      <>
                        <p className="text-2xl font-bold" style={{ color: "var(--color-text)" }}>{r.score}/{r.total_marks}</p>
                        <p className="text-xs" style={{ color: "var(--color-text-subtle)" }}>{r.percentage}% · cutoff {r.pass_cutoff_percentage}%</p>
                      </>
                    ) : (
                      <p className="text-xs" style={{ color: "var(--color-text-subtle)" }}>Not shared by instructor</p>
                    )}
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </PageWrapper>
    </StudentLayout>
  );
}
