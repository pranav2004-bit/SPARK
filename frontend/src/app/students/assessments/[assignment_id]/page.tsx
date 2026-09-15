"use client";

import { useEffect, useState, useCallback, useRef, useMemo } from "react";
import { useParams, useRouter } from "next/navigation";
import {
  Clock, WifiOff, CheckCircle2, Maximize, Minimize, ShieldAlert, AlertTriangle,
  Award, HelpCircle, CalendarClock, UserCircle2, FileText, ListChecks, AppWindow,
  ChevronLeft, ChevronRight, Flag, X, DoorOpen,
} from "lucide-react";
import { StudentLayout, useExamMobileMenu } from "@/components/layout/StudentLayout";
import { PageWrapper } from "@/components/layout/PageWrapper";
import { Button } from "@/components/ui/Button";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import { ImageLoader } from "@/components/ui/ImageLoader";
import { GlobalLoader } from "@/components/ui/GlobalLoader";
import { useToast } from "@/components/ui/Toast";
import { useOfflineAnswerQueue } from "@/hooks/useOfflineAnswerQueue";
import { useServerTimeSync } from "@/hooks/useServerTimeSync";
import { useActivityCapture, clearExamViolationCounts } from "@/hooks/useActivityCapture";
import api, { getErrorMessage } from "@/lib/api";
import { toTitleCase } from "@/lib/format";
import type {
  ApiSuccess, StudentStartSessionResponse, StudentSessionQuestionsResponse,
  StudentQuestion, StudentSubmitResponse, StudentAssignmentListItem, StudentProfile,
} from "@/types";

function formatCountdown(totalSeconds: number): string {
  const h = Math.floor(totalSeconds / 3600);
  const m = Math.floor((totalSeconds % 3600) / 60);
  const s = totalSeconds % 60;
  const pad = (n: number) => String(n).padStart(2, "0");
  return h > 0 ? `${h}:${pad(m)}:${pad(s)}` : `${m}:${pad(s)}`;
}

