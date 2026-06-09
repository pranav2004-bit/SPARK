"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import {
  ListChecks, AlignLeft, Pencil, Trash2, Globe, EyeOff,
  Loader2, ChevronRight, Link2, Check, Search,
} from "lucide-react";
import { AdminLayout } from "@/components/layout/AdminLayout";
import { PageWrapper } from "@/components/layout/PageWrapper";
import { PageHeader } from "@/components/layout/PageHeader";
import { Button } from "@/components/ui/Button";
import { Modal } from "@/components/ui/Modal";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import { EmptyState } from "@/components/ui/EmptyState";
import { QuestionCardSkeleton, Skeleton } from "@/components/ui/Skeleton";
import { useToast } from "@/components/ui/Toast";
import { useCopyLink } from "@/hooks/useCopyLink";
import api, { getErrorMessage } from "@/lib/api";
import type { PracticeModule, PracticeSection, PracticeQuestion, ApiSuccess } from "@/types";

// ── Card colour palette ───────────────────────────────────────────────────────
const PALETTE = [
  { bg: "#FFF4E6", color: "#E8820C" },
  { bg: "#EFF6FF", color: "#2563EB" },
  { bg: "#F0FDF4", color: "#16A34A" },
  { bg: "#FDF4FF", color: "#9333EA" },
  { bg: "#FFF1F2", color: "#E11D48" },
  { bg: "#F0FDFA", color: "#0D9488" },
  { bg: "#FFFBEB", color: "#B45309" },
  { bg: "#F5F3FF", color: "#7C3AED" },
];
const palette = (i: number) => PALETTE[i % PALETTE.length];

// ── Question card ─────────────────────────────────────────────────────────────
interface QuestionCardProps {
  question:        PracticeQuestion;
  index:           number;
  isPublished:     boolean;
  publishing:      boolean;
  isCopied:        boolean;
  onNavigate:      () => void;
  onDelete:        () => void;
  onTogglePublish: () => void;
  onCopyLink:      () => void;
}

function QuestionCard({
  question, index, isPublished, publishing, isCopied,
  onNavigate, onDelete, onTogglePublish, onCopyLink,
}: QuestionCardProps) {
  const { bg, color } = palette(index);
  const isMcq      = question.question_type === "mcq";
  const TypeIcon   = isMcq ? ListChecks : AlignLeft;
  const typeLabel  = isMcq ? "MCQ" : "FIB";
  const typeBg     = isMcq ? "#EFF6FF" : "#FDF4FF";
  const typeColor  = isMcq ? "#2563EB" : "#9333EA";
  const typeBorder = isMcq ? "#BFDBFE" : "#E9D5FF";

  return (
    <div
      className="rounded-[var(--radius-xl)] overflow-hidden transition-shadow duration-150 hover:shadow-[var(--shadow-md)]"
      style={{ background: "var(--color-surface)", border: "1px solid var(--color-border)", boxShadow: "var(--shadow-sm)" }}
    >
      {/* Clickable body */}
      <button onClick={onNavigate} className="w-full text-left px-5 pt-5 pb-4 group cursor-pointer">
        <div className="flex items-start justify-between gap-3">
          <div className="w-11 h-11 rounded-[var(--radius-lg)] flex items-center justify-center shrink-0" style={{ background: bg }}>
            <TypeIcon size={20} style={{ color }} />
          </div>
          <ChevronRight size={16} style={{ color: "var(--color-text-subtle)", marginTop: 2, flexShrink: 0 }}
            className="transition-transform duration-150 group-hover:translate-x-0.5" />
        </div>
        <div className="mt-3">
          {/* Question number — the primary identity */}
          <p
            className="text-2xl font-bold tabular-nums leading-none"
            style={{ color: "var(--color-text)" }}
          >
            #{question.question_number}
          </p>
          {/* Type badge */}
          <span
            className="inline-flex items-center gap-1 mt-2 px-2 py-0.5 rounded text-[10px] font-bold tracking-[0.06em] uppercase"
            style={{ background: typeBg, color: typeColor, border: `1px solid ${typeBorder}`, lineHeight: 1.4 }}
          >
            <TypeIcon size={9} strokeWidth={2.5} />
            {typeLabel}
          </span>
        </div>
      </button>

      {/* Footer */}
      <div className="flex items-center justify-between px-4 py-3 gap-2" style={{ borderTop: "1px solid var(--color-border)" }}>
        <button
          onClick={onTogglePublish} disabled={publishing}
          className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-semibold transition-all disabled:opacity-60 cursor-pointer"
          style={isPublished
            ? { background: "var(--color-success-bg)", color: "var(--color-success)", border: "1px solid rgba(22,163,74,0.2)" }
            : { background: "var(--color-surface-secondary)", color: "var(--color-text-subtle)", border: "1px solid var(--color-border)" }
          }
        >
          {publishing ? <Loader2 size={11} className="animate-spin" />
            : isPublished ? <><Globe size={11} /> Published</>
            : <><EyeOff size={11} /> Unpublished</>
          }
        </button>

        <div className="flex items-center gap-1">
          <button onClick={onCopyLink}
            className="w-8 h-8 rounded-[var(--radius-md)] flex items-center justify-center transition-colors cursor-pointer"
            style={{ color: isCopied ? "var(--color-success)" : "var(--color-text-muted)" }} title="Copy student link"
            onMouseEnter={e => { e.currentTarget.style.background = isCopied ? "var(--color-success-bg)" : "var(--color-surface-hover)"; if (!isCopied) e.currentTarget.style.color = "var(--color-text)"; }}
            onMouseLeave={e => { e.currentTarget.style.background = "transparent"; e.currentTarget.style.color = isCopied ? "var(--color-success)" : "var(--color-text-muted)"; }}
          >
            {isCopied ? <Check size={14} /> : <Link2 size={14} />}
          </button>
          <button onClick={onDelete}
            className="w-8 h-8 rounded-[var(--radius-md)] flex items-center justify-center transition-colors cursor-pointer"
            style={{ color: "var(--color-text-subtle)" }} aria-label="Delete"
            onMouseEnter={e => { e.currentTarget.style.background = "var(--color-danger-bg)"; e.currentTarget.style.color = "var(--color-danger)"; }}
            onMouseLeave={e => { e.currentTarget.style.background = "transparent"; e.currentTarget.style.color = "var(--color-text-subtle)"; }}
          >
            <Trash2 size={14} />
          </button>
        </div>
      </div>
    </div>
  );
}

