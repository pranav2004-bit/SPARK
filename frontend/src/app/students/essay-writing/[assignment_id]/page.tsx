"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { Maximize2, Clock, CheckCircle2, CloudOff, Loader2 } from "lucide-react";
import { StudentLayout } from "@/components/layout/StudentLayout";
import { PageWrapper } from "@/components/layout/PageWrapper";
import { Button } from "@/components/ui/Button";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import { Skeleton } from "@/components/ui/Skeleton";
import { useToast } from "@/components/ui/Toast";
import api, { getErrorMessage } from "@/lib/api";
import { useEssayActivityCapture, clearEssayViolationCounts } from "@/hooks/useEssayActivityCapture";
import { saveDraftResilient, pendingDraft, flushDraftQueue } from "@/lib/essayDraftQueue";
import type { ApiSuccess, EssayAttemptStartResponse, EssayAttemptDetail } from "@/types";

// Task 4.1 (timer) + 4.2 (writing UI) + 4.3 (malpractice capture) combined
// into one page — unlike assessment-service's 1500-line MCQ exam page,
// essay-writing has exactly one question and no navigator, so there's
// fundamentally less surface here; this is a deliberately smaller page,
// not a trimmed-down copy of the MCQ one.

const AUTOSAVE_DEBOUNCE_MS = 2000; // fires after a typing pause, not a fixed interval — Task 4.2's explicit requirement (CLAP's real page, not its demo page)

type Phase = "loading" | "error" | "gate" | "writing" | "submitted" | "already-done";

