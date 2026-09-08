"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import {
  FileText, HelpCircle, AlertTriangle,
  Pencil, Trash2, ChevronRight, Layers, User, Lock,
} from "lucide-react";
import { AdminLayout } from "@/components/layout/AdminLayout";
import { PageWrapper } from "@/components/layout/PageWrapper";
import { PageHeader } from "@/components/layout/PageHeader";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Modal } from "@/components/ui/Modal";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import { EmptyState } from "@/components/ui/EmptyState";
import { ResourceItemCardSkeleton } from "@/components/ui/Skeleton";
import { useToast } from "@/components/ui/Toast";
import { useAuth } from "@/hooks/useAuth";
import api, { getErrorMessage } from "@/lib/api";
import type { QuestionPaper, ApiSuccess, PaginatedResponse } from "@/types";

// ── Card colour palette ───────────────────────────────────────────────────────
const PALETTE = [
  { bg: "#EFF6FF", color: "#2563EB" },
  { bg: "#F0FDF4", color: "#16A34A" },
  { bg: "#FDF4FF", color: "#9333EA" },
  { bg: "#FFF4E6", color: "#E8820C" },
  { bg: "#FFF1F2", color: "#E11D48" },
  { bg: "#F0FDFA", color: "#0D9488" },
];
const palette = (i: number) => PALETTE[i % PALETTE.length];

// ── Paper card ────────────────────────────────────────────────────────────────
interface PaperCardProps {
  paper: QuestionPaper;
  index: number;
  isOwner: boolean;
  onNavigate: () => void;
  onEdit: () => void;
  onDelete: () => void;
}

function PaperCard({ paper, index, isOwner, onNavigate, onEdit, onDelete }: PaperCardProps) {
  const { bg, color } = palette(index);
  const creatorLabel = paper.created_by_name || paper.created_by_email;

  return (
    <div
      className={["rounded-[var(--radius-xl)] overflow-hidden transition-shadow duration-150", isOwner ? "hover:shadow-[var(--shadow-md)]" : ""].join(" ")}
      style={{ background: "var(--color-surface)", border: "1px solid var(--color-border)", boxShadow: "var(--shadow-sm)" }}
    >
      <button
        onClick={onNavigate}
        disabled={!isOwner}
        title={isOwner ? undefined : `Created by ${creatorLabel || "another admin"} — you can't open this.`}
        className={["w-full text-left px-5 pt-5 pb-4 group", isOwner ? "cursor-pointer" : "cursor-not-allowed"].join(" ")}
      >
        <div className="flex items-start justify-between gap-3">
          <div className="w-11 h-11 rounded-[var(--radius-lg)] flex items-center justify-center shrink-0" style={{ background: bg }}>
            <FileText size={20} style={{ color }} />
          </div>
          {isOwner ? (
            <ChevronRight size={16} style={{ color: "var(--color-text-subtle)", marginTop: 2, flexShrink: 0 }}
              className="transition-transform duration-150 group-hover:translate-x-0.5" />
          ) : (
            <Lock size={14} style={{ color: "var(--color-text-subtle)", marginTop: 3, flexShrink: 0 }} />
          )}
        </div>
        <div className="mt-3">
          <p className="text-[15px] font-semibold leading-snug" style={{ color: "var(--color-text)" }}>{paper.title}</p>
          <p className="text-xs mt-1 flex items-center gap-1" style={{ color: "var(--color-text-subtle)" }}>
            <Layers size={11} /> {paper.set_count} set{paper.set_count === 1 ? "" : "s"}
          </p>
          {/* Falls back to email when the creator hasn't set a display
              name — omitted entirely (not "Created by") if neither
              resolved, e.g. a transient auth-service lookup failure. */}
          {creatorLabel && (
            <p className="text-xs mt-1 flex items-center gap-1 truncate" style={{ color: "var(--color-text-subtle)" }}>
              <User size={11} className="shrink-0" />
              <span className="truncate">Created by {creatorLabel}</span>
            </p>
          )}
        </div>
      </button>

      <div className="flex items-center justify-end px-4 py-3 gap-2" style={{ borderTop: "1px solid var(--color-border)" }}>
        {isOwner ? (
          <div className="flex items-center gap-1">
            <button onClick={onEdit}
              className="w-8 h-8 rounded-[var(--radius-md)] flex items-center justify-center transition-colors cursor-pointer"
              style={{ color: "var(--color-text-subtle)" }} aria-label="Edit"
              onMouseEnter={e => { e.currentTarget.style.background = "var(--color-surface-hover)"; e.currentTarget.style.color = "var(--color-text)"; }}
              onMouseLeave={e => { e.currentTarget.style.background = "transparent"; e.currentTarget.style.color = "var(--color-text-subtle)"; }}
            >
              <Pencil size={14} />
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
        ) : (
          <span className="inline-flex items-center gap-1.5 text-xs font-medium" style={{ color: "var(--color-text-subtle)" }}>
            <Lock size={11} /> View only
          </span>
        )}
      </div>
    </div>
  );
}

