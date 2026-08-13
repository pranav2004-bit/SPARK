"use client";

import { useEffect, useRef, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import {
  ListChecks, AlignLeft, ChevronRight,
  ChevronLeft, Eye, Lightbulb, CheckCircle2, XCircle, X,
} from "lucide-react";
import { StudentLayout } from "@/components/layout/StudentLayout";
import { PageWrapper } from "@/components/layout/PageWrapper";
import { Button } from "@/components/ui/Button";
import { Modal } from "@/components/ui/Modal";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import { useToast } from "@/components/ui/Toast";
import { ImageLoader } from "@/components/ui/ImageLoader";
import { LoadingSpinner } from "@/components/ui/Skeleton";
import { GlobalLoader } from "@/components/ui/GlobalLoader";
import api, { getErrorMessage } from "@/lib/api";
import type {
  PracticeModule, PracticeSection, PracticeQuestion,
  PracticeQuestionOption, ProgressStatus, McqType,
} from "@/types";

// ── Design tokens ─────────────────────────────────────────────────────────────
const T = {
  text:    "var(--color-text)",
  muted:   "var(--color-text-muted)",
  subtle:  "var(--color-text-subtle)",
  border:  "var(--color-border)",
  surface: "var(--color-surface-secondary)",
  white:   "#ffffff",
};

// ── Types ─────────────────────────────────────────────────────────────────────
interface AttemptInfo {
  attempt_count:     number;
  last_is_correct:   boolean;
  correct_option_ids: string[];
}

interface QuestionWithProgress extends PracticeQuestion {
  progress_status: ProgressStatus;
}

interface QuestionDetailData {
  question:          QuestionWithProgress;
  section:           PracticeSection;
  module:            PracticeModule | null;
  options:           PracticeQuestionOption[];
  prev_question_id:  string | null;
  next_question_id:  string | null;
  attempt_info:      AttemptInfo | null;
}

interface SubmitResult {
  is_correct:         boolean;
  attempt_number:     number;
  correct_option_ids: string[];
}

// ── FIB blank renderer ────────────────────────────────────────────────────────
function QuestionTextRenderer({ text }: { text: string }) {
  const parts = text.split("___");
  return (
    <p className="text-base sm:text-lg leading-relaxed whitespace-pre-wrap" style={{ color: T.text }}>
      {parts.map((part, i) => (
        <span key={i}>
          {part}
          {i < parts.length - 1 && (
            <span
              className="inline-block mx-1 align-bottom font-semibold"
              style={{
                minWidth: 80, borderBottom: `2.5px solid ${T.muted}`,
                color: "transparent", userSelect: "none",
              }}
              aria-hidden="true"
            >
              {"_____"}
            </span>
          )}
        </span>
      ))}
    </p>
  );
}

// ── Question image ────────────────────────────────────────────────────────────
function QuestionImage({ src, alt = "Question diagram" }: { src: string; alt?: string }) {
  return (
    <div className="rounded-[var(--radius-md)] overflow-hidden"
      style={{ border: `1px solid ${T.border}` }}>
      <ImageLoader src={src} alt={alt} maxHeight={400} background="#f8f9fa" skeletonHeight={200} />
    </div>
  );
}

// ── Question body (shared by MCQ and FIB) ─────────────────────────────────────
function QuestionBody({ question }: { question: PracticeQuestion }) {
  const qct       = question.question_content_type ?? "text";
  const showText  = qct === "text"  || qct === "both";
  const showImage = qct === "image" || qct === "both";
  const hasContent = (showText && !!question.question_text) ||
                     (showImage && !!question.question_image_url);

  return (
    <div className="rounded-[var(--radius-lg)] p-5 sm:p-6"
      style={{ background: T.white, border: `1px solid ${T.border}` }}>
      <p className="text-xs font-semibold uppercase tracking-widest mb-4" style={{ color: T.subtle }}>
        Question
      </p>
      {hasContent ? (
        <div className="space-y-4">
          {showText && question.question_text && (
            <QuestionTextRenderer text={question.question_text} />
          )}
          {showImage && (
            question.question_image_url
              ? <QuestionImage src={question.question_image_url} />
              : (
                <div className="flex items-center justify-center py-8 rounded-[var(--radius-md)]"
                  style={{ background: T.surface, border: `1px dashed ${T.border}` }}>
                  <p className="text-sm italic" style={{ color: T.subtle }}>
                    Question image is being prepared.
                  </p>
                </div>
              )
          )}
        </div>
      ) : (
        <p className="text-sm italic" style={{ color: T.subtle }}>
          Question content has not been authored yet.
        </p>
      )}
    </div>
  );
}

// ── MCQ Option button ─────────────────────────────────────────────────────────
interface OptionBtnProps {
  option:      PracticeQuestionOption;
  selected:    boolean;
  correct:     boolean | null;  // null = not revealed yet
  disabled:    boolean;
  mcqType:     McqType;
  onClick:     () => void;
}
function OptionBtn({ option, selected, correct, disabled, mcqType, onClick }: OptionBtnProps) {
  // Colour states:
  // not revealed + not selected: default gray
  // not revealed + selected:     accent blue
  // revealed correct:            green (regardless of selected)
  // revealed incorrect + selected: red
  let bg      = T.white;
  let border  = T.border;
  let color   = T.muted;
  let labelBg    = "var(--color-primary-light)";  // #e8eef5 — light navy tint, clearly readable
  let labelColor = "var(--color-primary)";         // #1A3150 — brand navy letter

  if (correct === true) {
    // This option IS correct — show green
    bg = "#F0FDF4"; border = "#BBF7D0"; color = "#166534";
    labelBg = "#16A34A"; labelColor = "#fff";
  } else if (correct === false && selected) {
    // Wrong selection
    bg = "#FEF2F2"; border = "#FECACA"; color = "#991B1B";
    labelBg = "#DC2626"; labelColor = "#fff";
  } else if (selected && correct === null) {
    // Selected, not yet revealed
    bg = "#EFF6FF"; border = "#93C5FD"; color = "#1D4ED8";
    labelBg = "#2563EB"; labelColor = "#fff";
  }

  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className="w-full flex items-start gap-3 px-4 py-3.5 rounded-[var(--radius-md)] text-left transition-all disabled:cursor-default"
      style={{ background: bg, border: `1.5px solid ${border}`, color }}
      onMouseEnter={e => {
        if (!disabled && correct === null && !selected)
          e.currentTarget.style.borderColor = T.muted;
      }}
      onMouseLeave={e => {
        if (!disabled && correct === null && !selected)
          e.currentTarget.style.borderColor = T.border;
      }}
    >
      {/* Label circle */}
      <span className="shrink-0 w-7 h-7 rounded-full flex items-center justify-center text-xs font-bold mt-0.5"
        style={{ background: labelBg, color: labelColor }}>
        {option.label}
      </span>
      {/* Option text */}
      <span className="text-sm leading-relaxed flex-1 pt-1" style={{ color }}>
        {option.text || <em style={{ color: T.subtle }}>No text</em>}
      </span>
    </button>
  );
}

