"use client";

import { useEffect, useState, useCallback } from "react";
import { useParams, useRouter } from "next/navigation";
import { ArrowLeft, ShieldAlert, Clock, Server, RefreshCcw, FileSearch, PencilLine, UserCog, Edit3 } from "lucide-react";
import { AdminLayout } from "@/components/layout/AdminLayout";
import { PageWrapper } from "@/components/layout/PageWrapper";
import { PageHeader } from "@/components/layout/PageHeader";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Modal } from "@/components/ui/Modal";
import { Skeleton } from "@/components/ui/Skeleton";
import { EmptyState } from "@/components/ui/EmptyState";
import { useToast } from "@/components/ui/Toast";
import api, { getErrorMessage } from "@/lib/api";
import type { ApiSuccess, EssaySubmissionDetail, EssaySubmissionEvent, EssayLLMTrace } from "@/types";

function StatusPill({ status }: { status: EssaySubmissionDetail["status"] }) {
  const styles: Record<string, { bg: string; color: string; label: string }> = {
    PENDING:           { bg: "#FFF4E6", color: "#E8820C", label: "Pending" },
    LLM_PROCESSING:    { bg: "#EFF6FF", color: "#2563EB", label: "Processing" },
    LLM_COMPLETE:      { bg: "#F0FDF4", color: "#16A34A", label: "Complete" },
    REPORT_GENERATING: { bg: "#EFF6FF", color: "#2563EB", label: "Complete" },
    REPORT_READY:      { bg: "#F0FDF4", color: "#16A34A", label: "Complete" },
    LLM_FAILED:        { bg: "#FEF2F2", color: "#DC2626", label: "Failed" },
  };
  const s = styles[status] ?? styles.PENDING;
  return (
    <span className="text-xs font-semibold px-2.5 py-1 rounded-full" style={{ background: s.bg, color: s.color }}>
      {s.label}
    </span>
  );
}

function formatDateTime(iso: string): string {
  return new Date(iso).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "medium" });
}

const EVENT_LABELS: Record<EssaySubmissionEvent["event_type"], string> = {
  STATUS_CHANGE: "Status change",
  DLQ_RECORDED: "DLQ recorded",
  ADMIN_RETRIGGER: "Admin retrigger",
  ADMIN_OVERRIDE: "Admin override",
  // Phase 11 — real event types, but nothing in this platform writes them
  // yet (no live bounce/complaint webhook exists anywhere here — see
  // essays/reports.py's own module docstring for the disclosed reasoning).
  // Labeled now so the event trail renders correctly the moment a future
  // webhook starts recording them, rather than falling back to the raw
  // constant.
  EMAIL_BOUNCED: "Email bounced",
  EMAIL_COMPLAINT: "Email complaint",
};

// Reason field styled to match Input.tsx's own look — no dedicated
// Textarea component exists in this project yet, and this is the only
// multiline field this page needs, so a plain <textarea> with matching
// classes is simpler than introducing a new shared component for one use.
function ReasonField({ value, onChange, placeholder }: { value: string; onChange: (v: string) => void; placeholder?: string }) {
  return (
    <textarea
      value={value}
      onChange={e => onChange(e.target.value)}
      placeholder={placeholder}
      rows={3}
      className="w-full rounded-[var(--radius-md)] border px-3 py-2 text-sm outline-none transition-colors resize-none"
      style={{ borderColor: "var(--color-border)", color: "var(--color-text)" }}
    />
  );
}