// ── Modal state ───────────────────────────────────────────────────────────────
type ModalState = null | "add" | { mode: "edit"; item: QuestionPaper };

// ── Page ──────────────────────────────────────────────────────────────────────
export default function AdminAssessmentPapersPage() {
  const router = useRouter();
  const toast  = useToast();
  const { user, isSuperAdmin } = useAuth();
  // This page is admin-only (route-guarded elsewhere), so `user` is always
  // AdminUser here in practice — StudentUser (the only AuthUser variant
  // without `.id`) narrowed out via the "id" in user check for TypeScript.
  const currentUserId = user && "id" in user ? user.id : undefined;

  const [papers,  setPapers]  = useState<QuestionPaper[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState(false);
  const [modal,   setModal]   = useState<ModalState>(null);
  const [modalTitle, setModalTitle] = useState("");
  const [modalDesc,  setModalDesc]  = useState("");
  const [modalError, setModalError] = useState("");
  const [saving,     setSaving]     = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<{ id: string; title: string } | null>(null);
  const [deleting, setDeleting] = useState(false);

  // ── Load ───────────────────────────────────────────────────────────────────
  // On failure this must not just toast and fall through to the normal
  // empty-state render below — "No question papers yet" reads as "you have
  // none," which is actively misleading when the real story is "this
  // couldn't load, try again" (e.g. a transient backend hiccup).
  function load() {
    setLoading(true);
    setLoadError(false);
    api.get<PaginatedResponse<QuestionPaper>>("/assessments/admin/papers/")
      .then(res => setPapers(res.data.results))
      .catch(() => { toast.error("Failed to load question papers."); setLoadError(true); })
      .finally(() => setLoading(false));
  }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(load, []);

  // ── Modal helpers ──────────────────────────────────────────────────────────
  function openModal(state: NonNullable<ModalState>) {
    setModalTitle(typeof state === "object" ? state.item.title : "");
    setModalDesc(typeof state === "object" ? state.item.description : "");
    setModalError(""); setModal(state);
  }
  function closeModal() { setModal(null); setModalTitle(""); setModalDesc(""); setModalError(""); }

  // ── Submit ─────────────────────────────────────────────────────────────────
  async function handleModalSubmit() {
    const title = modalTitle.trim();
    if (!title) { setModalError("Title is required."); return; }
    setSaving(true); setModalError("");
    try {
      if (modal === "add") {
        const res = await api.post<ApiSuccess<QuestionPaper>>("/assessments/admin/papers/", {
          title, description: modalDesc,
        });
        setPapers(prev => [res.data.data, ...prev]);
        toast.success("Question paper created.");
      } else if (modal !== null && typeof modal === "object" && modal.mode === "edit") {
        const res = await api.patch<ApiSuccess<QuestionPaper>>(`/assessments/admin/papers/${modal.item.id}/`, {
          title, description: modalDesc,
        });
        setPapers(prev => prev.map(p => p.id === modal.item.id ? res.data.data : p));
        toast.success("Question paper updated.");
      }
      closeModal();
    } catch (err) { setModalError(getErrorMessage(err)); }
    finally { setSaving(false); }
  }

  // ── Delete ─────────────────────────────────────────────────────────────────
  async function handleDelete() {
    if (!deleteTarget) return;
    setDeleting(true);
    try {
      await api.delete(`/assessments/admin/papers/${deleteTarget.id}/`);
      setPapers(prev => prev.filter(p => p.id !== deleteTarget.id));
      setDeleteTarget(null);
      toast.success("Question paper deleted.");
    } catch (err) { toast.error(getErrorMessage(err)); }
    finally { setDeleting(false); }
  }

  const isEmpty = !loading && papers.length === 0;

  return (
    <AdminLayout>
      <PageWrapper>

        <PageHeader
          title="Question Bank"
          subtitle="Author question papers for timed exams."
          backHref="/admin/assessments"
          rightSlot={
            <Button variant="primary" onClick={() => openModal("add")}>
              + New Paper
            </Button>
          }
        />

        {loading ? (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {[1, 2, 3].map(i => <ResourceItemCardSkeleton key={i} />)}
          </div>
        ) : loadError ? (
          <EmptyState
            icon={AlertTriangle}
            title="Couldn't load question papers"
            subtitle="Something went wrong fetching this data — it may be temporary. Try again in a moment."
            action={{ label: "Retry", onClick: load }}
          />
        ) : isEmpty ? (
          <EmptyState
            icon={HelpCircle}
            title="No question papers yet"
            subtitle="Create a paper to start authoring sets and questions."
          />
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {papers.map((p, i) => (
              <PaperCard
                key={p.id}
                paper={p}
                index={i}
                isOwner={isSuperAdmin || p.created_by === currentUserId}
                onNavigate={() => router.push(`/admin/assessments/papers/${p.id}`)}
                onEdit={() => openModal({ mode: "edit", item: p })}
                onDelete={() => setDeleteTarget({ id: p.id, title: p.title })}
              />
            ))}
          </div>
        )}

      </PageWrapper>

      {/* ── Modal ───────────────────────────────────────────────────────────────── */}
      <Modal isOpen={modal !== null} onClose={closeModal} title={modal === "add" ? "New Question Paper" : "Edit Question Paper"} maxWidth="sm">
        <form onSubmit={e => { e.preventDefault(); handleModalSubmit(); }}>
          <Input
            label="Title"
            placeholder="e.g. Aptitude Mock Test — Round 1"
            autoFocus
            value={modalTitle}
            onChange={e => { setModalTitle(e.target.value); setModalError(""); }}
            error={modalError}
          />
          <div className="mt-3">
            <label className="block text-xs font-semibold mb-1.5" style={{ color: "var(--color-text-muted)" }}>
              Description (optional)
            </label>
            <textarea
              value={modalDesc}
              onChange={e => setModalDesc(e.target.value)}
              rows={3}
              placeholder="Short internal note about this paper"
              className="w-full text-sm rounded-[var(--radius-md)] px-3.5 py-2.5 outline-none leading-relaxed"
              style={{ background: "var(--color-surface)", border: "1px solid var(--color-border)", color: "var(--color-text)" }}
            />
          </div>
          <div className="flex justify-end gap-3 mt-5">
            <Button variant="secondary" type="button" onClick={closeModal}>Cancel</Button>
            <Button type="submit" loading={saving} disabled={!modalTitle.trim()}>
              {modal === "add" ? "Create" : "Save changes"}
            </Button>
          </div>
        </form>
      </Modal>

      {/* ── Delete confirm ───────────────────────────────────────────────────────── */}
      <ConfirmDialog
        isOpen={!!deleteTarget}
        onClose={() => setDeleteTarget(null)}
        onConfirm={handleDelete}
        title="Delete question paper?"
        message={`"${deleteTarget?.title}" and all its sets, questions, and options will be permanently removed. This cannot be undone.`}
        confirmLabel="Delete"
        confirmVariant="danger"
        loading={deleting}
        requireTypedConfirmation="delete"
      />
    </AdminLayout>
  );
}
