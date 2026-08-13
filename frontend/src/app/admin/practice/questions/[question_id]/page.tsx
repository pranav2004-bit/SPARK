"use client";

import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import {
  ListChecks, AlignLeft, ChevronRight, ArrowLeft,
  Save, Upload, X, Image as ImageIcon, Loader2, Eye, EyeOff,
  Type, ImagePlus, LayoutTemplate, Plus, Trash2, Check,
} from "lucide-react";
import { AdminLayout } from "@/components/layout/AdminLayout";
import { PageWrapper } from "@/components/layout/PageWrapper";
import { Button } from "@/components/ui/Button";
import { Modal } from "@/components/ui/Modal";
import { useToast } from "@/components/ui/Toast";
import { ImageLoader } from "@/components/ui/ImageLoader";
import api, { getErrorMessage } from "@/lib/api";
import { putFileWithRetry } from "@/lib/uploadRetry";
import type {
  PracticeQuestion, PracticeSection, PracticeModule,
  PracticeQuestionOption, ExplanationType, QuestionContentType, McqType,
} from "@/types";

// ── Design tokens ─────────────────────────────────────────────────────────────
const T = {
  text:    "var(--color-text)",
  muted:   "var(--color-text-muted)",
  subtle:  "var(--color-text-subtle)",
  border:  "var(--color-border)",
  surface: "var(--color-surface)",
  white:   "var(--color-background)",
  accent:  "var(--color-accent)",
};

// ── Allowed image MIME types ───────────────────────────────────────────────────
// Mirrors services/practice-service/core/upload_constraints.py — keep both
// in sync. .svg is deliberately excluded: it can carry inline
// <script>/event-handler payloads, making it a stored-XSS vector.
const ALLOWED_IMAGE_TYPES = [
  "image/jpeg", "image/png", "image/webp",
  "image/gif", "image/avif",
];
const ALLOWED_IMAGE_LABEL = "JPEG, PNG, WebP, GIF, AVIF — max 5 MB";
const MAX_IMAGE_BYTES      = 5 * 1024 * 1024;

// ── Types ─────────────────────────────────────────────────────────────────────
interface QuestionDetail {
  question: PracticeQuestion;
  section:  PracticeSection;
  module:   PracticeModule | null;
  options:  PracticeQuestionOption[];
}

interface QuestionForm {
  question_content_type:  QuestionContentType;
  question_text:          string;
  question_image_key:     string;
  question_image_url:     string | null;
  fib_answer:             string;
  mcq_type:               McqType;
  explanation_type:       ExplanationType;
  explanation_text:       string;
  explanation_image_key:  string;
  explanation_image_url:  string | null;
  is_published:           boolean;
}

type UploadState = "idle" | "uploading" | "done" | "error";

// ── Helpers ───────────────────────────────────────────────────────────────────
function formFromQuestion(q: PracticeQuestion): QuestionForm {
  return {
    question_content_type:  q.question_content_type,
    question_text:          q.question_text,
    question_image_key:     q.question_image_key,
    question_image_url:     q.question_image_url,
    fib_answer:             q.fib_answer,
    mcq_type:               q.mcq_type ?? "single",
    explanation_type:       q.explanation_type,
    explanation_text:       q.explanation_text,
    explanation_image_key:  q.explanation_image_key,
    explanation_image_url:  q.explanation_image_url,
    is_published:           q.is_published,
  };
}

function isDirty(a: QuestionForm, b: QuestionForm): boolean {
  return (
    a.question_content_type  !== b.question_content_type  ||
    a.question_text          !== b.question_text          ||
    a.question_image_key     !== b.question_image_key     ||
    a.fib_answer             !== b.fib_answer             ||
    a.mcq_type               !== b.mcq_type               ||
    a.explanation_type       !== b.explanation_type       ||
    a.explanation_text       !== b.explanation_text       ||
    a.explanation_image_key  !== b.explanation_image_key  ||
    a.is_published           !== b.is_published
  );
}

// ── Content-type selector pills ───────────────────────────────────────────────
const CONTENT_TYPES: { value: QuestionContentType; label: string; icon: React.ReactNode }[] = [
  { value: "text",  label: "Text",         icon: <Type size={13} /> },
  { value: "image", label: "Image",        icon: <ImagePlus size={13} /> },
  { value: "both",  label: "Text + Image", icon: <LayoutTemplate size={13} /> },
];

// ── Explanation type pills ────────────────────────────────────────────────────
const EXP_TYPES: { value: ExplanationType; label: string }[] = [
  { value: "none",  label: "None"  },
  { value: "text",  label: "Text"  },
  { value: "image", label: "Image" },
  { value: "both",  label: "Both"  },
];

