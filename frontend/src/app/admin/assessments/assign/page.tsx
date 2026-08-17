"use client";

import { useEffect, useState, useCallback } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { PlayCircle, StopCircle, RefreshCcw, Users, Clock, CheckCircle2, FileText, TrendingUp, LayoutDashboard, ChevronDown } from "lucide-react";
import { AdminLayout } from "@/components/layout/AdminLayout";
import { PageWrapper } from "@/components/layout/PageWrapper";
import { PageHeader } from "@/components/layout/PageHeader";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Select } from "@/components/ui/Select";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import { Skeleton } from "@/components/ui/Skeleton";
import { useToast } from "@/components/ui/Toast";
import { useAuth } from "@/hooks/useAuth";
import api, { getErrorMessage } from "@/lib/api";
import { DEPARTMENTS } from "@/lib/constants";
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
  const router = useRouter();
  const searchParams = useSearchParams();
  const toast = useToast();
  const { user, isSuperAdmin } = useAuth();
  // This page is admin-only (route-guarded elsewhere), so `user` is always
  // AdminUser here in practice — StudentUser (the only AuthUser variant
  // without `.id`) narrowed out via the "id" in user check for TypeScript.
  const currentUserId = user && "id" in user ? user.id : undefined;

  const [papers, setPapers] = useState<QuestionPaper[]>([]);
  const [batches, setBatches] = useState<Batch[]>([]);
  const [loadingOptions, setLoadingOptions] = useState(true);
  const [loadOptionsError, setLoadOptionsError] = useState(false);

  const [paperId, setPaperId] = useState(searchParams.get("paper") ?? "");
  const [assignments, setAssignments] = useState<BatchAssignment[]>([]);
  const [statusByAssignment, setStatusByAssignment] = useState<Record<string, BatchAssignmentStatusPoll>>({});
  const [loadingAssignments, setLoadingAssignments] = useState(true);
  const [loadAssignmentsError, setLoadAssignmentsError] = useState(false);
  // Collapsed by default — the create form is tucked behind a "Create
  // Assessment" toggle so the page opens straight onto the assignment
  // history instead of an empty form, opening only when the admin actually
  // wants to create one; pre-arriving with ?paper= (from a paper's own
  // page) still opens it, since that's a clear signal of create intent.
  const [formOpen, setFormOpen] = useState(!!searchParams.get("paper"));

  const [batchId, setBatchId] = useState("");
  // Empty = every department in the batch (unchanged default behavior).
  const [selectedDepartments, setSelectedDepartments] = useState<string[]>([]);
  const [duration, setDuration] = useState("60");
  const [startTime, setStartTime] = useState("");
  const [expireTime, setExpireTime] = useState("");
  const [passCutoff, setPassCutoff] = useState("40");
  const [showResult, setShowResult] = useState(true);
  const [creating, setCreating] = useState(false);
  const [formError, setFormError] = useState("");

  const [confirmStart, setConfirmStart] = useState<BatchAssignment | null>(null);
  const [confirmClose, setConfirmClose] = useState<BatchAssignment | null>(null);
  const [actingOn, setActingOn] = useState<string | null>(null);
  const [resyncingId, setResyncingId] = useState<string | null>(null);

  // Papers + batches — the two dropdown sources — loaded once. Papers is
  // filtered to ones this admin can actually assign (faculty-privacy
  // restriction: assigning is creator-only, same as opening/editing a
  // paper — see assessment-service's _require_paper_owner) so the dropdown
  // never offers a choice that would 403 on submit. A super admin sees
  // every paper, matching their backend override.
  // On failure this must not just toast and leave the dropdown looking
  // merely empty — "author one in Question Bank first" (below) is
  // misleading if papers actually exist and this just failed to load.
  const loadOptions = useCallback(() => {
    setLoadingOptions(true);
    setLoadOptionsError(false);
    Promise.all([
      api.get<PaginatedResponse<QuestionPaper>>("/assessments/admin/papers/"),
      api.get<ApiSuccess<Batch[]>>("/users/batches/"),
    ])
      .then(([papersRes, batchesRes]) => {
        const assignable = isSuperAdmin
          ? papersRes.data.results
          : papersRes.data.results.filter(p => p.created_by === currentUserId);
        setPapers(assignable);
        setBatches(batchesRes.data.data);
      })
      .catch(err => { toast.error(getErrorMessage(err)); setLoadOptionsError(true); })
      .finally(() => setLoadingOptions(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isSuperAdmin, currentUserId]);

  useEffect(loadOptions, [loadOptions]);

  // Unfiltered (every assignment across every paper) when no paper is
  // picked in the create form — this is what renders as the page's default
  // "past assessments" view now that the form itself is collapsed by
  // default; scoped to just that paper once one is selected, same as
  // before. Same reasoning as elsewhere — "No assignments yet" (below)
  // shouldn't be shown when the fetch itself failed.
  const loadAssignments = useCallback(() => {
    setLoadingAssignments(true);
    setLoadAssignmentsError(false);
    const url = paperId
      ? `/assessments/admin/assignments/?paper_id=${paperId}`
      : "/assessments/admin/assignments/";
    api.get<PaginatedResponse<BatchAssignment>>(url)
      .then(res => setAssignments(res.data.results))
      .catch(err => { toast.error(getErrorMessage(err)); setLoadAssignmentsError(true); })
      .finally(() => setLoadingAssignments(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [paperId]);

  useEffect(loadAssignments, [loadAssignments]);

  // Keep the URL's ?paper= in sync so the pre-selection (arriving from a
  // paper's own page) is also reflected if the admin reloads or shares the
  // link, without a full navigation/remount.
  useEffect(() => {
    const url = paperId ? `/admin/assessments/assign?paper=${paperId}` : "/admin/assessments/assign";
    window.history.replaceState(null, "", url);
  }, [paperId]);

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
    if (!paperId) { setFormError("Select a question paper."); return; }
    if (!batchId) { setFormError("Select a batch."); return; }
    if (!expireTime) { setFormError("Global expire time is required."); return; }
    const durationNum = Number(duration);
    if (!durationNum || durationNum <= 0) { setFormError("Exam duration must be a positive number of minutes."); return; }

    const payload: Record<string, unknown> = {
      paper: paperId,
      batch_id: batchId,
      global_expire_time: new Date(expireTime).toISOString(),
      exam_duration_minutes: durationNum,
      pass_cutoff_percentage: Number(passCutoff) || 40,
      show_result_to_student: showResult,
      departments: selectedDepartments,
    };
    if (startTime) payload.global_start_time = new Date(startTime).toISOString();

    setCreating(true);
    try {
      const res = await api.post<ApiSuccess<BatchAssignment>>("/assessments/admin/assignments/", payload);
      setAssignments(prev => [res.data.data, ...prev]);
      setBatchId(""); setSelectedDepartments([]); setStartTime(""); setExpireTime(""); setDuration("60"); setPassCutoff("40"); setShowResult(true);
      setFormOpen(false);
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
  const selectedPaper = papers.find(p => p.id === paperId);

  function toggleDepartment(dept: string) {
    setSelectedDepartments(prev =>
      prev.includes(dept) ? prev.filter(d => d !== dept) : [...prev, dept]
    );
  }

  return (
    <AdminLayout>
      <PageWrapper className="max-w-4xl">
        <PageHeader
          title={selectedPaper ? `Assign — ${selectedPaper.title}` : "Assign"}
          titleSkeleton={loadingOptions ? <Skeleton className="h-8 w-64" /> : undefined}
          subtitle="Pick a question paper and a batch, then manually start the global exam timer when ready."
          backHref="/admin/assessments"
        />

        {/* Create assignment — collapsed by default behind this toggle, so
            the page opens straight onto assignment history (below) instead
            of an empty form every time. */}
        <div
          className="rounded-[var(--radius-xl)] mb-6 overflow-hidden"
          style={{ background: "var(--color-surface)", border: "1px solid var(--color-border)", boxShadow: "var(--shadow-sm)" }}
        >
          <button
            type="button"
            onClick={() => setFormOpen(v => !v)}
            aria-expanded={formOpen}
            className="w-full flex items-center justify-between px-5 py-4 cursor-pointer"
          >
            <span className="text-sm font-semibold" style={{ color: "var(--color-text)" }}>Create Assessment</span>
            <ChevronDown
              size={16}
              style={{
                color: "var(--color-text-subtle)",
                transform: formOpen ? "rotate(180deg)" : "rotate(0deg)",
                transition: "transform 200ms ease",
              }}
            />
          </button>
          <div
            style={{
              maxHeight: formOpen ? "2400px" : "0px",
              opacity: formOpen ? 1 : 0,
              overflow: "hidden",
              transition: "max-height 300ms ease, opacity 200ms ease",
            }}
          >
          <div className="px-5 pb-5 pt-1" style={{ borderTop: "1px solid var(--color-border)" }}>
          <form onSubmit={handleCreate} className="space-y-4">
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <Select
                label="Question paper"
                value={paperId}
                onChange={e => setPaperId(e.target.value)}
                options={[
                  { value: "", label: loadingOptions ? "Loading…" : "Select a question paper…" },
                  ...papers.map(p => ({ value: p.id, label: p.title })),
                ]}
              />
              <Select
                label="Batch"
                value={batchId}
                onChange={e => setBatchId(e.target.value)}
                options={[
                  { value: "", label: "Select a batch…" },
                  ...batches.map(b => ({
                    value: b.id,
                    label: `${b.batch_name}${typeof b.student_count === "number" ? ` (${b.student_count} students)` : ""}`,
                  })),
                ]}
              />
            </div>
            {!loadingOptions && loadOptionsError && (
              <p className="text-xs" style={{ color: "var(--color-danger)" }}>
                Couldn't load question papers/batches — this may be temporary.{" "}
                <button type="button" onClick={loadOptions} className="underline cursor-pointer">Retry</button>
              </p>
            )}
            {!loadingOptions && !loadOptionsError && papers.length === 0 && (
              <p className="text-xs" style={{ color: "var(--color-text-subtle)" }}>
                No question papers to assign yet — author one in Question Bank first.
              </p>
            )}

            <div>
              <label className="block text-xs font-medium mb-1.5" style={{ color: "var(--color-text-muted)" }}>
                Departments (optional — leave all unchecked to include every department in the batch)
              </label>
              <div className="flex flex-wrap gap-2">
                {DEPARTMENTS.map(dept => {
                  const active = selectedDepartments.includes(dept);
                  return (
                    <button
                      key={dept}
                      type="button"
                      aria-pressed={active}
                      onClick={() => toggleDepartment(dept)}
                      className="px-3 py-1.5 rounded-full text-xs font-semibold transition-colors cursor-pointer"
                      style={active
                        ? { background: "var(--color-accent)", color: "#fff", border: "1px solid var(--color-accent)" }
                        : { background: "var(--color-surface)", color: "var(--color-text-muted)", border: "1px solid var(--color-border)" }
                      }
                    >
                      {dept}
                    </button>
                  );
                })}
              </div>
              {selectedDepartments.length > 0 && (
                <p className="text-xs mt-1.5" style={{ color: "var(--color-text-subtle)" }}>
                  Only {selectedDepartments.join(", ")} student{selectedDepartments.length === 1 ? "" : "s"} in the selected batch will be assigned this exam.
                </p>
              )}
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

            <div className="flex items-end gap-6 flex-wrap">
              <Input
                label="Pass cutoff (%)"
                type="number"
                min={0}
                max={100}
                value={passCutoff}
                onChange={e => setPassCutoff(e.target.value)}
                className="max-w-[160px]"
              />

              <div>
                <label className="block text-xs font-medium mb-1.5" style={{ color: "var(--color-text-muted)" }}>
                  Show result to student after submission
                </label>
                <button
                  type="button"
                  role="switch"
                  aria-checked={showResult}
                  onClick={() => setShowResult(v => !v)}
                  className="h-9 inline-flex items-center gap-2.5 cursor-pointer"
                >
                  <span
                    className="relative inline-flex h-5 w-10 shrink-0 items-center rounded-full transition-colors"
                    style={{ background: showResult ? "#16A34A" : "var(--color-border-strong)" }}
                  >
                    <span
                      className="inline-block h-4 w-4 rounded-full bg-white shadow transition-transform"
                      style={{ transform: showResult ? "translateX(21px)" : "translateX(3px)" }}
                    />
                  </span>
                  <span className="text-sm font-semibold" style={{ color: showResult ? "#16A34A" : "var(--color-text-muted)" }}>
                    {showResult ? "On" : "Off"}
                  </span>
                </button>
              </div>
            </div>

            {formError && <p className="text-xs" style={{ color: "var(--color-danger)" }}>{formError}</p>}

            <div className="flex justify-end">
              <Button type="submit" loading={creating}>Create assignment</Button>
            </div>
          </form>
          </div>
          </div>
        </div>

        {/* Assignment history — every assignment by default, scoped down
            to one paper once the create form's paper dropdown picks one. */}
        <h3 className="text-sm font-semibold mb-3" style={{ color: "var(--color-text)" }}>
          {paperId && selectedPaper ? `Assignments — ${selectedPaper.title}` : "Assignments"}
        </h3>
        {loadingAssignments ? (
          <Skeleton className="h-24 w-full rounded-[var(--radius-xl)]" />
        ) : loadAssignmentsError ? (
          <p className="text-sm" style={{ color: "var(--color-danger)" }}>
            Couldn't load assignments — this may be temporary.{" "}
            <button type="button" onClick={loadAssignments} className="underline cursor-pointer">Retry</button>
          </p>
        ) : assignments.length === 0 ? (
          <p className="text-sm" style={{ color: "var(--color-text-subtle)" }}>
            {paperId ? "No assignments yet for this paper." : "No assignments yet — create one above to get started."}
          </p>
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
                        <span>{a.show_result_to_student ? "Results visible to students" : "Results hidden from students"}</span>
                        {a.departments.length > 0 && (
                          <span>Departments: {a.departments.join(", ")}</span>
                        )}
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
