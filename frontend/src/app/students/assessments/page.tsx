"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { ClipboardList, Clock, PlayCircle, CheckCircle2, Hourglass, Ban, History, AlertTriangle } from "lucide-react";
import { StudentLayout } from "@/components/layout/StudentLayout";
import { PageWrapper } from "@/components/layout/PageWrapper";
import { PageHeader } from "@/components/layout/PageHeader";
import { Button } from "@/components/ui/Button";
import { EmptyState } from "@/components/ui/EmptyState";
import { Modal } from "@/components/ui/Modal";
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
  const [rulesGate, setRulesGate] = useState<StudentAssignmentListItem | null>(null);
  const [rulesAgreed, setRulesAgreed] = useState(false);

  function handleEnter(item: StudentAssignmentListItem) {
    // Resuming an already-started session skips the gate entirely — the
    // student's timer is already running, re-showing rules would just
    // burn their remaining time for no reason. Only a brand-new start
    // (never opened this session before), and only if the admin actually
    // set rules text, shows the gate first.
    if (item.session_status === "IN_PROGRESS" || !item.paper_instructions.trim()) {
      router.push(`/students/assessments/${item.assignment_id}`);
      return;
    }
    setRulesAgreed(false);
    setRulesGate(item);
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
      <PageWrapper className="max-w-3xl">
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
          <div className="space-y-3">
            {[1, 2].map(i => <Skeleton key={i} className="h-24 w-full rounded-[var(--radius-xl)]" />)}
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
          <div className="space-y-3">
            {items.map(item => {
              const completed = item.session_status === "SUBMITTED" || item.session_status === "AUTO_SUBMITTED";
              const canEnter = item.status === "LIVE" && !completed;
              return (
                <div
                  key={item.assignment_id}
                  className="rounded-[var(--radius-xl)] p-5"
                  style={{ background: "var(--color-surface)", border: "1px solid var(--color-border)", boxShadow: "var(--shadow-sm)" }}
                >
                  <div className="flex items-start justify-between gap-4 flex-wrap">
                    <div>
                      <div className="mb-2"><StatusPill item={item} /></div>
                      <h3 className="text-base font-semibold" style={{ color: "var(--color-text)" }}>{item.paper_title}</h3>
                      <p className="text-xs mt-1 flex items-center gap-1.5" style={{ color: "var(--color-text-subtle)" }}>
                        <Clock size={11} /> {item.exam_duration_minutes} minutes · closes {formatDateTime(item.global_expire_time)}
                      </p>
                    </div>
                    {canEnter && (
                      <Button
                        variant="primary"
                        onClick={() => handleEnter(item)}
                      >
                        {item.session_status === "IN_PROGRESS" ? "Resume Exam" : "Start Exam"}
                      </Button>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </PageWrapper>

      <Modal
        isOpen={rulesGate !== null}
        onClose={() => setRulesGate(null)}
        title="Before you start"
        maxWidth="lg"
      >
        {rulesGate && (
          <>
            <p className="text-sm font-semibold mb-2" style={{ color: "var(--color-text)" }}>{rulesGate.paper_title}</p>
            <div
              className="text-sm leading-relaxed whitespace-pre-wrap max-h-72 overflow-y-auto p-4 rounded-[var(--radius-md)] mb-4"
              style={{ background: "var(--color-surface)", border: "1px solid var(--color-border)", color: "var(--color-text-muted)" }}
            >
              {rulesGate.paper_instructions}
            </div>
            <label className="flex items-start gap-2.5 cursor-pointer select-none">
              <input
                type="checkbox"
                checked={rulesAgreed}
                onChange={e => setRulesAgreed(e.target.checked)}
                className="mt-0.5 h-4 w-4 shrink-0 rounded border-[var(--color-border)] text-[var(--color-accent)] focus:ring-[var(--color-accent)]"
              />
              <span className="text-sm" style={{ color: "var(--color-text)" }}>
                I have read all the instructions above.
              </span>
            </label>
            <div className="flex justify-end gap-3 mt-5">
              <Button variant="secondary" type="button" onClick={() => setRulesGate(null)}>Cancel</Button>
              <Button
                type="button"
                disabled={!rulesAgreed}
                onClick={() => router.push(`/students/assessments/${rulesGate.assignment_id}`)}
              >
                Start Exam
              </Button>
            </div>
          </>
        )}
      </Modal>
    </StudentLayout>
  );
}