// ── Auto-growing textarea ─────────────────────────────────────────────────────
interface AutoTextareaProps extends React.TextareaHTMLAttributes<HTMLTextAreaElement> {
  minRows?: number;
}
function AutoTextarea({ minRows = 3, style, onChange, ...props }: AutoTextareaProps) {
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

// ── Image upload zone ─────────────────────────────────────────────────────────
interface ImageUploadZoneProps {
  previewUrl:    string | null;
  imageKey:      string;
  uploadState:   UploadState;
  fileInputRef:  React.RefObject<HTMLInputElement | null>;
  onSelect:      (file: File) => void;
  onRemove:      () => void;
  label?:        string;
  hint?:         string;
}
function ImageUploadZone({
  previewUrl, imageKey, uploadState, fileInputRef,
  onSelect, onRemove, label = "Click or drag & drop an image", hint = ALLOWED_IMAGE_LABEL,
}: ImageUploadZoneProps) {
  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    const file = e.dataTransfer.files[0];
    if (file) onSelect(file);
  };

  if (previewUrl && imageKey) {
    return (
      <div className="relative rounded-[var(--radius-md)] overflow-hidden"
        style={{ border: `1px solid ${T.border}` }}>
        <ImageLoader
          src={previewUrl}
          alt="Question image"
          maxHeight={360}
          background="#f8f9fa"
          skeletonHeight={180}
        />
        <button
          onClick={onRemove}
          className="absolute top-2 right-2 w-7 h-7 rounded-full flex items-center justify-center shadow-md transition-opacity hover:opacity-80"
          style={{ background: "rgba(0,0,0,0.6)", color: "#fff" }}
          aria-label="Remove image"
          type="button"
        >
          <X size={13} />
        </button>
      </div>
    );
  }

  return (
    <>
      <div
        className="flex flex-col items-center justify-center gap-3 py-8 rounded-[var(--radius-md)] transition-colors"
        style={{
          background:  T.surface,
          border:      `2px dashed ${T.border}`,
          cursor:      uploadState === "uploading" ? "wait" : "pointer",
        }}
        onClick={() => uploadState !== "uploading" && fileInputRef.current?.click()}
        onDragOver={e => e.preventDefault()}
        onDrop={handleDrop}
        role="button"
        tabIndex={0}
        onKeyDown={e => e.key === "Enter" && fileInputRef.current?.click()}
      >
        {uploadState === "uploading"
          ? <Loader2 size={24} className="animate-spin" style={{ color: T.muted }} />
          : <ImageIcon size={24} style={{ color: T.subtle }} />
        }
        <div className="text-center px-4">
          <p className="text-xs font-semibold" style={{ color: T.muted }}>
            {uploadState === "uploading" ? "Uploading…" : label}
          </p>
          {uploadState !== "uploading" && (
            <p className="text-[11px] mt-0.5" style={{ color: T.subtle }}>{hint}</p>
          )}
          {uploadState === "error" && (
            <p className="text-[11px] mt-1 font-semibold" style={{ color: "var(--color-danger)" }}>
              Upload failed — try again
            </p>
          )}
        </div>
        {uploadState !== "uploading" && (
          <button
            type="button"
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-[var(--radius-md)] text-xs font-semibold border transition-colors"
            style={{ background: T.white, color: T.muted, borderColor: T.border }}
            onClick={e => { e.stopPropagation(); fileInputRef.current?.click(); }}
          >
            <Upload size={11} />
            Browse
          </button>
        )}
      </div>
      <input
        ref={fileInputRef}
        type="file"
        accept={ALLOWED_IMAGE_TYPES.join(",")}
        className="hidden"
        onChange={e => {
          const file = e.target.files?.[0];
          if (file) onSelect(file);
          e.target.value = "";
        }}
      />
    </>
  );
}

