"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { PenLine, Clock, PlayCircle, CheckCircle2, Hourglass, Ban, AlertTriangle, History } from "lucide-react";
import { StudentLayout } from "@/components/layout/StudentLayout";
import { PageWrapper } from "@/components/layout/PageWrapper";
import { PageHeader } from "@/components/layout/PageHeader";
import { Button } from "@/components/ui/Button";
import { EmptyState } from "@/components/ui/EmptyState";
import { Skeleton } from "@/components/ui/Skeleton";
import { useToast } from "@/components/ui/Toast";
import api, { getErrorMessage } from "@/lib/api";
import type { ApiSuccess, StudentEssayAssignmentListItem } from "@/types";

// Mirrors students/assessments/page.tsx's card-list convention exactly
// (Task 4.4) — same visual/navigation pattern as the existing MCQ
// assessments card, adapted field names (attempt_status instead of
// session_status, no exam_duration_minutes — see EssayAssignment's own
// type comment for why).

function formatDateTime(iso: string | null): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
}

function StatusPill({ item }: { item: StudentEssayAssignmentListItem }) {
  const completed = item.attempt_status === "SUBMITTED" || item.attempt_status === "AUTO_SUBMITTED";

  if (completed) {
    return (
      <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold"
        style={{ background: "#F0FDF4", color: "#16A34A" }}>
        <CheckCircle2 size={12} /> Completed
      </span>
    );
  }
  if (item.status === "SCHEDULED") {
    return (
      <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold"
        style={{ background: "#FFF4E6", color: "#E8820C" }}>
        <Hourglass size={12} /> Not started yet
      </span>
    );
  }
  if (item.status === "LIVE") {
    return (
      <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold"
        style={{ background: "#EFF6FF", color: "#2563EB" }}>
        <PlayCircle size={12} /> {item.attempt_status === "IN_PROGRESS" ? "In progress" : "Live"}
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold"
      style={{ background: "#F3F4F6", color: "#6B7280" }}>
      <Ban size={12} /> Closed
    </span>
  );
}

export default function StudentEssayWritingPage() {
  const router = useRouter();
  const toast = useToast();

  const [items, setItems] = useState<StudentEssayAssignmentListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState(false);

  function handleEnter(item: StudentEssayAssignmentListItem) {
    router.push(`/students/essay-writing/${item.assignment_id}`);
  }

  function load() {
    setLoading(true);
    setLoadError(false);
    api.get<ApiSuccess<StudentEssayAssignmentListItem[]>>("/essay/student/assignments/")
      .then(res => setItems(res.data.data))
      .catch(err => { toast.error(getErrorMessage(err)); setLoadError(true); })
      .finally(() => setLoading(false));
  }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(load, []);

  const isEmpty = !loading && items.length === 0;

  return (
    <StudentLayout>
      <PageWrapper>
        <PageHeader
          title="Essay Writing"
          subtitle="Timed essay assessments assigned to you. You can enter once your admin starts the timer."
          rightSlot={
            <Button variant="secondary" leftIcon={<History size={14} />} onClick={() => router.push("/students/essay-writing/results")}>
              Past Results
            </Button>
          }
        />

        {loading ? (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {[1, 2, 3].map(i => <Skeleton key={i} className="h-44 w-full rounded-[var(--radius-xl)]" />)}
          </div>
        ) : loadError ? (
          <EmptyState
            icon={AlertTriangle}
            title="Couldn't load your essay assessments"
            subtitle="Something went wrong fetching this — it may be temporary. Try again in a moment."
            action={{ label: "Retry", onClick: load }}
          />
        ) : isEmpty ? (
          <EmptyState
            icon={PenLine}
            title="No essay assessments yet"
            subtitle="Essay assessments assigned to your batch will appear here automatically."
          />
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {items.map(item => {
              const completed = item.attempt_status === "SUBMITTED" || item.attempt_status === "AUTO_SUBMITTED";
              const canEnter = item.status === "LIVE" && !completed;
              return (
                <div
                  key={item.assignment_id}
                  className="rounded-[var(--radius-xl)] p-5 flex flex-col gap-4"
                  style={{ background: "var(--color-surface)", border: "1px solid var(--color-border)", boxShadow: "var(--shadow-sm)" }}
                >
                  <div>
                    <div className="mb-2"><StatusPill item={item} /></div>
                    <h3 className="text-base font-semibold leading-snug" style={{ color: "var(--color-text)" }}>{item.paper_title}</h3>
                    {item.time_limit_minutes != null && (
                      <p className="text-xs mt-2 flex items-center gap-1.5" style={{ color: "var(--color-text-subtle)" }}>
                        <Clock size={11} /> {item.time_limit_minutes} minutes
                        {item.word_limit != null && <> · {item.word_limit} word limit</>}
                      </p>
                    )}
                    <p className="text-xs mt-1 flex items-center gap-1.5" style={{ color: "var(--color-text-subtle)" }}>
                      closes {formatDateTime(item.global_expire_time)}
                    </p>
                  </div>
                  {canEnter && (
                    <Button variant="primary" className="mt-auto self-start" onClick={() => handleEnter(item)}>
                      {item.attempt_status === "IN_PROGRESS" ? "Resume" : "Start Writing"}
                    </Button>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </PageWrapper>
    </StudentLayout>
  );
}
