"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { ClipboardList, Clock, PlayCircle, CheckCircle2, Hourglass, Ban, History, AlertTriangle } from "lucide-react";
import { StudentLayout } from "@/components/layout/StudentLayout";
import { PageWrapper } from "@/components/layout/PageWrapper";
import { PageHeader } from "@/components/layout/PageHeader";
import { Button } from "@/components/ui/Button";
import { EmptyState } from "@/components/ui/EmptyState";
import { Skeleton } from "@/components/ui/Skeleton";
import { useToast } from "@/components/ui/Toast";
import api, { getErrorMessage } from "@/lib/api";
import type { ApiSuccess, StudentAssignmentListItem } from "@/types";

function formatDateTime(iso: string | null): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleString(undefined, {
    dateStyle: "medium", timeStyle: "short",
  });
}

function StatusPill({ item }: { item: StudentAssignmentListItem }) {
  const completed = item.session_status === "SUBMITTED" || item.session_status === "AUTO_SUBMITTED";

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
        <PlayCircle size={12} /> {item.session_status === "IN_PROGRESS" ? "In progress" : "Live"}
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

export default function StudentAssessmentsPage() {
  const router = useRouter();
  const toast = useToast();

  const [items, setItems] = useState<StudentAssignmentListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState(false);

  // The pre-exam briefing (assessment facts, identity confirmation, admin
  // instructions, system rules, readiness checklist) now lives on the exam
  // page itself (2026-08-27) rather than a modal here — a full page does
  // that content justice, and it means the exact same briefing shows up
  // correctly whether a student arrives via this list or a direct/
  // bookmarked link. That page fetches this assignment's own current
  // session_status fresh on load and decides for itself whether to show
  // the full briefing (never started), a lightweight resume screen
  // (already IN_PROGRESS — re-showing the full briefing would just burn
  // remaining time for no reason), or skip straight through (already
  // finished) — so this click is just a plain navigation either way.
  function handleEnter(item: StudentAssignmentListItem) {
    router.push(`/students/assessments/${item.assignment_id}`);
  }

  // On failure this must not just toast and fall through to "No assessments
  // yet" below — a student reading that during a transient backend hiccup
  // could reasonably conclude they have nothing due and miss a live exam.
  function load() {
    setLoading(true);
    setLoadError(false);
    api.get<ApiSuccess<StudentAssignmentListItem[]>>("/assessments/student/assignments/")
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
          title="Assessments"
          subtitle="Timed exams assigned to you. You can enter once your admin starts the timer."
          rightSlot={
            <Button variant="secondary" leftIcon={<History size={14} />} onClick={() => router.push("/students/assessments/results")}>
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
            title="Couldn't load your assessments"
            subtitle="Something went wrong fetching this — it may be temporary. Try again in a moment."
            action={{ label: "Retry", onClick: load }}
          />
        ) : isEmpty ? (
          <EmptyState
            icon={ClipboardList}
            title="No assessments yet"
            subtitle="Assessments assigned to your batch will appear here automatically."
          />
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {items.map(item => {
              const completed = item.session_status === "SUBMITTED" || item.session_status === "AUTO_SUBMITTED";
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
                    <p className="text-xs mt-2 flex items-center gap-1.5" style={{ color: "var(--color-text-subtle)" }}>
                      <Clock size={11} /> {item.exam_duration_minutes} minutes
                    </p>
                    <p className="text-xs mt-1 flex items-center gap-1.5" style={{ color: "var(--color-text-subtle)" }}>
                      closes {formatDateTime(item.global_expire_time)}
                    </p>
                  </div>
                  {canEnter && (
                    <Button
                      variant="primary"
                      className="mt-auto self-start"
                      onClick={() => handleEnter(item)}
                    >
                      {item.session_status === "IN_PROGRESS" ? "Resume Exam" : "Start Exam"}
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