function formatDateTime(iso: string): string {
  return new Date(iso).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
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

// TEMPORARY DEV OVERRIDE (added 2026-08-27) — set back to false before this
// page is considered done. While true, tab-switch/fullscreen-exit counts
// are still tracked (useActivityCapture keeps running) but never escalate
// into a warning toast or the lockout-triggered auto-submit below, so
// switching away to iterate on this page's interface doesn't keep ending
// the test session. The countdown timer's own expiry-based auto-submit
// (separate effect, further down) is NOT affected by this flag — it still
// fires normally when time runs out. This must not ship live: it silently
// disables a real anti-cheat mechanism for every student, not just this
// dev session.
const DEV_DISABLE_ANTI_CHEAT_LOCKOUT = true;

// Mobile hamburger dropdown content (added 2026-08-31, explicit request) —
// a real component, not just inline JSX in StudentExamPage, because it
// needs useExamMobileMenu(), and that context is only readable by
// descendants of the <StudentLayout examMode> that provides it.
// StudentExamPage itself renders that StudentLayout, so it can't read the
// context directly — only something nested inside `children` can. Renders
// in normal document flow, just above the active question, not as a
// floating overlay.
function MobileExamMenu({ children }: { children: React.ReactNode }) {
  const { open, setOpen } = useExamMobileMenu();
  if (!open) return null;
  return (
    <>
      {/* Backdrop — blurs the rest of the exam behind the dropdown
          (explicit request 2026-08-31) rather than just dimming it; also
          closes the dropdown on tap-outside. */}
      <div
        className="lg:hidden fixed inset-0 top-14 z-30"
        style={{ background: "rgba(15, 23, 42, 0.15)", backdropFilter: "blur(4px)", WebkitBackdropFilter: "blur(4px)" }}
        onClick={() => setOpen(false)}
        aria-hidden="true"
      />
      <div className="lg:hidden relative z-40 mb-5 flex flex-col gap-4 rounded-[var(--radius-lg)] bg-white p-4" style={{ border: "1px solid var(--color-border)" }}>
        {children}
      </div>
    </>
  );
}

export default function StudentExamPage() {
  const { assignment_id } = useParams<{ assignment_id: string }>();
  const router = useRouter();
  const toast = useToast();

  // ── Entry gate — exam doesn't start (no start-session call, no server
  // timer) until the student has actually entered fullscreen. ─────────────
  const [examEntered, setExamEntered] = useState(false);
  const [enteringFullscreen, setEnteringFullscreen] = useState(false);
  const [fullscreenError, setFullscreenError] = useState("");

  // ── Pre-exam briefing data (added 2026-08-27) — assessment facts, admin
  // instructions, and this assignment's own current session_status, fetched
  // fresh on every load rather than trusted from wherever the student
  // navigated here from (a direct/bookmarked link must work identically to
  // arriving via the assessments list). Reused from the same list endpoint
  // the list page itself calls, filtered to this one assignment — no new
  // endpoint needed. `profile` (identity confirmation) is a separate,
  // best-effort fetch: it's a safety nicety, not something that should ever
  // block the briefing from rendering if it fails.
  const [briefing, setBriefing] = useState<StudentAssignmentListItem | null>(null);
  const [profile, setProfile] = useState<StudentProfile | null>(null);
  const [briefingLoading, setBriefingLoading] = useState(true);
  const [briefingLoadError, setBriefingLoadError] = useState(false);
  const [agreed, setAgreed] = useState(false);

  useEffect(() => {
    let cancelled = false;

    api.get<ApiSuccess<StudentProfile>>("/users/me/")
      .then(res => { if (!cancelled) setProfile(res.data.data); })
      .catch(() => { /* best-effort — see comment above */ });

    setBriefingLoading(true);
    setBriefingLoadError(false);
    api.get<ApiSuccess<StudentAssignmentListItem[]>>("/assessments/student/assignments/")
      .then(res => {
        if (cancelled) return;
        const item = res.data.data.find(a => a.assignment_id === assignment_id);
        if (!item) { setBriefingLoadError(true); return; }
        setBriefing(item);
        // Already finished (reopened a completed exam's URL directly) —
        // skip the gate entirely; the existing start-session -> "already
        // finished" flow further below already handles this correctly.
        if (item.session_status === "SUBMITTED" || item.session_status === "AUTO_SUBMITTED") {
          setExamEntered(true);
        }
      })
      .catch(() => { if (!cancelled) setBriefingLoadError(true); })
      .finally(() => { if (!cancelled) setBriefingLoading(false); });

    return () => { cancelled = true; };
  }, [assignment_id]);

  const [sessionId, setSessionId] = useState<string | null>(null);
  const [sessionStatus, setSessionStatus] = useState<string | null>(null);
  const [questions, setQuestions] = useState<StudentQuestion[]>([]);
  const [loading, setLoading] = useState(false);
  const [activeIndex, setActiveIndex] = useState(0);
  const [answers, setAnswers] = useState<Record<string, string[]>>({}); // questionId -> selected
  // Drives the Question-numbers panel's 4-state legend/coloring (not
  // visited / answered / not answered / flagged) — visited is index-based
  // (a question is "visited" once it's ever been the active one, tracked
  // by the effect below), flagged is question-id based and toggled by the
  // student from the active-question card, independent of whether it's
  // answered.
  const [visitedIndices, setVisitedIndices] = useState<Set<number>>(() => new Set([0]));
  const [flaggedIds, setFlaggedIds] = useState<Set<string>>(() => new Set());
  useEffect(() => {
    setVisitedIndices(prev => (prev.has(activeIndex) ? prev : new Set(prev).add(activeIndex)));
  }, [activeIndex]);
  const [savingState, setSavingState] = useState<Record<string, "saving" | "saved" | "queued">>({});
  const [confirmSubmit, setConfirmSubmit] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  // "Exit Test" in the exam-mode header — before the exam has actually
  // started (briefing/resume/error/finished screens) there's nothing to
  // lose, so it navigates straight away. Once questions are on screen it
  // routes through this confirm instead: leaving here does NOT submit —
  // the session stays IN_PROGRESS server-side, same as closing the tab —
  // so a student needs to understand that before doing it on purpose.
  const [confirmExit, setConfirmExit] = useState(false);
  const exitToAssessments = useCallback(() => router.push("/students/assessments"), [router]);
  const [result, setResult] = useState<StudentSubmitResponse | null>(null);
  const autoSubmitTriggered = useRef(false);

  const { saveAnswer, isReconnecting } = useOfflineAnswerQueue(sessionId ?? "");
  const { secondsRemaining, isSyncFailing, lastExtension } = useServerTimeSync();
  const {
    isFullscreen, requestFullscreen, tabSwitchCount, fullscreenExitCount, screenshotAttempts,
    notifyActiveQuestion,
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
        "but tab switches, window changes and fullscreen exits are still monitored and limited."
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
          // Resuming an already-finished exam (e.g. reopening the URL
          // later) — genuinely terminal, safe to stop tracking.
          clearExamViolationCounts(session_id);
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

  // Feeds the "average time spent per question" analytics — fires on every
  // navigation (Prev/Next or the jump navigator), letting useActivityCapture
  // finalize the previously-active question's foreground time and start
  // timing the new one. Only while IN_PROGRESS: once the exam ends,
  // useActivityCapture's own cleanup (triggered by sessionId flipping to
  // null, see the hook call above) finalizes whichever question was last
  // active — this effect deliberately doesn't also fire for that case.
  useEffect(() => {
    if (sessionStatus !== "IN_PROGRESS") return;
    notifyActiveQuestion(activeQuestion?.question_number);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeQuestion?.question_number, sessionStatus]);

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

  // Single-choice questions have no natural way to deselect (clicking the
  // same option again is a no-op — see the "single" branch above, which
  // always ends up with that one option selected), so this is the only way
  // to unselect once an answer's been picked.
  const handleClear = useCallback((questionId: string) => {
    setAnswers(prev => {
      const next = { ...prev, [questionId]: [] };
      setSavingState(s => ({ ...s, [questionId]: "saving" }));
      saveAnswer(questionId, [])
        .then(outcome => setSavingState(s => ({ ...s, [questionId]: outcome })))
        .catch(() => {
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
      // A successful submit here is always a genuine terminal transition —
      // safe to stop tracking this session's violation counts.
      clearExamViolationCounts(sessionId);
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
    if (DEV_DISABLE_ANTI_CHEAT_LOCKOUT) return;
    if (tabSwitchCount === 0 || sessionStatus !== "IN_PROGRESS") return;
    if (tabSwitchCount > TAB_SWITCH_LIMIT) {
      setLockout(prev => prev ?? { label: "tab switches", secondsLeft: LOCKOUT_COUNTDOWN_SECONDS });
    } else {
      toast.warning(
        `Tab switch detected - warning ${tabSwitchCount} of ${TAB_SWITCH_LIMIT}. ` +
        `Reaching the limit will auto-submit your exam.`
      );
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tabSwitchCount]);

  useEffect(() => {
    if (DEV_DISABLE_ANTI_CHEAT_LOCKOUT) return;
    if (fullscreenExitCount === 0 || sessionStatus !== "IN_PROGRESS") return;
    if (fullscreenExitCount > FULLSCREEN_EXIT_LIMIT) {
      setLockout(prev => prev ?? { label: "fullscreen exits", secondsLeft: LOCKOUT_COUNTDOWN_SECONDS });
    } else {
      toast.warning(
        `Fullscreen exit detected - warning ${fullscreenExitCount} of ${FULLSCREEN_EXIT_LIMIT}. ` +
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

  // An admin extended this session's deadline — useServerTimeSync already
  // updates the countdown display on its own (it just re-reads the same
  // ends_at this notification is reacting to), this only adds the popup.
  // Fires up to ~20s after the admin's action (the next poll), not
  // instantly — there's no push channel for this (ADR 001).
  useEffect(() => {
    if (!lastExtension) return;
    toast.success(
      `Good news - your exam time was extended by ${lastExtension.addedMinutes} minute` +
      `${lastExtension.addedMinutes === 1 ? "" : "s"}.`
    );
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [lastExtension]);

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

  // Question-numbers panel's 4-state legend counts. Mutually exclusive so
  // they sum to questions.length and match each button's single color:
  // flagged wins over answered/not-answered/not-visited regardless of
  // actual answer state, same priority order as the button coloring below.
  const statusCounts = useMemo(() => {
    let flaggedN = 0, answeredN = 0, notAnsweredN = 0, notVisitedN = 0;
    questions.forEach((q, i) => {
      if (flaggedIds.has(q.id)) flaggedN++;
      else if ((answers[q.id]?.length ?? 0) > 0) answeredN++;
      else if (visitedIndices.has(i)) notAnsweredN++;
      else notVisitedN++;
    });
    return { flagged: flaggedN, answered: answeredN, notAnswered: notAnsweredN, notVisited: notVisitedN };
  }, [questions, answers, flaggedIds, visitedIndices]);

  const QUESTION_STATUS_STYLE = {
    flagged: { background: "#F5F3FF", color: "#7C3AED", border: "#DDD6FE" },
    answered: { background: "#F0FDF4", color: "#16A34A", border: "#BBF7D0" },
    notAnswered: { background: "#FEF2F2", color: "#DC2626", border: "#FECACA" },
    notVisited: { background: "#F3F4F6", color: "var(--color-text-muted)", border: "#E5E7EB" },
  } as const;
  const getQuestionStatus = useCallback((q: StudentQuestion, i: number): keyof typeof QUESTION_STATUS_STYLE => {
    if (flaggedIds.has(q.id)) return "flagged";
    if ((answers[q.id]?.length ?? 0) > 0) return "answered";
    if (visitedIndices.has(i)) return "notAnswered";
    return "notVisited";
  }, [flaggedIds, answers, visitedIndices]);

  const statusLegend = (
    <div className="grid grid-cols-2 gap-2.5 mb-3 w-full">
      {([
        ["notVisited", "Not Visited", statusCounts.notVisited],
        ["answered", "Answered", statusCounts.answered],
        ["notAnswered", "Not Answered", statusCounts.notAnswered],
        ["flagged", "Flagged", statusCounts.flagged],
      ] as const).map(([key, label, count]) => (
        <div
          key={key}
          className="flex items-center justify-between px-2 py-2 rounded-[var(--radius-md)] min-w-0"
          style={{ background: QUESTION_STATUS_STYLE[key].background, border: `1px solid ${QUESTION_STATUS_STYLE[key].border}` }}
        >
          <span className="text-[13px] font-medium truncate" style={{ color: QUESTION_STATUS_STYLE[key].color }}>{label}</span>
          <span className="text-[13px] font-bold shrink-0 pl-1" style={{ color: QUESTION_STATUS_STYLE[key].color }}>{count}</span>
        </div>
      ))}
    </div>
  );

  // Question-numbers content for the mobile hamburger menu (rendered by
  // MobileExamMenu, above) — moved out of the page's own 3-column row
  // (2026-08-31, explicit request) since on narrow screens it used to sit
  // inline before the actual question, pushing it far down the page. The
  // desktop fixed/bled version below (inside the row) is untouched.
  const mobileNumberGrid = (
    <div className="lg:hidden">
      {statusLegend}
      <div className="grid grid-cols-[repeat(5,2.25rem)] gap-2 justify-center">
        {questions.map((q, i) => {
          const status = getQuestionStatus(q, i);
          const isActive = i === activeIndex;
          return (
            <button
              key={q.id}
              onClick={() => setActiveIndex(i)}
              className="h-9 w-9 rounded-[var(--radius-md)] text-xs font-semibold flex items-center justify-center transition-colors"
              style={{
                background: isActive ? "var(--color-accent)" : QUESTION_STATUS_STYLE[status].background,
                color: isActive ? "#fff" : QUESTION_STATUS_STYLE[status].color,
                border: `1.5px solid ${isActive ? "var(--color-accent)" : QUESTION_STATUS_STYLE[status].border}`,
              }}
            >
              {q.question_number}
            </button>
          );
        })}
      </div>
    </div>
  );

  // Sections navigator (added 2026-08-28) — questions arrive from the
  // backend already ordered by section then question_number, so grouping
  // by first-seen section_id here preserves that order without a second
  // sort. A Map (not a plain object) specifically for its guaranteed
  // insertion-order iteration. Every question always belongs to a real
  // section (the backend auto-creates a default one), so a single-section
  // paper always produces exactly one group here — that case is handled by
  // simply not rendering the column at all below, not by anything in this
  // computation.
  const sections = useMemo(() => {
    const bySection = new Map<string, { id: string; title: string; indices: number[] }>();
    questions.forEach((q, i) => {
      if (!bySection.has(q.section_id)) {
        bySection.set(q.section_id, { id: q.section_id, title: q.section_title, indices: [] });
      }
      bySection.get(q.section_id)!.indices.push(i);
    });
    return Array.from(bySection.values());
  }, [questions]);

  // Collapse (no manual drag-resize — removed 2026-08-31, explicit
  // request) for the two side panels — desktop-only (mobile stacks
  // everything full-width already, nothing to reclaim there). `null` width
  // means "no explicit size yet" — rendered as `flex: 0 0 150px`, a fixed
  // default rather than a proportional share of the row.
  const [sectionsOpen, setSectionsOpen] = useState(true);
  const [navigatorOpen, setNavigatorOpen] = useState(true);
  const [sectionsWidth] = useState<number | null>(null);
  const [navigatorWidth] = useState<number | null>(null);
  const sectionsPanelRef = useRef<HTMLDivElement>(null);
  const navigatorPanelRef = useRef<HTMLDivElement>(null);

  // Dedicated mobile Sections dropdown (2026-08-31, explicit request) — its
  // own toggle + state, separate from both the plain inline stack it
  // briefly used and the hamburger menu it also briefly lived in. Rendered
  // just below the header / above the question (not here — see near the
  // return statement), collapsed by default so it doesn't push the actual
  // question down the page.
  const [mobileSectionsOpen, setMobileSectionsOpen] = useState(false);
  const activeSectionTitle = sections.find(s => s.indices.includes(activeIndex))?.title;
  const mobileSectionsDropdown = sections.length > 1 && (
    <div className="lg:hidden mb-5 relative z-40">
      <button
        onClick={() => setMobileSectionsOpen(v => !v)}
        aria-expanded={mobileSectionsOpen}
        className="w-full flex items-center justify-between px-4 py-3 rounded-[var(--radius-lg)] bg-white cursor-pointer"
        style={{ border: "1px solid var(--color-border)" }}
      >
        <span className="text-sm font-semibold truncate" style={{ color: "var(--color-text)" }}>
          {activeSectionTitle ?? "Sections"}
        </span>
        <ChevronRight
          size={16}
          className="shrink-0 transition-transform"
          style={{ color: "var(--color-text-muted)", transform: mobileSectionsOpen ? "rotate(-90deg)" : "rotate(90deg)" }}
        />
      </button>
      {mobileSectionsOpen && (
        <>
          {/* Backdrop — blurs the rest of the exam behind the dropdown
              (explicit request 2026-08-31) rather than just dimming it;
              also closes the dropdown on tap-outside. */}
          <div
            className="fixed inset-0 top-14 z-30"
            style={{ background: "rgba(15, 23, 42, 0.15)", backdropFilter: "blur(4px)", WebkitBackdropFilter: "blur(4px)" }}
            onClick={() => setMobileSectionsOpen(false)}
            aria-hidden="true"
          />
          <div className="relative mt-2 p-2 rounded-[var(--radius-lg)] bg-white space-y-1" style={{ border: "1px solid var(--color-border)" }}>
          {sections.map(section => {
            const answeredInSection = section.indices.filter(
              i => (answers[questions[i].id]?.length ?? 0) > 0
            ).length;
            const isActiveSection = section.indices.includes(activeIndex);
            return (
              <button
                key={section.id}
                onClick={() => { setActiveIndex(section.indices[0]); setMobileSectionsOpen(false); }}
                className="w-full text-left pl-3 pr-3.5 py-3 rounded-[var(--radius-md)] transition-colors"
                style={{
                  background: isActiveSection ? "var(--color-accent-light)" : "transparent",
                  border: `1.5px solid ${isActiveSection ? "var(--color-accent)" : "transparent"}`,
                }}
              >
                <p
                  className="text-sm font-semibold truncate"
                  style={{ color: isActiveSection ? "var(--color-accent)" : "var(--color-text)" }}
                >
                  {section.title}
                </p>
                <p
                  className="text-xs mt-1"
                  style={{ color: isActiveSection ? "var(--color-accent)" : "var(--color-text-subtle)" }}
                >
                  {answeredInSection}/{section.indices.length} answered
                </p>
              </button>
            );
          })}
          </div>
        </>
      )}
    </div>
  );

  // Real viewport-left-edge-to-panel-right-edge pixel width for the
  // Sections column's full-bleed white background (below). PageWrapper
  // centers its content (max-w-1400 mx-auto), so the panel's own box is
  // never flush with the true browser edge — a CSS-only "50vw" bleed trick
  // only works when its positioned ancestor is itself viewport-centered,
  // which this narrow flex column isn't. Measuring directly sidesteps that.
  const [sectionsBgWidth, setSectionsBgWidth] = useState<number | null>(null);
  useEffect(() => {
    function measure() {
      const el = sectionsPanelRef.current;
      if (el) setSectionsBgWidth(el.getBoundingClientRect().right);
    }
    measure();
    window.addEventListener("resize", measure);
    return () => window.removeEventListener("resize", measure);
    // questions.length: the panel this measures doesn't exist in the DOM
    // yet on mount (the page is still on the briefing/loading screen) — the
    // ref is null until the real exam UI replaces it once questions load,
    // so that transition has to be a dependency or this never re-measures.
  }, [sectionsOpen, sectionsWidth, questions.length]);

  // Same idea as sectionsBgWidth, mirrored for the Question-numbers panel's
  // bleed to the true viewport *right* edge: distance from the panel's own
  // left edge to the right edge of the window.
  const [navigatorBgWidth, setNavigatorBgWidth] = useState<number | null>(null);
  useEffect(() => {
    function measure() {
      const el = navigatorPanelRef.current;
      if (el) setNavigatorBgWidth(window.innerWidth - el.getBoundingClientRect().left);
    }
    measure();
    window.addEventListener("resize", measure);
    return () => window.removeEventListener("resize", measure);
  }, [navigatorOpen, navigatorWidth, questions.length]);

  // The two vertical dividers between Sections/Question/Question-numbers
  // need to run the full height below the header, not just alongside the
  // question card — same reasoning as sectionsBgWidth above: their real x
  // position depends on the (possibly dragged) column widths, so it's
  // measured rather than guessed at with a fraction.
  const questionColumnRef = useRef<HTMLDivElement>(null);
  const [dividerX, setDividerX] = useState<{ left: number; right: number } | null>(null);
  useEffect(() => {
    function measure() {
      const el = questionColumnRef.current;
      if (el) {
        const rect = el.getBoundingClientRect();
        setDividerX({ left: rect.left, right: rect.right });
      }
    }
    measure();
    window.addEventListener("resize", measure);
    return () => window.removeEventListener("resize", measure);
  }, [sectionsOpen, navigatorOpen, sectionsWidth, navigatorWidth, questions.length]);

  // ── Entry gate — shown before start-session is ever called ──────────────
  // Three variants, decided by the fresh fetch above: a full first-time
  // briefing, a lightweight resume screen, or (handled by examEntered
  // already being true) skip straight through for an already-finished exam.
  if (!examEntered) {
    if (briefingLoading) return <GlobalLoader />;

    if (briefingLoadError || !briefing) {
      return (
        <StudentLayout examMode onExitExam={exitToAssessments}>
          <PageWrapper className="py-16">
            <div className="text-center">
              <div className="w-16 h-16 rounded-full flex items-center justify-center mx-auto mb-5"
                style={{ background: "#FEF2F2" }}>
                <AlertTriangle size={28} style={{ color: "#DC2626" }} />
              </div>
              <h1 className="text-xl font-bold mb-2" style={{ color: "var(--color-text)" }}>
                Couldn't load this assessment
              </h1>
              <p className="text-sm mb-6 leading-relaxed" style={{ color: "var(--color-text-muted)" }}>
                Something went wrong, or this assessment is no longer assigned to you.
                Try again from your assessments list.
              </p>
              <Button variant="primary" onClick={() => router.push("/students/assessments")}>
                Back to Assessments
              </Button>
            </div>
          </PageWrapper>
        </StudentLayout>
      );
    }

    // ── Resume — session already IN_PROGRESS ───────────────────────────────
    // No need to re-show the full briefing: the student already agreed to
    // it once, and their timer is already running, so every extra second
    // here is exam time they don't get back.
    if (briefing.session_status === "IN_PROGRESS") {
      return (
        <StudentLayout examMode onExitExam={exitToAssessments}>
          <PageWrapper className="py-16">
            <div className="text-center">
              <div className="w-16 h-16 rounded-full flex items-center justify-center mx-auto mb-5"
                style={{ background: "#EFF6FF" }}>
                <Maximize size={28} style={{ color: "#2563EB" }} />
              </div>
              <h1 className="text-xl font-bold mb-2" style={{ color: "var(--color-text)" }}>
                Resume {briefing.paper_title}
              </h1>
              <p className="text-sm mb-6 leading-relaxed" style={{ color: "var(--color-text-muted)" }}>
                Your timer is still running. Re-enter fullscreen to continue exactly where you left off.
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
                  Resume in Fullscreen
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

    // ── Full pre-exam briefing — first-time start only ──────────────────────
    // Every section here earns its place: assessment facts (so the student
    // knows what they're walking into before the clock starts), identity
    // confirmation (catches a wrong-account mistake before it becomes an
    // unrecoverable one), the admin's own instructions, the platform's
    // actual enforced rules (numbers below are read from the same
    // TAB_SWITCH_LIMIT/FULLSCREEN_EXIT_LIMIT constants the enforcement
    // effects further down use, so they can never drift out of sync with
    // what actually happens), and practical readiness advice for a
    // placement-drive-grade assessment, not a casual quiz.
    return (
      <StudentLayout examMode onExitExam={exitToAssessments}>
        <PageWrapper className="py-8">
          <h1 className="text-2xl font-bold mb-1" style={{ color: "var(--color-text)" }}>
            {briefing.paper_title}
          </h1>
          <p className="text-sm mb-6" style={{ color: "var(--color-text-subtle)" }}>
            Proctored assessment - read everything below before you begin.
          </p>

          {/* Key facts + identity, side by side — stacking these (each a
              short, wide row) left a lot of dead space at full page width
              and cost an extra screen of vertical scroll for no reason.
              Paired into one row when identity is available; key facts
              alone reclaims the full width and its original 4-across
              layout when the (best-effort) profile fetch failed. */}
          <div className={profile ? "grid grid-cols-1 lg:grid-cols-2 gap-4 mb-6" : "mb-6"}>
            {/* Identity confirmation goes first (left, read first) — best-
                effort, so it's simply absent (not blocking the page) if the
                profile fetch failed. It's a gate ("do not proceed if this
                is wrong"), not supplementary info like the stats beside
                it, so it earns first read-position — the same convention
                a hall ticket or boarding pass uses: identity leads, then
                trip/exam details. */}
            {profile && (
              <div className="rounded-[var(--radius-lg)] p-4"
                style={{ background: "var(--color-surface)", border: "1px solid var(--color-border)" }}>
                <div className="flex items-center gap-2 mb-3">
                  <UserCircle2 size={16} style={{ color: "var(--color-text-muted)" }} />
                  <p className="text-sm font-semibold" style={{ color: "var(--color-text)" }}>Confirm your identity</p>
                </div>
                {/* ID-badge layout, not a 4-column data grid — at full page
                    width a grid this sparse (4 short values) left huge dead
                    gaps between columns instead of reading as one identity. A
                    name + a single "roll · batch · department" line next to
                    an avatar stays compact and legible at any container
                    width, the way an actual ID badge does. */}
                <div className="flex items-center gap-3.5">
                  <div
                    className="w-11 h-11 rounded-full flex items-center justify-center shrink-0 text-sm font-bold text-white"
                    style={{ background: "var(--color-accent)" }}
                  >
                    {(profile.fullname?.[0] ?? profile.student_id[0]).toUpperCase()}
                  </div>
                  <div className="min-w-0">
                    <p className="text-sm font-semibold truncate" style={{ color: "var(--color-text)" }}>
                      {profile.fullname ? toTitleCase(profile.fullname) : "-"}
                    </p>
                    <p className="text-xs mt-0.5 flex items-center gap-1.5 flex-wrap" style={{ color: "var(--color-text-muted)" }}>
                      <span>{profile.student_id}</span>
                      <span aria-hidden="true">·</span>
                      <span>{profile.batch_name}</span>
                      <span aria-hidden="true">·</span>
                      <span>{profile.department}</span>
                    </p>
                  </div>
                </div>
                <p className="text-xs leading-relaxed mt-3 pt-3" style={{ color: "var(--color-text-subtle)", borderTop: "1px solid var(--color-border)" }}>
                  If any of this is incorrect, do not proceed - contact your administrator first.
                  Your submission is recorded permanently under this identity.
                </p>
              </div>
            )}

            <div className={profile ? "grid grid-cols-2 gap-3" : "grid grid-cols-2 sm:grid-cols-4 gap-3"}>
              {[
                // Duration + Questions read together first (the pacing
                // pair — how long, how many, so a student can mentally
                // divide one by the other), then Total Marks + Closes (the
                // scoring/deadline pair — administrative, not pacing).
                { icon: Clock, label: "Duration", value: `${briefing.exam_duration_minutes} min` },
                { icon: HelpCircle, label: "Questions", value: String(briefing.question_count) },
                { icon: Award, label: "Total Marks", value: String(briefing.total_marks) },
                { icon: CalendarClock, label: "Closes", value: formatDateTime(briefing.global_expire_time) },
              ].map(({ icon: Icon, label, value }) => (
                <div key={label} className="rounded-[var(--radius-lg)] p-3.5"
                  style={{ background: "var(--color-surface)", border: "1px solid var(--color-border)" }}>
                  <div className="flex items-center gap-1.5 mb-1" style={{ color: "var(--color-text-subtle)" }}>
                    <Icon size={13} />
                    <span className="text-[11px] font-semibold uppercase tracking-wide">{label}</span>
                  </div>
                  <p className="text-sm font-bold" style={{ color: "var(--color-text)" }}>{value}</p>
                </div>
              ))}
            </div>
          </div>

          {/* Admin instructions + system rules — side by side once there's
              room for it; each reads independently so neither needs the
              other's context, and both are roughly the same weight/length. */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-5 mb-5">
            {/* Admin instructions */}
            <div>
              <p className="text-sm font-semibold mb-2 flex items-center gap-2" style={{ color: "var(--color-text)" }}>
                <FileText size={16} style={{ color: "var(--color-text-muted)" }} /> Instructions from your administrator
              </p>
              <div
                className="text-sm leading-relaxed whitespace-pre-wrap h-56 overflow-y-auto p-4 rounded-[var(--radius-md)]"
                style={{ background: "var(--color-surface)", border: "1px solid var(--color-border)", color: "var(--color-text-muted)" }}
              >
                {briefing.paper_instructions.trim() || "No additional instructions were provided for this assessment."}
              </div>
            </div>

            {/* System rules — accurate to what's actually enforced below,
                not aspirational copy. */}
            <div>
              <p className="text-sm font-semibold mb-2 flex items-center gap-2" style={{ color: "var(--color-text)" }}>
                <ShieldAlert size={16} style={{ color: "var(--color-text-muted)" }} /> System rules - automatically enforced
              </p>
              <ul
                className="space-y-1.5 text-sm leading-relaxed h-56 overflow-y-auto p-4 rounded-[var(--radius-md)]"
                style={{ background: "var(--color-surface)", border: "1px solid var(--color-border)", color: "var(--color-text-muted)" }}
              >
                <li>• This exam must be taken in fullscreen for its entire duration.</li>
                <li>• Exiting fullscreen more than {FULLSCREEN_EXIT_LIMIT} times auto-submits your exam immediately.</li>
                <li>• Switching to another tab or application more than {TAB_SWITCH_LIMIT} times auto-submits your exam immediately.</li>
                <li>• Copy and paste are disabled on every question and answer.</li>
                <li>• Right-clicks and PrintScreen attempts are recorded and reviewed.</li>
                <li>• The exam submits automatically the instant your time runs out - there is no grace period.</li>
                <li>• Once submitted, your answers are final and cannot be changed.</li>
              </ul>
            </div>
          </div>

          {/* Readiness checklist + consent/action, side by side — trial
              layout (2026-08-28) to compare against the stacked version.
              Note this pairs an informational checklist with the actual
              commit-to-start action, which read fine stacked (checklist,
              then act) but are not equal-weight peers side by side; kept
              here only for a visual before/after comparison. */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 mb-6 items-stretch">
            {/* Readiness checklist — practical, not decorative: every line
                here is something that has actually cost a candidate time or
                an attempt in a real placement drive. Title lives inside the
                bordered box (not above it) so this card starts and ends at
                the exact same edges as the consent card beside it — a title
                sitting outside the box was what made the two look
                mismatched even with equal-height grid cells. */}
            <div
              className="p-4 rounded-[var(--radius-md)]"
              style={{ background: "var(--color-surface)", border: "1px solid var(--color-border)" }}
            >
              <p className="text-sm font-semibold mb-2 flex items-center gap-2" style={{ color: "var(--color-text)" }}>
                <ListChecks size={16} style={{ color: "var(--color-text-muted)" }} /> Before you begin
              </p>
              <ul className="space-y-2 text-sm leading-relaxed" style={{ color: "var(--color-text-muted)" }}>
                <li>• Confirm a stable internet connection - a prolonged outage costs exam time you can't get back.</li>
                <li>• Make sure your laptop or desktop is charged, or connected to power, for the full duration.</li>
                <li>• Close every other tab and app - each one counts as a tab switch.</li>
                <li>• Find a quiet, private space where you won't be interrupted.</li>
                <li>• Use a laptop or desktop for the most reliable fullscreen and timing experience.</li>
              </ul>
            </div>

            {/* Consent + action — stretched to match the checklist's height
                (items-stretch on the parent) with its own content spread
                top-to-bottom (label up top, buttons pinned to the bottom),
                so the extra height reads as intentional breathing room
                instead of a mismatched, half-empty card next to a taller one. */}
            <div className="rounded-[var(--radius-lg)] p-4 flex flex-col" style={{ background: "var(--color-surface-hover)", border: "1px solid var(--color-border)" }}>
              {fullscreenError && (
                <p className="text-xs mb-3 leading-relaxed" style={{ color: "var(--color-danger)" }}>
                  {fullscreenError}
                </p>
              )}
              {/* Final glance recap — not decorative: these are the four
                  facts most likely to actually end a student's exam early
                  if forgotten, not just mild inconveniences. Fullscreen and
                  copy/paste were dropped from here on purpose — fullscreen
                  is already stated by the button right below, and
                  copy/paste is an inconvenience, not something that can cut
                  the exam short the way these four can. The tab-switch and
                  fullscreen-exit numbers read straight from
                  TAB_SWITCH_LIMIT/FULLSCREEN_EXIT_LIMIT so they can't drift
                  from what's actually enforced. Placed above the checkbox
                  on purpose: the checkbox affirms "I've read and understood
                  every instruction on this page," so the summary it's
                  affirming needs to be seen first, not after the box is
                  already ticked. */}
              <div className="grid grid-cols-2 gap-2.5 mb-4">
                {[
                  { icon: AppWindow, label: `${TAB_SWITCH_LIMIT} tab switches = auto-submit` },
                  { icon: Minimize, label: `${FULLSCREEN_EXIT_LIMIT} fullscreen exits = auto-submit` },
                  { icon: ShieldAlert, label: "Activity monitored" },
                  { icon: Clock, label: "Auto-submits at 0:00" },
                ].map(({ icon: Icon, label }) => (
                  <div key={label} className="flex items-center gap-2 text-xs" style={{ color: "var(--color-text-muted)" }}>
                    <Icon size={14} style={{ color: "var(--color-text-subtle)", flexShrink: 0 }} />
                    {label}
                  </div>
                ))}
              </div>

              <label className="flex items-start gap-2.5 cursor-pointer select-none">
                <input
                  type="checkbox"
                  checked={agreed}
                  onChange={e => setAgreed(e.target.checked)}
                  className="mt-0.5 h-4 w-4 shrink-0 rounded border-[var(--color-border)] text-[var(--color-accent)] focus:ring-[var(--color-accent)]"
                />
                <span className="text-sm" style={{ color: "var(--color-text)" }}>
                  I confirm the identity above is mine, I have read and understood every instruction
                  and rule on this page and I am ready to begin this proctored, timed assessment.
                </span>
              </label>

              {/* Back removed — the exam-mode header's own "Exit Test"
                  button (top right, always visible) already covers leaving
                  this screen; a second, duplicate way to do the same thing
                  here just crowded the one action that actually belongs on
                  this card. */}
              <div className="flex items-center justify-end gap-2 flex-wrap mt-auto pt-4">
                {fullscreenError && (
                  <Button variant="secondary" size="sm" onClick={() => setExamEntered(true)}>
                    Continue without fullscreen
                  </Button>
                )}
                <Button
                  variant="primary" leftIcon={<Maximize size={15} />}
                  disabled={!agreed} loading={enteringFullscreen} onClick={handleEnterExam}
                >
                  Enter Fullscreen &amp; Start Exam
                </Button>
              </div>
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
      <StudentLayout examMode onExitExam={exitToAssessments}>
        <PageWrapper className="py-16">
          <div className="text-center">
            <div className="w-16 h-16 rounded-full flex items-center justify-center mx-auto mb-5"
              style={{ background: "#F0FDF4" }}>
              <CheckCircle2 size={30} style={{ color: "#16A34A" }} />
            </div>
            <h1 className="text-xl font-bold mb-2" style={{ color: "var(--color-text)" }}>
              {sessionStatus === "AUTO_SUBMITTED" ? "Time's up - Submitted automatically" : "Submitted"}
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

  // Moved into the exam-mode header's center cell (2026-08-28, then joined
  // by the reconnecting badge / answered-count on 2026-08-31, then Submit
  // Exam moved out to the right cell the same day — grouped with Exit Test
  // since both are session-ending actions, rather than sitting next to the
  // purely informational countdown) — a persistent, always-visible header
  // is a better home for the things a student checks/uses most often than
  // a bar that scrolls away with the page content.
  const examCenterContent = (
    <div className="flex items-center gap-2 flex-wrap justify-center">
      {(isReconnecting || isSyncFailing) && (
        <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold"
          style={{ background: "#FFF4E6", color: "#E8820C" }}>
          <WifiOff size={12} /> Reconnecting…
        </span>
      )}
      <div
        className="inline-flex items-center px-2.5 py-1 rounded-[var(--radius-lg)] font-mono text-sm font-bold"
        style={{
          background: lowTime ? "#FEF2F2" : "#EFF6FF",
          color: lowTime ? "#DC2626" : "#2563EB",
          border: `1px solid ${lowTime ? "#FECACA" : "#BFDBFE"}`,
        }}
      >
        {secondsRemaining !== null ? formatCountdown(secondsRemaining) : "-:-"}
      </div>
    </div>
  );
  const examRightContent = (
    <Button variant="primary" size="sm" onClick={() => setConfirmSubmit(true)}>
      Submit Exam
    </Button>
  );

  return (
    <StudentLayout
      examMode
      examCenterContent={examCenterContent}
      examRightContent={examRightContent}
      onExitExam={() => setConfirmExit(true)}
    >
      <PageWrapper className="select-none">

        {/* Dedicated mobile Sections dropdown — just below the header,
            above everything else on the page (2026-08-31, explicit
            request: its own standalone dropdown, not inside the hamburger
            menu, and not the plain always-expanded list it briefly was). */}
        {mobileSectionsDropdown}

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
                This exam monitors tab switches, window focus, fullscreen exits and copy/paste.
                Fullscreen exits are limited to {FULLSCREEN_EXIT_LIMIT} - going over auto-submits your exam.
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

        {/* Three columns on desktop — sections, question, question numbers,
            in that reading order (2026-08-28) — via lg:order-* rather than
            DOM order, so mobile keeps its own sensible stack (sections,
            then the number grid to jump around, then the question itself)
            instead of inheriting the desktop reading order unchanged.
            items-stretch (not items-start) so the side panels' resize
            handles run the full row height corner-to-corner instead of
            stopping wherever that panel's own (often much shorter)
            content ends. */}
        <div className="lg:flex lg:gap-6 lg:items-stretch">
          {/* The two vertical dividing lines, full height below the header
              (top-14 to bottom-0) regardless of how tall the columns'
              actual content is — see dividerX above for why these are
              measured rather than CSS borders on the question column. */}
          {dividerX && (
            <>
              {/* A|B seam — static divider only, not draggable (removed
                  2026-08-31, explicit request): the Sections panel is no
                  longer manually resizable. */}
              <div
                aria-hidden="true"
                className="hidden lg:block fixed top-14 bottom-0 w-px z-20"
                style={{ left: dividerX.left, background: "var(--color-border)" }}
              />
              {/* B|C seam — static divider only, not draggable (removed
                  2026-08-31, explicit request): the Question-numbers panel
                  is no longer manually resizable. */}
              <div
                aria-hidden="true"
                className="hidden lg:block fixed top-14 bottom-0 w-px z-20"
                style={{ left: dividerX.right, background: "var(--color-border)" }}
              />
            </>
          )}
          {/* ── Sections ───────────────────────────────────────────────────
              Only rendered when the paper actually has more than one —
              every question always belongs to *some* section (the backend
              auto-creates a default one for papers that were never split
              up), so a single-section paper would otherwise show a
              "sections" column with exactly one, meaningless entry.
              flex-grow (not a width utility) is what makes this a genuine
              20% share of the row by default — see the sectionsWidth state
              comment above for why. */}
          {sections.length > 1 && (
            sectionsOpen ? (
              <div
                ref={sectionsPanelRef}
                className="relative mb-5 lg:mb-0 lg:order-1 lg:min-w-0 bg-white"
                style={{ flex: sectionsWidth !== null ? `0 0 ${sectionsWidth}px` : "0 0 150px" }}
              >
                {/* The visible content (below) is rendered fixed to the true
                    viewport left edge, not here — this box only reserves
                    width in the flex row so B/C sizing stays correct.
                    PageWrapper centers its content (max-w-1400 mx-auto)
                    with its own p-6, so a plain in-flow child here would
                    sit well short of the real edge on wide screens — the
                    same reason the background needed the same treatment.
                    The mobile copy that used to render inline here now
                    lives in its own dedicated dropdown instead
                    (mobileSectionsDropdown, rendered just below the header
                    near the top of the page, not inside this spacer). */}
                {sectionsBgWidth !== null && (
                  <div
                    className="hidden lg:flex lg:flex-col fixed left-0 top-14 bottom-0 bg-white py-2 pl-3 pr-2"
                    style={{ width: sectionsBgWidth + 24 }}
                  >
                    <div
                      className="flex items-center justify-between pr-1.5 pb-1.5 mb-1"
                      style={{ borderBottom: "1px solid var(--color-border)" }}
                    >
                      <span className="text-xs font-semibold" style={{ color: "var(--color-text-subtle)" }}>
                        Sections
                      </span>
                      <button
                        onClick={() => setSectionsOpen(false)}
                        aria-label="Collapse sections panel"
                        title="Collapse sections panel"
                        className="w-6 h-6 rounded-full flex items-center justify-center cursor-pointer"
                        style={{ background: "#fff", border: "1px solid var(--color-border)", boxShadow: "var(--shadow-sm)" }}
                      >
                        <ChevronLeft size={14} style={{ color: "var(--color-text-muted)" }} />
                      </button>
                    </div>
                    <div className="space-y-1 overflow-y-auto">
                      {sections.map(section => {
                        const answeredInSection = section.indices.filter(
                          i => (answers[questions[i].id]?.length ?? 0) > 0
                        ).length;
                        const isActiveSection = section.indices.includes(activeIndex);
                        return (
                          <button
                            key={section.id}
                            onClick={() => setActiveIndex(section.indices[0])}
                            className="w-full text-left pl-3 pr-3.5 py-3 rounded-[var(--radius-md)] transition-colors"
                            style={{
                              background: isActiveSection ? "var(--color-accent-light)" : "transparent",
                              border: `1.5px solid ${isActiveSection ? "var(--color-accent)" : "transparent"}`,
                            }}
                          >
                            <p
                              className="text-sm font-semibold truncate"
                              style={{ color: isActiveSection ? "var(--color-accent)" : "var(--color-text)" }}
                            >
                              {section.title}
                            </p>
                            <p
                              className="text-xs mt-1"
                              style={{ color: isActiveSection ? "var(--color-accent)" : "var(--color-text-subtle)" }}
                            >
                              {answeredInSection}/{section.indices.length} answered
                            </p>
                          </button>
                        );
                      })}
                    </div>
                  </div>
                )}

              </div>
            ) : (
              <button
                onClick={() => setSectionsOpen(true)}
                aria-label="Expand sections panel"
                title="Expand sections panel"
                className="hidden lg:flex mb-5 lg:mb-0 lg:order-1 lg:shrink-0 lg:self-start w-7 h-10 rounded-[var(--radius-md)] items-center justify-center cursor-pointer"
                style={{ background: "var(--color-surface)", border: "1px solid var(--color-border)" }}
              >
                <ChevronRight size={14} style={{ color: "var(--color-text-muted)" }} />
              </button>
            )
          )}

          {/* ── Question numbers ──────────────────────────────────────────── */}
          {navigatorOpen ? (
            <div
              ref={navigatorPanelRef}
              className="relative mb-5 lg:mb-0 lg:order-3 lg:min-w-0 bg-white"
              style={{ flex: navigatorWidth !== null ? `0 0 ${navigatorWidth}px` : "0 0 150px" }}
            >
              {/* The spacer here only reserves width for the flex row's
                  sizing math on desktop — its real visible content is the
                  fixed, JS-measured panel below. The mobile copy that used
                  to render inline here now lives in the mobile hamburger
                  menu instead (mobileNumberGrid, rendered by
                  MobileExamMenu just above the question) — unlike
                  Sections, which gets its own dedicated dropdown rather
                  than sharing this hamburger. */}
              {navigatorBgWidth !== null && (
                <div
                  className="hidden lg:flex lg:flex-col fixed right-0 top-14 bottom-0 bg-white py-2 pr-3 pl-2"
                  style={{ width: navigatorBgWidth + 24 }}
                >
                  <button
                    onClick={() => setNavigatorOpen(false)}
                    aria-label="Collapse question numbers panel"
                    title="Collapse question numbers panel"
                    className="self-start w-6 h-6 mb-2 rounded-full flex items-center justify-center cursor-pointer"
                    style={{ background: "#fff", border: "1px solid var(--color-border)", boxShadow: "var(--shadow-sm)" }}
                  >
                    <ChevronRight size={14} style={{ color: "var(--color-text-muted)" }} />
                  </button>

                  {statusLegend}
                  <div className="grid grid-cols-[repeat(5,2.25rem)] gap-2 justify-center">
                    {questions.map((q, i) => {
                      const status = getQuestionStatus(q, i);
                      const isActive = i === activeIndex;
                      return (
                        <button
                          key={q.id}
                          onClick={() => setActiveIndex(i)}
                          className="h-9 w-9 rounded-[var(--radius-md)] text-xs font-semibold flex items-center justify-center transition-colors"
                          style={{
                            background: isActive ? "var(--color-accent)" : QUESTION_STATUS_STYLE[status].background,
                            color: isActive ? "#fff" : QUESTION_STATUS_STYLE[status].color,
                            border: `1.5px solid ${isActive ? "var(--color-accent)" : QUESTION_STATUS_STYLE[status].border}`,
                          }}
                        >
                          {q.question_number}
                        </button>
                      );
                    })}
                  </div>
                </div>
              )}
            </div>
          ) : (
            <button
              onClick={() => setNavigatorOpen(true)}
              aria-label="Expand question numbers panel"
              title="Expand question numbers panel"
              className="hidden lg:flex mb-5 lg:mb-0 lg:order-3 lg:shrink-0 lg:self-start w-7 h-10 rounded-[var(--radius-md)] items-center justify-center cursor-pointer"
              style={{ background: "var(--color-surface)", border: "1px solid var(--color-border)" }}
            >
              <ChevronLeft size={14} style={{ color: "var(--color-text-muted)" }} />
            </button>
          )}

          <MobileExamMenu>
            <div className="flex items-center justify-center gap-2 flex-wrap pb-4" style={{ borderBottom: "1px solid var(--color-border)" }}>
              {examRightContent}
              <button
                onClick={() => setConfirmExit(true)}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-[var(--radius-md)] text-sm font-medium border transition-colors cursor-pointer"
                style={{ color: "var(--color-danger)", borderColor: "var(--color-danger)" }}
              >
                <DoorOpen size={15} />
                Exit Test
              </button>
            </div>
            {mobileNumberGrid}
          </MobileExamMenu>

          {/* ── Active question ───────────────────────────────────────────── */}
          {/* flex-grow of 60 vs. the side panels' 20 each (when they're at
              their un-dragged default) — a 20/60/20 split, per explicit
              request (2026-08-30). The two vertical dividing lines are
              rendered separately above (fixed, full height below the
              header, via dividerX) rather than as this box's own
              border-l/border-r — a box-local border only spans this box's
              own height, which starts below the answered-count/Submit bar,
              not up at the header. */}
          <div
            ref={questionColumnRef}
            className="min-w-0 lg:order-2 lg:px-6"
            style={{ flex: "60 1 0%" }}
          >
            <div className="rounded-[var(--radius-xl)] p-5 sm:p-6" style={{ background: "var(--color-surface)", border: "1px solid var(--color-border)" }}>
              <div className="flex items-center justify-between flex-wrap gap-2 mb-4">
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
                  <span className="text-xs" style={{ color: "#E8820C" }}>Saved locally - will sync</span>
                )}
                <button
                  onClick={() => setFlaggedIds(prev => {
                    const next = new Set(prev);
                    if (next.has(activeQuestion.id)) next.delete(activeQuestion.id); else next.add(activeQuestion.id);
                    return next;
                  })}
                  className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold transition-colors cursor-pointer"
                  style={{
                    background: flaggedIds.has(activeQuestion.id) ? "#F5F3FF" : "transparent",
                    color: flaggedIds.has(activeQuestion.id) ? "#7C3AED" : "var(--color-text-subtle)",
                    border: `1px solid ${flaggedIds.has(activeQuestion.id) ? "#DDD6FE" : "var(--color-border)"}`,
                  }}
                >
                  <Flag size={12} fill={flaggedIds.has(activeQuestion.id) ? "#7C3AED" : "none"} />
                  <span className="hidden lg:inline">{flaggedIds.has(activeQuestion.id) ? "Flagged" : "Flag for review"}</span>
                </button>
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

              <div className="flex items-center justify-between mb-3">
                <p className="text-xs font-semibold uppercase tracking-widest" style={{ color: "var(--color-text-subtle)" }}>
                  {activeQuestion.mcq_type === "single" ? "Select one answer" : "Select all that apply"}
                </p>
                {(answers[activeQuestion.id]?.length ?? 0) > 0 && (
                  <button
                    type="button"
                    onClick={() => handleClear(activeQuestion.id)}
                    className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold transition-colors cursor-pointer"
                    style={{ color: "var(--color-text-subtle)", border: "1px solid var(--color-border)" }}
                    onMouseEnter={e => { e.currentTarget.style.background = "var(--color-surface-hover)"; }}
                    onMouseLeave={e => { e.currentTarget.style.background = "transparent"; }}
                  >
                    <X size={12} />
                    Clear response
                  </button>
                )}
              </div>

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
                        background: selected ? "var(--color-accent-light)" : "#fff",
                        border: `1.5px solid ${selected ? "var(--color-accent)" : "var(--color-border)"}`,
                        color: selected ? "var(--color-accent)" : "var(--color-text)",
                      }}
                    >
                      <span className="shrink-0 w-7 h-7 rounded-full flex items-center justify-center text-xs font-bold mt-0.5"
                        style={{ background: selected ? "var(--color-accent)" : "var(--color-primary-light)", color: selected ? "#fff" : "var(--color-primary)" }}>
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

      <ConfirmDialog
        isOpen={confirmExit}
        onClose={() => setConfirmExit(false)}
        onConfirm={exitToAssessments}
        title="Exit without submitting?"
        message={`You have answered ${answeredCount} of ${questions.length} questions. Leaving now does NOT submit your exam - your timer keeps running and your session stays in progress. Come back to this page to resume.`}
        confirmLabel="Exit Test"
        confirmVariant="danger"
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
