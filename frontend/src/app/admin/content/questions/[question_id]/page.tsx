"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { ImagePlus, Layers, Plus, Trash2 } from "lucide-react";
import { AdminLayout } from "@/components/layout/AdminLayout";
import { PageWrapper } from "@/components/layout/PageWrapper";
import { PageHeader } from "@/components/layout/PageHeader";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { EmptyState } from "@/components/ui/EmptyState";
import { Skeleton } from "@/components/ui/Skeleton";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import { useToast } from "@/components/ui/Toast";
import {
  contentApi, messageFor, ContentApiError, STATUS_TEXT,
  type ContentOption, type ContentQuestion, type ContentStatus,
} from "@/lib/contentApi";

const LETTERS = ["A", "B", "C", "D", "E", "F"];
const MIN_OPTIONS = 2;
const MAX_OPTIONS = 6;
const IMAGE_TYPES = ["image/jpeg", "image/png", "image/webp", "image/gif", "image/avif"];

type ConfirmAction = "publish" | "retire" | "discard-draft" | "delete" | null;

interface DraftOption {
  option_text: string;
  is_correct: boolean;
}

export default function AdminContentQuestionPage() {
  const { question_id } = useParams<{ question_id: string }>();
  const toast = useToast();
  const [question, setQuestion] = useState<ContentQuestion | null>(null);
  const [etag, setEtag] = useState<string | null>(null);
  const [versions, setVersions] = useState<{ version_no: number; state: string; published_at: string | null }[]>([]);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [staleError, setStaleError] = useState(false);
  const [busy, setBusy] = useState(false);

  const [text, setText] = useState("");
  const [explanation, setExplanation] = useState("");
  const [options, setOptions] = useState<DraftOption[]>([]);
  const [formError, setFormError] = useState<string | null>(null);

  const [confirming, setConfirming] = useState<ConfirmAction>(null);
  const [imageAlt, setImageAlt] = useState("");
  const [imageError, setImageError] = useState<string | null>(null);
  const fileInput = useRef<HTMLInputElement>(null);

  const editable = question?.editable_version ?? null;
  const inReview = editable?.state === "in_review";
  const retired = question?.status === "retired";
  const lockedForEdit = inReview || retired;

  const applyQuestion = useCallback((q: ContentQuestion, newEtag: string | null) => {
    setQuestion(q);
    setEtag(newEtag);
    setStaleError(false);
    const v = q.editable_version;
    setText(v?.question_text ?? "");
    setExplanation(v?.explanation ?? "");
    setOptions(
      v?.options.length
        ? v.options.map((o) => ({ option_text: o.option_text, is_correct: !!o.is_correct }))
        : [{ option_text: "", is_correct: true }, { option_text: "", is_correct: false }],
    );
  }, []);

  const load = useCallback(async () => {
    setLoadError(null);
    try {
      const { data, etag: tag } = await contentApi.getQuestion(question_id);
      applyQuestion(data, tag);
      const { data: list } = await contentApi.listVersions(question_id);
      setVersions(list);
    } catch (err) {
      setLoadError(messageFor(err));
    }
  }, [question_id, applyQuestion]);

  useEffect(() => {
    load();
  }, [load]);

  function isStale(err: unknown) {
    return err instanceof ContentApiError && (err.status === 412 || err.code === "stale_version");
  }

  // Shared handler: a stale ETag means someone else changed the question, so
  // the form is not trusted any more and the user must reload.
  function handleError(err: unknown, setInline?: (msg: string) => void) {
    if (isStale(err)) {
      setStaleError(true);
      return;
    }
    const msg = messageFor(err);
    if (setInline) setInline(msg);
    else toast.error(msg);
  }

  function validDraftOptions() {
    return options
      .map((o) => ({ option_text: o.option_text.trim(), is_correct: o.is_correct }))
      .filter((o) => o.option_text.length > 0);
  }

  async function saveDraft() {
    setFormError(null);
    if (!text.trim()) {
      setFormError("Enter the question text.");
      return;
    }
    const opts = validDraftOptions();
    if (opts.length > MAX_OPTIONS) {
      setFormError(`Use at most ${MAX_OPTIONS} options.`);
      return;
    }
    const payload: ContentOption[] = opts.map((o, idx) => ({
      label: LETTERS[idx], option_text: o.option_text, is_correct: o.is_correct, display_order: idx + 1,
    }));
    setBusy(true);
    try {
      const { data, etag: tag } = await contentApi.saveDraft(
        question_id, { text: text.trim(), explanation: explanation.trim(), options: payload }, etag,
      );
      applyQuestion(data, tag);
      toast.success("Draft saved.");
    } catch (err) {
      handleError(err, setFormError);
    } finally {
      setBusy(false);
    }
  }

  async function runAction(action: "submit-review" | "withdraw-review" | "publish" | "retire" | "restore" | "discard-draft") {
    setBusy(true);
    try {
      const { data, etag: tag } = await contentApi.questionAction(question_id, action, etag);
      applyQuestion(data, tag ?? etag);
      const { data: list } = await contentApi.listVersions(question_id);
      setVersions(list);
      toast.success(`Done: ${action.replace("-", " ")}.`);
    } catch (err) {
      handleError(err);
    } finally {
      setBusy(false);
      setConfirming(null);
    }
  }

  async function deleteQuestion() {
    setBusy(true);
    try {
      await contentApi.deleteQuestion(question_id);
      toast.success("Question deleted.");
      window.location.assign(question ? `/admin/content/nodes/${question.node_id}` : "/admin/content");
    } catch (err) {
      // Used questions cannot be deleted: the server says so and we surface it.
      toast.error(messageFor(err));
      setConfirming(null);
    } finally {
      setBusy(false);
    }
  }

  async function uploadImage(file: File) {
    setImageError(null);
    if (!imageAlt.trim()) {
      setImageError("Add alt text describing the image before uploading.");
      return;
    }
    if (!IMAGE_TYPES.includes(file.type)) {
      setImageError("Only JPEG, PNG, WebP, GIF, or AVIF images are allowed.");
      return;
    }
    setBusy(true);
    try {
      const presign = await contentApi.presignImage(question_id, file.name, file.type, etag);
      // Direct upload to storage. Plain fetch on purpose: the API client's
      // auth header must not be sent to the storage host.
      const put = await fetch(presign.data.upload_url, {
        method: "PUT",
        headers: { "Content-Type": file.type },
        body: file,
      });
      if (!put.ok) {
        setImageError("Upload failed. Try again.");
        return;
      }
      const { data, etag: tag } = await contentApi.confirmImage(question_id, presign.data.file_key, imageAlt.trim(), etag);
      applyQuestion(data, tag);
      setImageAlt("");
      toast.success("Image attached.");
    } catch (err) {
      handleError(err, setImageError);
    } finally {
      setBusy(false);
      if (fileInput.current) fileInput.current.value = "";
    }
  }

  async function removeImage() {
    setBusy(true);
    try {
      const { data, etag: tag } = await contentApi.removeImage(question_id, etag);
      applyQuestion(data, tag);
      toast.success("Image removed.");
    } catch (err) {
      handleError(err);
    } finally {
      setBusy(false);
    }
  }

  function setOption(idx: number, patch: Partial<DraftOption>) {
    setOptions((prev) => prev.map((o, j) => (j === idx ? { ...o, ...patch } : o)));
  }

  function markCorrect(idx: number) {
    setOptions((prev) => prev.map((o, j) => ({ ...o, is_correct: j === idx })));
  }

  function removeOption(idx: number) {
    setOptions((prev) => prev.filter((_, j) => j !== idx));
  }

  if (loadError) {
    return (
      <AdminLayout>
        <PageWrapper>
          <EmptyState icon={Layers} title="Could not load this question" subtitle={loadError} action={{ label: "Try again", onClick: load }} />
        </PageWrapper>
      </AdminLayout>
    );
  }

  const statusLabel = STATUS_TEXT;

  return (
    <AdminLayout>
      <PageWrapper>
        <nav aria-label="Breadcrumb" className="text-xs mb-3" style={{ color: "var(--color-text-muted)" }}>
          <Link href="/admin/content" className="underline-offset-2 hover:underline">Content</Link>
          {question && (
            <>
              {" / "}
              <Link href={`/admin/content/nodes/${question.node_id}`} className="underline-offset-2 hover:underline">Topic</Link>
            </>
          )}
        </nav>

        {question === null ? (
          <Skeleton className="h-10 w-64" />
        ) : (
          <PageHeader
            title={`Question ${question.display_order}`}
            subtitle={`${statusLabel[question.status]} · version ${question.current_version_no}${editable ? ` (${editable.state.replace("_", " ")})` : ""}`}
            rightSlot={
              <div className="flex flex-wrap gap-2">
                {question.status === "draft" && editable?.state === "draft" && (
                  <Button size="sm" variant="secondary" disabled={busy} onClick={() => runAction("submit-review")}>Submit for review</Button>
                )}
                {inReview && (
                  <Button size="sm" variant="secondary" disabled={busy} onClick={() => runAction("withdraw-review")}>Withdraw review</Button>
                )}
                {editable && !inReview && (
                  <Button size="sm" variant="primary" disabled={busy} onClick={() => setConfirming("publish")}>Publish</Button>
                )}
                {question.status === "published" && (
                  <Button size="sm" variant="warning" disabled={busy} onClick={() => setConfirming("retire")}>Unpublish</Button>
                )}
                {question.status === "retired" && (
                  <Button size="sm" variant="secondary" disabled={busy} onClick={() => runAction("restore")}>Publish</Button>
                )}
                {editable?.state === "draft" && question.published_version_no !== null && (
                  <Button size="sm" variant="ghost" disabled={busy} onClick={() => setConfirming("discard-draft")}>Discard draft</Button>
                )}
                {question.published_version_no === null && (
                  <Button size="sm" variant="danger" disabled={busy} onClick={() => setConfirming("delete")}>Delete</Button>
                )}
              </div>
            }
          />
        )}

        {staleError && question && (
          <div role="alert" className="mt-4 rounded-[var(--radius-lg)] p-3 text-sm flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between"
            style={{ border: "1px solid var(--color-warning)", background: "var(--color-surface)" }}>
            <span>{CONFLICT_TEXT}</span>
            <Button size="sm" variant="secondary" onClick={load}>Reload</Button>
          </div>
        )}

        {question && (
          <div className="mt-6 grid gap-6 lg:grid-cols-3">
            <section aria-labelledby="editor-heading" className="lg:col-span-2 space-y-5">
              <h2 id="editor-heading" className="text-sm font-semibold">Editor</h2>
              {lockedForEdit && (
                <p className="text-sm" style={{ color: "var(--color-text-muted)" }}>
                  {retired ? "This question is unpublished. Publish it to edit." : "This draft is in review. Withdraw the review to edit it."}
                </p>
              )}
              <fieldset disabled={lockedForEdit || busy} className="space-y-5">
                <Input label="Question text" value={text} onChange={(e) => setText(e.target.value)} maxLength={2000} />

                <div>
                  <label htmlFor="explanation" className="block text-xs font-medium mb-1">Explanation (optional)</label>
                  <textarea
                    id="explanation"
                    value={explanation}
                    onChange={(e) => setExplanation(e.target.value)}
                    maxLength={2000}
                    rows={3}
                    className="w-full rounded-[var(--radius-md)] p-2 text-sm"
                    style={{ border: "1px solid var(--color-border)", background: "var(--color-surface)" }}
                  />
                </div>

                <fieldset>
                  <legend className="text-xs font-medium mb-2">Options (mark the one correct answer)</legend>
                  <div className="space-y-2">
                    {options.map((o, idx) => (
                      <div key={idx} className="flex items-center gap-2">
                        <input
                          type="radio"
                          name="correct"
                          aria-label={`Option ${LETTERS[idx]} is correct`}
                          checked={o.is_correct}
                          onChange={() => markCorrect(idx)}
                          className="h-5 w-5 shrink-0"
                        />
                        <div className="flex-1 min-w-0">
                          <Input
                            aria-label={`Option ${LETTERS[idx]} text`}
                            value={o.option_text}
                            onChange={(e) => setOption(idx, { option_text: e.target.value })}
                            maxLength={500}
                          />
                        </div>
                        <Button size="sm" variant="ghost" aria-label={`Remove option ${LETTERS[idx]}`} disabled={options.length <= MIN_OPTIONS} onClick={() => removeOption(idx)}>
                          <Trash2 size={14} />
                        </Button>
                      </div>
                    ))}
                  </div>
                  <Button
                    size="sm" variant="secondary" className="mt-3" leftIcon={<Plus size={14} />}
                    disabled={options.length >= MAX_OPTIONS}
                    onClick={() => setOptions((prev) => [...prev, { option_text: "", is_correct: false }])}
                  >
                    Add option
                  </Button>
                </fieldset>

                {formError && <p role="alert" className="text-sm" style={{ color: "var(--color-danger)" }}>{formError}</p>}

                <Button variant="primary" loading={busy} disabled={lockedForEdit} onClick={saveDraft}>Save draft</Button>
              </fieldset>
            </section>

            <aside className="space-y-6" aria-label="Image and versions">
              <section aria-labelledby="image-heading" className="space-y-3">
                <h2 id="image-heading" className="text-sm font-semibold">Image</h2>
                {editable?.image_url ? (
                  <div className="space-y-2">
                    {/* eslint-disable-next-line @next/next/no-img-element */}
                    <img src={editable.image_url} alt={editable.image_alt_text} className="max-h-60 rounded-[var(--radius-md)]" />
                    <Button size="sm" variant="danger" leftIcon={<Trash2 size={14} />} disabled={busy || lockedForEdit} onClick={removeImage}>Remove image</Button>
                  </div>
                ) : (
                  <p className="text-xs" style={{ color: "var(--color-text-muted)" }}>No image attached.</p>
                )}
                <Input label="Alt text (required for images)" value={imageAlt} onChange={(e) => setImageAlt(e.target.value)} maxLength={500} error={imageError ?? undefined} disabled={lockedForEdit} />
                <input
                  ref={fileInput}
                  type="file"
                  accept={IMAGE_TYPES.join(",")}
                  aria-label="Choose image file"
                  disabled={busy || lockedForEdit}
                  onChange={(e) => {
                    const file = e.target.files?.[0];
                    if (file) uploadImage(file);
                  }}
                  className="text-sm"
                />
                <p className="text-xs flex items-center gap-1" style={{ color: "var(--color-text-muted)" }}>
                  <ImagePlus size={12} /> JPEG, PNG, WebP, GIF or AVIF.
                </p>
              </section>

              <section aria-labelledby="versions-heading" className="space-y-2">
                <h2 id="versions-heading" className="text-sm font-semibold">Versions</h2>
                {versions.length === 0 ? (
                  <p className="text-xs" style={{ color: "var(--color-text-muted)" }}>No versions yet.</p>
                ) : (
                  <ul className="text-sm space-y-1" aria-label="Versions">
                    {versions.map((v) => (
                      <li key={v.version_no}>
                        <Link href={`/admin/content/questions/${question_id}/versions/${v.version_no}`} className="underline-offset-2 hover:underline">
                          v{v.version_no}
                        </Link>
                        {" · "}{v.state.replace("_", " ")}
                      </li>
                    ))}
                  </ul>
                )}
              </section>
            </aside>
          </div>
        )}

        <ConfirmDialog
          isOpen={confirming === "publish"}
          onClose={() => setConfirming(null)}
          onConfirm={() => runAction("publish")}
          title="Publish this question?"
          message="Publishing makes this version live for exams. Published versions cannot be edited; changes need a new draft."
          confirmLabel="Publish"
          confirmVariant="primary"
          loading={busy}
        />
        <ConfirmDialog
          isOpen={confirming === "retire"}
          onClose={() => setConfirming(null)}
          onConfirm={() => runAction("retire")}
          title="Unpublish this question?"
          message="Unpublished questions stop being offered. They stay in exam history."
          confirmLabel="Unpublish"
          confirmVariant="warning"
          loading={busy}
        />
        <ConfirmDialog
          isOpen={confirming === "discard-draft"}
          onClose={() => setConfirming(null)}
          onConfirm={() => runAction("discard-draft")}
          title="Discard the draft?"
          message="Unpublished edits are removed and the question goes back to its last published version."
          confirmLabel="Discard draft"
          confirmVariant="danger"
          loading={busy}
        />
        <ConfirmDialog
          isOpen={confirming === "delete"}
          onClose={() => setConfirming(null)}
          onConfirm={deleteQuestion}
          title="Delete this question?"
          message="Questions used in an exam cannot be deleted; unpublish them instead. This cannot be undone."
          confirmLabel="Delete"
          confirmVariant="danger"
          loading={busy}
        />
      </PageWrapper>
    </AdminLayout>
  );
}

const CONFLICT_TEXT = "This question changed since you opened it. Reload to see the latest version before saving again.";
