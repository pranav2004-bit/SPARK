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
function OptionRow({ option, mcqType, onSaveText, onToggle, onDelete }: {
  option: AssessmentQuestionOption;
  mcqType: AssessmentMcqType;
  onSaveText: (id: string, text: string) => Promise<void>;
  onToggle: (id: string, current: boolean) => Promise<void>;
  onDelete: (id: string) => Promise<void>;
}) {
  const [text, setText] = useState(option.text);
  const [busy, setBusy] = useState(false);
  const isCorrect = !!option.is_correct;
  useEffect(() => { setText(option.text); }, [option.text]);

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
    if (!current) { toast.error("Save the question first, then add an image."); return; }
    if (!ALLOWED_IMAGE_TYPES.includes(file.type)) { toast.error(`Unsupported format. Allowed: ${ALLOWED_IMAGE_LABEL}`); return; }
    if (file.size > MAX_IMAGE_BYTES) { toast.error("Image exceeds 5 MB limit."); return; }
    setImgState("uploading");
    setPreviewUrl(URL.createObjectURL(file));
    try {
      const presignRes = await api.post(`/assessments/admin/questions/${current.id}/image-presign/`, {
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

  async function handleSave() {
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
        toast.success("Question created — now add answer options below.");
      } else {
        const res = await api.patch<ApiSuccess<AssessmentQuestion>>(`/assessments/admin/questions/${current.id}/`, payload);
        setCurrent(res.data.data);
        onUpdated(res.data.data);
        toast.success("Question saved.");
      }
    } catch (err) {
      toast.error(getErrorMessage(err));
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

  async function handleOptionSaveText(id: string, text: string) {
    if (!current) return;
    try {
      const res = await api.patch<ApiSuccess<AssessmentQuestionOption>>(`/assessments/admin/questions/${current.id}/options/${id}/`, { text });
      setOptions(prev => prev.map(o => o.id === id ? res.data.data : o));
    } catch (err) { toast.error(getErrorMessage(err)); }
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

  return (
    <Modal isOpen={isOpen} onClose={onClose} title={current ? `Question ${current.question_number}` : "New Question"} maxWidth="lg">
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
            {!current ? (
              <p className="text-xs italic" style={{ color: T.subtle }}>Save the question first to enable image upload.</p>
            ) : (
              <ImageUploadZone previewUrl={previewUrl} imageKey={imageKey} uploadState={imgState}
                fileInputRef={fileInputRef} onSelect={handleImageSelect} onRemove={handleImageRemove} />
            )}
          </div>
        )}

        {/* Answer type */}
        <div>
          <p className="text-xs font-semibold mb-2" style={{ color: T.muted }}>Answer Type</p>
          <div className="flex gap-2">
            {(["single", "multiple"] as AssessmentMcqType[]).map(t => (
              <button key={t} type="button" onClick={() => setMcqType(t)}
                className="flex-1 py-2 rounded-[var(--radius-md)] text-sm font-semibold border transition-all"
                style={mcqType === t
                  ? { background: "#EFF6FF", color: "#2563EB", borderColor: "#BFDBFE" }
                  : { background: T.surface, color: T.muted, borderColor: T.border }}>
                {t === "single" ? "Single Correct" : "Multiple Correct"}
              </button>
            ))}
          </div>
        </div>

        <div className="flex justify-end">
          <Button variant="primary" size="sm" onClick={handleSave} loading={saving}>
            {current ? "Save Question" : "Create Question"}
          </Button>
        </div>

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
                    onSaveText={handleOptionSaveText} onToggle={handleOptionToggle} onDelete={handleOptionDelete} />
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