// ── Explanation panel ─────────────────────────────────────────────────────────
function ExplanationPanel({ question, onClose }: { question: PracticeQuestion; onClose: () => void }) {
  const showText  = question.explanation_type === "text"  || question.explanation_type === "both";
  const showImage = question.explanation_type === "image" || question.explanation_type === "both";

  return (
    <div className="rounded-[var(--radius-lg)] p-5 sm:p-6 space-y-4"
      style={{
        background:  "#FFFBEB",
        border:      "1px solid #FCD34D",
        borderLeft:  "4px solid #F59E0B",
        boxShadow:   "var(--shadow-sm)",
      }}>
      <div className="flex items-center justify-between mb-1">
        <div className="flex items-center gap-2">
          <Lightbulb size={15} style={{ color: "#D97706" }} />
          <p className="text-sm font-semibold" style={{ color: "#92400E" }}>Explanation</p>
        </div>
        <button
          type="button"
          onClick={onClose}
          aria-label="Close explanation"
          className="w-6 h-6 flex items-center justify-center rounded-full transition-colors"
          style={{ color: "#92400E", background: "transparent" }}
          onMouseEnter={e => (e.currentTarget.style.background = "#FDE68A")}
          onMouseLeave={e => (e.currentTarget.style.background = "transparent")}
        >
          <X size={13} />
        </button>
      </div>
      {showText && question.explanation_text && (
        <p className="text-sm leading-relaxed whitespace-pre-wrap" style={{ color: "#78350F" }}>
          {question.explanation_text}
        </p>
      )}
      {showImage && (
        question.explanation_image_url
          ? (
            <div className="rounded-[var(--radius-md)] overflow-hidden"
              style={{ border: "1px solid #FDE68A" }}>
              <ImageLoader
                src={question.explanation_image_url}
                alt="Explanation diagram"
                maxHeight={320}
                background="#fffbeb"
                skeletonHeight={160}
              />
            </div>
          )
          : <p className="text-sm italic" style={{ color: "#92400E" }}>Explanation image is being prepared.</p>
      )}
      {!showText && !showImage && (
        <p className="text-sm italic" style={{ color: "#92400E" }}>Explanation content is being prepared.</p>
      )}
    </div>
  );
}

