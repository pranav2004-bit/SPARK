"use client";

import { useEffect, useState, useCallback } from "react";
import { useParams, useRouter } from "next/navigation";
import { PlayCircle, StopCircle, RefreshCcw, Users, Clock, CheckCircle2, FileText, TrendingUp, LayoutDashboard } from "lucide-react";
import { AdminLayout } from "@/components/layout/AdminLayout";
import { PageWrapper } from "@/components/layout/PageWrapper";
import { PageHeader } from "@/components/layout/PageHeader";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import { Skeleton } from "@/components/ui/Skeleton";
import { useToast } from "@/components/ui/Toast";
import api, { getErrorMessage } from "@/lib/api";
import type {
  QuestionPaper, Batch, BatchAssignment, BatchAssignmentStatusPoll, ApiSuccess, PaginatedResponse,
} from "@/types";

const STATUS_STYLES: Record<string, { bg: string; color: string; label: string }> = {
  SCHEDULED: { bg: "#FFF4E6", color: "#E8820C", label: "Scheduled" },
  LIVE:      { bg: "#F0FDF4", color: "#16A34A", label: "Live" },
  CLOSED:    { bg: "#F3F4F6", color: "#6B7280", label: "Closed" },
};

function StatusBadge({ status }: { status: string }) {
  const s = STATUS_STYLES[status] ?? STATUS_STYLES.SCHEDULED;
  return (
    <span
      className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold"
      style={{ background: s.bg, color: s.color }}
    >
      <span className="w-1.5 h-1.5 rounded-full" style={{ background: s.color }} />
      {s.label}
    </span>
  );
}

