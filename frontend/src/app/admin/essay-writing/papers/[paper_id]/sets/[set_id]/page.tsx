"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { Trash2, PenLine } from "lucide-react";
import { AdminLayout } from "@/components/layout/AdminLayout";
import { PageWrapper } from "@/components/layout/PageWrapper";
import { PageHeader } from "@/components/layout/PageHeader";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import { EmptyState } from "@/components/ui/EmptyState";
import { Skeleton } from "@/components/ui/Skeleton";
import { useToast } from "@/components/ui/Toast";
import api, { getErrorMessage } from "@/lib/api";
import type { EssayPaper, EssaySet, EssayQuestion, ApiSuccess } from "@/types";

interface SetDetail {
  set:      EssaySet;
  paper:    EssayPaper;
  question: EssayQuestion | null;
}

// Exactly one question per set (EssayQuestion.set is a OneToOneField on the
// backend) — this page is a single-prompt editor, not a question list, and
// deliberately has no image upload / options / sections, unlike
// assessment-service's equivalent set editor (essay-service's scope is
// text-only per docs/adr/002-essay-service-architecture.md Decision 5).
export default function AdminEssaySetPage() {
  const { paper_id, set_id } = useParams<{ paper_id: string; set_id: string }>();
  const router = useRouter();
  const toast  = useToast();

  const [detail, setDetail] = useState<SetDetail | null>(null);
  const [loading, setLoading] = useState(true);

  const [questionText, setQuestionText] = useState("");
  const [rubricPrompt, setRubricPrompt] = useState("");
  const [wordLimit, setWordLimit] = useState("500");
  const [timeLimit, setTimeLimit] = useState("30");
  const [maxScore, setMaxScore] = useState("10");
  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useState("");
  const [deleteConfirm, setDeleteConfirm] = useState(false);
  const [deleting, setDeleting] = useState(false);

  function populateForm(q: EssayQuestion | null) {
    setQuestionText(q?.question_text ?? "");
    setRubricPrompt(q?.llm_rubric_prompt ?? "");
    setWordLimit(String(q?.word_limit ?? 500));
    setTimeLimit(String(q?.time_limit_minutes ?? 30));
    setMaxScore(String(q?.max_score ?? 10));
  }

  const load = () => {
    api.get<ApiSuccess<SetDetail>>(`/essay/admin/sets/${set_id}/`)
      .then(res => { setDetail(res.data.data); populateForm(res.data.data.question); })
      .catch(err => { toast.error(getErrorMessage(err)); router.push(`/admin/essay-writing/papers/${paper_id}`); })
      .finally(() => setLoading(false));
  };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(load, [set_id]);

  const hasQuestion = !!detail?.question;

  async function handleSave() {
    if (!questionText.trim()) { setFormError("The essay prompt cannot be empty."); return; }
    if (!rubricPrompt.trim()) { setFormError("The LLM evaluation rubric cannot be empty."); return; }
    const wl = Number(wordLimit), tl = Number(timeLimit), ms = Number(maxScore);
    if (!Number.isInteger(wl) || wl <= 0) { setFormError("Word limit must be a positive whole number."); return; }
    if (!Number.isInteger(tl) || tl <= 0) { setFormError("Time limit must be a positive whole number of minutes."); return; }
    if (!Number.isInteger(ms) || ms <= 0) { setFormError("Max score must be a positive whole number."); return; }

    setSaving(true); setFormError("");
    try {
      if (hasQuestion) {
        const res = await api.patch<ApiSuccess<EssayQuestion>>(`/essay/admin/questions/${detail!.question!.id}/`, {
          question_text: questionText, llm_rubric_prompt: rubricPrompt,
          word_limit: wl, time_limit_minutes: tl, max_score: ms,
        });
        setDetail(prev => prev ? { ...prev, question: res.data.data } : prev);
        toast.success("Prompt updated.");
      } else {
        const res = await api.post<ApiSuccess<EssayQuestion>>(`/essay/admin/sets/${set_id}/question/`, {
          question_text: questionText, llm_rubric_prompt: rubricPrompt,
          word_limit: wl, time_limit_minutes: tl, max_score: ms,
        });
        setDetail(prev => prev ? { ...prev, question: res.data.data } : prev);
        toast.success("Prompt created.");
      }
    } catch (err) { setFormError(getErrorMessage(err)); }
    finally { setSaving(false); }
  }

  async function handleDelete() {
    if (!detail?.question) return;
    setDeleting(true);
    try {
      await api.delete(`/essay/admin/questions/${detail.question.id}/`);
      setDetail(prev => prev ? { ...prev, question: null } : prev);
      populateForm(null);
      setDeleteConfirm(false);
      toast.success("Prompt deleted.");
    } catch (err) { toast.error(getErrorMessage(err)); }
    finally { setDeleting(false); }
  }

  return (
    <AdminLayout>
      <PageWrapper>
        <PageHeader
          title={detail?.set.label ?? ""}
          titleSkeleton={loading ? <Skeleton className="h-8 w-32" /> : undefined}
          subtitle={detail ? `${detail.paper.title} — writing prompt & LLM evaluation rubric` : ""}
          backHref={`/admin/essay-writing/papers/${paper_id}`}
          breadcrumb={
            <span className="cursor-pointer hover:underline" onClick={() => router.push(`/admin/essay-writing/papers/${paper_id}`)}>
              {detail?.paper.title ?? "Essay Writing"}
            </span>
          }
          rightSlot={hasQuestion ? (
            <Button variant="secondary" leftIcon={<Trash2 size={14} />} onClick={() => setDeleteConfirm(true)}>
              Delete prompt
            </Button>
          ) : undefined}
        />

        {loading ? (
          <div className="space-y-3">
            <Skeleton className="h-32 w-full" />
            <Skeleton className="h-10 w-full" />
          </div>
        ) : (
          <div
            className="rounded-[var(--radius-xl)] p-5"
            style={{ background: "var(--color-surface)", border: "1px solid var(--color-border)", boxShadow: "var(--shadow-sm)" }}
          >
            {!hasQuestion && (
              <EmptyState
                icon={PenLine}
                title="No prompt authored yet"
                subtitle="This set needs exactly one writing prompt — fill in the form below and save."
              />
            )}

            <div className="mt-4">
              <label className="block text-xs font-semibold mb-1.5" style={{ color: "var(--color-text-muted)" }}>
                Essay prompt (shown to the student)
              </label>
              <textarea
                value={questionText}
                onChange={e => { setQuestionText(e.target.value); setFormError(""); }}
                rows={4}
                placeholder="e.g. Describe a time you overcame a significant challenge and what you learned from it."
                className="w-full text-sm rounded-[var(--radius-md)] px-3.5 py-2.5 outline-none leading-relaxed border"
                style={{ background: "var(--color-surface)", borderColor: "var(--color-border)", color: "var(--color-text)" }}
              />
            </div>

            <div className="mt-4">
              <label className="block text-xs font-semibold mb-1.5" style={{ color: "var(--color-text-muted)" }}>
                LLM evaluation rubric (admin-only — never shown to the student)
              </label>
              <textarea
                value={rubricPrompt}
                onChange={e => { setRubricPrompt(e.target.value); setFormError(""); }}
                rows={4}
                placeholder="e.g. Score for clarity, structure, grammar, and how directly the response addresses the prompt. Deduct for off-topic content."
                className="w-full text-sm rounded-[var(--radius-md)] px-3.5 py-2.5 outline-none leading-relaxed border"
                style={{ background: "var(--color-surface)", borderColor: "var(--color-border)", color: "var(--color-text)" }}
              />
              <p className="text-xs mt-1.5" style={{ color: "var(--color-text-subtle)" }}>
                Sent to the LLM alongside this question and the student's response — never sent to the student.
              </p>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 mt-4">
              <Input
                label="Word limit"
                type="number"
                min={1}
                value={wordLimit}
                onChange={e => { setWordLimit(e.target.value); setFormError(""); }}
              />
              <Input
                label="Time limit (minutes)"
                type="number"
                min={1}
                value={timeLimit}
                onChange={e => { setTimeLimit(e.target.value); setFormError(""); }}
              />
              <Input
                label="Max score"
                type="number"
                min={1}
                value={maxScore}
                onChange={e => { setMaxScore(e.target.value); setFormError(""); }}
              />
            </div>

            {formError && (
              <p className="text-xs mt-3" style={{ color: "var(--color-danger)" }}>{formError}</p>
            )}

            <div className="flex justify-end mt-5">
              <Button loading={saving} onClick={handleSave}>
                {hasQuestion ? "Save changes" : "Create prompt"}
              </Button>
            </div>
          </div>
        )}
      </PageWrapper>

      <ConfirmDialog
        isOpen={deleteConfirm}
        onClose={() => setDeleteConfirm(false)}
        onConfirm={handleDelete}
        title="Delete prompt?"
        message="This set's writing prompt and rubric will be permanently removed. This cannot be undone."
        confirmLabel="Delete"
        confirmVariant="danger"
        loading={deleting}
      />
    </AdminLayout>
  );
}
