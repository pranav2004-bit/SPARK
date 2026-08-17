"use client";

import { useEffect, useState, useCallback, useRef, useMemo } from "react";
import { useParams, useRouter } from "next/navigation";
import { Clock, WifiOff, CheckCircle2, Maximize, ShieldAlert, AlertTriangle } from "lucide-react";
import { StudentLayout } from "@/components/layout/StudentLayout";
import { PageWrapper } from "@/components/layout/PageWrapper";
import { Button } from "@/components/ui/Button";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import { ImageLoader } from "@/components/ui/ImageLoader";
import { GlobalLoader } from "@/components/ui/GlobalLoader";
import { useToast } from "@/components/ui/Toast";
import { useOfflineAnswerQueue } from "@/hooks/useOfflineAnswerQueue";
import { useServerTimeSync } from "@/hooks/useServerTimeSync";
import { useActivityCapture } from "@/hooks/useActivityCapture";
import api, { getErrorMessage } from "@/lib/api";
import type {
  ApiSuccess, StudentStartSessionResponse, StudentSessionQuestionsResponse,
  StudentQuestion, StudentSubmitResponse,
} from "@/types";

function formatCountdown(totalSeconds: number): string {
  const h = Math.floor(totalSeconds / 3600);
  const m = Math.floor((totalSeconds % 3600) / 60);
  const s = totalSeconds % 60;
  const pad = (n: number) => String(n).padStart(2, "0");
  return h > 0 ? `${h}:${pad(m)}:${pad(s)}` : `${m}:${pad(s)}`;
}

// Mirrors scoring.py's TAB_SWITCH_THRESHOLD / FULLSCREEN_EXIT_THRESHOLD
// exactly (backend: "> 5" and "> 3", i.e. the 6th switch / 4th exit trips
// it) — kept in sync by convention since neither constant is exposed via
// any API. This is a client-side UX consequence layered on top of the
// server's own malpractice flagging, not a replacement for it: the server
// computes malpractice_flag independently, from its own logged event
// counts, at finalize time, regardless of whether this lockout ever fires.
const TAB_SWITCH_LIMIT = 5;
const FULLSCREEN_EXIT_LIMIT = 3;
const LOCKOUT_COUNTDOWN_SECONDS = 5;

