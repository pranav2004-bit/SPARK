"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import {
  HelpCircle, AlertTriangle,
  Pencil, Trash2, ChevronRight,
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
import api, { getErrorMessage } from "@/lib/api";
import type { QuestionPaper, ApiSuccess, PaginatedResponse } from "@/types";

// Small icon button with a black/white hover tooltip showing its label —
// Edit/Delete here are icon-only with no visible text, so on-hover
// identification matters. Mirrors the same component in the sibling
// papers/[paper_id] and papers/[paper_id]/sets/[set_id] pages.
function IconActionButton({ label, onClick, color, children }: {
  label: string;
  onClick: (e: React.MouseEvent) => void;
  color: string;
  children: React.ReactNode;
}) {
  return (
    <div className="relative group">
      <button onClick={onClick} aria-label={label}
        className="w-8 h-8 rounded-[var(--radius-md)] flex items-center justify-center transition-colors cursor-pointer"
        style={{ color }}>
        {children}
      </button>
      <span
        className="pointer-events-none absolute left-1/2 -translate-x-1/2 bottom-full mb-1.5 whitespace-nowrap rounded px-2 py-1 text-xs font-medium opacity-0 group-hover:opacity-100 transition-opacity z-10"
        style={{ background: "#111827", color: "#fff" }}
      >
        {label}
      </span>
    </div>
  );
}

// ── Paper card ────────────────────────────────────────────────────────────────
// No more locked/"View only" state (changed 2026-11-14, user decision) —
// this list is now always just the papers this admin can actually open
// (their own, or every paper for a super_admin), since the backend
// (AdminPaperListCreateView.get) no longer sends anyone else's papers to
// a regular admin at all.
interface PaperCardProps {
  paper: QuestionPaper;
  onNavigate: () => void;
  onEdit: () => void;
  onDelete: () => void;
}

function PaperCard({ paper, onNavigate, onEdit, onDelete }: PaperCardProps) {
  const creatorLabel = paper.created_by_name || paper.created_by_email;

  return (
    <div
      className="flex items-center justify-between gap-3 p-4 rounded-[var(--radius-xl)] transition-shadow duration-150 group/card cursor-pointer hover:shadow-[var(--shadow-md)]"
      style={{ background: "var(--color-surface)", border: "1px solid var(--color-border)", boxShadow: "var(--shadow-sm)" }}
      onClick={onNavigate}
    >
      <div className="min-w-0 flex-1">
        <p className="text-base font-semibold leading-snug break-words" style={{ color: "var(--color-text)" }}>{paper.title}</p>
        <p className="text-sm mt-1" style={{ color: "var(--color-text-subtle)" }}>
          {paper.set_count} set{paper.set_count === 1 ? "" : "s"}
        </p>
        {/* Falls back to email when the creator hasn't set a display
            name — omitted entirely (not "Created by") if neither
            resolved, e.g. a transient auth-service lookup failure. Still
            shown even for an admin's own papers (not just a super_admin
            viewing someone else's) — harmless and consistent either way. */}
        {creatorLabel && (
          <p className="text-sm mt-0.5 truncate" style={{ color: "var(--color-text-subtle)" }}>
            Created by {creatorLabel}
          </p>
        )}
      </div>
      <div className="flex items-center gap-0.5 shrink-0">
        <ChevronRight size={16} style={{ color: "var(--color-text-subtle)" }}
          className="transition-transform duration-150 group-hover/card:translate-x-0.5" />
        <span className="w-px h-5 mx-1" style={{ background: "var(--color-border)" }} />
        <IconActionButton label="Edit" color="#2563EB"
          onClick={e => { e.stopPropagation(); onEdit(); }}>
          <Pencil size={14} />
        </IconActionButton>
        <IconActionButton label="Delete" color="var(--color-danger)"
          onClick={e => { e.stopPropagation(); onDelete(); }}>
          <Trash2 size={14} />
        </IconActionButton>
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
          <div className="grid gap-4" style={{ gridTemplateColumns: "repeat(auto-fill, minmax(260px, 1fr))" }}>
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
          <div className="grid gap-4" style={{ gridTemplateColumns: "repeat(auto-fill, minmax(260px, 1fr))" }}>
            {papers.map((p) => (
              <PaperCard
                key={p.id}
                paper={p}
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