// ── MCQ Options Editor ────────────────────────────────────────────────────────
interface OptionRowProps {
  option:      PracticeQuestionOption;
  mcqType:     McqType;
  saving:      boolean;
  onSaveText:  (id: string, text: string) => Promise<void>;
  onToggle:       (id: string, current: boolean) => Promise<void>;
  onDelete:       (id: string) => Promise<void>;
  onAddWithText:  (text: string) => Promise<void>;
}
function OptionRow({ option, mcqType, saving, onSaveText, onToggle, onDelete, onAddWithText }: OptionRowProps) {
  const [text,    setText]    = useState(option.text);
  const [editing, setEditing] = useState(false);
  const [busy,    setBusy]    = useState(false);
  const isCorrect = !!option.is_correct;

  // Sync if parent updates (e.g., single-mode deselect)
  useEffect(() => { setText(option.text); }, [option.text]);

  const handleBlur = async () => {
    setEditing(false);
    if (text === option.text) return;
    setBusy(true);
    try { await onSaveText(option.id, text); } finally { setBusy(false); }
  };

  const handleToggle = async () => {
    setBusy(true);
    try { await onToggle(option.id, isCorrect); } finally { setBusy(false); }
  };

  const handleDelete = async () => {
    setBusy(true);
    try { await onDelete(option.id); } finally { setBusy(false); }
  };

  // Paste handler: if pasted text has multiple lines, spill each line into
  // a new option automatically instead of cramming them all into one field.
  const handlePaste = async (e: React.ClipboardEvent<HTMLTextAreaElement>) => {
    const pasted = e.clipboardData.getData("text");
    const lines  = pasted.split(/\r?\n/).map(l => l.trim()).filter(l => l.length > 0);
    if (lines.length <= 1) return; // single line → normal paste
    e.preventDefault();
    // First line fills this option
    setText(lines[0]);
    setBusy(true);
    try {
      await onSaveText(option.id, lines[0]);
      // Remaining lines each become a new option, created sequentially
      for (const line of lines.slice(1)) {
        await onAddWithText(line);
      }
    } finally {
      setBusy(false);
    }
  };

  return (
    <div
      className="flex items-start gap-3 p-3 rounded-[var(--radius-md)] transition-colors"
      style={{
        background:  isCorrect ? "#F0FDF4" : T.surface,
        border:      `1.5px solid ${isCorrect ? "#BBF7D0" : T.border}`,
      }}
    >
      {/* Label badge */}
      <span
        className="shrink-0 w-7 h-7 rounded-full flex items-center justify-center text-xs font-bold mt-0.5"
        style={{
          background: isCorrect ? "#16A34A" : T.border,
          color:      isCorrect ? "#fff" : T.muted,
        }}
      >
        {option.label}
      </span>

      {/* Text input */}
      <div className="flex-1 min-w-0">
        <AutoTextarea
          value={text}
          minRows={1}
          placeholder="Option text… (paste multiple lines to create multiple options)"
          className="w-full text-sm rounded-[var(--radius-sm)] px-2 py-1 outline-none leading-relaxed"
          style={{ background: "transparent", border: `1px solid ${editing ? T.muted : "transparent"}`, color: T.text }}
          onFocus={() => setEditing(true)}
          onBlur={handleBlur}
          onChange={e => setText(e.target.value)}
          onPaste={handlePaste}
        />
      </div>

      {/* Correct toggle */}
      <button
        type="button"
        onClick={handleToggle}
        disabled={busy || saving}
        title={isCorrect
          ? "Mark as incorrect"
          : mcqType === "single" ? "Mark as correct (deselects others)" : "Mark as correct"}
        className="shrink-0 w-7 h-7 rounded-full flex items-center justify-center transition-all mt-0.5 disabled:opacity-50"
        style={{
          background: isCorrect ? "#16A34A" : T.surface,
          border:     `1.5px solid ${isCorrect ? "#16A34A" : T.border}`,
          color:      isCorrect ? "#fff" : T.subtle,
        }}
        onMouseEnter={e => {
          if (!isCorrect) {
            e.currentTarget.style.borderColor = "#16A34A";
            e.currentTarget.style.color = "#16A34A";
          }
        }}
        onMouseLeave={e => {
          if (!isCorrect) {
            e.currentTarget.style.borderColor = T.border;
            e.currentTarget.style.color = T.subtle;
          }
        }}
      >
        {busy ? <Loader2 size={12} className="animate-spin" /> : <Check size={12} />}
      </button>

      {/* Delete */}
      <button
        type="button"
        onClick={handleDelete}
        disabled={busy || saving}
        title="Delete option"
        className="shrink-0 w-7 h-7 rounded-full flex items-center justify-center transition-colors mt-0.5 disabled:opacity-50"
        style={{ background: T.surface, border: `1.5px solid ${T.border}`, color: T.subtle }}
        onMouseEnter={e => {
          e.currentTarget.style.borderColor = "var(--color-danger, #DC2626)";
          e.currentTarget.style.color = "var(--color-danger, #DC2626)";
        }}
        onMouseLeave={e => {
          e.currentTarget.style.borderColor = T.border;
          e.currentTarget.style.color = T.subtle;
        }}
      >
        <Trash2 size={12} />
      </button>
    </div>
  );
}