export default function AdminEssaySubmissionDetailPage() {
  const { submission_id } = useParams<{ submission_id: string }>();
  const router = useRouter();
  const toast = useToast();

  const [submission, setSubmission] = useState<EssaySubmissionDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState(false);

  const [trace, setTrace] = useState<EssayLLMTrace | null | undefined>(undefined); // undefined = not loaded yet
  const [traceLoading, setTraceLoading] = useState(false);

  const [retriggerOpen, setRetriggerOpen] = useState(false);
  const [retriggerReason, setRetriggerReason] = useState("");
  const [retriggering, setRetriggering] = useState(false);

  const [overrideOpen, setOverrideOpen] = useState(false);
  const [overrideScore, setOverrideScore] = useState("");
  const [overrideFeedback, setOverrideFeedback] = useState("");
  const [overrideReason, setOverrideReason] = useState("");
  const [overriding, setOverriding] = useState(false);

  // Phase 8, Task 8.1's own "General score override" — distinct from the
  // DLQ-recovery override above (that one only ever applies to a
  // permanently LLM_FAILED submission with no score at all). This one
  // corrects a score that already exists (a student appeal, a human
  // regrade) — the two are mutually exclusive by construction (a
  // LLM_FAILED submission never has a score, per the pipeline's own
  // status machine), so their trigger buttons below never both show at
  // once.
  const [generalOverrideOpen, setGeneralOverrideOpen] = useState(false);
  const [generalOverrideScore, setGeneralOverrideScore] = useState("");
  const [generalOverrideFeedback, setGeneralOverrideFeedback] = useState("");
  const [generalOverrideReason, setGeneralOverrideReason] = useState("");
  const [generalOverriding, setGeneralOverriding] = useState(false);

  const load = useCallback(() => {
    setLoading(true);
    setLoadError(false);
    api.get<ApiSuccess<EssaySubmissionDetail>>(`/essay/admin/submissions/${submission_id}/`)
      .then(res => setSubmission(res.data.data))
      .catch(err => { toast.error(getErrorMessage(err)); setLoadError(true); })
      .finally(() => setLoading(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [submission_id]);

  const loadTrace = useCallback(() => {
    setTraceLoading(true);
    api.get<ApiSuccess<EssayLLMTrace>>(`/essay/admin/submissions/${submission_id}/trace/`)
      .then(res => setTrace(res.data.data ?? null))
      .catch(() => setTrace(null))
      .finally(() => setTraceLoading(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [submission_id]);

  useEffect(load, [load]);
  useEffect(loadTrace, [loadTrace]);

  async function submitRetrigger() {
    if (!retriggerReason.trim()) {
      toast.error("A reason is required to retrigger evaluation.");
      return;
    }
    setRetriggering(true);
    try {
      await api.post(`/essay/admin/submissions/${submission_id}/retrigger/`, { reason: retriggerReason.trim() });
      toast.success("Evaluation retriggered.");
      setRetriggerOpen(false);
      setRetriggerReason("");
      load();
      setTrace(undefined);
      loadTrace();
    } catch (err) {
      toast.error(getErrorMessage(err));
    } finally {
      setRetriggering(false);
    }
  }

  async function submitOverride() {
    const scoreNum = Number(overrideScore);
    if (overrideScore.trim() === "" || Number.isNaN(scoreNum) || scoreNum < 0 || scoreNum > 10 || !Number.isInteger(scoreNum)) {
      toast.error("Score must be a whole number between 0 and 10.");
      return;
    }
    if (!overrideFeedback.trim()) {
      toast.error("Feedback is required.");
      return;
    }
    if (!overrideReason.trim()) {
      toast.error("A reason is required to override a score.");
      return;
    }
    setOverriding(true);
    try {
      const res = await api.post<ApiSuccess<EssaySubmissionDetail>>(`/essay/admin/submissions/${submission_id}/override-score/`, {
        score: scoreNum,
        feedback: { overall: overrideFeedback.trim() },
        reason: overrideReason.trim(),
      });
      setSubmission(res.data.data);
      toast.success("Score overridden.");
      setOverrideOpen(false);
      setOverrideScore("");
      setOverrideFeedback("");
      setOverrideReason("");
    } catch (err) {
      toast.error(getErrorMessage(err));
    } finally {
      setOverriding(false);
    }
  }

  async function submitGeneralOverride() {
    const scoreNum = Number(generalOverrideScore);
    if (generalOverrideScore.trim() === "" || Number.isNaN(scoreNum) || scoreNum < 0 || scoreNum > 10 || !Number.isInteger(scoreNum)) {
      toast.error("Score must be a whole number between 0 and 10.");
      return;
    }
    if (!generalOverrideFeedback.trim()) {
      toast.error("Feedback is required.");
      return;
    }
    if (!generalOverrideReason.trim()) {
      toast.error("A reason is required to override a score.");
      return;
    }
    if (generalOverrideReason.trim().length > 500) {
      toast.error("Reason must be 500 characters or fewer.");
      return;
    }
    setGeneralOverriding(true);
    try {
      const res = await api.post<ApiSuccess<EssaySubmissionDetail>>(`/essay/admin/submissions/${submission_id}/general-override-score/`, {
        score: scoreNum,
        feedback: { overall: generalOverrideFeedback.trim() },
        reason: generalOverrideReason.trim(),
      });
      setSubmission(res.data.data);
      toast.success("Score overridden.");
      setGeneralOverrideOpen(false);
      setGeneralOverrideScore("");
      setGeneralOverrideFeedback("");
      setGeneralOverrideReason("");
    } catch (err) {
      toast.error(getErrorMessage(err));
    } finally {
      setGeneralOverriding(false);
    }
  }

  return (
    <AdminLayout>
      <PageWrapper>
        <button
          onClick={() => router.push("/admin/essay-writing/submissions")}
          className="flex items-center gap-1.5 text-sm mb-4 cursor-pointer"
          style={{ color: "var(--color-text-subtle)" }}
        >
          <ArrowLeft size={15} /> Back to Submissions
        </button>

        {loading ? (
          <div className="space-y-4">
            <Skeleton className="h-8 w-64" />
            <Skeleton className="h-40 w-full" />
            <Skeleton className="h-40 w-full" />
          </div>
        ) : loadError || !submission ? (
          <EmptyState icon={ShieldAlert} title="Couldn't load this submission" subtitle="Please try again." />
        ) : (
          <>
            <div className="flex items-start justify-between gap-3 mb-5 flex-wrap">
              <PageHeader title={submission.paper_title} subtitle={`Submission ${submission.id}`} />
              <div className="flex items-center gap-2 pt-1 flex-wrap">
                {submission.malpractice_flag && (
                  <span className="flex items-center gap-1 text-xs font-semibold px-2.5 py-1 rounded-full" style={{ background: "#FEF2F2", color: "#DC2626" }}>
                    <ShieldAlert size={12} /> Flagged
                  </span>
                )}
                <StatusPill status={submission.status} />
                <Button
                  variant="secondary" size="sm" leftIcon={<RefreshCcw size={13} />}
                  onClick={() => setRetriggerOpen(true)}
                  disabled={submission.status === "LLM_PROCESSING"}
                  title={submission.status === "LLM_PROCESSING" ? "Evaluation is already in progress." : undefined}
                >
                  Retrigger
                </Button>
                {submission.status === "LLM_FAILED" && (
                  <Button variant="warning" size="sm" leftIcon={<UserCog size={13} />} onClick={() => setOverrideOpen(true)}>
                    Override Score
                  </Button>
                )}
                {/* Phase 8's general override — only once a score already
                    exists to correct (mutually exclusive with the
                    DLQ-recovery button above, by construction). */}
                {submission.score !== null && (
                  <Button variant="secondary" size="sm" leftIcon={<Edit3 size={13} />} onClick={() => setGeneralOverrideOpen(true)}>
                    Correct Score
                  </Button>
                )}
              </div>
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
              <div className="lg:col-span-2 space-y-4">
                <div className="rounded-[var(--radius-lg)] p-5" style={{ background: "var(--color-surface)", border: "1px solid var(--color-border)" }}>
                  <p className="text-xs font-semibold uppercase tracking-wide mb-2" style={{ color: "var(--color-text-subtle)" }}>Question</p>
                  <p className="text-sm mb-4" style={{ color: "var(--color-text)" }}>{submission.question_text}</p>
                  <p className="text-xs font-semibold uppercase tracking-wide mb-2" style={{ color: "var(--color-text-subtle)" }}>Response</p>
                  <p className="text-sm whitespace-pre-wrap leading-relaxed" style={{ color: "var(--color-text)" }}>
                    {submission.draft_response || <em style={{ color: "var(--color-text-subtle)" }}>No response submitted.</em>}
                  </p>
                </div>

                {submission.malpractice_reasons.length > 0 && (
                  <div className="rounded-[var(--radius-lg)] p-5" style={{ background: "#FEF2F2", border: "1px solid #FECACA" }}>
                    <p className="text-xs font-semibold uppercase tracking-wide mb-2" style={{ color: "#DC2626" }}>Malpractice Reasons</p>
                    <ul className="list-disc list-inside text-sm" style={{ color: "#991B1B" }}>
                      {submission.malpractice_reasons.map(r => <li key={r}>{r.replace(/_/g, " ")}</li>)}
                    </ul>
                  </div>
                )}

                {/* LLM trace/debug view — Task 7.1's own requirement: the
                    exact prompt, the raw response, the request id, and
                    when it was evaluated, for diagnosing "why did this
                    essay get this score". */}
                <div className="rounded-[var(--radius-lg)] p-5" style={{ background: "var(--color-surface)", border: "1px solid var(--color-border)" }}>
                  <p className="text-xs font-semibold uppercase tracking-wide mb-3 flex items-center gap-1.5" style={{ color: "var(--color-text-subtle)" }}>
                    <FileSearch size={13} /> LLM Trace
                  </p>
                  {traceLoading ? (
                    <Skeleton className="h-16 w-full" />
                  ) : !trace ? (
                    <p className="text-sm" style={{ color: "var(--color-text-subtle)" }}>No LLM trace recorded for this submission.</p>
                  ) : (
                    <div className="space-y-3 text-sm">
                      <div className="grid grid-cols-2 gap-2 text-xs" style={{ color: "var(--color-text-subtle)" }}>
                        <div>Model: <span style={{ color: "var(--color-text)" }}>{trace.model_used || "—"}</span></div>
                        <div>Request ID: <span className="font-mono" style={{ color: "var(--color-text)" }}>{trace.request_id || "—"}</span></div>
                        <div className="col-span-2">Evaluated: <span style={{ color: "var(--color-text)" }}>{formatDateTime(trace.evaluated_at)}</span></div>
                      </div>
                      <details>
                        <summary className="cursor-pointer text-xs font-semibold" style={{ color: "var(--color-text)" }}>Prompt messages ({trace.prompt_messages.length})</summary>
                        <pre className="mt-2 p-3 rounded-[var(--radius-md)] text-xs overflow-x-auto whitespace-pre-wrap" style={{ background: "var(--color-surface-subtle)", color: "var(--color-text)" }}>
                          {trace.prompt_messages.map(m => `[${m.role}]\n${m.content}`).join("\n\n---\n\n")}
                        </pre>
                      </details>
                      <details>
                        <summary className="cursor-pointer text-xs font-semibold" style={{ color: "var(--color-text)" }}>Raw response</summary>
                        <pre className="mt-2 p-3 rounded-[var(--radius-md)] text-xs overflow-x-auto whitespace-pre-wrap" style={{ background: "var(--color-surface-subtle)", color: "var(--color-text)" }}>
                          {trace.raw_response}
                        </pre>
                      </details>
                    </div>
                  )}
                </div>

                {/* Audit trail — Task 6.1's own requirement: every status
                    transition and DLQ write, in chronological order, with
                    worker id where available. Phase 7 adds admin-initiated
                    events (retrigger/override) to this same trail. */}
                <div className="rounded-[var(--radius-lg)] p-5" style={{ background: "var(--color-surface)", border: "1px solid var(--color-border)" }}>
                  <p className="text-xs font-semibold uppercase tracking-wide mb-3" style={{ color: "var(--color-text-subtle)" }}>Event Trail</p>
                  {submission.events.length === 0 ? (
                    <p className="text-sm" style={{ color: "var(--color-text-subtle)" }}>No events recorded yet.</p>
                  ) : (
                    <ol className="space-y-3">
                      {submission.events.map(ev => (
                        <li key={ev.id} className="flex items-start gap-3 text-sm">
                          {ev.event_type.startsWith("ADMIN_") ? (
                            <PencilLine size={14} className="mt-0.5 shrink-0" style={{ color: "#D97706" }} />
                          ) : (
                            <Clock size={14} className="mt-0.5 shrink-0" style={{ color: "var(--color-text-subtle)" }} />
                          )}
                          <div className="min-w-0">
                            <p style={{ color: "var(--color-text)" }}>
                              <span className="font-semibold">{EVENT_LABELS[ev.event_type] ?? ev.event_type}</span>
                              {" — "}{ev.detail}
                            </p>
                            {ev.reason && (
                              <p className="text-xs mt-0.5 italic" style={{ color: "var(--color-text-subtle)" }}>&ldquo;{ev.reason}&rdquo;</p>
                            )}
                            <p className="text-xs mt-0.5 flex items-center gap-2 flex-wrap" style={{ color: "var(--color-text-subtle)" }}>
                              {formatDateTime(ev.occurred_at)}
                              {ev.worker_hostname && (
                                <span className="flex items-center gap-1"><Server size={11} /> {ev.worker_hostname}</span>
                              )}
                              {ev.admin_user_id && (
                                <span className="flex items-center gap-1"><UserCog size={11} /> {ev.admin_user_id.slice(0, 8)}</span>
                              )}
                            </p>
                          </div>
                        </li>
                      ))}
                    </ol>
                  )}
                </div>
              </div>

              <div className="space-y-4">
                <div className="rounded-[var(--radius-lg)] p-5" style={{ background: "var(--color-surface)", border: "1px solid var(--color-border)" }}>
                  <div className="flex items-center justify-between mb-3">
                    <p className="text-xs font-semibold uppercase tracking-wide" style={{ color: "var(--color-text-subtle)" }}>Score</p>
                    {submission.evaluated_by === "admin" && (
                      <span className="text-[10px] font-semibold uppercase tracking-wide px-2 py-0.5 rounded-full" style={{ background: "#FFF4E6", color: "#E8820C" }}>
                        Admin override
                      </span>
                    )}
                  </div>
                  {submission.score !== null ? (
                    <>
                      <p className="text-3xl font-bold mb-2" style={{ color: "var(--color-text)" }}>{submission.score}<span className="text-base font-medium" style={{ color: "var(--color-text-subtle)" }}>/10</span></p>
                      {submission.feedback?.overall && (
                        <p className="text-sm leading-relaxed" style={{ color: "var(--color-text-subtle)" }}>{submission.feedback.overall}</p>
                      )}
                      {/* Per-criterion rubric breakdown — Phase 8, Task
                          8.1's own required Results column. The data has
                          always been in EssayScore.feedback.breakdown
                          (ADR 003's own shape), just never rendered
                          anywhere in the UI until now. */}
                      {submission.feedback?.breakdown && Object.keys(submission.feedback.breakdown).length > 0 && (
                        <div className="mt-3 pt-3 space-y-2" style={{ borderTop: "1px solid var(--color-border)" }}>
                          <p className="text-xs font-semibold uppercase tracking-wide" style={{ color: "var(--color-text-subtle)" }}>Breakdown</p>
                          {Object.entries(submission.feedback.breakdown).map(([criterion, c]) => (
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
                    </>
                  ) : (
                    <p className="text-sm" style={{ color: "var(--color-text-subtle)" }}>Not yet scored.</p>
                  )}
                </div>

                <div className="rounded-[var(--radius-lg)] p-5 text-sm space-y-2" style={{ background: "var(--color-surface)", border: "1px solid var(--color-border)" }}>
                  <p className="text-xs font-semibold uppercase tracking-wide mb-1" style={{ color: "var(--color-text-subtle)" }}>Details</p>
                  <div className="flex justify-between"><span style={{ color: "var(--color-text-subtle)" }}>Student</span><span className="font-mono text-xs" style={{ color: "var(--color-text)" }}>{submission.student_id.slice(0, 8)}</span></div>
                  <div className="flex justify-between"><span style={{ color: "var(--color-text-subtle)" }}>Batch</span><span className="font-mono text-xs" style={{ color: "var(--color-text)" }}>{submission.batch_id.slice(0, 8)}</span></div>
                  <div className="flex justify-between"><span style={{ color: "var(--color-text-subtle)" }}>Submitted</span><span style={{ color: "var(--color-text)" }}>{formatDateTime(submission.created_at)}</span></div>
                  <div className="flex justify-between"><span style={{ color: "var(--color-text-subtle)" }}>Updated</span><span style={{ color: "var(--color-text)" }}>{formatDateTime(submission.updated_at)}</span></div>
                </div>
              </div>
            </div>
          </>
        )}

        {/* Retrigger modal */}
        <Modal isOpen={retriggerOpen} onClose={() => !retriggering && setRetriggerOpen(false)} title="Retrigger Evaluation" maxWidth="sm">
          <div className="space-y-3">
            <p className="text-sm" style={{ color: "var(--color-text-subtle)" }}>
              This deletes any existing score and re-runs the LLM evaluation from scratch. A reason is required for the audit log.
            </p>
            <ReasonField value={retriggerReason} onChange={setRetriggerReason} placeholder="Why are you retriggering this evaluation?" />
            <div className="flex justify-end gap-2 pt-1">
              <Button variant="secondary" size="sm" onClick={() => setRetriggerOpen(false)} disabled={retriggering}>Cancel</Button>
              <Button variant="primary" size="sm" loading={retriggering} onClick={submitRetrigger}>Retrigger</Button>
            </div>
          </div>
        </Modal>

        {/* Manual score override modal — mandatory reason surfaced
            prominently, since this is a deliberate human override of an
            automated system (Task 7.2's own instruction). */}
        <Modal isOpen={overrideOpen} onClose={() => !overriding && setOverrideOpen(false)} title="Manual Score Override" maxWidth="sm">
          <div className="space-y-3">
            <p className="text-sm" style={{ color: "var(--color-text-subtle)" }}>
              Use this only when the LLM has permanently failed to evaluate this essay. This score will be marked as admin-assigned.
            </p>
            <Input
              type="number" min={0} max={10} step={1}
              label="Score (0–10)"
              value={overrideScore}
              onChange={e => setOverrideScore(e.target.value)}
            />
            <div>
              <label className="block text-xs font-medium mb-1" style={{ color: "var(--color-text-subtle)" }}>Feedback</label>
              <ReasonField value={overrideFeedback} onChange={setOverrideFeedback} placeholder="Overall feedback for the student." />
            </div>
            <div>
              <label className="block text-xs font-semibold mb-1" style={{ color: "#D97706" }}>Reason for override (required)</label>
              <ReasonField value={overrideReason} onChange={setOverrideReason} placeholder="Why is a manual override needed here?" />
            </div>
            <div className="flex justify-end gap-2 pt-1">
              <Button variant="secondary" size="sm" onClick={() => setOverrideOpen(false)} disabled={overriding}>Cancel</Button>
              <Button variant="warning" size="sm" loading={overriding} onClick={submitOverride}>Save Override</Button>
            </div>
          </div>
        </Modal>

        {/* General score override modal (Phase 8, Task 8.1) — corrects an
            ALREADY-EXISTING score (a student appeal, a human regrade),
            distinct from the DLQ-recovery modal above. Mandatory reason
            surfaced prominently for the same reason as that one. */}
        <Modal isOpen={generalOverrideOpen} onClose={() => !generalOverriding && setGeneralOverrideOpen(false)} title="Correct Score" maxWidth="sm">
          <div className="space-y-3">
            <p className="text-sm" style={{ color: "var(--color-text-subtle)" }}>
              Corrects this submission's existing score — for a student appeal or a human regrade decision. This score will be marked as admin-assigned.
            </p>
            <Input
              type="number" min={0} max={10} step={1}
              label="New score (0–10)"
              value={generalOverrideScore}
              onChange={e => setGeneralOverrideScore(e.target.value)}
            />
            <div>
              <label className="block text-xs font-medium mb-1" style={{ color: "var(--color-text-subtle)" }}>Feedback</label>
              <ReasonField value={generalOverrideFeedback} onChange={setGeneralOverrideFeedback} placeholder="Overall feedback for the student." />
            </div>
            <div>
              <label className="block text-xs font-semibold mb-1" style={{ color: "#D97706" }}>Reason for correction (required, max 500 chars)</label>
              <ReasonField value={generalOverrideReason} onChange={setGeneralOverrideReason} placeholder="Why is this score being corrected?" />
            </div>
            <div className="flex justify-end gap-2 pt-1">
              <Button variant="secondary" size="sm" onClick={() => setGeneralOverrideOpen(false)} disabled={generalOverriding}>Cancel</Button>
              <Button variant="warning" size="sm" loading={generalOverriding} onClick={submitGeneralOverride}>Save Correction</Button>
            </div>
          </div>
        </Modal>
      </PageWrapper>
    </AdminLayout>
  );
}