// ── MCQ view ──────────────────────────────────────────────────────────────────
interface McqViewProps {
  question:            QuestionWithProgress;
  options:             PracticeQuestionOption[];
  attemptInfo:         AttemptInfo | null;
  questionId:          string;
  nextId:              string | null;
  onNavigate:          (id: string) => void;
  explRevealed:        boolean;     // lifted to page level so layout can respond
  onExplReveal:        () => void;  // fetches correct IDs + sets explRevealed
  revealedCorrectIds:  string[];    // correct IDs fetched at page level for unattempted questions
}
function McqView({ question, options, attemptInfo, questionId, nextId, onNavigate, explRevealed, onExplReveal, revealedCorrectIds }: McqViewProps) {
  const { error: toastError } = useToast();

  // Selected option IDs (Set for O(1) lookup)
  const [selected,     setSelected]     = useState<Set<string>>(new Set());
  const [submitting,   setSubmitting]   = useState(false);
  const [submitResult, setSubmitResult] = useState<SubmitResult | null>(null);
  const [explConfirm,  setExplConfirm]  = useState(false);
  const [redirecting,  setRedirecting]  = useState(false);

  const mcqType = question.mcq_type ?? "single";

  // If already completed on page load, show correct options immediately
  const alreadyCompleted = question.progress_status === "completed";
  const alreadyAttempted = question.progress_status === "attempted" || alreadyCompleted;

  // Correct option IDs — priority order:
  // 1. Fresh submit result (just answered)
  // 2. attempt_info from server (previously attempted/completed)
  // 3. revealedCorrectIds fetched at page level when explanation was revealed
  const correctIds: string[] =
    submitResult?.correct_option_ids ??
    attemptInfo?.correct_option_ids ??
    revealedCorrectIds;

  // Attempt count: from latest submit result, or from server attempt_info
  const attemptCount = submitResult?.attempt_number
    ?? (attemptInfo?.attempt_count ?? 0);

  // Last submit was correct?
  const lastCorrect = submitResult?.is_correct
    ?? (alreadyCompleted ? true : (attemptInfo?.last_is_correct ?? null));

  // Whether to reveal correct option highlights:
  // - after explanation is shown, OR
  // - already completed (they got it right)
  const revealAnswers = explRevealed || alreadyCompleted;

  // Explanation available if there's content and student has attempted at least once
  const hasExplanation   = question.explanation_type !== "none";
  // Show explanation button from the very first visit — no attempt required.
  const canShowExplButton = hasExplanation;

  const handleSelect = (optId: string) => {
    if (alreadyCompleted || (submitResult?.is_correct)) return;  // no re-select after correct
    setSelected(prev => {
      const next = new Set(prev);
      if (mcqType === "single") {
        next.clear();
        next.add(optId);
      } else {
        if (next.has(optId)) next.delete(optId);
        else next.add(optId);
      }
      return next;
    });
  };

  const handleSubmit = async () => {
    if (selected.size === 0) return;
    setSubmitting(true);
    try {
      const res = await api.post(`/practice/student/questions/${questionId}/submit/`, {
        selected_option_ids: Array.from(selected),
      });
      const result: SubmitResult = res.data.data;
      setSubmitResult(result);

      if (result.is_correct) {
        // Auto-redirect to next question after 1.8 s
        setRedirecting(true);
        setTimeout(() => {
          if (nextId) onNavigate(nextId);
          else setRedirecting(false);
        }, 1800);
      }
    } catch (err) {
      toastError(getErrorMessage(err));
    } finally {
      setSubmitting(false);
    }
  };

  // Options disabled when: submitting, already correct (just submitted or already completed), or redirecting
  const optionsDisabled = submitting || redirecting ||
    alreadyCompleted || (submitResult?.is_correct === true);

  // Determine per-option reveal state.
  // Rule: after a WRONG submission, only mark the student's own wrong selections
  // (red). Never expose the correct answer — no green highlights until the
  // student explicitly requests the explanation or answers correctly.
  const getOptionReveal = (optId: string): boolean | null => {
    if (submitResult && !submitResult.is_correct && !explRevealed) {
      // Wrong submit, explanation not yet shown: mark student's choice red only
      return selected.has(optId) ? false : null;
    }
    if (!revealAnswers) return null;
    return correctIds.includes(optId);
  };

  return (
    <div className="space-y-5">
      {/* Question body */}
      <QuestionBody question={question} />

      {/* MCQ type label */}
      <p className="text-xs font-semibold uppercase tracking-widest" style={{ color: T.subtle }}>
        {mcqType === "single" ? "Single Correct Answer" : "Multiple Correct Answers"}
      </p>

      {/* Already completed banner */}
      {alreadyCompleted && !submitResult && (
        <div className="flex items-center gap-3 px-4 py-3.5 rounded-[var(--radius-md)]"
          style={{ background: "#F0FDF4", border: "1px solid #BBF7D0" }}>
          <CheckCircle2 size={18} style={{ color: "#16A34A", flexShrink: 0 }} />
          <div>
            <p className="text-sm font-bold" style={{ color: "#166534" }}>Already Completed</p>
            <p className="text-xs mt-0.5" style={{ color: "#15803D" }}>
              You answered this correctly.
              {attemptCount > 0 && ` (${attemptCount} attempt${attemptCount > 1 ? "s" : ""})`}
            </p>
          </div>
        </div>
      )}

      {/* Previous attempts info (attempted but not completed) */}
      {!alreadyCompleted && alreadyAttempted && !submitResult && attemptCount > 0 && (
        <div className="flex items-center gap-3 px-4 py-3.5 rounded-[var(--radius-md)]"
          style={{ background: "#FFF7ED", border: "1px solid #FED7AA" }}>
          <XCircle size={18} style={{ color: "#EA580C", flexShrink: 0 }} />
          <div>
            <p className="text-sm font-bold" style={{ color: "#C2410C" }}>Not completed yet</p>
            <p className="text-xs mt-0.5" style={{ color: "#EA580C" }}>
              {attemptCount} previous attempt{attemptCount > 1 ? "s" : ""} — keep trying!
            </p>
          </div>
        </div>
      )}

      {/* Submit result banner */}
      {submitResult && (
        <div className="flex items-center gap-3 px-4 py-3.5 rounded-[var(--radius-md)]"
          style={submitResult.is_correct
            ? { background: "#F0FDF4", border: "1px solid #BBF7D0" }
            : { background: "#FEF2F2", border: "1px solid #FECACA" }
          }>
          {submitResult.is_correct
            ? <CheckCircle2 size={18} style={{ color: "#16A34A", flexShrink: 0 }} />
            : <XCircle      size={18} style={{ color: "#DC2626", flexShrink: 0 }} />
          }
          <div>
            {submitResult.is_correct ? (
              <>
                <p className="text-sm font-bold" style={{ color: "#166534" }}>Correct!</p>
                <p className="text-xs mt-0.5" style={{ color: "#15803D" }}>
                  {redirecting && nextId
                    ? "Navigating to next question…"
                    : nextId ? "Redirecting to next question…" : "Well done!"}
                </p>
              </>
            ) : (
              <>
                <p className="text-sm font-bold" style={{ color: "#991B1B" }}>Incorrect</p>
                <p className="text-xs mt-0.5" style={{ color: "#DC2626" }}>
                  Attempt {submitResult.attempt_number} — try again.
                </p>
              </>
            )}
          </div>
        </div>
      )}

      {/* Options — single column stack (global standard: mirrors TCS/Infosys/Wipro placement test format) */}
      <div className="space-y-2">
        {options.map(opt => (
          <OptionBtn
            key={opt.id}
            option={opt}
            selected={selected.has(opt.id)}
            correct={getOptionReveal(opt.id)}
            disabled={optionsDisabled}
            mcqType={mcqType}
            onClick={() => handleSelect(opt.id)}
          />
        ))}
        {options.length === 0 && (
          <div className="py-8 text-center rounded-[var(--radius-md)]"
            style={{ background: T.surface, border: `1px dashed ${T.border}` }}>
            <p className="text-sm italic" style={{ color: T.subtle }}>
              Answer options are being prepared.
            </p>
          </div>
        )}
      </div>

      {/* Action row */}
      <div className="flex flex-wrap gap-3">
        {/* Submit button — only when not yet correct */}
        {!alreadyCompleted && !(submitResult?.is_correct) && (
          <Button
            variant="primary" size="md"
            onClick={handleSubmit}
            loading={submitting}
            disabled={selected.size === 0 || submitting || redirecting}
          >
            Submit Answer
          </Button>
        )}

        {/* Clear selection button — visible only when at least one option is selected and not yet submitted correctly */}
        {!alreadyCompleted && !(submitResult?.is_correct) && selected.size > 0 && (
          <button
            type="button"
            onClick={() => { setSelected(new Set()); setSubmitResult(null); }}
            disabled={submitting || redirecting}
            className="inline-flex items-center gap-1.5 px-4 py-2 rounded-[var(--radius-md)] text-sm font-semibold border transition-colors disabled:opacity-50"
            style={{ background: T.white, color: T.muted, border: `1px solid ${T.border}` }}
            onMouseEnter={e => {
              e.currentTarget.style.borderColor = T.muted;
              e.currentTarget.style.color = T.text;
            }}
            onMouseLeave={e => {
              e.currentTarget.style.borderColor = T.border;
              e.currentTarget.style.color = T.muted;
            }}
          >
            Clear
          </button>
        )}

        {/* Explanation button */}
        {canShowExplButton && !explRevealed && (
          <Button
            variant="secondary" size="md" leftIcon={<Lightbulb size={15} />}
            onClick={() => setExplConfirm(true)}
            disabled={redirecting}
          >
            Show Explanation
          </Button>
        )}
      </div>

      {/* Explanation confirm — triggers page-level split layout via onExplReveal */}
      <ConfirmDialog
        isOpen={explConfirm}
        onClose={() => setExplConfirm(false)}
        onConfirm={() => { setExplConfirm(false); onExplReveal(); }}
        title="View Explanation"
        message="Viewing the explanation will reveal the correct answer(s). Continue?"
        confirmLabel="Show explanation"
        confirmVariant="warning"
      />
    </div>
  );
}