// ── Main page ─────────────────────────────────────────────────────────────────
export default function PracticeQuestionEditorPage() {
  const { question_id } = useParams<{ question_id: string }>();
  const router = useRouter();
  const toast  = useToast();

  const [detail,   setDetail]   = useState<QuestionDetail | null>(null);
  const [loading,  setLoading]  = useState(true);
  const [saving,   setSaving]   = useState(false);
  const [toggling, setToggling] = useState(false);
  const [addingOpt, setAddingOpt] = useState(false);

  const [form,     setForm]     = useState<QuestionForm | null>(null);
  const [original, setOriginal] = useState<QuestionForm | null>(null);
  const [options,  setOptions]  = useState<PracticeQuestionOption[]>([]);

  // ── Question body image ───────────────────────────────────────────────────
  const [qImgState,   setQImgState]   = useState<UploadState>("idle");
  const [qPreviewUrl, setQPreviewUrl] = useState<string | null>(null);
  const qFileInputRef = useRef<HTMLInputElement>(null);

  // ── Explanation image ─────────────────────────────────────────────────────
  const [eImgState,   setEImgState]   = useState<UploadState>("idle");
  const [ePreviewUrl, setEPreviewUrl] = useState<string | null>(null);
  const eFileInputRef = useRef<HTMLInputElement>(null);

  // ── Load ──────────────────────────────────────────────────────────────────
  const loadQuestion = useCallback(() => {
    setLoading(true);
    api.get(`/practice/questions/${question_id}/`)
      .then(res => {
        const { question, section, module, options: opts } = res.data.data as QuestionDetail;
        setDetail({ question, section, module, options: opts ?? [] });
        setOptions(opts ?? []);
        const snap = formFromQuestion(question);
        setForm(snap);
        setOriginal(snap);
        setQPreviewUrl(question.question_image_url ?? null);
        setEPreviewUrl(question.explanation_image_url ?? null);
      })
      .catch(err => {
        toast.error(getErrorMessage(err));
        router.push("/admin/practice");
      })
      .finally(() => setLoading(false));
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [question_id]);

  useEffect(() => { loadQuestion(); }, [loadQuestion]);

  // ── Helpers ───────────────────────────────────────────────────────────────
  const patch = <K extends keyof QuestionForm>(key: K, val: QuestionForm[K]) =>
    setForm(f => f ? { ...f, [key]: val } : f);

  const dirty = form && original ? isDirty(original, form) : false;

  // ── Leave-with-unsaved-changes guard ──────────────────────────────────────
  // Every in-app "back" trigger (arrow button, breadcrumbs) routes through
  // this instead of calling router.push directly. If there are unsaved
  // edits, navigation is held and a confirm dialog offers Save & Leave /
  // Leave without saving / Cancel instead of silently discarding the work.
  const [pendingHref, setPendingHref] = useState<string | null>(null);

  const guardedNavigate = useCallback((href: string) => {
    if (dirty) {
      setPendingHref(href);
    } else {
      router.push(href);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [dirty]);

  const handleLeaveWithoutSaving = () => {
    if (pendingHref) router.push(pendingHref);
    setPendingHref(null);
  };

  const handleSaveAndLeave = async () => {
    const ok = await handleSave();
    if (ok && pendingHref) {
      router.push(pendingHref);
      setPendingHref(null);
    }
  };

  // Covers the browser's own back/forward, refresh, and tab-close — the
  // in-app dialog above only intercepts clicks on this page's own back
  // controls, not the browser chrome, so this is the standard native
  // fallback for that case.
  useEffect(() => {
    if (!dirty) return;
    const handler = (e: BeforeUnloadEvent) => {
      e.preventDefault();
      e.returnValue = "";
    };
    window.addEventListener("beforeunload", handler);
    return () => window.removeEventListener("beforeunload", handler);
  }, [dirty]);

  // ── Shared field payload (text/image fields + mcq_type/fib_answer) ────────
  // Used by both handleSave and handlePublishToggle so a publish click
  // always carries the form's current values, not whatever the backend
  // last had saved.
  const buildFieldPayload = (f: QuestionForm): Record<string, unknown> => {
    const payload: Record<string, unknown> = {
      question_content_type: f.question_content_type,
      question_text:         f.question_text,
      question_image_key:    f.question_image_key,
      explanation_type:      f.explanation_type,
      explanation_text:      f.explanation_text,
      explanation_image_key: f.explanation_image_key,
    };
    if (detail?.question.question_type === "fib") {
      payload.fib_answer = f.fib_answer;
    }
    if (detail?.question.question_type === "mcq") {
      payload.mcq_type = f.mcq_type;
    }
    return payload;
  };

  const applyUpdatedQuestion = (updated: PracticeQuestion) => {
    const snap = formFromQuestion(updated);
    setForm(snap);
    setOriginal(snap);
    setQPreviewUrl(updated.question_image_url ?? null);
    setEPreviewUrl(updated.explanation_image_url ?? null);
  };

  // ── Save question (text/image fields + mcq_type) ──────────────────────────
  // Returns whether the save actually succeeded — callers that need to chain
  // an action afterward (e.g. "Save & Leave") can't rely on reading `dirty`
  // right after awaiting this, since the state update that clears it hasn't
  // necessarily flowed through a re-render yet.
  const handleSave = async (): Promise<boolean> => {
    if (!form || !dirty) return true; // nothing pending — treat as success
    setSaving(true);
    try {
      const res = await api.patch(`/practice/questions/${question_id}/`, buildFieldPayload(form));
      applyUpdatedQuestion(res.data.data);
      toast.success("Question saved.");
      return true;
    } catch (err) {
      toast.error(getErrorMessage(err));
      return false;
    } finally {
      setSaving(false);
    }
  };

  // ── Publish toggle ────────────────────────────────────────────────────────
  // Sends any unsaved field edits together with is_published in a single
  // atomic PATCH — otherwise a click here would check the publish
  // requirements against whatever was last saved, not what's on screen,
  // and could reject (or wrongly allow) publishing based on stale data.
  const handlePublishToggle = async () => {
    if (!form) return;
    const newVal = !form.is_published;
    const hadUnsavedEdits = dirty;
    setToggling(true);
    try {
      const payload = { ...buildFieldPayload(form), is_published: newVal };
      const res = await api.patch(`/practice/questions/${question_id}/`, payload);
      applyUpdatedQuestion(res.data.data);
      toast.success(
        newVal
          ? hadUnsavedEdits ? "Changes saved and question published." : "Question published."
          : hadUnsavedEdits ? "Changes saved and question unpublished." : "Question unpublished."
      );
    } catch (err) {
      toast.error(getErrorMessage(err));
    } finally {
      setToggling(false);
    }
  };

  // ── Generic image upload ──────────────────────────────────────────────────
  const handleImageUpload = async (opts: {
    file:           File;
    presignUrl:     string;
    setUploadState: (s: UploadState) => void;
    setPreview:     (url: string | null) => void;
    onSuccess:      (fileKey: string, cdnUrl: string) => void;
    onError:        () => void;
  }) => {
    const { file, presignUrl, setUploadState, setPreview, onSuccess, onError } = opts;

    if (!ALLOWED_IMAGE_TYPES.includes(file.type)) {
      toast.error(`Unsupported format. Allowed: ${ALLOWED_IMAGE_LABEL}`);
      return;
    }
    if (file.size > MAX_IMAGE_BYTES) {
      toast.error("Image exceeds 5 MB limit.");
      return;
    }

    setUploadState("uploading");
    setPreview(URL.createObjectURL(file));

    try {
      const presignRes = await api.post(presignUrl, {
        filename: file.name, content_type: file.type,
      });
      const { upload_url, file_key, cdn_url } = presignRes.data.data;

      // Retries on transient network drops — the presigned URL stays valid
      // for its full expiry window, so re-sending the same PUT is safe.
      await putFileWithRetry(upload_url, file, () => {});

      setPreview(cdn_url);
      setUploadState("done");
      onSuccess(file_key, cdn_url);
      toast.success("Image uploaded.");
    } catch {
      setUploadState("error");
      onError();
      toast.error("Image upload failed. Please try again.");
    }
  };

  const handleQImageSelect = (file: File) =>
    handleImageUpload({
      file,
      presignUrl:     `/practice/questions/${question_id}/question-image/presign/`,
      setUploadState: setQImgState,
      setPreview:     setQPreviewUrl,
      onSuccess:      (key) => patch("question_image_key", key),
      onError:        () => { setQPreviewUrl(form?.question_image_url ?? null); setQImgState("error"); },
    });

  const handleQImageRemove = () => {
    patch("question_image_key", "");
    setQPreviewUrl(null);
    setQImgState("idle");
  };

  const handleEImageSelect = (file: File) =>
    handleImageUpload({
      file,
      presignUrl:     `/practice/questions/${question_id}/explanation-image/presign/`,
      setUploadState: setEImgState,
      setPreview:     setEPreviewUrl,
      onSuccess:      (key) => patch("explanation_image_key", key),
      onError:        () => { setEPreviewUrl(form?.explanation_image_url ?? null); setEImgState("error"); },
    });

  const handleEImageRemove = () => {
    patch("explanation_image_key", "");
    setEPreviewUrl(null);
    setEImgState("idle");
  };

  // ── MCQ Type change ───────────────────────────────────────────────────────
  const handleMcqTypeChange = async (newType: McqType) => {
    patch("mcq_type", newType);
    // Persist immediately (so backend enforces correct constraints)
    try {
      await api.patch(`/practice/questions/${question_id}/`, { mcq_type: newType });
      setOriginal(prev => prev ? { ...prev, mcq_type: newType } : prev);
    } catch (err) {
      toast.error(getErrorMessage(err));
    }
  };

  // ── Options CRUD ──────────────────────────────────────────────────────────
  const handleAddOption = async () => {
    setAddingOpt(true);
    try {
      const res = await api.post(`/practice/questions/${question_id}/options/`, {
        text:       "",
        is_correct: false,
      });
      setOptions(prev => [...prev, res.data.data]);
    } catch (err) {
      toast.error(getErrorMessage(err));
    } finally {
      setAddingOpt(false);
    }
  };

  // Used by OptionRow paste handler — creates a new option pre-filled with text.
  const handleAddOptionWithText = async (text: string) => {
    try {
      const res = await api.post(`/practice/questions/${question_id}/options/`, {
        text,
        is_correct: false,
      });
      setOptions(prev => [...prev, res.data.data]);
    } catch (err) {
      toast.error(getErrorMessage(err));
    }
  };

  const handleOptionTextSave = async (optionId: string, text: string) => {
    try {
      const res = await api.patch(
        `/practice/questions/${question_id}/options/${optionId}/`,
        { text }
      );
      setOptions(prev => prev.map(o => o.id === optionId ? res.data.data : o));
    } catch (err) {
      toast.error(getErrorMessage(err));
    }
  };

  const handleOptionToggleCorrect = async (optionId: string, currentlyCorrect: boolean) => {
    const newValue = !currentlyCorrect;
    try {
      const res = await api.patch(
        `/practice/questions/${question_id}/options/${optionId}/`,
        { is_correct: newValue }
      );
      // For single-correct MCQ, backend deselected others — reload all options
      if (form?.mcq_type === "single" && newValue) {
        const listRes = await api.get(`/practice/questions/${question_id}/options/`);
        setOptions(listRes.data.data);
      } else {
        setOptions(prev => prev.map(o => o.id === optionId ? res.data.data : o));
      }
    } catch (err) {
      toast.error(getErrorMessage(err));
    }
  };

  const handleOptionDelete = async (optionId: string) => {
    try {
      await api.delete(`/practice/questions/${question_id}/options/${optionId}/`);
      setOptions(prev => prev.filter(o => o.id !== optionId));
    } catch (err) {
      toast.error(getErrorMessage(err));
    }
  };

  // ── Derived ───────────────────────────────────────────────────────────────
  const question    = detail?.question;
  const isMcq       = question?.question_type === "mcq";
  const TypeIcon    = isMcq ? ListChecks : AlignLeft;
  const typeBg      = isMcq ? "#EFF6FF" : "#FDF4FF";
  const typeColor   = isMcq ? "#2563EB" : "#9333EA";
  const typeBorder  = isMcq ? "#BFDBFE" : "#E9D5FF";
  const typeLabel   = isMcq ? "Multiple Choice (MCQ)" : "Fill in the Blank (FIB)";
  const backHref    = detail?.section
    ? `/admin/practice/sections/${detail.section.id}`
    : "/admin/practice";

  const showQText  = form?.question_content_type === "text"  || form?.question_content_type === "both";
  const showQImage = form?.question_content_type === "image" || form?.question_content_type === "both";
  const showEText  = form?.explanation_type === "text"  || form?.explanation_type === "both";
  const showEImage = form?.explanation_type === "image" || form?.explanation_type === "both";

  // ── Loading skeleton ──────────────────────────────────────────────────────
  if (loading) {
    return (
      <AdminLayout>
        <PageWrapper className="max-w-5xl">
          <div className="h-4 w-48 rounded animate-pulse mb-5"  style={{ background: T.surface }} />
          <div className="h-8 w-56 rounded-lg animate-pulse mb-8" style={{ background: T.surface }} />
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <div className="space-y-5">
              <div className="h-52 rounded-[var(--radius-lg)] animate-pulse" style={{ background: T.surface }} />
              <div className="h-16 rounded-[var(--radius-lg)] animate-pulse" style={{ background: T.surface }} />
            </div>
            <div className="h-72 rounded-[var(--radius-lg)] animate-pulse" style={{ background: T.surface }} />
          </div>
        </PageWrapper>
      </AdminLayout>
    );
  }

  return (
    <AdminLayout>
      <PageWrapper className="max-w-5xl">

        {/* ── Breadcrumb ──────────────────────────────────────────────────── */}
        <Breadcrumb detail={detail} onNavigate={guardedNavigate} backHref={backHref} />

        {/* ── Title row ───────────────────────────────────────────────────── */}
        <div className="flex items-center justify-between gap-4 mb-6 flex-wrap">
          <div className="flex items-center gap-3 min-w-0">
            <button
              onClick={() => guardedNavigate(backHref)}
              className="p-1.5 rounded-[var(--radius-sm)] transition-colors shrink-0"
              style={{ color: T.muted }}
              onMouseEnter={e => (e.currentTarget.style.background = "var(--color-surface-hover)")}
              onMouseLeave={e => (e.currentTarget.style.background = "transparent")}
              aria-label="Back"
            >
              <ArrowLeft size={18} />
            </button>
            <div>
              <h1 className="text-2xl font-bold tracking-tight" style={{ color: T.text }}>
                Question {question?.question_number}
              </h1>
              <span
                className="inline-flex items-center gap-1 mt-1 px-2 py-0.5 rounded-full text-xs font-semibold"
                style={{ background: typeBg, color: typeColor, border: `1px solid ${typeBorder}` }}
              >
                <TypeIcon size={10} />
                {typeLabel}
              </span>
            </div>
          </div>

          {/* Publish toggle + Save */}
          <div className="flex items-center gap-3 shrink-0">
            <button
              onClick={handlePublishToggle}
              disabled={toggling}
              className="inline-flex items-center gap-2 px-3 py-1.5 rounded-[var(--radius-md)] text-sm font-medium border transition-colors disabled:opacity-50"
              style={form?.is_published
                ? { background: "#F0FDF4", color: "#16A34A", borderColor: "#BBF7D0" }
                : { background: T.surface, color: T.muted,   borderColor: T.border }
              }
            >
              {toggling
                ? <Loader2 size={13} className="animate-spin" />
                : form?.is_published ? <Eye size={13} /> : <EyeOff size={13} />
              }
              {form?.is_published ? "Published" : "Draft"}
            </button>
            <Button
              variant="primary" size="md"
              onClick={handleSave}
              loading={saving}
              disabled={!dirty || saving}
              leftIcon={<Save size={14} />}
            >
              Save
            </Button>
          </div>
        </div>

        {/* ── Two-column editor ────────────────────────────────────────────── */}
        <div className={[
          "grid grid-cols-1 lg:grid-cols-2 gap-6 items-start",
          dirty ? "pb-20 lg:pb-0" : "",
        ].join(" ")}>

          {/* ── LEFT COLUMN ──────────────────────────────────────────────────── */}
          <div className="space-y-5">

            {/* ── Question Content card ─────────────────────────────────────── */}
            <div className="rounded-[var(--radius-lg)] p-5"
              style={{ background: T.white, border: `1px solid ${T.border}` }}>

              <div className="flex items-center justify-between gap-2 mb-4">
                <p className="text-sm font-semibold" style={{ color: T.text }}>Question Content</p>

                {/* Content-type selector */}
                <div className="flex items-center gap-1">
                  {CONTENT_TYPES.map(({ value, label, icon }) => (
                    <button
                      key={value}
                      type="button"
                      onClick={() => patch("question_content_type", value)}
                      className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold border transition-all"
                      style={form?.question_content_type === value
                        ? { background: "var(--color-text)", color: "#fff", borderColor: "transparent" }
                        : { background: T.surface, color: T.subtle, borderColor: T.border }
                      }
                      title={label}
                    >
                      {icon}
                      <span className="hidden sm:inline">{label}</span>
                    </button>
                  ))}
                </div>
              </div>

              <div className="space-y-4">
                {showQText && (
                  <div>
                    <label className="block text-xs font-semibold mb-1.5" style={{ color: T.muted }}>
                      Question Text
                      {!isMcq && (
                        <span className="ml-1 font-normal" style={{ color: T.subtle }}>
                          — use <code className="px-1 py-0.5 rounded text-[11px]"
                            style={{ background: T.surface, color: typeColor }}>___</code> for the blank
                        </span>
                      )}
                    </label>
                    <AutoTextarea
                      value={form?.question_text ?? ""}
                      onChange={e => patch("question_text", e.target.value)}
                      placeholder={isMcq ? "Enter the question…" : "e.g. The capital of India is ___."}
                      minRows={4}
                      className="w-full text-sm rounded-[var(--radius-md)] px-3.5 py-2.5 outline-none leading-relaxed"
                      style={{ background: T.surface, border: `1px solid ${T.border}`, color: T.text }}
                      onFocus={e => (e.currentTarget.style.borderColor = "var(--color-accent)")}
                      onBlur={e  => (e.currentTarget.style.borderColor = T.border)}
                    />
                  </div>
                )}

                {showQImage && (
                  <div>
                    <label className="block text-xs font-semibold mb-1.5" style={{ color: T.muted }}>
                      Question Image
                    </label>
                    <ImageUploadZone
                      previewUrl={qPreviewUrl}
                      imageKey={form?.question_image_key ?? ""}
                      uploadState={qImgState}
                      fileInputRef={qFileInputRef}
                      onSelect={handleQImageSelect}
                      onRemove={handleQImageRemove}
                    />
                  </div>
                )}
              </div>
            </div>

            {/* ── FIB: Correct Answer card ──────────────────────────────────── */}
            {!isMcq && (
              <div className="rounded-[var(--radius-lg)] p-5"
                style={{ background: T.white, border: `1px solid ${T.border}` }}>
                <label className="block text-sm font-semibold mb-1.5" style={{ color: T.text }}>
                  Correct Answer
                </label>
                <p className="text-xs mb-3" style={{ color: T.muted }}>
                  The exact text that fills the blank. Students see this after confirmation.
                </p>
                <input
                  type="text"
                  value={form?.fib_answer ?? ""}
                  onChange={e => patch("fib_answer", e.target.value)}
                  placeholder="e.g. New Delhi"
                  className="w-full text-sm rounded-[var(--radius-md)] px-3.5 py-2.5 outline-none"
                  style={{ background: T.surface, border: `1px solid ${T.border}`, color: T.text }}
                  onFocus={e => (e.currentTarget.style.borderColor = "var(--color-accent)")}
                  onBlur={e  => (e.currentTarget.style.borderColor = T.border)}
                />
              </div>
            )}

            {/* ── MCQ: Answer Type + Options ────────────────────────────────── */}
            {isMcq && (
              <>
                {/* Answer type selector */}
                <div className="rounded-[var(--radius-lg)] p-5"
                  style={{ background: T.white, border: `1px solid ${T.border}` }}>
                  <p className="text-sm font-semibold mb-3" style={{ color: T.text }}>Answer Type</p>
                  <div className="flex gap-2">
                    {(["single", "multiple"] as McqType[]).map(t => (
                      <button
                        key={t}
                        type="button"
                        onClick={() => handleMcqTypeChange(t)}
                        className="flex-1 py-2.5 rounded-[var(--radius-md)] text-sm font-semibold border transition-all"
                        style={form?.mcq_type === t
                          ? { background: typeBg, color: typeColor, borderColor: typeBorder }
                          : { background: T.surface, color: T.muted, borderColor: T.border }
                        }
                      >
                        {t === "single" ? "Single Correct" : "Multiple Correct"}
                      </button>
                    ))}
                  </div>
                  <p className="text-xs mt-2.5" style={{ color: T.subtle }}>
                    {form?.mcq_type === "single"
                      ? "Only one option can be marked correct. Selecting another auto-deselects the previous."
                      : "Multiple options can be marked correct. Students must select all of them exactly."
                    }
                  </p>
                </div>

                {/* Options editor */}
                <div className="rounded-[var(--radius-lg)] p-5"
                  style={{ background: T.white, border: `1px solid ${T.border}` }}>
                  <div className="flex items-center justify-between gap-2 mb-4">
                    <div>
                      <p className="text-sm font-semibold" style={{ color: T.text }}>Answer Options</p>
                      <p className="text-xs mt-0.5" style={{ color: T.subtle }}>
                        Click <Check size={10} className="inline" /> to mark as correct.
                        Edit text directly in each row.
                      </p>
                    </div>
                    <button
                      type="button"
                      onClick={handleAddOption}
                      disabled={addingOpt || options.length >= 26}
                      className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-[var(--radius-md)] text-xs font-semibold border transition-colors disabled:opacity-50"
                      style={{ background: T.surface, color: T.muted, borderColor: T.border }}
                    >
                      {addingOpt
                        ? <Loader2 size={12} className="animate-spin" />
                        : <Plus size={12} />
                      }
                      Add Option
                    </button>
                  </div>

                  {options.length === 0 ? (
                    <div className="flex flex-col items-center justify-center py-8 rounded-[var(--radius-md)]"
                      style={{ background: T.surface, border: `1px dashed ${T.border}` }}>
                      <p className="text-xs font-semibold" style={{ color: T.muted }}>No options yet</p>
                      <p className="text-[11px] mt-0.5" style={{ color: T.subtle }}>
                        Click &quot;Add Option&quot; to create answer choices.
                      </p>
                    </div>
                  ) : (
                    <div className="space-y-2">
                      {options.map(opt => (
                        <OptionRow
                          key={opt.id}
                          option={opt}
                          mcqType={form?.mcq_type ?? "single"}
                          saving={saving}
                          onSaveText={handleOptionTextSave}
                          onToggle={handleOptionToggleCorrect}
                          onDelete={handleOptionDelete}
                          onAddWithText={handleAddOptionWithText}
                        />
                      ))}
                    </div>
                  )}

                  {options.length > 0 && (
                    <p className="text-[11px] mt-3" style={{ color: T.subtle }}>
                      {options.filter(o => o.is_correct).length === 0
                        ? "⚠ No correct option marked yet."
                        : `${options.filter(o => o.is_correct).length} correct option${options.filter(o => o.is_correct).length > 1 ? "s" : ""} marked.`
                      }
                    </p>
                  )}
                </div>
              </>
            )}

          </div>{/* end LEFT */}

          {/* ── RIGHT COLUMN: Explanation ─────────────────────────────────────── */}
          <div className="rounded-[var(--radius-lg)] p-5"
            style={{ background: T.white, border: `1px solid ${T.border}` }}>

            <div className="flex items-center justify-between gap-2 mb-4">
              <p className="text-sm font-semibold" style={{ color: T.text }}>Explanation</p>
              <div className="flex items-center gap-1">
                {EXP_TYPES.map(({ value, label }) => (
                  <button
                    key={value}
                    type="button"
                    onClick={() => patch("explanation_type", value)}
                    className="px-2.5 py-1 rounded-full text-xs font-semibold border transition-all"
                    style={form?.explanation_type === value
                      ? { background: "var(--color-text)", color: "#fff", borderColor: "transparent" }
                      : { background: T.surface, color: T.subtle, borderColor: T.border }
                    }
                  >
                    {label}
                  </button>
                ))}
              </div>
            </div>

            {form?.explanation_type === "none" && (
              <div className="flex items-center justify-center py-10 rounded-[var(--radius-md)]"
                style={{ background: T.surface, border: `1px dashed ${T.border}` }}>
                <p className="text-xs" style={{ color: T.subtle }}>
                  No explanation will be shown to students.
                </p>
              </div>
            )}

            <div className="space-y-4">
              {showEText && (
                <div>
                  <label className="block text-xs font-semibold mb-1.5" style={{ color: T.muted }}>
                    Explanation Text
                  </label>
                  <AutoTextarea
                    value={form?.explanation_text ?? ""}
                    onChange={e => patch("explanation_text", e.target.value)}
                    placeholder="Explain why the answer is correct…"
                    minRows={4}
                    className="w-full text-sm rounded-[var(--radius-md)] px-3.5 py-2.5 outline-none leading-relaxed"
                    style={{ background: T.surface, border: `1px solid ${T.border}`, color: T.text }}
                    onFocus={e => (e.currentTarget.style.borderColor = "var(--color-accent)")}
                    onBlur={e  => (e.currentTarget.style.borderColor = T.border)}
                  />
                </div>
              )}

              {showEImage && (
                <div>
                  <label className="block text-xs font-semibold mb-1.5" style={{ color: T.muted }}>
                    Explanation Image
                  </label>
                  <ImageUploadZone
                    previewUrl={ePreviewUrl}
                    imageKey={form?.explanation_image_key ?? ""}
                    uploadState={eImgState}
                    fileInputRef={eFileInputRef}
                    onSelect={handleEImageSelect}
                    onRemove={handleEImageRemove}
                  />
                </div>
              )}
            </div>
          </div>{/* end RIGHT */}

        </div>{/* end grid */}

        {/* ── Sticky save bar (mobile) ─────────────────────────────────────── */}
        {dirty && (
          <div className="lg:hidden fixed bottom-0 left-0 right-0 z-40 px-4 py-3 flex justify-end"
            style={{ background: "var(--color-background)", borderTop: `1px solid ${T.border}` }}>
            <Button variant="primary" size="md" onClick={handleSave} loading={saving}
              leftIcon={<Save size={14} />}>
              Save Changes
            </Button>
          </div>
        )}

        {/* ── Unsaved-changes guard ────────────────────────────────────────── */}
        <Modal
          isOpen={pendingHref !== null}
          onClose={() => setPendingHref(null)}
          title="Unsaved changes"
          maxWidth="sm"
        >
          <p className="text-sm leading-relaxed" style={{ color: T.muted }}>
            You have unsaved changes on this question. Save them before leaving,
            or they&apos;ll be lost.
          </p>
          <div className="flex items-center justify-end gap-3 mt-6">
            <Button variant="ghost" onClick={() => setPendingHref(null)} disabled={saving}>
              Cancel
            </Button>
            <Button variant="danger" onClick={handleLeaveWithoutSaving} disabled={saving}>
              Leave without saving
            </Button>
            <Button variant="primary" onClick={handleSaveAndLeave} loading={saving}
              leftIcon={<Save size={14} />}>
              Save &amp; Leave
            </Button>
          </div>
        </Modal>

      </PageWrapper>
    </AdminLayout>
  );
}

// ── Breadcrumb ────────────────────────────────────────────────────────────────
function Breadcrumb({ detail, onNavigate, backHref }: {
  detail: QuestionDetail | null;
  onNavigate: (href: string) => void;
  backHref: string;
}) {
  return (
    <div className="flex items-center gap-1.5 text-xs font-medium mb-5" style={{ color: T.muted }}>
      <button onClick={() => onNavigate("/admin/practice")} className="transition-colors shrink-0"
        onMouseEnter={e => (e.currentTarget.style.color = T.text)}
        onMouseLeave={e => (e.currentTarget.style.color = T.muted)}>
        Practice
      </button>
      {detail?.module && (
        <>
          <ChevronRight size={12} style={{ color: T.subtle, flexShrink: 0 }} />
          <button onClick={() => onNavigate(`/admin/practice/${detail.module!.id}`)}
            className="transition-colors truncate"
            onMouseEnter={e => (e.currentTarget.style.color = T.text)}
            onMouseLeave={e => (e.currentTarget.style.color = T.muted)}>
            {detail.module.name}
          </button>
        </>
      )}
      {detail?.section && (
        <>
          <ChevronRight size={12} style={{ color: T.subtle, flexShrink: 0 }} />
          <button onClick={() => onNavigate(backHref)} className="transition-colors truncate"
            onMouseEnter={e => (e.currentTarget.style.color = T.text)}
            onMouseLeave={e => (e.currentTarget.style.color = T.muted)}>
            {detail.section.name}
          </button>
        </>
      )}
      <ChevronRight size={12} style={{ color: T.subtle, flexShrink: 0 }} />
      <span style={{ color: T.text }}>
        {detail?.question
          ? `Question ${detail.question.question_number}`
          : <span className="inline-block h-3 w-20 rounded animate-pulse" style={{ background: T.surface }} />
        }
      </span>
    </div>
  );
}