export default function StudentExamPage() {
  const { assignment_id } = useParams<{ assignment_id: string }>();
  const router = useRouter();
  const toast = useToast();

  // ── Entry gate — exam doesn't start (no start-session call, no server
  // timer) until the student has actually entered fullscreen. ─────────────
  const [examEntered, setExamEntered] = useState(false);
  const [enteringFullscreen, setEnteringFullscreen] = useState(false);
  const [fullscreenError, setFullscreenError] = useState("");

  const [sessionId, setSessionId] = useState<string | null>(null);
  const [sessionStatus, setSessionStatus] = useState<string | null>(null);
  const [questions, setQuestions] = useState<StudentQuestion[]>([]);
  const [loading, setLoading] = useState(false);
  const [activeIndex, setActiveIndex] = useState(0);
  const [answers, setAnswers] = useState<Record<string, string[]>>({}); // questionId -> selected
  const [savingState, setSavingState] = useState<Record<string, "saving" | "saved" | "queued">>({});
  const [confirmSubmit, setConfirmSubmit] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [result, setResult] = useState<StudentSubmitResponse | null>(null);
  const autoSubmitTriggered = useRef(false);

  const { saveAnswer, isReconnecting } = useOfflineAnswerQueue(sessionId ?? "");
  const { secondsRemaining, isSyncFailing } = useServerTimeSync();
  const {
    isFullscreen, requestFullscreen, tabSwitchCount, fullscreenExitCount, screenshotAttempts,
  } = useActivityCapture(sessionStatus === "IN_PROGRESS" ? sessionId : null);
  const [fullscreenPromptDismissed, setFullscreenPromptDismissed] = useState(false);

  // Reached once either count crosses its limit — drives the blocking,
  // non-dismissable "auto-submitting" overlay with its own countdown.
  const [lockout, setLockout] = useState<{ label: string; secondsLeft: number } | null>(null);

  // Re-arm the prompt every time fullscreen is (re-)entered, so exiting
  // again later shows it fresh rather than staying dismissed forever
  // after the first time.
  useEffect(() => {
    if (isFullscreen) setFullscreenPromptDismissed(false);
  }, [isFullscreen]);

  // Warn before an accidental tab close / reload / back-navigation while an
  // exam is actually in progress — answers themselves are never lost
  // (useOfflineAnswerQueue persists them locally and syncs on reconnect),
  // but a student who isn't sure whether their last click was saved
  // shouldn't be one misclick away from losing their place mid-exam.
  // Browsers ignore the custom message and show their own generic prompt;
  // setting returnValue is what actually triggers that native dialog.
  useEffect(() => {
    if (sessionStatus !== "IN_PROGRESS") return;
    function handleBeforeUnload(e: BeforeUnloadEvent) {
      e.preventDefault();
      e.returnValue = "";
    }
    window.addEventListener("beforeunload", handleBeforeUnload);
    return () => window.removeEventListener("beforeunload", handleBeforeUnload);
  }, [sessionStatus]);

  // Clicking "Enter Fullscreen & Start Exam" on the gate screen below.
  // Only on success does examEntered flip true, which is what lets the
  // load() effect fire and call start-session — so the server-side timer
  // (computed at session creation) genuinely doesn't start until the
  // student is in fullscreen. requestFullscreen can fail/reject (denied
  // permission, unsupported browser, iframe restrictions) — that's handled
  // as an explicit error state with its own "continue without" escape
  // hatch below, rather than silently swallowed, so a student on a
  // genuinely unsupported device isn't permanently locked out.
  async function handleEnterExam() {
    setFullscreenError("");
    setEnteringFullscreen(true);
    try {
      await requestFullscreen();
      setExamEntered(true);
    } catch {
      setFullscreenError(
        "Fullscreen couldn't be enabled on this device or browser. You can continue without it, " +
        "but tab switches, window changes, and fullscreen exits are still monitored and limited."
      );
    } finally {
      setEnteringFullscreen(false);
    }
  }

  // ── Load: start-session (idempotent) → fetch questions ───────────────────
  // Gated on examEntered — never fires until the fullscreen gate above has
  // been passed (or explicitly bypassed via its escape hatch).
  useEffect(() => {
    if (!examEntered) return;
    let cancelled = false;

    async function load() {
      setLoading(true);
      try {
        const startRes = await api.post<ApiSuccess<StudentStartSessionResponse>>(
          `/assessments/student/assignments/${assignment_id}/start-session/`
        );
        if (cancelled) return;
        const { session_id, status } = startRes.data.data;
        setSessionId(session_id);
        setSessionStatus(status);

        if (status === "SUBMITTED" || status === "AUTO_SUBMITTED") {
          setLoading(false);
          return;
        }

        const qRes = await api.get<ApiSuccess<StudentSessionQuestionsResponse>>(
          `/assessments/student/sessions/${session_id}/questions/`
        );
        if (cancelled) return;
        setQuestions(qRes.data.data.questions);
        const initialAnswers: Record<string, string[]> = {};
        qRes.data.data.questions.forEach(q => { initialAnswers[q.id] = q.selected_option_ids; });
        setAnswers(initialAnswers);
      } catch (err) {
        if (cancelled) return;
        toast.error(getErrorMessage(err));
        router.push("/students/assessments");
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    load();
    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [assignment_id, examEntered]);

  const activeQuestion = questions[activeIndex] as StudentQuestion | undefined;

  const handleSelect = useCallback((questionId: string, optionId: string, mcqType: string) => {
    setAnswers(prev => {
      const current = new Set(prev[questionId] ?? []);
      if (mcqType === "single") {
        current.clear();
        current.add(optionId);
      } else {
        if (current.has(optionId)) current.delete(optionId);
        else current.add(optionId);
      }
      const next = { ...prev, [questionId]: Array.from(current) };

      setSavingState(s => ({ ...s, [questionId]: "saving" }));
      saveAnswer(questionId, next[questionId])
        .then(outcome => setSavingState(s => ({ ...s, [questionId]: outcome })))
        .catch(() => { /* real rejection — session no longer writable; leave state as "saving" cleared below */
          setSavingState(s => { const copy = { ...s }; delete copy[questionId]; return copy; });
        });

      return next;
    });
  }, [saveAnswer]);

  // A ref, not the `submitting` state, guards re-entrancy — state updates
  // are batched/async, so two callers landing in the same tick (e.g. the
  // countdown timer hitting 0 right as the lockout overlay also reaches 0)
  // could both pass a `submitting` check before either had actually set it.
  // The backend's own race-safe finalize already makes a genuine double
  // POST harmless (verified earlier), but this avoids firing the second
  // network call — and the resulting "already submitted" error toast —
  // at all.
  const submitInFlight = useRef(false);

  const handleSubmit = useCallback(async () => {
    if (!sessionId || submitInFlight.current) return;
    submitInFlight.current = true;
    setSubmitting(true);
    try {
      const res = await api.post<ApiSuccess<StudentSubmitResponse>>(
        `/assessments/student/sessions/${sessionId}/submit/`
      );
      setResult(res.data.data);
      setSessionStatus(res.data.data.status);
    } catch (err) {
      toast.error(getErrorMessage(err));
    } finally {
      setSubmitting(false);
      setConfirmSubmit(false);
      submitInFlight.current = false;
    }
  }, [sessionId, toast]);

  // ── Tab-switch / fullscreen-exit graduated warnings + hard lockout ──────
  // Every occurrence below the limit shows a warning toast naming how many
  // are left; crossing the limit (same boundary as the backend's own
  // malpractice check — see TAB_SWITCH_LIMIT/FULLSCREEN_EXIT_LIMIT above)
  // starts the lockout overlay instead. setLockout(prev => prev ?? ...)
  // guards against a second trigger (e.g. both counts crossing near
  // simultaneously) restarting an already-running countdown.
  useEffect(() => {
    if (tabSwitchCount === 0 || sessionStatus !== "IN_PROGRESS") return;
    if (tabSwitchCount > TAB_SWITCH_LIMIT) {
      setLockout(prev => prev ?? { label: "tab switches", secondsLeft: LOCKOUT_COUNTDOWN_SECONDS });
    } else {
      toast.warning(
        `Tab switch detected — warning ${tabSwitchCount} of ${TAB_SWITCH_LIMIT}. ` +
        `Reaching the limit will auto-submit your exam.`
      );
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tabSwitchCount]);

  useEffect(() => {
    if (fullscreenExitCount === 0 || sessionStatus !== "IN_PROGRESS") return;
    if (fullscreenExitCount > FULLSCREEN_EXIT_LIMIT) {
      setLockout(prev => prev ?? { label: "fullscreen exits", secondsLeft: LOCKOUT_COUNTDOWN_SECONDS });
    } else {
      toast.warning(
        `Fullscreen exit detected — warning ${fullscreenExitCount} of ${FULLSCREEN_EXIT_LIMIT}. ` +
        `Reaching the limit will auto-submit your exam.`
      );
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [fullscreenExitCount]);

  // Best-effort only — see useActivityCapture's own doc comment for why a
  // browser can never reliably detect a screenshot in general. This is
  // strictly a UX warning, not tied to the lockout mechanism above.
  useEffect(() => {
    if (screenshotAttempts === 0 || sessionStatus !== "IN_PROGRESS") return;
    toast.warning("Screenshot attempt detected. Screenshots are not permitted during this exam.");
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [screenshotAttempts]);

  // Ticks the lockout overlay's countdown down to 0, then actually submits
  // (reusing the exact same submit path a manual click uses) and redirects
  // to the student's assessments home once that call settles.
  useEffect(() => {
    if (!lockout) return;
    if (lockout.secondsLeft <= 0) {
      handleSubmit().finally(() => router.push("/students/assessments"));
      return;
    }
    const t = setTimeout(() => {
      setLockout(l => (l ? { ...l, secondsLeft: l.secondsLeft - 1 } : l));
    }, 1000);
    return () => clearTimeout(t);
  }, [lockout, handleSubmit, router]);

  // Auto-submit attempt once the local countdown hits 0 — the server sweep
  // will catch it within ~20s regardless, but attempting an immediate
  // submit gives a snappier transition when it's this student's own
  // deadline (not a race against another cause of expiry).
  useEffect(() => {
    if (secondsRemaining === 0 && !autoSubmitTriggered.current && sessionStatus === "IN_PROGRESS") {
      autoSubmitTriggered.current = true;
      handleSubmit();
    }
  }, [secondsRemaining, sessionStatus, handleSubmit]);

  const answeredCount = useMemo(
    () => questions.filter(q => (answers[q.id]?.length ?? 0) > 0).length,
    [questions, answers]
  );

  // ── Entry gate screen — shown before start-session is ever called ───────
  if (!examEntered) {
    return (
      <StudentLayout>
        <PageWrapper className="max-w-lg py-16">
          <div className="text-center">
            <div className="w-16 h-16 rounded-full flex items-center justify-center mx-auto mb-5"
              style={{ background: "#EFF6FF" }}>
              <Maximize size={28} style={{ color: "#2563EB" }} />
            </div>
            <h1 className="text-xl font-bold mb-2" style={{ color: "var(--color-text)" }}>
              Continue to your exam
            </h1>
            <p className="text-sm mb-6 leading-relaxed" style={{ color: "var(--color-text-muted)" }}>
              This exam runs in fullscreen. If this is your first time opening it, your timer starts
              the moment you enter fullscreen — not before. Tab switches, fullscreen exits, and
              copy/paste are monitored and limited for the rest of the exam.
            </p>
            {fullscreenError && (
              <p className="text-xs mb-4 leading-relaxed" style={{ color: "var(--color-danger)" }}>
                {fullscreenError}
              </p>
            )}
            <div className="flex flex-col items-center gap-2.5">
              <Button
                variant="primary" leftIcon={<Maximize size={15} />}
                loading={enteringFullscreen} onClick={handleEnterExam}
              >
                Enter Fullscreen & Continue
              </Button>
              {fullscreenError && (
                <Button variant="secondary" size="sm" onClick={() => setExamEntered(true)}>
                  Continue without fullscreen
                </Button>
              )}
            </div>
          </div>
        </PageWrapper>
      </StudentLayout>
    );
  }

  if (loading) return <GlobalLoader />;

  // ── Already-finished view ─────────────────────────────────────────────────
  if (sessionStatus === "SUBMITTED" || sessionStatus === "AUTO_SUBMITTED" || result) {
    const finalResult = result;
    return (
      <StudentLayout>
        <PageWrapper className="max-w-lg py-16">
          <div className="text-center">
            <div className="w-16 h-16 rounded-full flex items-center justify-center mx-auto mb-5"
              style={{ background: "#F0FDF4" }}>
              <CheckCircle2 size={30} style={{ color: "#16A34A" }} />
            </div>
            <h1 className="text-xl font-bold mb-2" style={{ color: "var(--color-text)" }}>
              {sessionStatus === "AUTO_SUBMITTED" ? "Time's up — Submitted automatically" : "Submitted"}
            </h1>
            {finalResult && finalResult.score !== null && (
              <p className="text-sm mb-6" style={{ color: "var(--color-text-muted)" }}>
                You scored <strong>{finalResult.score}</strong> out of <strong>{finalResult.total_marks}</strong>.
              </p>
            )}
            {finalResult && finalResult.results_visible === false && (
              <p className="text-sm mb-6" style={{ color: "var(--color-text-subtle)" }}>
                Your result will be shared by your instructor.
              </p>
            )}
            <Button variant="primary" onClick={() => router.push("/students/assessments")}>
              Back to Assessments
            </Button>
          </div>
        </PageWrapper>
      </StudentLayout>
    );
  }

  if (!activeQuestion) return null;

  const lowTime = secondsRemaining !== null && secondsRemaining <= 60;

  return (
    <StudentLayout>
      <PageWrapper className="max-w-5xl select-none">
        {/* ── Top bar: countdown + connectivity ─────────────────────────── */}
        <div className="flex items-center justify-between gap-3 mb-5 flex-wrap">
          <div
            className="inline-flex items-center gap-2 px-3.5 py-2 rounded-[var(--radius-lg)] font-mono text-base font-bold"
            style={{
              background: lowTime ? "#FEF2F2" : "#EFF6FF",
              color: lowTime ? "#DC2626" : "#2563EB",
              border: `1px solid ${lowTime ? "#FECACA" : "#BFDBFE"}`,
            }}
          >
            <Clock size={16} />
            {secondsRemaining !== null ? formatCountdown(secondsRemaining) : "—:—"}
          </div>

          <div className="flex items-center gap-2">
            {(isReconnecting || isSyncFailing) && (
              <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold"
                style={{ background: "#FFF4E6", color: "#E8820C" }}>
                <WifiOff size={12} /> Reconnecting…
              </span>
            )}
            <span className="text-xs" style={{ color: "var(--color-text-subtle)" }}>
              {answeredCount}/{questions.length} answered
            </span>
            <Button variant="primary" size="sm" onClick={() => setConfirmSubmit(true)}>
              Submit Exam
            </Button>
          </div>
        </div>

        {/* ── Fullscreen nudge — shown again if the student exits fullscreen
            mid-exam. Not a hard block on its own (they get graduated
            warnings first, per the effect above), but exits do count toward
            the same limit that triggers the lockout overlay below. ────── */}
        {!isFullscreen && !fullscreenPromptDismissed && (
          <div
            className="flex items-start gap-3 px-4 py-3.5 rounded-[var(--radius-lg)] mb-5"
            style={{ background: "#FFF4E6", border: "1px solid #FDE0B0" }}
          >
            <ShieldAlert size={18} style={{ color: "#B45309", flexShrink: 0, marginTop: 2 }} />
            <div className="flex-1 min-w-0">
              <p className="text-sm font-semibold" style={{ color: "#92400E" }}>
                You've left fullscreen
              </p>
              <p className="text-xs mt-1 leading-relaxed" style={{ color: "#92400E" }}>
                This exam monitors tab switches, window focus, fullscreen exits, and copy/paste.
                Fullscreen exits are limited to {FULLSCREEN_EXIT_LIMIT} — going over auto-submits your exam.
              </p>
              <div className="flex gap-2 mt-2.5">
                <Button variant="warning" size="sm" leftIcon={<Maximize size={13} />} onClick={() => { requestFullscreen().catch(() => {}); }}>
                  Return to Fullscreen
                </Button>
                <Button variant="secondary" size="sm" onClick={() => setFullscreenPromptDismissed(true)}>
                  Dismiss
                </Button>
              </div>
            </div>
          </div>
        )}

        <div className="lg:flex lg:gap-6 lg:items-start">
          {/* ── Question navigator ────────────────────────────────────────── */}
          <div className="lg:w-56 lg:shrink-0 mb-5 lg:mb-0">
            <div className="grid grid-cols-8 sm:grid-cols-10 lg:grid-cols-5 gap-2">
              {questions.map((q, i) => {
                const answered = (answers[q.id]?.length ?? 0) > 0;
                const isActive = i === activeIndex;
                return (
                  <button
                    key={q.id}
                    onClick={() => setActiveIndex(i)}
                    className="h-9 w-9 rounded-[var(--radius-md)] text-xs font-semibold flex items-center justify-center transition-colors"
                    style={{
                      background: isActive ? "var(--color-accent)" : answered ? "#F0FDF4" : "var(--color-surface)",
                      color: isActive ? "#fff" : answered ? "#16A34A" : "var(--color-text-muted)",
                      border: `1.5px solid ${isActive ? "var(--color-accent)" : answered ? "#BBF7D0" : "var(--color-border)"}`,
                    }}
                  >
                    {q.question_number}
                  </button>
                );
              })}
            </div>
          </div>

          {/* ── Active question ───────────────────────────────────────────── */}
          <div className="flex-1 min-w-0">
            <div className="rounded-[var(--radius-xl)] p-5 sm:p-6" style={{ background: "var(--color-surface)", border: "1px solid var(--color-border)" }}>
              <div className="flex items-center justify-between mb-4">
                <p className="text-xs font-semibold uppercase tracking-widest" style={{ color: "var(--color-text-subtle)" }}>
                  Question {activeQuestion.question_number} · {activeQuestion.marks} mark{activeQuestion.marks === 1 ? "" : "s"}
                </p>
                {savingState[activeQuestion.id] === "saving" && (
                  <span className="text-xs" style={{ color: "var(--color-text-subtle)" }}>Saving…</span>
                )}
                {savingState[activeQuestion.id] === "saved" && (
                  <span className="text-xs" style={{ color: "#16A34A" }}>Saved</span>
                )}
                {savingState[activeQuestion.id] === "queued" && (
                  <span className="text-xs" style={{ color: "#E8820C" }}>Saved locally — will sync</span>
                )}
              </div>

              {(activeQuestion.question_content_type === "text" || activeQuestion.question_content_type === "both") && (
                <p className="text-base leading-relaxed whitespace-pre-wrap mb-4" style={{ color: "var(--color-text)" }}>
                  {activeQuestion.question_text}
                </p>
              )}
              {(activeQuestion.question_content_type === "image" || activeQuestion.question_content_type === "both") && activeQuestion.question_image_url && (
                <div className="mb-4 rounded-[var(--radius-md)] overflow-hidden" style={{ border: "1px solid var(--color-border)" }}>
                  <ImageLoader src={activeQuestion.question_image_url} alt="Question" maxHeight={360} />
                </div>
              )}

              <p className="text-xs font-semibold uppercase tracking-widest mb-3" style={{ color: "var(--color-text-subtle)" }}>
                {activeQuestion.mcq_type === "single" ? "Select one answer" : "Select all that apply"}
              </p>

              <div className="space-y-2">
                {activeQuestion.options.map(opt => {
                  const selected = (answers[activeQuestion.id] ?? []).includes(opt.id);
                  return (
                    <button
                      key={opt.id}
                      type="button"
                      onClick={() => handleSelect(activeQuestion.id, opt.id, activeQuestion.mcq_type)}
                      className="w-full flex items-start gap-3 px-4 py-3.5 rounded-[var(--radius-md)] text-left transition-all"
                      style={{
                        background: selected ? "#EFF6FF" : "#fff",
                        border: `1.5px solid ${selected ? "#93C5FD" : "var(--color-border)"}`,
                        color: selected ? "#1D4ED8" : "var(--color-text-muted)",
                      }}
                    >
                      <span className="shrink-0 w-7 h-7 rounded-full flex items-center justify-center text-xs font-bold mt-0.5"
                        style={{ background: selected ? "#2563EB" : "var(--color-primary-light)", color: selected ? "#fff" : "var(--color-primary)" }}>
                        {opt.label}
                      </span>
                      <span className="text-sm leading-relaxed flex-1 pt-1">
                        {opt.text}
                        {opt.image_url && (
                          <div className="mt-2 rounded-[var(--radius-md)] overflow-hidden max-w-xs" style={{ border: "1px solid var(--color-border)" }}>
                            <ImageLoader src={opt.image_url} alt={`Option ${opt.label}`} maxHeight={160} />
                          </div>
                        )}
                      </span>
                    </button>
                  );
                })}
              </div>
            </div>

            {/* Prev / Next */}
            <div className="flex items-center justify-between mt-5">
              <Button
                variant="secondary"
                disabled={activeIndex === 0}
                onClick={() => setActiveIndex(i => Math.max(0, i - 1))}
              >
                Previous
              </Button>
              <Button
                variant="secondary"
                disabled={activeIndex === questions.length - 1}
                onClick={() => setActiveIndex(i => Math.min(questions.length - 1, i + 1))}
              >
                Next
              </Button>
            </div>
          </div>
        </div>
      </PageWrapper>

      <ConfirmDialog
        isOpen={confirmSubmit}
        onClose={() => setConfirmSubmit(false)}
        onConfirm={handleSubmit}
        title="Submit exam?"
        message={`You have answered ${answeredCount} of ${questions.length} questions. Once submitted, you cannot change your answers. This cannot be undone.`}
        confirmLabel="Submit"
        confirmVariant="warning"
        loading={submitting}
      />

      {/* ── Lockout overlay — reaching either limit lands here. No close
          button, no Escape-to-dismiss (unlike Modal): the whole point is
          that this can't be dismissed, only counted down through. ────── */}
      {lockout && (
        <div
          className="fixed inset-0 z-[200] flex items-center justify-center p-4"
          style={{ background: "rgba(15,23,42,0.75)" }}
          role="alertdialog"
          aria-modal="true"
        >
          <div
            className="w-full max-w-sm rounded-[var(--radius-xl)] p-6 text-center"
            style={{ background: "#fff", boxShadow: "var(--shadow-xl)" }}
          >
            <div className="w-14 h-14 rounded-full flex items-center justify-center mx-auto mb-4"
              style={{ background: "#FEF2F2" }}>
              <AlertTriangle size={26} style={{ color: "#DC2626" }} />
            </div>
            <h2 className="text-lg font-bold mb-2" style={{ color: "var(--color-text)" }}>
              You've reached the limit
            </h2>
            <p className="text-sm mb-5 leading-relaxed" style={{ color: "var(--color-text-muted)" }}>
              Too many {lockout.label} were detected. Your assessment is being submitted automatically.
            </p>
            <div
              className="w-14 h-14 rounded-full flex items-center justify-center mx-auto font-mono text-xl font-bold"
              style={{ background: "#FEF2F2", color: "#DC2626", border: "2px solid #FECACA" }}
            >
              {lockout.secondsLeft}
            </div>
          </div>
        </div>
      )}
    </StudentLayout>
  );
}