export default function AdminAssessmentAssignPage() {
  const { paper_id } = useParams<{ paper_id: string }>();
  const router = useRouter();
  const toast = useToast();

  const [paper, setPaper] = useState<QuestionPaper | null>(null);
  const [batches, setBatches] = useState<Batch[]>([]);
  const [assignments, setAssignments] = useState<BatchAssignment[]>([]);
  const [statusByAssignment, setStatusByAssignment] = useState<Record<string, BatchAssignmentStatusPoll>>({});
  const [loading, setLoading] = useState(true);

  const [batchId, setBatchId] = useState("");
  const [duration, setDuration] = useState("60");
  const [startTime, setStartTime] = useState("");
  const [expireTime, setExpireTime] = useState("");
  const [passCutoff, setPassCutoff] = useState("40");
  const [creating, setCreating] = useState(false);
  const [formError, setFormError] = useState("");

  const [confirmStart, setConfirmStart] = useState<BatchAssignment | null>(null);
  const [confirmClose, setConfirmClose] = useState<BatchAssignment | null>(null);
  const [actingOn, setActingOn] = useState<string | null>(null);
  const [resyncingId, setResyncingId] = useState<string | null>(null);

  const load = useCallback(() => {
    Promise.all([
      api.get<ApiSuccess<{ paper: QuestionPaper }>>(`/assessments/admin/papers/${paper_id}/`),
      api.get<ApiSuccess<Batch[]>>("/users/batches/"),
      api.get<PaginatedResponse<BatchAssignment>>(`/assessments/admin/assignments/?paper_id=${paper_id}`),
    ])
      .then(([paperRes, batchesRes, assignRes]) => {
        setPaper(paperRes.data.data.paper);
        setBatches(batchesRes.data.data);
        setAssignments(assignRes.data.results);
      })
      .catch(err => { toast.error(getErrorMessage(err)); router.push("/admin/assessments/papers"); })
      .finally(() => setLoading(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [paper_id]);

  useEffect(load, [load]);

  // Poll every non-CLOSED assignment's live status widget — CLOSED is
  // terminal so there's nothing left to change; polling it forever would
  // just waste requests.
  const pollingIds = assignments.filter(a => a.status !== "CLOSED").map(a => a.id).join(",");
  useEffect(() => {
    if (!pollingIds) return;
    const ids = pollingIds.split(",");
    const poll = () => {
      ids.forEach(id => {
        api.get<ApiSuccess<BatchAssignmentStatusPoll>>(`/assessments/admin/assignments/${id}/status/`)
          .then(res => setStatusByAssignment(prev => ({ ...prev, [id]: res.data.data })))
          .catch(() => {});
      });
    };
    poll();
    const interval = setInterval(poll, 8000);
    return () => clearInterval(interval);
  }, [pollingIds]);

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    setFormError("");
    if (!batchId) { setFormError("Select a batch."); return; }
    if (!expireTime) { setFormError("Global expire time is required."); return; }
    const durationNum = Number(duration);
    if (!durationNum || durationNum <= 0) { setFormError("Exam duration must be a positive number of minutes."); return; }

    const payload: Record<string, unknown> = {
      paper: paper_id,
      batch_id: batchId,
      global_expire_time: new Date(expireTime).toISOString(),
      exam_duration_minutes: durationNum,
      pass_cutoff_percentage: Number(passCutoff) || 40,
    };
    if (startTime) payload.global_start_time = new Date(startTime).toISOString();

    setCreating(true);
    try {
      const res = await api.post<ApiSuccess<BatchAssignment>>("/assessments/admin/assignments/", payload);
      setAssignments(prev => [res.data.data, ...prev]);
      setBatchId(""); setStartTime(""); setExpireTime(""); setDuration("60"); setPassCutoff("40");
      toast.success("Assignment created.");
    } catch (err) {
      setFormError(getErrorMessage(err));
    } finally {
      setCreating(false);
    }
  }

  async function handleStart(assignment: BatchAssignment) {
    setActingOn(assignment.id);
    try {
      const res = await api.patch<ApiSuccess<BatchAssignment>>(`/assessments/admin/assignments/${assignment.id}/start/`);
      setAssignments(prev => prev.map(a => a.id === assignment.id ? res.data.data : a));
      toast.success("Exam started — the global timer is now live.");
    } catch (err) {
      toast.error(getErrorMessage(err));
    } finally {
      setActingOn(null);
      setConfirmStart(null);
    }
  }

  async function handleClose(assignment: BatchAssignment) {
    setActingOn(assignment.id);
    try {
      const res = await api.patch<ApiSuccess<BatchAssignment>>(`/assessments/admin/assignments/${assignment.id}/close/`);
      setAssignments(prev => prev.map(a => a.id === assignment.id ? res.data.data : a));
      toast.success("Exam closed.");
    } catch (err) {
      toast.error(getErrorMessage(err));
    } finally {
      setActingOn(null);
      setConfirmClose(null);
    }
  }

  async function handleResync(assignment: BatchAssignment) {
    setResyncingId(assignment.id);
    try {
      const res = await api.post<ApiSuccess<{ new_allocations: number }>>(
        `/assessments/admin/assignments/${assignment.id}/resync-roster/`
      );
      toast.success(
        res.data.data.new_allocations > 0
          ? `${res.data.data.new_allocations} new student(s) allocated.`
          : "Roster already up to date."
      );
    } catch (err) {
      toast.error(getErrorMessage(err));
    } finally {
      setResyncingId(null);
    }
  }

  const batchName = (id: string) => batches.find(b => b.id === id)?.batch_name ?? id;

  return (
    <AdminLayout>
      <PageWrapper className="max-w-4xl">
        <PageHeader
          title={paper ? `Assign — ${paper.title}` : ""}
          titleSkeleton={loading ? <Skeleton className="h-8 w-64" /> : undefined}
          subtitle="Assign this paper to a batch, then manually start the global exam timer when ready."
          backHref={`/admin/assessments/papers/${paper_id}`}
        />

        {!loading && paper && !paper.is_published && (
          <div
            className="mb-5 px-4 py-3 rounded-[var(--radius-lg)] text-sm"
            style={{ background: "#FFF4E6", color: "#B45309", border: "1px solid #FDE0B0" }}
          >
            This paper isn&apos;t published yet. You can create an assignment now, but starting the exam
            will be rejected until the paper is published.
          </div>
        )}

        {/* Create assignment form */}
        <div
          className="rounded-[var(--radius-xl)] p-5 mb-6"
          style={{ background: "var(--color-surface)", border: "1px solid var(--color-border)", boxShadow: "var(--shadow-sm)" }}
        >
          <h3 className="text-sm font-semibold mb-4" style={{ color: "var(--color-text)" }}>New assignment</h3>
          <form onSubmit={handleCreate} className="space-y-4">
            <div>
              <label className="block text-xs font-medium mb-1.5" style={{ color: "var(--color-text-muted)" }}>Batch</label>
              <select
                value={batchId}
                onChange={e => setBatchId(e.target.value)}
                className="w-full h-9 px-3 rounded-[var(--radius-md)] text-sm"
                style={{ border: "1px solid var(--color-border)", background: "var(--color-surface)", color: "var(--color-text)" }}
              >
                <option value="">Select a batch…</option>
                {batches.map(b => (
                  <option key={b.id} value={b.id}>
                    {b.batch_name} {typeof b.student_count === "number" ? `(${b.student_count} students)` : ""}
                  </option>
                ))}
              </select>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
              <Input
                label="Exam duration (minutes)"
                type="number"
                min={1}
                value={duration}
                onChange={e => setDuration(e.target.value)}
              />
              <Input
                label="Global start time (optional)"
                type="datetime-local"
                value={startTime}
                onChange={e => setStartTime(e.target.value)}
              />
              <Input
                label="Global expire time"
                type="datetime-local"
                value={expireTime}
                onChange={e => setExpireTime(e.target.value)}
              />
            </div>

            <Input
              label="Pass cutoff (%)"
              type="number"
              min={0}
              max={100}
              value={passCutoff}
              onChange={e => setPassCutoff(e.target.value)}
              className="max-w-[160px]"
            />

            {formError && <p className="text-xs" style={{ color: "var(--color-danger)" }}>{formError}</p>}

            <div className="flex justify-end">
              <Button type="submit" loading={creating}>Create assignment</Button>
            </div>
          </form>
        </div>

        {/* Existing assignments */}
        <h3 className="text-sm font-semibold mb-3" style={{ color: "var(--color-text)" }}>Assignments</h3>
        {loading ? (
          <Skeleton className="h-24 w-full rounded-[var(--radius-xl)]" />
        ) : assignments.length === 0 ? (
          <p className="text-sm" style={{ color: "var(--color-text-subtle)" }}>No assignments yet for this paper.</p>
        ) : (
          <div className="space-y-3">
            {assignments.map(a => {
              const poll = statusByAssignment[a.id];
              return (
                <div
                  key={a.id}
                  className="rounded-[var(--radius-xl)] p-4"
                  style={{ background: "var(--color-surface)", border: "1px solid var(--color-border)", boxShadow: "var(--shadow-sm)" }}
                >
                  <div className="flex items-start justify-between gap-3 flex-wrap">
                    <div>
                      <div className="flex items-center gap-2 mb-1">
                        <StatusBadge status={poll?.status ?? a.status} />
                        <span className="text-sm font-medium" style={{ color: "var(--color-text)" }}>{batchName(a.batch_id)}</span>
                      </div>
                      <p className="text-xs flex items-center gap-3 flex-wrap" style={{ color: "var(--color-text-subtle)" }}>
                        <span className="flex items-center gap-1"><Clock size={11} /> {a.exam_duration_minutes} min</span>
                        <span className="flex items-center gap-1">
                          <Users size={11} />
                          {poll ? (
                            poll.student_count_completed !== undefined
                              ? `${poll.student_count_completed}/${poll.student_count_total} completed`
                              : `${poll.student_count_total} allocated`
                          ) : "…"}
                        </span>
                        <span className="flex items-center gap-1"><CheckCircle2 size={11} /> cutoff {a.pass_cutoff_percentage}%</span>
                      </p>
                    </div>

                    <div className="flex items-center gap-2">
                      <Button
                        variant="secondary" size="sm"
                        leftIcon={<FileText size={13} />}
                        onClick={() => router.push(`/admin/assessments/results/${a.id}`)}
                      >
                        Results
                      </Button>
                      <Button
                        variant="secondary" size="sm"
                        leftIcon={<TrendingUp size={13} />}
                        onClick={() => router.push(`/admin/assessments/analytics/${a.id}`)}
                      >
                        Analytics
                      </Button>
                      <Button
                        variant="secondary" size="sm"
                        leftIcon={<LayoutDashboard size={13} />}
                        onClick={() => router.push(`/admin/assessments/dashboard/${a.id}`)}
                      >
                        Dashboard
                      </Button>
                      <Button
                        variant="secondary" size="sm"
                        leftIcon={<RefreshCcw size={13} />}
                        loading={resyncingId === a.id}
                        onClick={() => handleResync(a)}
                      >
                        Resync roster
                      </Button>
                      {a.status === "SCHEDULED" && (
                        <Button
                          variant="success" size="sm"
                          leftIcon={<PlayCircle size={13} />}
                          onClick={() => setConfirmStart(a)}
                        >
                          Start Exam
                        </Button>
                      )}
                      {a.status !== "CLOSED" && (
                        <Button
                          variant="danger" size="sm"
                          leftIcon={<StopCircle size={13} />}
                          onClick={() => setConfirmClose(a)}
                        >
                          Close Exam
                        </Button>
                      )}
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </PageWrapper>

      <ConfirmDialog
        isOpen={!!confirmStart}
        onClose={() => setConfirmStart(null)}
        onConfirm={() => confirmStart && handleStart(confirmStart)}
        title="Start exam now?"
        message={`This manually starts the global timer for ${confirmStart ? batchName(confirmStart.batch_id) : ""} right now. Students will be able to begin the exam immediately. This cannot be undone.`}
        confirmLabel="Start Exam"
        confirmVariant="warning"
        loading={actingOn === confirmStart?.id}
      />

      <ConfirmDialog
        isOpen={!!confirmClose}
        onClose={() => setConfirmClose(null)}
        onConfirm={() => confirmClose && handleClose(confirmClose)}
        title="Close exam now?"
        message={`This immediately closes the exam for ${confirmClose ? batchName(confirmClose.batch_id) : ""} and blocks any student who hasn't started yet. Use this for emergencies only.`}
        confirmLabel="Close Exam"
        confirmVariant="danger"
        loading={actingOn === confirmClose?.id}
      />
    </AdminLayout>
  );
}
