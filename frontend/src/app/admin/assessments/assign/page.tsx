"use client";

import { useEffect, useState, useCallback } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { PlayCircle, StopCircle, RefreshCcw, Users, Clock, CheckCircle2, FileText, TrendingUp, LayoutDashboard, ChevronDown, AlertTriangle, FlaskConical } from "lucide-react";
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
import { useDepartments } from "@/lib/departmentsContext";
import type {
  QuestionPaper, QuestionSet, Batch, BatchAssignment, BatchAssignmentStatusPoll, ApiSuccess, PaginatedResponse,
} from "@/types";

interface PaperReviewDetail {
  paper: QuestionPaper;
  sets: QuestionSet[];
}

function formatReviewDateTime(value: string): string {
  const d = new Date(value);
  return isNaN(d.getTime()) ? value : d.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
}

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
  const { activeDepartments } = useDepartments();
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

  // Final Review — the selected paper's structure (sets/sections/questions/
  // marks) fetched fresh whenever paperId changes, so the checklist below
  // never shows stale data from a previously-selected paper.
  const [paperDetail, setPaperDetail] = useState<PaperReviewDetail | null>(null);
  const [loadingPaperDetail, setLoadingPaperDetail] = useState(false);
  const [paperDetailError, setPaperDetailError] = useState(false);
  // Which of the 10 review items the admin has manually ticked. Reset to {}
  // by the effect below whenever ANY reviewed field changes, so a stale
  // confirmation can never survive a post-review edit.
  const [reviewed, setReviewed] = useState<Record<string, boolean>>({});
  // Mock-test gate (added 2026-08-27) — once every review item is ticked,
  // the admin must explicitly say Yes/No to a mock test before "Create
  // assignment" itself appears. "Yes" opens the real exam-taking interface
  // in a new tab (session started via AdminTrialStartView) without
  // blocking creation — the admin can take as many mock attempts as they
  // want, before or after actually creating the assignment.
  const [mockChoice, setMockChoice] = useState<"yes" | "no" | null>(null);
  const [startingMockTrial, setStartingMockTrial] = useState(false);
  const [startingMockFor, setStartingMockFor] = useState<string | null>(null);

  const loadPaperDetail = useCallback(() => {
    if (!paperId) { setPaperDetail(null); setPaperDetailError(false); return; }
    setLoadingPaperDetail(true);
    setPaperDetailError(false);
    api.get<ApiSuccess<PaperReviewDetail>>(`/assessments/admin/papers/${paperId}/`)
      .then(res => setPaperDetail(res.data.data))
      .catch(() => { setPaperDetail(null); setPaperDetailError(true); })
      .finally(() => setLoadingPaperDetail(false));
  }, [paperId]);

  useEffect(loadPaperDetail, [loadPaperDetail]);

  useEffect(() => {
    setReviewed({});
    setMockChoice(null);
  }, [paperId, batchId, selectedDepartments, duration, startTime, expireTime, passCutoff, showResult, paperDetail]);

  // Shared by the Final Review "Yes" prompt and each assignment card's
  // "Mock Test" toolbar button — starts (or resumes) a trial session on
  // the given paper and opens the real exam-taking UI in a new tab, so the
  // admin's in-progress form/page state here is never disturbed.
  async function startMockTrial(targetPaperId: string, durationMinutes: number) {
    try {
      const res = await api.post<ApiSuccess<{ session_id: string }>>(
        `/assessments/admin/papers/${targetPaperId}/trial/start/`,
        { duration_minutes: durationMinutes },
      );
      window.open(`/admin/assessments/trial/${res.data.data.session_id}`, "_blank");
    } catch (err) {
      toast.error(getErrorMessage(err));
    }
  }

  function handleTakeMockFromReview() {
    setMockChoice("yes");
    setStartingMockTrial(true);
    startMockTrial(paperId, Number(duration) || 30).finally(() => setStartingMockTrial(false));
  }

  function handleMockTestForAssignment(a: BatchAssignment) {
    setStartingMockFor(a.id);
    startMockTrial(a.paper, a.exam_duration_minutes).finally(() => setStartingMockFor(null));
  }

  // "Students attending this assessment" — deliberately requires BOTH a
  // batch AND at least one department selected before showing a number
  // (leaving departments empty means "every department," but the admin
  // asked for this preview to only populate once both choices are
  // explicit, not fall back to the batch's whole headcount). page_size=1
  // keeps the request cheap — only `count` is used, never `results`.
  const [eligibleCount, setEligibleCount] = useState<number | null>(null);
  const [loadingEligibleCount, setLoadingEligibleCount] = useState(false);
  const [eligibleCountError, setEligibleCountError] = useState(false);

  useEffect(() => {
    if (!batchId || selectedDepartments.length === 0) {
      setEligibleCount(null);
      setLoadingEligibleCount(false);
      setEligibleCountError(false);
      return;
    }
    let cancelled = false;
    setLoadingEligibleCount(true);
    setEligibleCountError(false);
    api.get<PaginatedResponse<unknown>>(
      `/users/batches/${batchId}/students/?departments=${encodeURIComponent(selectedDepartments.join(","))}&page_size=1`
    )
      .then(res => { if (!cancelled) setEligibleCount(res.data.count); })
      .catch(() => { if (!cancelled) { setEligibleCount(null); setEligibleCountError(true); } })
      .finally(() => { if (!cancelled) setLoadingEligibleCount(false); });
    return () => { cancelled = true; };
  }, [batchId, selectedDepartments]);

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

  // The 10-item Final Review checklist — order follows the data's own
  // hierarchy (sets → sections → questions → marks), then who it's for
  // (batch → department), then timing (duration → global timer), then
  // outcome (cutoff → results visibility). Only populated once the
  // selected paper's structure has actually loaded.
  const reviewSets = paperDetail?.sets ?? [];
  const hasSets = reviewSets.length > 0;
  const hasEmptySections = reviewSets.some(s => s.section_count === 0);
  const hasEmptyQuestions = reviewSets.some(s => s.question_count === 0);
  // Surfaced instead of a silent "0"/"—" — a structurally incomplete paper
  // would still fail the backend's own readiness check at submit time, but
  // this catches it during review instead of after a failed submit.
  const structureIncomplete = !!paperDetail && (!hasSets || hasEmptySections || hasEmptyQuestions);

  const reviewItems: { id: string; label: string; value: string; warn?: boolean }[] = paperDetail ? [
    {
      id: "sets", label: "Total number of sets",
      value: hasSets ? `${reviewSets.length} set${reviewSets.length === 1 ? "" : "s"}` : "No sets found on this paper.",
      warn: !hasSets,
    },
    {
      id: "sections", label: "Sections per set",
      value: hasSets ? reviewSets.map(s => `${s.label}: ${s.section_count} section${s.section_count === 1 ? "" : "s"}`).join("  ·  ") : "—",
      warn: hasSets && hasEmptySections,
    },
    {
      id: "questions", label: "Questions per set",
      value: hasSets ? reviewSets.map(s => `${s.label}: ${s.question_count} question${s.question_count === 1 ? "" : "s"}`).join("  ·  ") : "—",
      warn: hasSets && hasEmptyQuestions,
    },
    {
      id: "marks", label: "Marks per set",
      value: hasSets ? reviewSets.map(s => `${s.label}: ${s.total_marks} marks`).join("  ·  ") : "—",
      warn: hasSets && hasEmptyQuestions,
    },
    {
      id: "batch", label: "Assigned batch",
      value: batchId ? batchName(batchId) : "Not selected",
    },
    {
      id: "departments", label: "Assigned department(s)",
      value: selectedDepartments.length > 0 ? selectedDepartments.join(", ") : "All departments in the batch",
    },
    {
      id: "duration", label: "Exam duration",
      value: Number(duration) > 0 ? `${duration} minutes` : "Not set",
    },
    {
      id: "timer", label: "Global timer",
      // Same "  ·  " separator as the per-set rows above — was "|" here,
      // which read as an inconsistent second style in the same checklist.
      value: `Start: ${startTime ? formatReviewDateTime(startTime) : "not set — begins immediately once you start the exam"}  ·  Expire: ${expireTime ? formatReviewDateTime(expireTime) : "not set"}`,
    },
    {
      id: "cutoff", label: "Pass cutoff",
      value: passCutoff ? `${passCutoff}%` : "Not set",
    },
    {
      id: "results", label: "Results visibility",
      value: showResult ? "Visible to students after submission" : "Hidden from students",
    },
  ] : [];
  const allReviewed = reviewItems.length > 0 && reviewItems.every(item => reviewed[item.id]);
  const canSubmit = !!paperId && !!batchId && !!expireTime && Number(duration) > 0 && allReviewed;

  return (
    <AdminLayout>
      <PageWrapper>
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
                  ...batches.map(b => ({ value: b.id, label: b.batch_name })),
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
                {activeDepartments.map(d => {
                  const active = selectedDepartments.includes(d.code);
                  return (
                    <button
                      key={d.id}
                      type="button"
                      aria-pressed={active}
                      onClick={() => toggleDepartment(d.code)}
                      className="px-3 py-1.5 rounded-full text-xs font-semibold transition-colors cursor-pointer"
                      style={active
                        ? { background: "var(--color-accent)", color: "#fff", border: "1px solid var(--color-accent)" }
                        : { background: "var(--color-surface)", color: "var(--color-text-muted)", border: "1px solid var(--color-border)" }
                      }
                    >
                      {d.name || d.code}
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

            <div>
              <label className="block text-xs font-medium mb-1.5" style={{ color: "var(--color-text-muted)" }}>
                Students attending this assessment
              </label>
              <div
                className="h-9 flex items-center px-3.5 rounded-[var(--radius-md)] text-sm max-w-[240px]"
                style={{ background: "var(--color-surface-hover)", border: "1px solid var(--color-border)" }}
              >
                {!batchId || selectedDepartments.length === 0 ? (
                  <span style={{ color: "var(--color-text-subtle)" }}>
                    Select a batch and department(s) to see this
                  </span>
                ) : loadingEligibleCount ? (
                  <span style={{ color: "var(--color-text-subtle)" }}>Calculating…</span>
                ) : eligibleCountError ? (
                  <span style={{ color: "var(--color-danger)" }}>
                    Couldn't calculate —{" "}
                    <button
                      type="button"
                      onClick={() => setSelectedDepartments(prev => [...prev])}
                      className="underline cursor-pointer"
                    >
                      retry
                    </button>
                  </span>
                ) : (
                  <span style={{ color: "var(--color-text)" }}>
                    {eligibleCount} student{eligibleCount === 1 ? "" : "s"}
                  </span>
                )}
              </div>
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

            {paperId && (
              <div
                className="rounded-[var(--radius-lg)] p-4"
                style={{ background: "var(--color-surface-hover)", border: "1px solid var(--color-border)" }}
              >
                <h4 className="text-sm font-semibold mb-1" style={{ color: "var(--color-text)" }}>Final Review</h4>
                <p className="text-xs mb-3" style={{ color: "var(--color-text-subtle)" }}>
                  Tick every item after checking it against the values shown — this locks the paper and creates real student sessions once the exam starts.
                </p>
                {loadingPaperDetail ? (
                  <Skeleton className="h-32 w-full" />
                ) : paperDetailError ? (
                  <p className="text-xs" style={{ color: "var(--color-danger)" }}>
                    Couldn't load this paper's structure for review — this may be temporary.{" "}
                    <button type="button" onClick={loadPaperDetail} className="underline cursor-pointer">Retry</button>
                  </p>
                ) : (
                  <>
                    {structureIncomplete && (
                      <p className="text-xs mb-2.5 flex items-center gap-1.5" style={{ color: "var(--color-danger)" }}>
                        <AlertTriangle size={12} className="shrink-0" />
                        This paper's structure looks incomplete — check the highlighted item(s) below before proceeding.
                      </p>
                    )}
                    <div className="space-y-1.5">
                      {reviewItems.map(item => (
                        <label key={item.id} className="flex items-start gap-2.5 py-1 cursor-pointer">
                          <input
                            type="checkbox"
                            checked={!!reviewed[item.id]}
                            onChange={e => setReviewed(prev => ({ ...prev, [item.id]: e.target.checked }))}
                            className="mt-0.5 w-4 h-4 shrink-0 cursor-pointer accent-[var(--color-accent)]"
                          />
                          <span className="text-xs leading-relaxed min-w-0 flex-1">
                            <span className="font-semibold" style={{ color: "var(--color-text)" }}>{item.label}:</span>{" "}
                            <span style={{ color: item.warn ? "var(--color-danger)" : "var(--color-text-subtle)" }}>
                              {item.value}
                            </span>
                          </span>
                        </label>
                      ))}
                    </div>
                  </>
                )}
              </div>
            )}

            {formError && <p className="text-xs" style={{ color: "var(--color-danger)" }}>{formError}</p>}

            {allReviewed && mockChoice === null ? (
              <div
                className="rounded-[var(--radius-lg)] p-4 flex items-center justify-between gap-3 flex-wrap"
                style={{ background: "#EFF6FF", border: "1px solid #BFDBFE" }}
              >
                <p className="text-sm font-medium" style={{ color: "var(--color-text)" }}>
                  Are you willing to take the mock test before creating this assessment?
                </p>
                <div className="flex gap-2">
                  <Button type="button" variant="secondary" size="sm" onClick={() => setMockChoice("no")}>No</Button>
                  <Button
                    type="button" variant="primary" size="sm"
                    leftIcon={<FlaskConical size={13} />}
                    loading={startingMockTrial}
                    onClick={handleTakeMockFromReview}
                  >
                    Yes
                  </Button>
                </div>
              </div>
            ) : (
              <div className="flex items-center justify-between gap-2 flex-wrap">
                {mockChoice === "yes" ? (
                  <button
                    type="button" onClick={handleTakeMockFromReview} disabled={startingMockTrial}
                    className="text-xs underline cursor-pointer disabled:opacity-50"
                    style={{ color: "var(--color-accent)" }}
                  >
                    {startingMockTrial ? "Opening mock test…" : "Take the mock test again"}
                  </button>
                ) : <span />}
                <Button type="submit" loading={creating} disabled={!canSubmit}>Create assignment</Button>
              </div>
            )}
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
                      <Button
                        variant="secondary" size="sm"
                        leftIcon={<FlaskConical size={13} />}
                        loading={startingMockFor === a.id}
                        onClick={() => handleMockTestForAssignment(a)}
                      >
                        Mock Test
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
