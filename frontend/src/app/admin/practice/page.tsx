"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import {
  Layers, FolderOpen, HelpCircle, AlertTriangle,
  Pencil, Trash2, Globe, EyeOff, Loader2, ChevronRight, Link2, Check,
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
import { useCopyLink } from "@/hooks/useCopyLink";
import api, { getErrorMessage } from "@/lib/api";
import type { PracticeModule, PracticeSection, ApiSuccess } from "@/types";

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

// ── Shared card ───────────────────────────────────────────────────────────────
interface PracticeCardProps {
  name: string;
  type: "module" | "section";
  index: number;
  isPublished: boolean;
  publishing: boolean;
  isCopied: boolean;
  onNavigate: () => void;
  onEdit: () => void;
  onDelete: () => void;
  onTogglePublish: () => void;
  onCopyLink: () => void;
}

function PracticeCard({
  name, type, index, isPublished, publishing, isCopied,
  onNavigate, onEdit, onDelete, onTogglePublish, onCopyLink,
}: PracticeCardProps) {
  const { bg, color } = palette(index);
  const Icon = type === "module" ? Layers : FolderOpen;

  return (
    <div
      className="rounded-[var(--radius-xl)] overflow-hidden transition-shadow duration-150 hover:shadow-[var(--shadow-md)]"
      style={{
        background: "var(--color-surface)",
        border: "1px solid var(--color-border)",
        boxShadow: "var(--shadow-sm)",
      }}
    >
      {/* Clickable body */}
      <button onClick={onNavigate} className="w-full text-left px-5 pt-5 pb-4 group cursor-pointer">
        <div className="flex items-start justify-between gap-3">
          <div
            className="w-11 h-11 rounded-[var(--radius-lg)] flex items-center justify-center shrink-0"
            style={{ background: bg }}
          >
            <Icon size={20} style={{ color }} />
          </div>
          <ChevronRight
            size={16}
            style={{ color: "var(--color-text-subtle)", marginTop: 2, flexShrink: 0 }}
            className="transition-transform duration-150 group-hover:translate-x-0.5"
          />
        </div>
        <div className="mt-3">
          <p className="text-[15px] font-semibold leading-snug" style={{ color: "var(--color-text)" }}>
            {name}
          </p>
          <p className="text-xs mt-1" style={{ color: "var(--color-text-subtle)" }}>
            {type === "module" ? "Module" : "Section"}
          </p>
        </div>
      </button>

      {/* Footer */}
      <div
        className="flex items-center justify-between px-4 py-3 gap-2"
        style={{ borderTop: "1px solid var(--color-border)" }}
      >
        {/* Publish toggle */}
        <button
          onClick={onTogglePublish}
          disabled={publishing}
          className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-semibold transition-all disabled:opacity-60 cursor-pointer"
          style={
            isPublished
              ? { background: "var(--color-success-bg)", color: "var(--color-success)", border: "1px solid rgba(22,163,74,0.2)" }
              : { background: "var(--color-surface-secondary)", color: "var(--color-text-subtle)", border: "1px solid var(--color-border)" }
          }
        >
          {publishing ? <Loader2 size={11} className="animate-spin" />
            : isPublished ? <><Globe size={11} /> Published</>
            : <><EyeOff size={11} /> Unpublished</>
          }
        </button>

        {/* Action icons */}
        <div className="flex items-center gap-1">
          <button
            onClick={onCopyLink}
            className="w-8 h-8 rounded-[var(--radius-md)] flex items-center justify-center transition-colors cursor-pointer"
            style={{ color: isCopied ? "var(--color-success)" : "var(--color-text-muted)" }}
            title="Copy student link"
            onMouseEnter={e => {
              e.currentTarget.style.background = isCopied ? "var(--color-success-bg)" : "var(--color-surface-hover)";
              if (!isCopied) e.currentTarget.style.color = "var(--color-text)";
            }}
            onMouseLeave={e => {
              e.currentTarget.style.background = "transparent";
              e.currentTarget.style.color = isCopied ? "var(--color-success)" : "var(--color-text-muted)";
            }}
          >
            {isCopied ? <Check size={14} /> : <Link2 size={14} />}
          </button>
          <button
            onClick={onEdit}
            className="w-8 h-8 rounded-[var(--radius-md)] flex items-center justify-center transition-colors cursor-pointer"
            style={{ color: "var(--color-text-subtle)" }}
            aria-label="Edit"
            onMouseEnter={e => { e.currentTarget.style.background = "var(--color-surface-hover)"; e.currentTarget.style.color = "var(--color-text)"; }}
            onMouseLeave={e => { e.currentTarget.style.background = "transparent"; e.currentTarget.style.color = "var(--color-text-subtle)"; }}
          >
            <Pencil size={14} />
          </button>
          <button
            onClick={onDelete}
            className="w-8 h-8 rounded-[var(--radius-md)] flex items-center justify-center transition-colors cursor-pointer"
            style={{ color: "var(--color-text-subtle)" }}
            aria-label="Delete"
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

// ── Modal state ───────────────────────────────────────────────────────────────
type ModalState =
  | null
  | "add-module"
  | "add-section"
  | { mode: "edit-module";  item: PracticeModule }
  | { mode: "edit-section"; item: PracticeSection };

// ── Page ──────────────────────────────────────────────────────────────────────
export default function AdminPracticePage() {
  const router = useRouter();
  const toast  = useToast();
  const { copy: copyLink, copiedId } = useCopyLink();

  const [modules,   setModules]   = useState<PracticeModule[]>([]);
  const [sections,  setSections]  = useState<PracticeSection[]>([]);
  const [loading,   setLoading]   = useState(true);
  const [loadError, setLoadError] = useState(false);
  const [modal,     setModal]     = useState<ModalState>(null);
  const [modalName, setModalName] = useState("");
  const [modalError, setModalError] = useState("");
  const [saving,    setSaving]    = useState(false);
  const [publishing, setPublishing] = useState<string | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<
    { id: string; name: string; type: "module" | "section" } | null
  >(null);
  const [deleting, setDeleting] = useState(false);

  // ── Load ───────────────────────────────────────────────────────────────────
  // On failure this must not just toast and fall through to "Nothing here
  // yet" below — that reads as "you have no modules/sections," not "this
  // failed to load."
  function load() {
    setLoading(true);
    setLoadError(false);
    api.get("/practice/")
      .then(res => {
        setModules(res.data.data.modules);
        setSections(res.data.data.sections);
      })
      .catch(() => { toast.error("Failed to load practice hub."); setLoadError(true); })
      .finally(() => setLoading(false));
  }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(load, []);

  // ── Modal helpers ──────────────────────────────────────────────────────────
  function openModal(state: NonNullable<ModalState>) {
    const initial = typeof state === "object" ? state.item.name : "";
    setModalName(initial);
    setModalError("");
    setModal(state);
  }
  function closeModal() { setModal(null); setModalName(""); setModalError(""); }

  const modalConfig =
    modal === null           ? null
    : modal === "add-module"   ? { title: "New Module",   label: "Module name",  placeholder: "e.g. Aptitude",       submitLabel: "Create" }
    : modal === "add-section"  ? { title: "New Section",  label: "Section name", placeholder: "e.g. Number Series",  submitLabel: "Create" }
    : modal.mode === "edit-module"  ? { title: "Edit Module",  label: "Module name",  placeholder: "Module name",   submitLabel: "Save changes" }
    : modal.mode === "edit-section" ? { title: "Edit Section", label: "Section name", placeholder: "Section name",  submitLabel: "Save changes" }
    : null;

  // ── Submit ─────────────────────────────────────────────────────────────────
  async function handleModalSubmit() {
    const name = modalName.trim();
    if (!name) { setModalError("Name is required."); return; }
    setSaving(true); setModalError("");
    try {
      if (modal === "add-module") {
        const res = await api.post<ApiSuccess<PracticeModule>>("/practice/modules/", { name });
        setModules(prev => [...prev, res.data.data]);
        toast.success("Module created.");
      } else if (modal === "add-section") {
        const res = await api.post<ApiSuccess<PracticeSection>>("/practice/sections/", { name });
        setSections(prev => [...prev, res.data.data]);
        toast.success("Section created.");
      } else if (modal !== null && typeof modal === "object" && modal.mode === "edit-module") {
        const res = await api.patch<ApiSuccess<PracticeModule>>(`/practice/modules/${modal.item.id}/`, { name });
        setModules(prev => prev.map(m => m.id === modal.item.id ? res.data.data : m));
        toast.success("Module updated.");
      } else if (modal !== null && typeof modal === "object" && modal.mode === "edit-section") {
        const res = await api.patch<ApiSuccess<PracticeSection>>(`/practice/sections/${modal.item.id}/`, { name });
        setSections(prev => prev.map(s => s.id === modal.item.id ? res.data.data : s));
        toast.success("Section updated.");
      }
      closeModal();
    } catch (err) { setModalError(getErrorMessage(err)); }
    finally { setSaving(false); }
  }

  // ── Toggle publish ─────────────────────────────────────────────────────────
  async function handleToggleModule(item: PracticeModule) {
    setPublishing(item.id);
    try {
      const res = await api.patch<ApiSuccess<PracticeModule>>(`/practice/modules/${item.id}/`, { is_published: !item.is_published });
      setModules(prev => prev.map(m => m.id === item.id ? res.data.data : m));
    } catch (err) { toast.error(getErrorMessage(err)); }
    finally { setPublishing(null); }
  }

  async function handleToggleSection(item: PracticeSection) {
    setPublishing(item.id);
    try {
      const res = await api.patch<ApiSuccess<PracticeSection>>(`/practice/sections/${item.id}/`, { is_published: !item.is_published });
      setSections(prev => prev.map(s => s.id === item.id ? res.data.data : s));
    } catch (err) { toast.error(getErrorMessage(err)); }
    finally { setPublishing(null); }
  }

  // ── Delete ─────────────────────────────────────────────────────────────────
  async function handleDelete() {
    if (!deleteTarget) return;
    setDeleting(true);
    try {
      if (deleteTarget.type === "module") {
        await api.delete(`/practice/modules/${deleteTarget.id}/`);
        setModules(prev => prev.filter(m => m.id !== deleteTarget.id));
      } else {
        await api.delete(`/practice/sections/${deleteTarget.id}/`);
        setSections(prev => prev.filter(s => s.id !== deleteTarget.id));
      }
      setDeleteTarget(null);
      toast.success(`${deleteTarget.type === "module" ? "Module" : "Section"} deleted.`);
    } catch (err) { toast.error(getErrorMessage(err)); }
    finally { setDeleting(false); }
  }

  const isEmpty = !loading && modules.length === 0 && sections.length === 0;

  return (
    <AdminLayout>
      <PageWrapper>

        <PageHeader
          title="Practice"
          subtitle="Manage modules and sections for the student practice hub."
          rightSlot={
            <div className="flex items-center gap-2">
              <Button variant="secondary" onClick={() => openModal("add-section")}>
                + Add Section
              </Button>
              <Button variant="primary" onClick={() => openModal("add-module")}>
                + Add Module
              </Button>
            </div>
          }
        />

        {/* ── Content ─────────────────────────────────────────────────────────── */}
        {loading ? (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {[1, 2, 3].map(i => <ResourceItemCardSkeleton key={i} />)}
          </div>
        ) : loadError ? (
          <EmptyState
            icon={AlertTriangle}
            title="Couldn't load the practice hub"
            subtitle="Something went wrong fetching this data — it may be temporary. Try again in a moment."
            action={{ label: "Retry", onClick: load }}
          />
        ) : isEmpty ? (
          <EmptyState
            icon={HelpCircle}
            title="Nothing here yet"
            subtitle="Add a module to group sections, or add a section directly to get started."
          />
        ) : (
          <>
            {/* Modules */}
            {modules.length > 0 && (
              <div className="mb-8">
                <p className="text-[11px] font-bold tracking-[0.12em] uppercase mb-3"
                  style={{ color: "var(--color-text-subtle)" }}>
                  Modules ({modules.length})
                </p>
                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
                  {modules.map((m, i) => (
                    <PracticeCard
                      key={m.id}
                      name={m.name}
                      type="module"
                      index={i}
                      isPublished={m.is_published}
                      publishing={publishing === m.id}
                      isCopied={copiedId === `${typeof window !== "undefined" ? window.location.origin : ""}/students/practice/${m.id}`}
                      onNavigate={() => router.push(`/admin/practice/${m.id}`)}
                      onEdit={() => openModal({ mode: "edit-module", item: m })}
                      onDelete={() => setDeleteTarget({ id: m.id, name: m.name, type: "module" })}
                      onTogglePublish={() => handleToggleModule(m)}
                      onCopyLink={() => {
                        copyLink(`${window.location.origin}/students/practice/${m.id}`);
                        toast.success("Student link copied.");
                      }}
                    />
                  ))}
                </div>
              </div>
            )}

            {/* Sections */}
            {sections.length > 0 && (
              <div>
                <p className="text-[11px] font-bold tracking-[0.12em] uppercase mb-3"
                  style={{ color: "var(--color-text-subtle)" }}>
                  Sections ({sections.length})
                </p>
                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
                  {sections.map((s, i) => (
                    <PracticeCard
                      key={s.id}
                      name={s.name}
                      type="section"
                      index={i}
                      isPublished={s.is_published}
                      publishing={publishing === s.id}
                      isCopied={copiedId === `${typeof window !== "undefined" ? window.location.origin : ""}/students/practice/sections/${s.id}`}
                      onNavigate={() => router.push(`/admin/practice/sections/${s.id}`)}
                      onEdit={() => openModal({ mode: "edit-section", item: s })}
                      onDelete={() => setDeleteTarget({ id: s.id, name: s.name, type: "section" })}
                      onTogglePublish={() => handleToggleSection(s)}
                      onCopyLink={() => {
                        copyLink(`${window.location.origin}/students/practice/sections/${s.id}`);
                        toast.success("Student link copied.");
                      }}
                    />
                  ))}
                </div>
              </div>
            )}
          </>
        )}

      </PageWrapper>

      {/* ── Modal ───────────────────────────────────────────────────────────────── */}
      <Modal isOpen={modal !== null} onClose={closeModal} title={modalConfig?.title ?? ""} maxWidth="sm">
        <form onSubmit={e => { e.preventDefault(); handleModalSubmit(); }}>
          <Input
            label={modalConfig?.label ?? "Name"}
            placeholder={modalConfig?.placeholder ?? ""}
            autoFocus
            value={modalName}
            onChange={e => { setModalName(e.target.value); setModalError(""); }}
            error={modalError}
          />
          <div className="flex justify-end gap-3 mt-5">
            <Button variant="secondary" type="button" onClick={closeModal}>Cancel</Button>
            <Button type="submit" loading={saving} disabled={!modalName.trim()}>
              {modalConfig?.submitLabel ?? "Create"}
            </Button>
          </div>
        </form>
      </Modal>

      {/* ── Delete confirm ───────────────────────────────────────────────────────── */}
      <ConfirmDialog
        isOpen={!!deleteTarget}
        onClose={() => setDeleteTarget(null)}
        onConfirm={handleDelete}
        title={`Delete ${deleteTarget?.type === "module" ? "module" : "section"}?`}
        message={`"${deleteTarget?.name}" will be permanently removed. This cannot be undone.`}
        confirmLabel="Delete"
        confirmVariant="danger"
        loading={deleting}
      />
    </AdminLayout>
  );
}
