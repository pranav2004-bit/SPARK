"use client";

import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import {
  ListChecks, ChevronRight, Plus, Pencil, Trash2, Loader2, Check,
  Type, ImagePlus, LayoutTemplate, Upload, X, Image as ImageIcon,
} from "lucide-react";
import { AdminLayout } from "@/components/layout/AdminLayout";
import { PageWrapper } from "@/components/layout/PageWrapper";
import { PageHeader } from "@/components/layout/PageHeader";
import { Button } from "@/components/ui/Button";
import { Modal } from "@/components/ui/Modal";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import { EmptyState } from "@/components/ui/EmptyState";
import { ResourceItemCardSkeleton, Skeleton } from "@/components/ui/Skeleton";
import { useToast } from "@/components/ui/Toast";
import { ImageLoader } from "@/components/ui/ImageLoader";
import api, { getErrorMessage } from "@/lib/api";
import { putFileWithRetry } from "@/lib/uploadRetry";
import type {
  QuestionPaper, QuestionSet, AssessmentQuestion, AssessmentQuestionOption,
  AssessmentQuestionContentType, AssessmentMcqType, ApiSuccess,
} from "@/types";

// Mirrors services/assessment-service/core/upload_constraints.py
const ALLOWED_IMAGE_TYPES = ["image/jpeg", "image/png", "image/webp", "image/gif", "image/avif"];
const ALLOWED_IMAGE_LABEL = "JPEG, PNG, WebP, GIF, AVIF — max 5 MB";
const MAX_IMAGE_BYTES = 5 * 1024 * 1024;

const T = {
  text: "var(--color-text)", muted: "var(--color-text-muted)", subtle: "var(--color-text-subtle)",
  border: "var(--color-border)", surface: "var(--color-surface)", white: "var(--color-background)",
};

const CONTENT_TYPES: { value: AssessmentQuestionContentType; label: string; icon: React.ReactNode }[] = [
  { value: "text",  label: "Text",         icon: <Type size={13} /> },
  { value: "image", label: "Image",        icon: <ImagePlus size={13} /> },
  { value: "both",  label: "Text + Image", icon: <LayoutTemplate size={13} /> },
];

type UploadState = "idle" | "uploading" | "done" | "error";

interface SetDetail {
  set:       QuestionSet;
  paper:     QuestionPaper;
  questions: AssessmentQuestion[];
}

