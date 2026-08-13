"use client";

import { useEffect, useState, useCallback, useRef, useMemo } from "react";
import { useParams, useRouter } from "next/navigation";
import { Clock, WifiOff, CheckCircle2, Maximize, ShieldAlert } from "lucide-react";
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

export default function StudentExamPage() {
  const { assignment_id } = useParams<{ assignment_id: string }>();
  const router = useRouter();
  const toast = useToast();

  const [sessionId, setSessionId] = useState<string | null>(null);
  const [sessionStatus, setSessionStatus] = useState<string | null>(null);
  const [questions, setQuestions] = useState<StudentQuestion[]>([]);
  const [loading, setLoading] = useState(true);
  const [activeIndex, setActiveIndex] = useState(0);
  const [answers, setAnswers] = useState<Record<string, string[]>>({}); // questionId -> selected
  const [savingState, setSavingState] = useState<Record<string, "saving" | "saved" | "queued">>({});
  const [confirmSubmit, setConfirmSubmit] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [result, setResult] = useState<StudentSubmitResponse | null>(null);
  const autoSubmitTriggered = useRef(false);

  const { saveAnswer, isReconnecting } = useOfflineAnswerQueue(sessionId ?? "");
  const { secondsRemaining, isSyncFailing } = useServerTimeSync();
  const { isFullscreen, requestFullscreen } = useActivityCapture(
    sessionStatus === "IN_PROGRESS" ? sessionId : null
  );
  const [fullscreenPromptDismissed, setFullscreenPromptDismissed] = useState(false);

  // Re-arm the prompt every time fullscreen is (re-)entered, so exiting
  // again later shows it fresh rather than staying dismissed forever
  // after the first time.
  useEffect(() => {
    if (isFullscreen) setFullscreenPromptDismissed(false);
  }, [isFullscreen]);

  // ── Load: start-session (idempotent) → fetch questions ───────────────────
  useEffect(() => {
    let cancelled = false;

    async function load() {
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
  }, [assignment_id]);

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

  const handleSubmit = useCallback(async () => {
    if (!sessionId) return;
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
    }
  }, [sessionId, toast]);

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

        {/* ── Fullscreen nudge — UX prompt, not a hard block ────────────── */}
        {!isFullscreen && !fullscreenPromptDismissed && (
          <div
            className="flex items-start gap-3 px-4 py-3.5 rounded-[var(--radius-lg)] mb-5"
            style={{ background: "#FFF4E6", border: "1px solid #FDE0B0" }}
          >
            <ShieldAlert size={18} style={{ color: "#B45309", flexShrink: 0, marginTop: 2 }} />
            <div className="flex-1 min-w-0">
              <p className="text-sm font-semibold" style={{ color: "#92400E" }}>
                Stay in fullscreen for this exam
              </p>
              <p className="text-xs mt-1 leading-relaxed" style={{ color: "#92400E" }}>
                For academic integrity, this exam monitors tab switches, window focus, fullscreen exits,
                and copy/paste while your session is active. Staying in fullscreen is recommended but not required.
              </p>
              <div className="flex gap-2 mt-2.5">
                <Button variant="warning" size="sm" leftIcon={<Maximize size={13} />} onClick={requestFullscreen}>
                  Enter Fullscreen
                </Button>
                <Button variant="secondary" size="sm" onClick={() => setFullscreenPromptDismissed(true)}>
                  Continue without
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
    </StudentLayout>
  );
}