function formatCountdown(msRemaining: number): string {
  if (msRemaining <= 0) return "00:00";
  const totalSeconds = Math.floor(msRemaining / 1000);
  const m = Math.floor(totalSeconds / 60);
  const s = totalSeconds % 60;
  return `${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
}

function wordCount(text: string): number {
  const trimmed = text.trim();
  return trimmed === "" ? 0 : trimmed.split(/\s+/).length;
}

/** Truncates text to at most `limit` words — Task 4.2's explicit
 * requirement: typing past the limit is discarded, not just flagged. */
function truncateToWordLimit(text: string, limit: number): string {
  const words = text.split(/(\s+)/); // keep whitespace tokens so spacing isn't mangled
  let count = 0;
  let cut = text.length;
  for (let i = 0; i < words.length; i++) {
    if (words[i].trim() === "") continue;
    count++;
    if (count > limit) {
      cut = words.slice(0, i).join("").length;
      break;
    }
  }
  return count > limit ? text.slice(0, cut) : text;
}

export default function StudentEssayAttemptPage() {
  const { assignment_id } = useParams<{ assignment_id: string }>();
  const router = useRouter();
  const toast = useToast();

  const [phase, setPhase] = useState<Phase>("loading");
  const [attemptId, setAttemptId] = useState<string | null>(null);
  const [detail, setDetail] = useState<EssayAttemptDetail | null>(null);
  const [draft, setDraft] = useState("");
  const [msRemaining, setMsRemaining] = useState<number | null>(null);
  const [saveStatus, setSaveStatus] = useState<"idle" | "saving" | "saved" | "queued">("idle");
  const [confirmSubmit, setConfirmSubmit] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  const autosaveTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const submitRef = useRef<() => void>(() => {});

  const activity = useEssayActivityCapture(phase === "writing" ? attemptId : null);

  function exitToList() {
    router.push("/students/essay-writing");
  }

  // ── Load: start-or-resume the attempt, then fetch its detail ───────────
  useEffect(() => {
    let cancelled = false;
    api.post<ApiSuccess<EssayAttemptStartResponse>>(`/essay/student/assignments/${assignment_id}/start-attempt/`)
      .then(res => {
        if (cancelled) return;
        const { attempt_id, status } = res.data.data;
        setAttemptId(attempt_id);
        if (status === "SUBMITTED" || status === "AUTO_SUBMITTED") {
          setPhase("already-done");
          return;
        }
        return api.get<ApiSuccess<EssayAttemptDetail>>(`/essay/student/attempts/${attempt_id}/`)
          .then(detailRes => {
            if (cancelled) return;
            setDetail(detailRes.data.data);
            // Recover a locally-queued draft (network drop before this
            // load) in preference to the server's last-confirmed draft —
            // the queued one is strictly newer by construction.
            const queued = pendingDraft(attempt_id);
            setDraft(queued ?? detailRes.data.data.draft_response);
            setPhase("gate");
          });
      })
      .catch(err => { if (!cancelled) { toast.error(getErrorMessage(err)); setPhase("error"); } });
    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [assignment_id]);

  // ── Timer: countdown ticks locally between attempts to re-sync with the
  // server; auto-submits once it hits zero (Task 4.1) ─────────────────────
  useEffect(() => {
    if (phase !== "writing" || !detail) return;
    const endsAtMs = new Date(detail.ends_at).getTime();
    const tick = () => {
      const remaining = endsAtMs - Date.now();
      setMsRemaining(remaining);
      if (remaining <= 0) submitRef.current();
    };
    tick();
    const interval = setInterval(tick, 1000);
    return () => clearInterval(interval);
  }, [phase, detail]);

  // ── Autosave: debounced, fires after a typing pause (Task 4.2) ─────────
  const scheduleAutosave = useCallback((text: string) => {
    if (!attemptId) return;
    if (autosaveTimerRef.current) clearTimeout(autosaveTimerRef.current);
    autosaveTimerRef.current = setTimeout(async () => {
      setSaveStatus("saving");
      try {
        const result = await saveDraftResilient(attemptId, text);
        setSaveStatus(result);
      } catch (err) {
        toast.error(getErrorMessage(err));
        setSaveStatus("idle");
      }
    }, AUTOSAVE_DEBOUNCE_MS);
  }, [attemptId, toast]);

  // ── Network-drop resilience: flush whatever's queued on reconnect (Task 4.2, ET10) ──
  useEffect(() => {
    if (!attemptId || phase !== "writing") return;
    const onOnline = () => {
      void flushDraftQueue(attemptId).then(flushed => { if (flushed) setSaveStatus("saved"); });
    };
    window.addEventListener("online", onOnline);
    // Also try periodically — `online` doesn't always fire reliably across
    // every browser/network-stack combination.
    const interval = setInterval(() => {
      if (pendingDraft(attemptId) !== null) void onOnline();
    }, 15000);
    return () => { window.removeEventListener("online", onOnline); clearInterval(interval); };
  }, [attemptId, phase]);

  function handleChange(text: string) {
    const limit = detail?.question?.word_limit;
    const bounded = limit != null ? truncateToWordLimit(text, limit) : text;
    setDraft(bounded);
    scheduleAutosave(bounded);
  }

  async function handleSubmit() {
    if (!attemptId || submitting) return;
    setSubmitting(true);
    try {
      await api.post(`/essay/student/attempts/${attemptId}/submit/`, { draft_response: draft });
      clearEssayViolationCounts(attemptId);
      setPhase("submitted");
    } catch (err) {
      toast.error(getErrorMessage(err));
    } finally {
      setSubmitting(false);
      setConfirmSubmit(false);
    }
  }
  submitRef.current = handleSubmit;

  async function handleEnterWriting() {
    try {
      await activity.requestFullscreen();
    } catch {
      // Unsupported/denied — proceed anyway rather than blocking the
      // student from an exam over a browser capability gap; the
      // server-side timer/malpractice checks are the real enforcement.
    }
    setPhase("writing");
  }

  // ── Render ───────────────────────────────────────────────────────────────

  if (phase === "loading") {
    return (
      <StudentLayout examMode onExitExam={exitToList}>
        <PageWrapper className="py-16">
          <Skeleton className="h-8 w-64 mb-4" />
          <Skeleton className="h-48 w-full" />
        </PageWrapper>
      </StudentLayout>
    );
  }

  if (phase === "error") {
    return (
      <StudentLayout examMode onExitExam={exitToList}>
        <PageWrapper className="py-16 text-center">
          <p className="text-sm" style={{ color: "var(--color-danger)" }}>
            Couldn't load this assessment. It may not be live, or you may not be allocated to it.
          </p>
          <Button className="mt-4" onClick={exitToList}>Back to Essay Writing</Button>
        </PageWrapper>
      </StudentLayout>
    );
  }

  if (phase === "already-done") {
    return (
      <StudentLayout examMode onExitExam={exitToList}>
        <PageWrapper className="py-16 text-center">
          <CheckCircle2 size={32} style={{ color: "#16A34A" }} className="mx-auto mb-3" />
          <p className="text-sm font-medium" style={{ color: "var(--color-text)" }}>You've already submitted this essay.</p>
          <Button className="mt-4" onClick={exitToList}>Back to Essay Writing</Button>
        </PageWrapper>
      </StudentLayout>
    );
  }

  if (phase === "submitted") {
    return (
      <StudentLayout examMode onExitExam={exitToList}>
        <PageWrapper className="py-16 text-center">
          <CheckCircle2 size={32} style={{ color: "#16A34A" }} className="mx-auto mb-3" />
          <p className="text-sm font-medium" style={{ color: "var(--color-text)" }}>Your essay has been submitted.</p>
          <p className="text-xs mt-1" style={{ color: "var(--color-text-subtle)" }}>Your score and feedback will be available once it's been evaluated.</p>
          <Button className="mt-4" onClick={exitToList}>Back to Essay Writing</Button>
        </PageWrapper>
      </StudentLayout>
    );
  }

  if (phase === "gate") {
    return (
      <StudentLayout examMode onExitExam={exitToList}>
        <PageWrapper className="py-16 text-center max-w-lg mx-auto">
          <Maximize2 size={28} style={{ color: "var(--color-accent)" }} className="mx-auto mb-3" />
          <h2 className="text-base font-semibold" style={{ color: "var(--color-text)" }}>Ready to begin?</h2>
          <p className="text-sm mt-2" style={{ color: "var(--color-text-subtle)" }}>
            The timer starts the moment you click Begin, and this page will enter fullscreen.
            Copying and pasting into your response are disabled and logged.
          </p>
          <Button className="mt-5" onClick={handleEnterWriting}>Begin Writing</Button>
        </PageWrapper>
      </StudentLayout>
    );
  }

  // phase === "writing"
  const question = detail?.question;
  const limit = question?.word_limit ?? 0;
  const count = wordCount(draft);
  const nearLimit = limit > 0 && count >= limit * 0.9;

  return (
    <StudentLayout
      examMode
      onExitExam={exitToList}
      examCenterContent={
        msRemaining != null && (
          <span className="flex items-center gap-1.5 text-sm font-semibold" style={{ color: msRemaining < 60000 ? "var(--color-danger)" : "var(--color-text)" }}>
            <Clock size={14} /> {formatCountdown(msRemaining)}
          </span>
        )
      }
      examRightContent={
        <Button size="sm" variant="primary" onClick={() => setConfirmSubmit(true)}>Submit</Button>
      }
    >
      <PageWrapper className="py-8">
        <div className="max-w-3xl mx-auto">
          <div
            className="rounded-[var(--radius-xl)] p-5 mb-4"
            style={{ background: "var(--color-surface)", border: "1px solid var(--color-border)", boxShadow: "var(--shadow-sm)" }}
          >
            <p className="text-sm leading-relaxed" style={{ color: "var(--color-text)" }}>{question?.question_text}</p>
          </div>

          <textarea
            autoFocus
            value={draft}
            onChange={e => handleChange(e.target.value)}
            onPaste={e => e.preventDefault()}
            rows={16}
            placeholder="Start writing your response…"
            className="w-full text-sm rounded-[var(--radius-md)] px-4 py-3 outline-none leading-relaxed resize-y border"
            style={{ background: "var(--color-surface)", borderColor: "var(--color-border)", color: "var(--color-text)" }}
          />

          <div className="flex items-center justify-between mt-2 text-xs">
            <span style={{ color: nearLimit ? "var(--color-danger)" : "var(--color-text-subtle)" }}>
              {count} / {limit} words
            </span>
            <span className="flex items-center gap-1.5" style={{ color: "var(--color-text-subtle)" }}>
              {saveStatus === "saving" && (<><Loader2 size={12} className="animate-spin" /> Saving…</>)}
              {saveStatus === "saved" && (<><CheckCircle2 size={12} style={{ color: "#16A34A" }} /> Saved</>)}
              {saveStatus === "queued" && (<><CloudOff size={12} /> Saved locally, reconnecting…</>)}
            </span>
          </div>
        </div>
      </PageWrapper>

      <ConfirmDialog
        isOpen={confirmSubmit}
        onClose={() => setConfirmSubmit(false)}
        onConfirm={handleSubmit}
        title="Submit your essay?"
        message="Once submitted, you won't be able to make further changes."
        confirmLabel="Submit"
        loading={submitting}
      />
    </StudentLayout>
  );
}