// ── Types ─────────────────────────────────────────────────────────────────────
type QuestionType = "mcq" | "fib";

type ModalState = null | "pick-type";

interface SectionDetail {
  section:   PracticeSection;
  module:    PracticeModule | null;
  questions: PracticeQuestion[];
}

// ── Page ──────────────────────────────────────────────────────────────────────
export default function PracticeSectionPage() {
  const { section_id } = useParams<{ section_id: string }>();
  const router = useRouter();
  const toast  = useToast();
  const { copy: copyLink, copiedId } = useCopyLink();

  const [detail,        setDetail]        = useState<SectionDetail | null>(null);
  const [loading,       setLoading]       = useState(true);
  const [modal,         setModal]         = useState<ModalState>(null);
  const [creatingType,  setCreatingType]  = useState<QuestionType | null>(null);
  const [publishing,    setPublishing]    = useState<string | null>(null);
  const [deleteTarget,  setDeleteTarget]  = useState<PracticeQuestion | null>(null);
  const [deleting,      setDeleting]      = useState(false);
  // ── Filter / search state ──────────────────────────────────────────────────
  const [search,      setSearch]      = useState("");
  const [typeFilter,  setTypeFilter]  = useState<"all" | "mcq" | "fib">("all");

  // ── Load ───────────────────────────────────────────────────────────────────
  useEffect(() => {
    api.get(`/admin/practice/sections/${section_id}/`)
      .then(res => setDetail(res.data.data))
      .catch(() => toast.error("Failed to load section."))
      .finally(() => setLoading(false));
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [section_id]);

  // ── Create question (no title input — number auto-assigned) ───────────────
  async function handleCreateQuestion(questionType: QuestionType) {
    setCreatingType(questionType);
    try {
      const res = await api.post<ApiSuccess<PracticeQuestion>>(
        `/admin/practice/sections/${section_id}/questions/`,
        { question_type: questionType }
      );
      setDetail(prev => prev ? { ...prev, questions: [...prev.questions, res.data.data] } : prev);
      setModal(null);
      toast.success(`Question #${res.data.data.question_number} created.`);
    } catch (err) {
      toast.error(getErrorMessage(err));
    } finally {
      setCreatingType(null);
    }
  }

  // ── Toggle publish ─────────────────────────────────────────────────────────
  async function handleTogglePublish(item: PracticeQuestion) {
    setPublishing(item.id);
    try {
      const res = await api.patch<ApiSuccess<PracticeQuestion>>(
        `/admin/practice/questions/${item.id}/`, { is_published: !item.is_published }
      );
      setDetail(prev => prev ? {
        ...prev,
        questions: prev.questions.map(q => q.id === item.id ? res.data.data : q),
      } : prev);
    } catch (err) { toast.error(getErrorMessage(err)); }
    finally { setPublishing(null); }
  }

  // ── Delete ─────────────────────────────────────────────────────────────────
  async function handleDelete() {
    if (!deleteTarget) return;
    setDeleting(true);
    try {
      await api.delete(`/admin/practice/questions/${deleteTarget.id}/`);
      setDetail(prev => prev ? {
        ...prev,
        questions: prev.questions.filter(q => q.id !== deleteTarget.id),
      } : prev);
      setDeleteTarget(null);
      toast.success("Question deleted.");
    } catch (err) { toast.error(getErrorMessage(err)); }
    finally { setDeleting(false); }
  }

  const section      = detail?.section;
  const parentModule = detail?.module;
  const backHref     = parentModule ? `/admin/practice/${parentModule.id}` : "/admin/practice";

  // ── Derived filtered list ──────────────────────────────────────────────────
  const allQuestions = detail?.questions ?? [];
  const filteredQuestions = allQuestions.filter(q => {
    const matchesType   = typeFilter === "all" || q.question_type === typeFilter;
    const matchesSearch = search.trim() === "" || String(q.question_number).includes(search.trim());
    return matchesType && matchesSearch;
  });

  return (
    <AdminLayout>
      <PageWrapper className="max-w-5xl">

        <PageHeader
          title={section?.name ?? ""}
          titleSkeleton={loading ? <Skeleton className="h-8 w-52" /> : undefined}
          subtitle={!loading ? `${detail?.questions.length ?? 0} ${(detail?.questions.length ?? 0) === 1 ? "question" : "questions"}` : undefined}
          backHref={backHref}
          breadcrumb={
            <span>
              <span className="cursor-pointer hover:underline" onClick={() => router.push("/admin/practice")}>
                Practice
              </span>
              {parentModule && (
                <>
                  {" › "}
                  <span className="cursor-pointer hover:underline" onClick={() => router.push(`/admin/practice/${parentModule.id}`)}>
                    {parentModule.name}
                  </span>
                </>
              )}
            </span>
          }
          rightSlot={
            <Button variant="primary" onClick={() => setModal("pick-type")}>
              + Add Question
            </Button>
          }
        />

        {/* ── Search + Filter bar ─────────────────────────────────────────────── */}
        {!loading && allQuestions.length > 0 && (
          <div className="flex flex-wrap items-center gap-2 mb-5">
            {/* Search input */}
            <div className="relative flex-1" style={{ minWidth: 180, maxWidth: 260 }}>
              <Search
                size={13}
                className="absolute left-3 top-1/2 -translate-y-1/2 pointer-events-none"
                style={{ color: "var(--color-text-muted)" }}
              />
              <input
                type="text"
                placeholder="Search by number…"
                value={search}
                onChange={e => setSearch(e.target.value)}
                className="w-full pl-8 pr-3 py-1.5 text-sm rounded-[var(--radius-md)] outline-none transition-colors"
                style={{
                  background: "var(--color-surface-secondary)",
                  border: "1px solid var(--color-border)",
                  color: "var(--color-text)",
                }}
                onFocus={e => (e.currentTarget.style.borderColor = "var(--color-primary)")}
                onBlur={e => (e.currentTarget.style.borderColor = "var(--color-border)")}
              />
            </div>

            {/* Type filter pills */}
            <div className="flex items-center gap-1">
              {(["all", "mcq", "fib"] as const).map(t => (
                <button
                  key={t}
                  onClick={() => setTypeFilter(t)}
                  className="px-3 py-1.5 rounded-full text-xs font-semibold transition-all cursor-pointer"
                  style={typeFilter === t
                    ? { background: "var(--color-text)", color: "#fff", border: "1px solid transparent" }
                    : { background: "var(--color-surface-secondary)", color: "var(--color-text-subtle)", border: "1px solid var(--color-border)" }
                  }
                >
                  {t === "all" ? "All" : t.toUpperCase()}
                </button>
              ))}
            </div>
          </div>
        )}

        {/* ── Content ─────────────────────────────────────────────────────────── */}
        {loading ? (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {[1, 2, 3].map(i => <QuestionCardSkeleton key={i} />)}
          </div>
        ) : allQuestions.length === 0 ? (
          <EmptyState
            icon={ListChecks}
            title="No questions yet"
            subtitle="Add your first question to this section."
            action={{ label: "+ Add Question", onClick: () => setModal("pick-type") }}
          />
        ) : filteredQuestions.length === 0 ? (
          <div
            className="flex flex-col items-center justify-center py-14 rounded-[var(--radius-xl)] text-center"
            style={{ background: "var(--color-surface)", border: "1px solid var(--color-border)" }}
          >
            <Search size={22} className="mb-3" style={{ color: "var(--color-text-muted)" }} />
            <p className="text-sm font-semibold" style={{ color: "var(--color-text-muted)" }}>
              No questions match
            </p>
            <p className="text-xs mt-1" style={{ color: "var(--color-text-subtle)" }}>
              Try a different number or change the filter.
            </p>
          </div>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {filteredQuestions.map((q, i) => (
              <QuestionCard
                key={q.id}
                question={q}
                index={i}
                isPublished={q.is_published}
                publishing={publishing === q.id}
                isCopied={copiedId === `${typeof window !== "undefined" ? window.location.origin : ""}/students/practice/questions/${q.id}`}
                onNavigate={() => router.push(`/admin/practice/questions/${q.id}`)}
                onDelete={() => setDeleteTarget(q)}
                onTogglePublish={() => handleTogglePublish(q)}
                onCopyLink={() => {
                  copyLink(`${window.location.origin}/students/practice/questions/${q.id}`);
                  toast.success("Student link copied.");
                }}
              />
            ))}
          </div>
        )}

      </PageWrapper>

      {/* ── Type Picker Modal ─────────────────────────────────────────────────── */}
      <Modal isOpen={modal === "pick-type"} onClose={() => { if (!creatingType) setModal(null); }} title="Add Question" maxWidth="sm">
        <p className="text-sm mb-4" style={{ color: "var(--color-text-subtle)" }}>
          Choose the question format — a number will be assigned automatically.
        </p>
        <div className="grid grid-cols-2 gap-3">

          {/* MCQ */}
          <button
            onClick={() => handleCreateQuestion("mcq")}
            disabled={!!creatingType}
            className="flex flex-col items-center gap-3 p-5 rounded-[var(--radius-xl)] text-center cursor-pointer transition-all disabled:opacity-60"
            style={{ border: "2px solid var(--color-border)", background: "var(--color-surface-secondary)" }}
            onMouseEnter={e => { if (!creatingType) { e.currentTarget.style.borderColor = "#2563EB"; e.currentTarget.style.background = "#EFF6FF"; } }}
            onMouseLeave={e => { e.currentTarget.style.borderColor = "var(--color-border)"; e.currentTarget.style.background = "var(--color-surface-secondary)"; }}
          >
            <div className="w-12 h-12 rounded-[var(--radius-lg)] flex items-center justify-center" style={{ background: "#EFF6FF" }}>
              {creatingType === "mcq"
                ? <Loader2 size={22} style={{ color: "#2563EB" }} className="animate-spin" />
                : <ListChecks size={22} style={{ color: "#2563EB" }} />
              }
            </div>
            <div>
              <p className="text-sm font-semibold" style={{ color: "var(--color-text)" }}>MCQ</p>
              <p className="text-xs mt-0.5 leading-snug" style={{ color: "var(--color-text-subtle)" }}>Multiple Choice</p>
            </div>
          </button>

          {/* FIB */}
          <button
            onClick={() => handleCreateQuestion("fib")}
            disabled={!!creatingType}
            className="flex flex-col items-center gap-3 p-5 rounded-[var(--radius-xl)] text-center cursor-pointer transition-all disabled:opacity-60"
            style={{ border: "2px solid var(--color-border)", background: "var(--color-surface-secondary)" }}
            onMouseEnter={e => { if (!creatingType) { e.currentTarget.style.borderColor = "#9333EA"; e.currentTarget.style.background = "#FDF4FF"; } }}
            onMouseLeave={e => { e.currentTarget.style.borderColor = "var(--color-border)"; e.currentTarget.style.background = "var(--color-surface-secondary)"; }}
          >
            <div className="w-12 h-12 rounded-[var(--radius-lg)] flex items-center justify-center" style={{ background: "#FDF4FF" }}>
              {creatingType === "fib"
                ? <Loader2 size={22} style={{ color: "#9333EA" }} className="animate-spin" />
                : <AlignLeft size={22} style={{ color: "#9333EA" }} />
              }
            </div>
            <div>
              <p className="text-sm font-semibold" style={{ color: "var(--color-text)" }}>FIB</p>
              <p className="text-xs mt-0.5 leading-snug" style={{ color: "var(--color-text-subtle)" }}>Fill in the Blank</p>
            </div>
          </button>

        </div>
        <div className="flex justify-end mt-5">
          <Button variant="secondary" onClick={() => setModal(null)} disabled={!!creatingType}>
            Cancel
          </Button>
        </div>
      </Modal>

      {/* ── Delete confirm ─────────────────────────────────────────────────────── */}
      <ConfirmDialog
        isOpen={!!deleteTarget}
        onClose={() => setDeleteTarget(null)}
        onConfirm={handleDelete}
        title="Delete question?"
        message={`Question #${deleteTarget?.question_number} will be permanently removed. This cannot be undone.`}
        confirmLabel="Delete"
        confirmVariant="danger"
        loading={deleting}
      />
    </AdminLayout>
  );
}