// ── Auto-growing textarea ─────────────────────────────────────────────────────
function AutoTextarea({ minRows = 3, style, onChange, ...props }: React.TextareaHTMLAttributes<HTMLTextAreaElement> & { minRows?: number }) {
  const ref = useRef<HTMLTextAreaElement>(null);
  const resize = useCallback(() => {
    const el = ref.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${el.scrollHeight}px`;
  }, []);
  useLayoutEffect(() => { resize(); }, [props.value, resize]);
  return (
    <textarea ref={ref} rows={minRows} {...props}
      style={{ ...style, resize: "none", overflow: "hidden" }}
      onChange={(e) => { resize(); onChange?.(e); }}
    />
  );
}

// ── Option row ────────────────────────────────────────────────────────────────
function OptionRow({ option, mcqType, onSaveText, onToggle, onDelete, onAddWithText }: {
  option: AssessmentQuestionOption;
  mcqType: AssessmentMcqType;
  onSaveText: (id: string, text: string) => Promise<void>;
  onToggle: (id: string, current: boolean) => Promise<void>;
  onDelete: (id: string) => Promise<void>;
  onAddWithText: (text: string) => Promise<void>;
}) {
  const [text, setText] = useState(option.text);
  const [busy, setBusy] = useState(false);
  const isCorrect = !!option.is_correct;
  useEffect(() => { setText(option.text); }, [option.text]);

  // Pasting multiple lines spills each line into a new option instead of
  // cramming them all into this one field — same pattern as practice-service's
  // question editor (practice/questions/[question_id]/page.tsx).
  const handlePaste = async (e: React.ClipboardEvent<HTMLTextAreaElement>) => {
    const pasted = e.clipboardData.getData("text");
    const lines = pasted.split(/\r?\n/).map(l => l.trim()).filter(l => l.length > 0);
    if (lines.length <= 1) return;
    e.preventDefault();
    setText(lines[0]);
    setBusy(true);
    try {
      await onSaveText(option.id, lines[0]);
      for (const line of lines.slice(1)) {
        await onAddWithText(line);
      }
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="flex items-start gap-3 p-3 rounded-[var(--radius-md)] transition-colors"
      style={{ background: isCorrect ? "#F0FDF4" : T.surface, border: `1.5px solid ${isCorrect ? "#BBF7D0" : T.border}` }}>
      <span className="shrink-0 w-7 h-7 rounded-full flex items-center justify-center text-xs font-bold mt-0.5"
        style={{ background: isCorrect ? "#16A34A" : T.border, color: isCorrect ? "#fff" : T.muted }}>
        {option.label}
      </span>
      <div className="flex-1 min-w-0">
        <AutoTextarea
          value={text} minRows={1} placeholder="Option text…"
          className="w-full text-sm rounded-[var(--radius-sm)] px-2 py-1 outline-none leading-relaxed"
          style={{ background: "transparent", border: "1px solid transparent", color: T.text }}
          onChange={e => setText(e.target.value)}
          onPaste={handlePaste}
          onBlur={async () => { if (text === option.text) return; setBusy(true); try { await onSaveText(option.id, text); } finally { setBusy(false); } }}
        />
      </div>
      <button type="button" disabled={busy}
        title={isCorrect ? "Mark as incorrect" : mcqType === "single" ? "Mark as correct (deselects others)" : "Mark as correct"}
        onClick={async () => { setBusy(true); try { await onToggle(option.id, isCorrect); } finally { setBusy(false); } }}
        className="shrink-0 w-7 h-7 rounded-full flex items-center justify-center transition-all mt-0.5 disabled:opacity-50"
        style={{ background: isCorrect ? "#16A34A" : T.surface, border: `1.5px solid ${isCorrect ? "#16A34A" : T.border}`, color: isCorrect ? "#fff" : T.subtle }}
      >
        {busy ? <Loader2 size={12} className="animate-spin" /> : <Check size={12} />}
      </button>
      <button type="button" disabled={busy} title="Delete option"
        onClick={async () => { setBusy(true); try { await onDelete(option.id); } finally { setBusy(false); } }}
        className="shrink-0 w-7 h-7 rounded-full flex items-center justify-center transition-colors mt-0.5 disabled:opacity-50"
        style={{ background: T.surface, border: `1.5px solid ${T.border}`, color: T.subtle }}
      >
        <Trash2 size={12} />
      </button>
    </div>
  );
}

// ── Image upload zone ─────────────────────────────────────────────────────────
function ImageUploadZone({ previewUrl, imageKey, uploadState, fileInputRef, onSelect, onRemove }: {
  previewUrl: string | null; imageKey: string; uploadState: UploadState;
  fileInputRef: React.RefObject<HTMLInputElement | null>;
  onSelect: (file: File) => void; onRemove: () => void;
}) {
  if (previewUrl && imageKey) {
    return (
      <div className="relative rounded-[var(--radius-md)] overflow-hidden" style={{ border: `1px solid ${T.border}` }}>
        <ImageLoader src={previewUrl} alt="Question image" maxHeight={300} background="#f8f9fa" skeletonHeight={160} />
        <button onClick={onRemove} type="button"
          className="absolute top-2 right-2 w-7 h-7 rounded-full flex items-center justify-center shadow-md transition-opacity hover:opacity-80"
          style={{ background: "rgba(0,0,0,0.6)", color: "#fff" }} aria-label="Remove image">
          <X size={13} />
        </button>
      </div>
    );
  }
  return (
    <>
      <div
        className="flex flex-col items-center justify-center gap-3 py-8 rounded-[var(--radius-md)] transition-colors"
        style={{ background: T.surface, border: `2px dashed ${T.border}`, cursor: uploadState === "uploading" ? "wait" : "pointer" }}
        onClick={() => uploadState !== "uploading" && fileInputRef.current?.click()}
        onDragOver={e => e.preventDefault()}
        onDrop={e => { e.preventDefault(); const f = e.dataTransfer.files[0]; if (f) onSelect(f); }}
        role="button" tabIndex={0}
      >
        {uploadState === "uploading" ? <Loader2 size={24} className="animate-spin" style={{ color: T.muted }} /> : <ImageIcon size={24} style={{ color: T.subtle }} />}
        <div className="text-center px-4">
          <p className="text-xs font-semibold" style={{ color: T.muted }}>
            {uploadState === "uploading" ? "Uploading…" : "Click or drag & drop an image"}
          </p>
          {uploadState !== "uploading" && <p className="text-[11px] mt-0.5" style={{ color: T.subtle }}>{ALLOWED_IMAGE_LABEL}</p>}
          {uploadState === "error" && <p className="text-[11px] mt-1 font-semibold" style={{ color: "var(--color-danger)" }}>Upload failed — try again</p>}
        </div>
        {uploadState !== "uploading" && (
          <button type="button" className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-[var(--radius-md)] text-xs font-semibold border transition-colors"
            style={{ background: T.white, color: T.muted, borderColor: T.border }}
            onClick={e => { e.stopPropagation(); fileInputRef.current?.click(); }}>
            <Upload size={11} /> Browse
          </button>
        )}
      </div>
      <input ref={fileInputRef} type="file" accept={ALLOWED_IMAGE_TYPES.join(",")} className="hidden"
        onChange={e => { const f = e.target.files?.[0]; if (f) onSelect(f); e.target.value = ""; }} />
    </>
  );
}

// ── Question editor modal ─────────────────────────────────────────────────────
function QuestionEditorModal({ isOpen, onClose, question, setId, onCreated, onUpdated }: {
  isOpen: boolean; onClose: () => void;
  question: AssessmentQuestion | null; // null = creating new
  setId: string;
  onCreated: (q: AssessmentQuestion) => void;
  onUpdated: (q: AssessmentQuestion) => void;
}) {
  const toast = useToast();
  const [current, setCurrent] = useState<AssessmentQuestion | null>(question);
  const [contentType, setContentType] = useState<AssessmentQuestionContentType>("text");
  const [text, setText] = useState("");
  const [imageKey, setImageKey] = useState("");
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [mcqType, setMcqType] = useState<AssessmentMcqType>("single");
  const [marks, setMarks] = useState(1);
  const [imgState, setImgState] = useState<UploadState>("idle");
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [saving, setSaving] = useState(false);
  const [options, setOptions] = useState<AssessmentQuestionOption[]>([]);
  const [addingOpt, setAddingOpt] = useState(false);
  // Shown only while creating a brand-new question (current === null) —
  // lets the admin type option text (and mark one correct) right in the
  // same form instead of a separate "Add Option" click immediately after
  // creating. A list, not a single field, so pasting multiple lines can
  // spill into multiple pending options (see handlePendingOptionPaste)
  // the same way OptionRow already does for an already-created question's
  // options — before this, Option A was a single field with no paste
  // handler at all, so a multi-line paste just landed as one giant option
  // instead of splitting. Always has >= 1 row; "Create Question" is gated
  // on at least one having text AND one marked correct (see
  // canCreateQuestion below) — a question with zero options or no correct
  // answer isn't assignable-ready anyway (get_assignment_readiness_blockers
  // would reject it later), so this just surfaces that requirement at
  // creation time instead of after.
  const [pendingOptions, setPendingOptions] = useState<{ text: string; correct: boolean }[]>([
    { text: "", correct: false },
  ]);
  const [showExitConfirm, setShowExitConfirm] = useState(false);

  useEffect(() => {
    if (!isOpen) return;
    setCurrent(question);
    setContentType(question?.question_content_type ?? "text");
    setText(question?.question_text ?? "");
    setImageKey(question?.question_image_key ?? "");
    setPreviewUrl(question?.question_image_url ?? null);
    setMcqType(question?.mcq_type ?? "single");
    setMarks(question?.marks ?? 1);
    setImgState("idle");
    setPendingOptions([{ text: "", correct: false }]);
    setShowExitConfirm(false);
    if (question) {
      api.get<ApiSuccess<{ question: AssessmentQuestion; options: AssessmentQuestionOption[] }>>(
        `/assessments/admin/questions/${question.id}/`
      ).then(res => setOptions(res.data.data.options)).catch(() => toast.error("Failed to load options."));
    } else {
      setOptions([]);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isOpen, question]);

  async function handleImageSelect(file: File) {
    if (!ALLOWED_IMAGE_TYPES.includes(file.type)) { toast.error(`Unsupported format. Allowed: ${ALLOWED_IMAGE_LABEL}`); return; }
    if (file.size > MAX_IMAGE_BYTES) { toast.error("Image exceeds 5 MB limit."); return; }
    setImgState("uploading");
    setPreviewUrl(URL.createObjectURL(file));
    try {
      // Before the question exists yet, presign against the set instead —
      // lets content_type='image'/'both' attach an image on the question's
      // very first save, instead of requiring a save-then-upload-then-save
      // round trip (previously the only way, and outright impossible for
      // 'both': it can't save without an image already present).
      const presignUrl = current
        ? `/assessments/admin/questions/${current.id}/image-presign/`
        : `/assessments/admin/sets/${setId}/image-presign/`;
      const presignRes = await api.post(presignUrl, {
        filename: file.name, content_type: file.type,
      });
      const { upload_url, file_key, cdn_url } = presignRes.data.data;
      await putFileWithRetry(upload_url, file, () => {});
      setImageKey(file_key);
      setPreviewUrl(cdn_url);
      setImgState("done");
      toast.success("Image uploaded.");
    } catch {
      setImgState("error");
      setPreviewUrl(current?.question_image_url ?? null);
      toast.error("Image upload failed. Please try again.");
    }
  }

  function handleImageRemove() {
    setImageKey(""); setPreviewUrl(null); setImgState("idle");
  }

  // ── Pending options (pre-creation) ────────────────────────────────────────
  function setPendingOptionText(index: number, value: string) {
    setPendingOptions(prev => prev.map((o, i) => i === index ? { ...o, text: value } : o));
  }

  // Mirrors handleOptionToggle's single-correct exclusivity (below, for an
  // already-created question) — without this, "Single Correct" mode let
  // every pending row stay checked since each toggle only touched its own
  // row, with nothing deselecting the others.
  function togglePendingOptionCorrect(index: number) {
    setPendingOptions(prev => {
      const turningOn = !prev[index].correct;
      return prev.map((o, i) => {
        if (i === index) return { ...o, correct: turningOn };
        if (mcqType === "single" && turningOn) return { ...o, correct: false };
        return o;
      });
    });
  }

  function removePendingOption(index: number) {
    setPendingOptions(prev => prev.length <= 1 ? prev : prev.filter((_, i) => i !== index));
  }

  // Same behavior as OptionRow's onPaste (below, for an already-created
  // question) — pasting multiple lines spills each extra line into a new
  // pending row instead of cramming them all into one option's text.
  // Before this existed, the pre-creation "Option A" field had no paste
  // handler at all, so a multi-line paste just landed as one giant option.
  function handlePendingOptionPaste(index: number, e: React.ClipboardEvent<HTMLTextAreaElement>) {
    const pasted = e.clipboardData.getData("text");
    const lines = pasted.split(/\r?\n/).map(l => l.trim()).filter(l => l.length > 0);
    if (lines.length <= 1) return;
    e.preventDefault();
    setPendingOptions(prev => {
      const next = [...prev];
      next[index] = { ...next[index], text: lines[0] };
      next.splice(index + 1, 0, ...lines.slice(1).map(text => ({ text, correct: false })));
      return next;
    });
  }

  async function handleSave(): Promise<boolean> {
    setSaving(true);
    try {
      const payload = {
        question_content_type: contentType,
        question_text: text,
        question_image_key: imageKey,
        mcq_type: mcqType,
        marks,
      };
      if (!current) {
        const res = await api.post<ApiSuccess<AssessmentQuestion>>(`/assessments/admin/sets/${setId}/questions/`, payload);
        setCurrent(res.data.data);
        onCreated(res.data.data);

        // Every non-blank pending option (Option A, plus any extra rows a
        // multi-line paste spilled into) is created right alongside the
        // question, in order — sequential (not Promise.all) so the
        // backend's auto-label-by-count logic assigns A, B, C… correctly
        // instead of a race where every request sees the same pre-insert
        // count. A failure partway through doesn't roll back the question
        // or the options already created — those are real and kept —
        // it's reported separately rather than folded into the outer catch.
        const toCreate = pendingOptions.filter(o => o.text.trim());
        if (toCreate.length) {
          const created: AssessmentQuestionOption[] = [];
          try {
            for (const opt of toCreate) {
              const optRes = await api.post<ApiSuccess<AssessmentQuestionOption>>(
                `/assessments/admin/questions/${res.data.data.id}/options/`,
                { text: opt.text.trim(), is_correct: opt.correct }
              );
              created.push(optRes.data.data);
            }
          } catch (optErr) {
            toast.error(getErrorMessage(optErr));
          } finally {
            setOptions(created);
          }
        }

        toast.success("Question created.");
      } else {
        const res = await api.patch<ApiSuccess<AssessmentQuestion>>(`/assessments/admin/questions/${current.id}/`, payload);
        setCurrent(res.data.data);
        onUpdated(res.data.data);
        toast.success("Question saved.");
      }
      return true;
    } catch (err) {
      toast.error(getErrorMessage(err));
      return false;
    } finally {
      setSaving(false);
    }
  }

  async function handleAddOption() {
    if (!current) return;
    setAddingOpt(true);
    try {
      const res = await api.post<ApiSuccess<AssessmentQuestionOption>>(`/assessments/admin/questions/${current.id}/options/`, {
        text: "", is_correct: false,
      });
      setOptions(prev => [...prev, res.data.data]);
    } catch (err) { toast.error(getErrorMessage(err)); }
    finally { setAddingOpt(false); }
  }

  // Used by OptionRow's paste handler — creates a new option pre-filled with text.
  async function handleAddOptionWithText(text: string) {
    if (!current) return;
    try {
      const res = await api.post<ApiSuccess<AssessmentQuestionOption>>(`/assessments/admin/questions/${current.id}/options/`, {
        text, is_correct: false,
      });
      setOptions(prev => [...prev, res.data.data]);
    } catch (err) { toast.error(getErrorMessage(err)); }
  }

  async function handleOptionSaveText(id: string, text: string) {
    if (!current) return;
    try {
      const res = await api.patch<ApiSuccess<AssessmentQuestionOption>>(`/assessments/admin/questions/${current.id}/options/${id}/`, { text });
      setOptions(prev => prev.map(o => o.id === id ? res.data.data : o));
    } catch (err) { toast.error(getErrorMessage(err)); }
  }

  // Real bug fixed here (live report, 2026-08-14): the "Answer Type" toggle
  // used to only call setMcqType(t) — pure local state, never persisted
  // until "Save Question" was clicked. But marking an option correct
  // (handleOptionToggle below) PATCHes immediately and is validated
  // server-side against the question's *saved* mcq_type — so clicking
  // "Multiple Correct" then immediately checking a 2nd option failed with
  // a confusing "single-choice" error, because the backend still thought
  // it was single-choice. Persisting the mcq_type change immediately (for
  // an already-created question) closes that gap instead of relying on
  // the admin knowing to click Save Question first.
  async function handleMcqTypeChange(t: AssessmentMcqType) {
    const previous = mcqType;
    setMcqType(t);
    if (!current) {
      // Switching a not-yet-created question to Single Correct: collapse
      // any pending rows checked while it was Multiple Correct down to
      // just the first one, so the same exclusivity holds no matter which
      // order the admin set answer type vs. correctness in.
      if (t === "single") {
        setPendingOptions(prev => {
          const firstCorrect = prev.findIndex(o => o.correct);
          if (firstCorrect === -1) return prev;
          return prev.map((o, i) => ({ ...o, correct: i === firstCorrect }));
        });
      }
      return;
    }
    if (current.mcq_type === t) return;
    try {
      const res = await api.patch<ApiSuccess<AssessmentQuestion>>(`/assessments/admin/questions/${current.id}/`, { mcq_type: t });
      setCurrent(res.data.data);
      onUpdated(res.data.data);
    } catch (err) {
      setMcqType(previous);
      toast.error(getErrorMessage(err));
    }
  }

  async function handleOptionToggle(id: string, currentlyCorrect: boolean) {
    if (!current) return;
    try {
      const res = await api.patch<ApiSuccess<AssessmentQuestionOption>>(`/assessments/admin/questions/${current.id}/options/${id}/`, { is_correct: !currentlyCorrect });
      if (mcqType === "single" && !currentlyCorrect) {
        const listRes = await api.get<ApiSuccess<AssessmentQuestionOption[]>>(`/assessments/admin/questions/${current.id}/options/`);
        setOptions(listRes.data.data);
      } else {
        setOptions(prev => prev.map(o => o.id === id ? res.data.data : o));
      }
    } catch (err) { toast.error(getErrorMessage(err)); }
  }

  async function handleOptionDelete(id: string) {
    if (!current) return;
    try {
      await api.delete(`/assessments/admin/questions/${current.id}/options/${id}/`);
      setOptions(prev => prev.filter(o => o.id !== id));
    } catch (err) { toast.error(getErrorMessage(err)); }
  }

  const showText  = contentType === "text"  || contentType === "both";
  const showImage = contentType === "image" || contentType === "both";
  const correctCount = options.filter(o => o.is_correct).length;

  const filledPendingOptions = pendingOptions.filter(o => o.text.trim());

  // Gates "Create Question" — question content, marks, an option, and that
  // option marked correct. Mirrors what get_assignment_readiness_blockers
  // would reject later anyway (content completeness, correct-answer
  // count) — this just surfaces it at creation time instead of after.
  const hasRequiredContent = (!showText || text.trim().length > 0) && (!showImage || !!imageKey);
  const canCreateQuestion =
    !current && hasRequiredContent && marks >= 1
    && filledPendingOptions.length > 0 && filledPendingOptions.some(o => o.correct);

  // True only while creating a brand-new question with something typed
  // that hasn't been saved yet — an already-created question (current set)
  // has nothing to lose by closing, since it's already persisted.
  const hasUnsavedNewQuestion = !current && (text.trim().length > 0 || !!imageKey || filledPendingOptions.length > 0);

  // For an already-created question, mcq_type and every option's text/
  // correctness already auto-save on change (handleMcqTypeChange,
  // handleOptionToggle, handleOptionSaveText all PATCH immediately) — only
  // these four fields sit in local state until "Save Question" is clicked,
  // so they're the only ones that make the question "dirty".
  const isEditDirty = !!current && (
    text !== (current.question_text ?? "") ||
    contentType !== current.question_content_type ||
    marks !== current.marks ||
    imageKey !== (current.question_image_key ?? "")
  );

  const canSaveExisting = !!current && hasRequiredContent && marks >= 1 && isEditDirty;
  const canSubmitQuestion = current ? canSaveExisting : canCreateQuestion;
  const hasUnsavedChanges = current ? isEditDirty : hasUnsavedNewQuestion;

  function handleAttemptClose() {
    if (hasUnsavedChanges) setShowExitConfirm(true);
    else onClose();
  }

  async function handleSaveFromExitConfirm() {
    const ok = await handleSave();
    setShowExitConfirm(false);
    if (ok) onClose();
  }

  // Actually throws away the unsaved edits — "Cancel" on this dialog only
  // dismisses it and returns to the still-open, still-unsaved form, which
  // isn't a way out for an admin who decided not to save.
  function handleDiscardQuestion() {
    setShowExitConfirm(false);
    onClose();
  }

  // Closes on a successful save either way — matches the Set-label modal's
  // header Save button, which always closes once the save lands. "Save
  // Question" now only lights up once something's actually changed
  // (canSubmitQuestion / isEditDirty), so a click always means a real,
  // intentional save, not a leftover click with nothing to persist.
  async function handleSaveClick() {
    const ok = await handleSave();
    if (ok) onClose();
  }

  return (
    <>
    <Modal
      isOpen={isOpen} onClose={handleAttemptClose}
      title={current ? `Question ${current.question_number}` : "New Question"}
      maxWidth="lg" disableBackdropClose
      headerAction={
        <Button
          variant="primary" size="sm" onClick={handleSaveClick} loading={saving}
          disabled={!canSubmitQuestion}
          title={!canSubmitQuestion
            ? (current ? "Change something to enable saving." : "Add the question content, marks, an option, and mark it correct first.")
            : undefined}
        >
          {current ? "Save Question" : "Create Question"}
        </Button>
      }
    >
      <div className="space-y-5">

        {/* Content type + marks */}
        <div className="flex items-center justify-between gap-3 flex-wrap">
          <div className="flex items-center gap-1">
            {CONTENT_TYPES.map(({ value, label, icon }) => (
              <button key={value} type="button" onClick={() => setContentType(value)}
                className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold border transition-all"
                style={contentType === value
                  ? { background: "var(--color-text)", color: "#fff", borderColor: "transparent" }
                  : { background: T.surface, color: T.subtle, borderColor: T.border }}>
                {icon}<span className="hidden sm:inline">{label}</span>
              </button>
            ))}
          </div>
          <div className="flex items-center gap-2">
            <label className="text-xs font-semibold" style={{ color: T.muted }}>Marks</label>
            <input type="number" min={1} value={marks} onChange={e => setMarks(Math.max(1, Number(e.target.value)))}
              className="w-16 text-sm rounded-[var(--radius-md)] px-2 py-1 outline-none"
              style={{ background: T.surface, border: `1px solid ${T.border}`, color: T.text }} />
          </div>
        </div>

        {showText && (
          <div>
            <label className="block text-xs font-semibold mb-1.5" style={{ color: T.muted }}>Question Text</label>
            <AutoTextarea value={text} onChange={e => setText(e.target.value)} placeholder="Enter the question…" minRows={3}
              className="w-full text-sm rounded-[var(--radius-md)] px-3.5 py-2.5 outline-none leading-relaxed"
              style={{ background: T.surface, border: `1px solid ${T.border}`, color: T.text }} />
          </div>
        )}

        {showImage && (
          <div>
            <label className="block text-xs font-semibold mb-1.5" style={{ color: T.muted }}>Question Image</label>
            <ImageUploadZone previewUrl={previewUrl} imageKey={imageKey} uploadState={imgState}
              fileInputRef={fileInputRef} onSelect={handleImageSelect} onRemove={handleImageRemove} />
          </div>
        )}

        {/* Answer type */}
        <div>
          <p className="text-xs font-semibold mb-2" style={{ color: T.muted }}>Answer Type</p>
          <div className="flex gap-2">
            {(["single", "multiple"] as AssessmentMcqType[]).map(t => (
              <button key={t} type="button" onClick={() => handleMcqTypeChange(t)}
                className="flex-1 py-2 rounded-[var(--radius-md)] text-sm font-semibold border transition-all"
                style={mcqType === t
                  ? { background: "#EFF6FF", color: "#2563EB", borderColor: "#BFDBFE" }
                  : { background: T.surface, color: T.muted, borderColor: T.border }}>
                {t === "single" ? "Single Correct" : "Multiple Correct"}
              </button>
            ))}
          </div>
        </div>

        {/* Pending options — only before the question exists. Once created,
            this is replaced by the full Answer Options editor below (which
            already includes everything entered here), so it's never shown
            alongside it. At least one row required, and at least one must
            be marked correct, to enable Create Question below — every
            question needs at least one right answer. Pasting multiple
            lines into any row's text splits into more rows (same behavior
            as OptionRow, below, for an already-created question). */}
        {!current && (
          <div>
            <label className="block text-xs font-semibold mb-1.5" style={{ color: T.muted }}>
              Answer Options <span className="font-normal" style={{ color: T.subtle }}>(required — mark at least one correct with the check button; add more after creating)</span>
            </label>
            <div className="space-y-2">
              {pendingOptions.map((opt, i) => (
                <div key={i} className="flex items-start gap-3 p-3 rounded-[var(--radius-md)]"
                  style={{ background: opt.correct ? "#F0FDF4" : T.surface, border: `1.5px solid ${opt.correct ? "#BBF7D0" : T.border}` }}>
                  <span className="shrink-0 w-7 h-7 rounded-full flex items-center justify-center text-xs font-bold mt-0.5"
                    style={{ background: opt.correct ? "#16A34A" : T.border, color: opt.correct ? "#fff" : T.muted }}>
                    {String.fromCharCode(65 + i)}
                  </span>
                  <div className="flex-1 min-w-0">
                    <AutoTextarea
                      value={opt.text} minRows={1} placeholder="Option text…"
                      className="w-full text-sm rounded-[var(--radius-sm)] px-2.5 py-1.5 outline-none leading-relaxed focus:ring-1"
                      style={{ background: T.white, border: `1px solid ${T.border}`, color: T.text }}
                      onChange={e => setPendingOptionText(i, e.target.value)}
                      onPaste={e => handlePendingOptionPaste(i, e)}
                    />
                  </div>
                  <button type="button"
                    title={opt.correct ? "Mark as incorrect" : "Mark as correct"}
                    onClick={() => togglePendingOptionCorrect(i)}
                    className="shrink-0 w-7 h-7 rounded-full flex items-center justify-center transition-all mt-0.5"
                    style={{ background: opt.correct ? "#16A34A" : T.surface, border: `1.5px solid ${opt.correct ? "#16A34A" : T.border}`, color: opt.correct ? "#fff" : T.subtle }}
                  >
                    <Check size={12} />
                  </button>
                  {pendingOptions.length > 1 && (
                    <button type="button" title="Remove option"
                      onClick={() => removePendingOption(i)}
                      className="shrink-0 w-7 h-7 rounded-full flex items-center justify-center transition-colors mt-0.5"
                      style={{ background: T.surface, border: `1.5px solid ${T.border}`, color: T.subtle }}
                    >
                      <Trash2 size={12} />
                    </button>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Options editor — only once the question exists */}
        {current && (
          <div className="pt-4" style={{ borderTop: `1px solid ${T.border}` }}>
            <div className="flex items-center justify-between gap-2 mb-3">
              <p className="text-sm font-semibold" style={{ color: T.text }}>Answer Options</p>
              <button type="button" onClick={handleAddOption} disabled={addingOpt || options.length >= 26}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-[var(--radius-md)] text-xs font-semibold border transition-colors disabled:opacity-50"
                style={{ background: T.surface, color: T.muted, borderColor: T.border }}>
                {addingOpt ? <Loader2 size={12} className="animate-spin" /> : <Plus size={12} />} Add Option
              </button>
            </div>
            {options.length === 0 ? (
              <div className="flex flex-col items-center justify-center py-6 rounded-[var(--radius-md)]"
                style={{ background: T.surface, border: `1px dashed ${T.border}` }}>
                <p className="text-xs font-semibold" style={{ color: T.muted }}>No options yet</p>
              </div>
            ) : (
              <div className="space-y-2">
                {options.map(opt => (
                  <OptionRow key={opt.id} option={opt} mcqType={mcqType}
                    onSaveText={handleOptionSaveText} onToggle={handleOptionToggle} onDelete={handleOptionDelete}
                    onAddWithText={handleAddOptionWithText} />
                ))}
              </div>
            )}
            {options.length > 0 && (
              <p className="text-[11px] mt-2" style={{ color: T.subtle }}>
                {correctCount === 0 ? "⚠ No correct option marked yet." : `${correctCount} correct option${correctCount > 1 ? "s" : ""} marked.`}
              </p>
            )}
          </div>
        )}
      </div>
    </Modal>

    {/* Closing (X / Escape) with unsaved details — for a new question, that's
        anything typed but not yet created; for an already-created one, any
        local edit that hasn't been through "Save Question" (mcq_type and
        option changes auto-save, so they don't count — see isEditDirty).
        Offers finishing it right now instead of silently discarding it. The
        confirm button is disabled under the same rule as the header button;
        if that's not met yet, "Keep Editing" or "Discard" are the only ways
        forward. */}
    <ConfirmDialog
      isOpen={showExitConfirm}
      onClose={() => setShowExitConfirm(false)}
      onConfirm={handleSaveFromExitConfirm}
      title="Unsaved changes"
      message={
        current
          ? (canSaveExisting
              ? "You've made changes to this question but haven't saved them yet. Leaving now will discard those changes."
              : "You've made changes to this question but haven't saved them yet. Leaving now will discard those changes. Finish the required fields (content, marks) to save instead of losing them.")
          : (canCreateQuestion
              ? "You've entered details for a new question but haven't created it yet. Leaving now will discard everything you've typed."
              : "You've entered details for a new question but haven't created it yet. Leaving now will discard everything you've typed. Finish the required fields (content, marks, one option marked correct) to create it instead of losing it.")
      }
      confirmLabel={current ? "Save Question" : "Create Question"}
      confirmVariant="primary"
      confirmDisabled={!canSubmitQuestion}
      loading={saving}
      secondaryActionLabel="Discard"
      onSecondaryAction={handleDiscardQuestion}
    />
    </>
  );
}

// ── Main page ─────────────────────────────────────────────────────────────────
export default function AdminAssessmentSetPage() {
  const { paper_id, set_id } = useParams<{ paper_id: string; set_id: string }>();
  const router = useRouter();
  const toast  = useToast();

  const [detail,  setDetail]  = useState<SetDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [editorQuestion, setEditorQuestion] = useState<AssessmentQuestion | null | "new">(null);
  const [deleteTarget, setDeleteTarget] = useState<{ id: string; label: string } | null>(null);
  const [deleting, setDeleting] = useState(false);

  const load = () => {
    api.get<ApiSuccess<SetDetail>>(`/assessments/admin/sets/${set_id}/`)
      .then(res => setDetail(res.data.data))
      .catch(err => { toast.error(getErrorMessage(err)); router.push(`/admin/assessments/papers/${paper_id}`); })
      .finally(() => setLoading(false));
  };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(load, [set_id]);

  function handleCreated(q: AssessmentQuestion) {
    setDetail(prev => prev ? { ...prev, questions: [...prev.questions, q] } : prev);
  }
  function handleUpdated(q: AssessmentQuestion) {
    setDetail(prev => prev ? { ...prev, questions: prev.questions.map(x => x.id === q.id ? q : x) } : prev);
  }
  async function handleDelete() {
    if (!deleteTarget) return;
    setDeleting(true);
    try {
      await api.delete(`/assessments/admin/questions/${deleteTarget.id}/`);
      setDetail(prev => prev ? { ...prev, questions: prev.questions.filter(q => q.id !== deleteTarget.id) } : prev);
      setDeleteTarget(null);
      toast.success("Question deleted.");
    } catch (err) { toast.error(getErrorMessage(err)); }
    finally { setDeleting(false); }
  }

  const set = detail?.set;
  const isEmpty = !loading && (detail?.questions.length ?? 0) === 0;

  return (
    <AdminLayout>
      <PageWrapper className="max-w-4xl">

        <PageHeader
          title={set?.label ?? ""}
          titleSkeleton={loading ? <Skeleton className="h-8 w-40" /> : undefined}
          subtitle={detail ? `${detail.paper.title} — ${detail.questions.length} question${detail.questions.length === 1 ? "" : "s"}` : undefined}
          backHref={`/admin/assessments/papers/${paper_id}`}
          breadcrumb={
            <span className="flex items-center gap-1.5">
              <span className="cursor-pointer hover:underline" onClick={() => router.push("/admin/assessments/papers")}>Assessments</span>
              <ChevronRight size={12} />
              <span className="cursor-pointer hover:underline" onClick={() => router.push(`/admin/assessments/papers/${paper_id}`)}>
                {detail?.paper.title ?? "..."}
              </span>
            </span>
          }
          rightSlot={
            <Button variant="primary" onClick={() => setEditorQuestion("new")}>+ Add Question</Button>
          }
        />

        {loading ? (
          <div className="space-y-3">
            {[1, 2, 3].map(i => <ResourceItemCardSkeleton key={i} />)}
          </div>
        ) : isEmpty ? (
          <EmptyState icon={ListChecks} title="No questions yet" subtitle="Add a question to start building this set." />
        ) : (
          <div className="space-y-3">
            {detail!.questions.map(q => (
              <div key={q.id}
                className="flex items-start justify-between gap-3 p-4 rounded-[var(--radius-lg)] cursor-pointer transition-shadow hover:shadow-[var(--shadow-sm)]"
                style={{ background: "var(--color-surface)", border: "1px solid var(--color-border)" }}
                onClick={() => setEditorQuestion(q)}
              >
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2 mb-1">
                    <span className="text-xs font-bold px-2 py-0.5 rounded-full" style={{ background: "#EFF6FF", color: "#2563EB" }}>
                      Q{q.question_number}
                    </span>
                    <span className="text-[11px] font-medium" style={{ color: T.subtle }}>
                      {q.mcq_type === "single" ? "Single correct" : "Multiple correct"} · {q.marks} mark{q.marks === 1 ? "" : "s"}
                    </span>
                  </div>
                  <p className="text-sm truncate" style={{ color: T.text }}>
                    {q.question_text || <span className="italic" style={{ color: T.subtle }}>Image-only question</span>}
                  </p>
                </div>
                <div className="flex items-center gap-1 shrink-0">
                  <button onClick={e => { e.stopPropagation(); setEditorQuestion(q); }}
                    className="w-8 h-8 rounded-[var(--radius-md)] flex items-center justify-center transition-colors"
                    style={{ color: T.subtle }} aria-label="Edit">
                    <Pencil size={14} />
                  </button>
                  <button onClick={e => { e.stopPropagation(); setDeleteTarget({ id: q.id, label: `Q${q.question_number}` }); }}
                    className="w-8 h-8 rounded-[var(--radius-md)] flex items-center justify-center transition-colors"
                    style={{ color: T.subtle }} aria-label="Delete">
                    <Trash2 size={14} />
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}

      </PageWrapper>

      <QuestionEditorModal
        isOpen={editorQuestion !== null}
        onClose={() => setEditorQuestion(null)}
        question={editorQuestion === "new" ? null : editorQuestion}
        setId={set_id}
        onCreated={handleCreated}
        onUpdated={handleUpdated}
      />

      <ConfirmDialog
        isOpen={!!deleteTarget}
        onClose={() => setDeleteTarget(null)}
        onConfirm={handleDelete}
        title="Delete question?"
        message={`"${deleteTarget?.label}" and its options will be permanently removed. This cannot be undone.`}
        confirmLabel="Delete"
        confirmVariant="danger"
        loading={deleting}
      />
    </AdminLayout>
  );
}