// ── Main page ─────────────────────────────────────────────────────────────────
export default function StudentPracticeQuestionPage() {
  const { question_id } = useParams<{ question_id: string }>();
  const router = useRouter();
  const { error: toastError } = useToast();

  const [detail,    setDetail]    = useState<QuestionDetailData | null>(null);
  const [loading,   setLoading]   = useState(true);
  const [ancestors, setAncestors] = useState<PracticeModule[]>([]);

  // Prevent duplicate "visited" POSTs on React StrictMode double-invoke
  const visitedRef = useRef<string | null>(null);

  // Walk up parent IDs to build the full ancestor chain for the breadcrumb.
  // e.g. module = "Functions" → ancestors = [Quantitative Aptitude]
  const buildAncestors = async (mod: PracticeModule) => {
    const chain: PracticeModule[] = [];
    let node = mod;
    while (node.parent) {
      try {
        const res = await api.get(`/practice/student/modules/${node.parent}/`);
        const parentMod = res.data.data?.module as PracticeModule | undefined;
        if (!parentMod) break;
        chain.unshift(parentMod);
        node = parentMod;
      } catch {
        break;
      }
    }
    setAncestors(chain);
  };

  // ── Copy / context-menu protection ───────────────────────────────────────
  // Block all text selection, clipboard copy and right-click on this page
  // so question content cannot be copied out of the exam interface.
  useEffect(() => {
    const prevent = (e: Event) => e.preventDefault();
    document.addEventListener("copy",        prevent);
    document.addEventListener("contextmenu", prevent);
    return () => {
      document.removeEventListener("copy",        prevent);
      document.removeEventListener("contextmenu", prevent);
    };
  }, []);

  // FIB state
  const [answerConfirmOpen, setAnswerConfirmOpen] = useState(false);
  const [answerModalOpen,   setAnswerModalOpen]   = useState(false);
  const [fibAnswer,         setFibAnswer]         = useState<string | null>(null);
  const [revealingAnswer,   setRevealingAnswer]   = useState(false);
  const [explConfirmOpen,   setExplConfirmOpen]   = useState(false);
  const [explRevealed,      setExplRevealed]      = useState(false);
  // Tracks which question ID is being navigated to — drives Prev/Next spinner
  const [navigatingTo,      setNavigatingTo]      = useState<string | null>(null);
  // Tracks breadcrumb/back navigation in progress
  const [breadcrumbLoading, setBreadcrumbLoading] = useState(false);
  // For MCQ: correct IDs fetched when student reveals explanation on an
  // unattempted question (attempt_info is null so server hasn't sent them yet).
  const [mcqRevealedCorrectIds, setMcqRevealedCorrectIds] = useState<string[]>([]);

  // ── Load ──────────────────────────────────────────────────────────────────
  useEffect(() => {
    setLoading(true);
    setDetail(null);
    setAncestors([]);
    setExplRevealed(false);
    setNavigatingTo(null);
    setBreadcrumbLoading(false);
    setMcqRevealedCorrectIds([]);
    setAnswerModalOpen(false);
    setAnswerConfirmOpen(false);
    setFibAnswer(null);
    setRevealingAnswer(false);
    setExplConfirmOpen(false);

    api.get(`/practice/student/questions/${question_id}/`)
      .then(res => {
        const data = res.data.data as QuestionDetailData;
        setDetail(data);
        if (data.module) buildAncestors(data.module);

        // Mark as visited (fire-and-forget, once per question_id)
        if (visitedRef.current !== question_id) {
          visitedRef.current = question_id;
          const st = data.question.progress_status;
          if (st !== "attempted" && st !== "completed") {
            api.post(`/practice/student/questions/${question_id}/progress/`, {
              status: "visited",
            }).catch(() => {/* non-critical */});
          }
        }
      })
      .catch(err => {
        toastError(getErrorMessage(err));
        router.push("/students/practice");
      })
      .finally(() => setLoading(false));
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [question_id]);

  // Prefetch adjacent questions
  useEffect(() => {
    if (!detail) return;
    if (detail.prev_question_id)
      router.prefetch(`/students/practice/questions/${detail.prev_question_id}`);
    if (detail.next_question_id)
      router.prefetch(`/students/practice/questions/${detail.next_question_id}`);
  }, [detail, router]);

  // ── Navigation ────────────────────────────────────────────────────────────
  const goTo = (id: string) => {
    setNavigatingTo(id);
    router.push(`/students/practice/questions/${id}`);
  };

  const navTo = (path: string) => {
    setBreadcrumbLoading(true);
    router.push(path);
  };

  // ── MCQ: reveal correct IDs when student shows explanation ───────────────
  // For attempted/completed questions attempt_info already carries the IDs —
  // no fetch needed. For not_visited/visited we must fetch them now.
  const handleMcqExplReveal = async () => {
    setExplRevealed(true);
    if (!detail?.attempt_info) {
      try {
        const res = await api.post(`/practice/student/questions/${question_id}/reveal-answer/`);
        const ids: string[] = res.data.data?.correct_option_ids ?? [];
        setMcqRevealedCorrectIds(ids);
      } catch (err) {
        // silently ignore — correct answer simply won't highlight
      }
    }
  };

  // ── FIB: reveal answer → fetch from secure endpoint + mark completed ────────
  const handleFibAnswerConfirm = async () => {
    setAnswerConfirmOpen(false);
    setRevealingAnswer(true);
    try {
      const res = await api.post(`/practice/student/questions/${question_id}/reveal-answer/`);
      setFibAnswer(res.data.data.fib_answer ?? "—");
    } catch {
      setFibAnswer("—");
    } finally {
      setRevealingAnswer(false);
      setAnswerModalOpen(true);
    }
  };

  // ── Derived ───────────────────────────────────────────────────────────────
  const question     = detail?.question;
  const section      = detail?.section;
  const parentModule = detail?.module;
  const prevId       = detail?.prev_question_id ?? null;
  const nextId       = detail?.next_question_id ?? null;

  const isMcq    = question?.question_type === "mcq";
  const TypeIcon = isMcq ? ListChecks : AlignLeft;
  const typeBg   = isMcq ? "#EFF6FF" : "#FDF4FF";
  const typeColor = isMcq ? "#2563EB" : "#9333EA";
  const typeBorder = isMcq ? "#BFDBFE" : "#E9D5FF";
  const typeLabel  = isMcq ? "Multiple Choice (MCQ)" : "Fill in the Blank (FIB)";

  const backHref = section ? `/students/practice/sections/${section.id}` : "/students/practice";

  // FIB flags
  const hasExplanation  = question && question.explanation_type !== "none";
  const showExplText    = question && (question.explanation_type === "text"  || question.explanation_type === "both");
  const showExplImage   = question && (question.explanation_type === "image" || question.explanation_type === "both");

  // ── Loading state — full-screen SPARK star animation ─────────────────────
  if (loading) return <GlobalLoader />;

  if (!question) return null;

  return (
    <StudentLayout>
      {/*
        PageWrapper has no max-width — the inner dynamic container controls width.
        Default: max-w-3xl (48rem) centred  →  on explanation reveal: expands to
        max-w-5xl (64rem) and splits into question-left / explanation-right.
        Transition is on max-width so the expansion is animated smoothly.
      */}
      <PageWrapper className="py-6 sm:py-8 select-none">

        {/* ── Dynamic container — expands when explanation is revealed ─────── */}
        <div
          className="mx-auto w-full transition-[max-width] duration-500 ease-in-out"
          style={{ maxWidth: explRevealed ? "64rem" : "48rem" }}
        >

          {/* ── Breadcrumb ────────────────────────────────────────────────── */}
          <nav className="flex items-center flex-wrap gap-1.5 text-sm font-medium mb-5 min-w-0" aria-label="Breadcrumb">

            <button
              onClick={() => navTo("/students/practice")}
              disabled={breadcrumbLoading}
              className="shrink-0 transition-all disabled:opacity-50 disabled:cursor-wait"
              style={{ color: T.muted }}
              onMouseEnter={e => { if (!breadcrumbLoading) e.currentTarget.style.color = T.text; }}
              onMouseLeave={e => (e.currentTarget.style.color = T.muted)}>
              {breadcrumbLoading ? <LoadingSpinner size={12} /> : "Practice"}
            </button>

            {ancestors.map(anc => (
              <span key={anc.id} className="flex items-center gap-1.5 min-w-0">
                <ChevronRight size={13} style={{ color: T.subtle, flexShrink: 0 }} />
                <button
                  onClick={() => navTo(`/students/practice/${anc.id}`)}
                  disabled={breadcrumbLoading}
                  className="truncate transition-all disabled:opacity-50 disabled:cursor-wait"
                  style={{ color: T.muted }}
                  onMouseEnter={e => { if (!breadcrumbLoading) e.currentTarget.style.color = T.text; }}
                  onMouseLeave={e => (e.currentTarget.style.color = T.muted)}>
                  {anc.name}
                </button>
              </span>
            ))}

            {parentModule && (
              <>
                <ChevronRight size={13} style={{ color: T.subtle, flexShrink: 0 }} />
                <button
                  onClick={() => navTo(`/students/practice/${parentModule.id}`)}
                  disabled={breadcrumbLoading}
                  className="truncate transition-all disabled:opacity-50 disabled:cursor-wait"
                  style={{ color: T.muted }}
                  onMouseEnter={e => { if (!breadcrumbLoading) e.currentTarget.style.color = T.text; }}
                  onMouseLeave={e => (e.currentTarget.style.color = T.muted)}>
                  {parentModule.name}
                </button>
              </>
            )}

            {section && (
              <>
                <ChevronRight size={13} style={{ color: T.subtle, flexShrink: 0 }} />
                <button
                  onClick={() => navTo(backHref)}
                  disabled={breadcrumbLoading}
                  className="truncate transition-all disabled:opacity-50 disabled:cursor-wait"
                  style={{ color: T.muted }}
                  onMouseEnter={e => { if (!breadcrumbLoading) e.currentTarget.style.color = T.text; }}
                  onMouseLeave={e => (e.currentTarget.style.color = T.muted)}>
                  {section.name}
                </button>
              </>
            )}

            <ChevronRight size={13} style={{ color: T.subtle, flexShrink: 0 }} />
            <span className="truncate font-semibold" style={{ color: T.text }}>
              Question {question.question_number}
            </span>

          </nav>

          {/* ── Header — full width above split so both cards top-align ────── */}
          <div className="mb-6">
            <h1 className="text-xl sm:text-2xl font-bold leading-snug mb-2" style={{ color: T.text }}>
              Question {question.question_number}
            </h1>
            <span
              className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold"
              style={{ background: typeBg, color: typeColor, border: `1px solid ${typeBorder}` }}>
              <TypeIcon size={11} />
              {typeLabel}
            </span>
          </div>

          {/* ── Split area: left = question card, right = explanation (lg+) ── */}
          {/* Both columns now start at the same top line                       */}
          <div className={`${explRevealed ? "lg:flex lg:gap-8 lg:items-start" : ""}`}>

            {/* ── LEFT: question card + options + actions ───────────────────── */}
            <div className={`${explRevealed ? "lg:flex-1 lg:min-w-0" : ""} transition-all duration-300`}>

              {/* MCQ view */}
              {isMcq && (
                <McqView
                  question={question}
                  options={detail?.options ?? []}
                  attemptInfo={detail?.attempt_info ?? null}
                  questionId={question_id}
                  nextId={nextId}
                  onNavigate={goTo}
                  explRevealed={explRevealed}
                  onExplReveal={handleMcqExplReveal}
                  revealedCorrectIds={mcqRevealedCorrectIds}
                />
              )}

              {/* FIB view */}
              {!isMcq && (
                <div className="space-y-5">
                  <QuestionBody question={question} />
                  {/* flex-col on mobile → intentional full-width stack (large tap targets)
                      flex-row on sm+ → side-by-side on desktop (matches MCQ action row)
                      min-h-[44px] → Apple 44pt tap-target standard on both buttons       */}
                  <div className="flex flex-col sm:flex-row gap-3">
                    <Button
                      variant="primary" size="md" leftIcon={<Eye size={15} />}
                      onClick={() => setAnswerConfirmOpen(true)}
                      loading={revealingAnswer}
                      disabled={revealingAnswer}
                      className="w-full sm:w-auto min-h-[44px]"
                    >
                      Show Answer
                    </Button>
                    {hasExplanation && !explRevealed && (
                      <Button
                        variant="secondary" size="md" leftIcon={<Lightbulb size={15} />}
                        onClick={() => setExplConfirmOpen(true)}
                        className="w-full sm:w-auto min-h-[44px]"
                      >
                        Show Explanation
                      </Button>
                    )}
                  </div>
                </div>
              )}

              {/* Mobile explanation — shown below content on small screens only */}
              {explRevealed && (
                <div className="lg:hidden mt-5">
                  <ExplanationPanel question={question} onClose={() => setExplRevealed(false)} />
                </div>
              )}

              {/* Prev / Next navigation */}
              {(prevId || nextId) && (
                <div className="flex items-center justify-between mt-5 pt-5"
                  style={{ borderTop: `1px solid ${T.border}` }}>
                  {prevId ? (
                    <button
                      onClick={() => goTo(prevId)}
                      disabled={!!navigatingTo || breadcrumbLoading}
                      className="inline-flex items-center gap-2 px-4 py-2.5 rounded-[var(--radius-md)] text-sm font-semibold transition-all disabled:opacity-50 disabled:cursor-wait"
                      style={{ background: T.white, color: T.muted, border: `1px solid ${T.border}` }}
                      onMouseEnter={e => {
                        if (navigatingTo || breadcrumbLoading) return;
                        e.currentTarget.style.background  = T.surface;
                        e.currentTarget.style.borderColor = T.muted;
                        e.currentTarget.style.color       = T.text;
                      }}
                      onMouseLeave={e => {
                        e.currentTarget.style.background  = T.white;
                        e.currentTarget.style.borderColor = T.border;
                        e.currentTarget.style.color       = T.muted;
                      }}>
                      {navigatingTo === prevId
                        ? <><LoadingSpinner size={14} /> Previous</>
                        : <><ChevronLeft size={16} /> Previous</>}
                    </button>
                  ) : <div />}
                  {nextId ? (
                    <button
                      onClick={() => goTo(nextId)}
                      disabled={!!navigatingTo || breadcrumbLoading}
                      className="inline-flex items-center gap-2 px-4 py-2.5 rounded-[var(--radius-md)] text-sm font-semibold transition-all disabled:opacity-50 disabled:cursor-wait"
                      style={{ background: "var(--color-accent)", color: "#fff", border: "1px solid transparent" }}
                      onMouseEnter={e => { if (!navigatingTo && !breadcrumbLoading) e.currentTarget.style.opacity = "0.88"; }}
                      onMouseLeave={e => (e.currentTarget.style.opacity = "1")}>
                      {navigatingTo === nextId
                        ? <><LoadingSpinner size={14} color="#fff" /> Next</>
                        : <>Next <ChevronRight size={16} /></>}
                    </button>
                  ) : <div />}
                </div>
              )}

            </div>{/* end left column */}

            {/* ── RIGHT: explanation panel — desktop only, slides in on reveal ── */}
            {explRevealed && (
              <div className="hidden lg:block lg:w-[360px] xl:w-[400px] lg:shrink-0 lg:sticky"
                style={{ top: "80px", alignSelf: "flex-start" }}>
                <ExplanationPanel question={question} onClose={() => setExplRevealed(false)} />
              </div>
            )}

          </div>{/* end split area */}

        </div>{/* end dynamic container */}

      </PageWrapper>

      {/* ── FIB: Answer confirm dialog ───────────────────────────────────────── */}
      <ConfirmDialog
        isOpen={answerConfirmOpen}
        onClose={() => setAnswerConfirmOpen(false)}
        onConfirm={handleFibAnswerConfirm}
        title="Reveal Answer"
        message="Are you sure you want to see the answer? Try to solve it yourself first for the best learning outcome."
        confirmLabel="Yes, show me"
        confirmVariant="primary"
      />

      {/* FIB: Answer modal */}
      <Modal
        isOpen={answerModalOpen}
        onClose={() => setAnswerModalOpen(false)}
        title={`Answer — Question ${question?.question_number}`}
        maxWidth="sm"
      >
        <div className="text-center py-4">
          <div
            className="inline-block px-5 py-3 rounded-[var(--radius-lg)] text-xl font-bold mb-3"
            style={{ background: "#F0FDF4", color: "#166534", border: "1px solid #BBF7D0" }}
          >
            {fibAnswer ?? "—"}
          </div>
          <p className="text-xs mt-2" style={{ color: T.subtle }}>
            This is the correct answer for the blank.
          </p>
        </div>
      </Modal>

      {/* ── FIB: Explanation confirm dialog ──────────────────────────────────── */}
      <ConfirmDialog
        isOpen={explConfirmOpen}
        onClose={() => setExplConfirmOpen(false)}
        onConfirm={() => { setExplConfirmOpen(false); setExplRevealed(true); }}
        title="View Explanation"
        message="Viewing the explanation before attempting the question may reduce its learning value. Continue?"
        confirmLabel="Show explanation"
        confirmVariant="warning"
      />

    </StudentLayout>
  );
}
