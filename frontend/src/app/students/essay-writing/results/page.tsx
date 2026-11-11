"use client";

import { useEffect, useState } from "react";
import { History, CheckCircle2, Clock, Hourglass, AlertTriangle } from "lucide-react";
import { StudentLayout } from "@/components/layout/StudentLayout";
import { PageWrapper } from "@/components/layout/PageWrapper";
import { PageHeader } from "@/components/layout/PageHeader";
import { EmptyState } from "@/components/ui/EmptyState";
import { Skeleton } from "@/components/ui/Skeleton";
import { useToast } from "@/components/ui/Toast";
import api, { getErrorMessage } from "@/lib/api";
import type { ApiSuccess, StudentEssayResultRow } from "@/types";

// Mirrors students/assessments/results/page.tsx's card-list convention
// (Task 14.1) — same visual/loading/error/empty pattern as the existing
// MCQ-assessment "Past Results" page, adapted to essay-service's own
// data shape (score + written feedback instead of pass/fail + cutoff).
// The score/feedback block itself reuses the admin submission-detail
// page's own established layout (essays/writing/submissions/[id]/page.tsx)
// so a student's own results read consistently with what an admin sees.

function formatDate(iso: string): string {
  return new Date(iso).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
}

const STATUS_LABELS: Record<string, string> = {
  SUBMITTED: "Submitted on time",
  AUTO_SUBMITTED: "Auto-submitted at deadline",
};

// "failed" (the pipeline's own internal bucket name) is deliberately never
// shown as-is — it reads as "you failed," not "grading hit an error."
function ExamStatusBadge({ status }: { status: StudentEssayResultRow["exam_status"] }) {
  if (status === "completed") {
    return (
      <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold" style={{ background: "#F0FDF4", color: "#16A34A" }}>
        <CheckCircle2 size={12} /> Scored
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold" style={{ background: "#FFF4E6", color: "#E8820C" }}>
      <Hourglass size={12} /> Results pending
    </span>
  );
}

function ScoreBlock({ result }: { result: StudentEssayResultRow }) {
  if (result.score === null) {
    // "processing" genuinely resolves on its own, usually within minutes —
    // "failed" means the automated grading permanently gave up and is
    // sitting in an admin-only retry queue until someone manually
    // retriggers it (Phase 12's DLQ module), which could take a while.
    // "check back soon" is a real, false promise for that second case —
    // found during Phase 14's third audit round, a genuine messaging-
    // accuracy gap, not just a missing test.
    const message = result.exam_status === "failed"
      ? "Evaluation is taking longer than expected. If this doesn't update soon, contact your administrator."
      : "Still being evaluated — check back soon.";
    return (
      <div className="rounded-[var(--radius-lg)] p-5" style={{ background: "var(--color-surface)", border: "1px solid var(--color-border)" }}>
        <p className="text-xs font-semibold uppercase tracking-wide mb-2" style={{ color: "var(--color-text-subtle)" }}>Score</p>
        <p className="text-sm" style={{ color: "var(--color-text-subtle)" }}>{message}</p>
      </div>
    );
  }
  return (
    <div className="rounded-[var(--radius-lg)] p-5" style={{ background: "var(--color-surface)", border: "1px solid var(--color-border)" }}>
      <p className="text-xs font-semibold uppercase tracking-wide mb-2" style={{ color: "var(--color-text-subtle)" }}>Score</p>
      <p className="text-3xl font-bold mb-2" style={{ color: "var(--color-text)" }}>
        {result.score}
        <span className="text-base font-medium" style={{ color: "var(--color-text-subtle)" }}>/{result.max_score ?? 10}</span>
      </p>
      {result.is_no_submission && (
        <p className="text-xs mb-2" style={{ color: "var(--color-danger)" }}>No response was submitted for this question.</p>
      )}
      {result.feedback?.overall && (
        <p className="text-sm leading-relaxed" style={{ color: "var(--color-text-subtle)" }}>{result.feedback.overall}</p>
      )}
      {result.feedback?.breakdown && Object.keys(result.feedback.breakdown).length > 0 && (
        <div className="mt-3 pt-3 space-y-2" style={{ borderTop: "1px solid var(--color-border)" }}>
          <p className="text-xs font-semibold uppercase tracking-wide" style={{ color: "var(--color-text-subtle)" }}>Breakdown</p>
          {Object.entries(result.feedback.breakdown).map(([criterion, c]) => (
            <div key={criterion} className="text-xs">
              <div className="flex justify-between">
                <span className="font-medium" style={{ color: "var(--color-text)" }}>{criterion}</span>
                <span style={{ color: "var(--color-text-subtle)" }}>{c.score}/{c.maxScore}</span>
              </div>
              {c.feedback && <p style={{ color: "var(--color-text-subtle)" }}>{c.feedback}</p>}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export default function StudentEssayResultsPage() {
  const toast = useToast();
  const [results, setResults] = useState<StudentEssayResultRow[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState(false);

  // On failure this must not just toast and fall through to "No past
  // results yet" below — that reads as "you haven't completed anything,"
  // not "this failed to load" (same reasoning as the MCQ results page).
  function load() {
    setLoading(true);
    setLoadError(false);
    api.get<ApiSuccess<StudentEssayResultRow[]>>("/essay/student/results/")
      .then(res => setResults(res.data.data))
      .catch(err => { toast.error(getErrorMessage(err)); setLoadError(true); })
      .finally(() => setLoading(false));
  }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(load, []);

  return (
    <StudentLayout>
      <PageWrapper>
        <PageHeader title="Past Results" subtitle="Every essay assessment you've completed, with your score and feedback." backHref="/students/essay-writing" />

        {loading ? (
          <div className="space-y-3">
            {[1, 2, 3].map(i => <Skeleton key={i} className="h-40 w-full rounded-[var(--radius-xl)]" />)}
          </div>
        ) : loadError ? (
          <EmptyState
            icon={AlertTriangle}
            title="Couldn't load your results"
            subtitle="Something went wrong fetching this — it may be temporary. Try again in a moment."
            action={{ label: "Retry", onClick: load }}
          />
        ) : !results || results.length === 0 ? (
          <EmptyState icon={History} title="No past results yet" subtitle="Once you complete an essay assessment, your score and feedback will show up here." />
        ) : (
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            {results.map(r => (
              <div key={r.attempt_id} className="space-y-3">
                <div
                  className="rounded-[var(--radius-xl)] p-5"
                  style={{ background: "var(--color-surface)", border: "1px solid var(--color-border)", boxShadow: "var(--shadow-sm)" }}
                >
                  <div className="mb-2"><ExamStatusBadge status={r.exam_status} /></div>
                  <h3 className="text-base font-semibold truncate" style={{ color: "var(--color-text)" }}>{r.paper_title}</h3>
                  <p className="text-xs mt-1" style={{ color: "var(--color-text-subtle)" }}>{r.set_label}</p>
                  <p className="text-xs mt-2 flex items-center gap-3 flex-wrap" style={{ color: "var(--color-text-subtle)" }}>
                    <span className="flex items-center gap-1"><Clock size={11} /> {formatDate(r.submitted_at ?? r.started_at)}</span>
                    <span>{STATUS_LABELS[r.attempt_status] ?? r.attempt_status}</span>
                  </p>
                </div>
                <ScoreBlock result={r} />
              </div>
            ))}
          </div>
        )}
      </PageWrapper>
    </StudentLayout>
  );
}
