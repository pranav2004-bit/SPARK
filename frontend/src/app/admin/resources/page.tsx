"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import {
  Building2, Layers, Pencil, Trash2, ChevronRight,
  Globe, EyeOff, Loader2, Check, Link2, ShieldCheck,
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
import type { ResourceModule, ApiSuccess } from "@/types";

// ── Decorative palette — intentional multi-colour variety for icon containers ─
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
const paletteFor = (i: number) => PALETTE[i % PALETTE.length];

// ── Module card ───────────────────────────────────────────────────────────────
interface ModuleCardProps {
  module:     ResourceModule;
  index:      number;
  isCopied:   boolean;
  publishing: boolean;
  onNavigate:      () => void;
  onEdit:          () => void;
  onDelete:        () => void;
  onTogglePublish: () => void;
  onCopyLink:      () => void;
}

function ModuleCard({
  module, index, isCopied, publishing,
  onNavigate, onEdit, onDelete, onTogglePublish, onCopyLink,
}: ModuleCardProps) {
  const { bg, color } = paletteFor(index);
  const Icon = module.is_system ? Building2 : Layers;
  const description = module.is_system
    ? "Company interview materials organised by company and section."
    : "Sub-modules, sections and uploaded resource materials.";

  return (
    <div
      className="rounded-[var(--radius-xl)] overflow-hidden transition-all duration-150 hover:shadow-[var(--shadow-md)]"
      style={{
        background: "var(--color-surface)",
        border:     "1px solid var(--color-border)",
        boxShadow:  "var(--shadow-sm)",
      }}
    >
      {/* Clickable body */}
      <button onClick={onNavigate} className="w-full text-left px-5 pt-4 pb-4 group cursor-pointer">
        <div className="flex items-start justify-between gap-3">
          <div
            className="w-10 h-10 rounded-[var(--radius-lg)] flex items-center justify-center shrink-0"
            style={{ background: bg }}
          >
            <Icon size={18} style={{ color }} />
          </div>
          <ChevronRight
            size={15}
            style={{ color: "var(--color-text-subtle)", marginTop: 1, flexShrink: 0 }}
            className="transition-transform duration-150 group-hover:translate-x-0.5"
          />
        </div>

        <div className="mt-3">
          <div className="flex items-center gap-1.5 flex-nowrap overflow-hidden">
            <p
              className="text-sm font-semibold leading-snug truncate"
              style={{ color: "var(--color-text)" }}
              title={module.name}
            >
              {module.name}
            </p>
            {module.is_system && (
              <span
                className="inline-flex items-center gap-1 shrink-0 text-[9px] font-bold tracking-[0.08em] uppercase px-1.5 py-0.5 rounded"
                style={{ background: "#EFF6FF", color: "#2563EB", border: "1px solid #BFDBFE", lineHeight: 1 }}
              >
                <ShieldCheck size={8} strokeWidth={2.5} />
                System
              </span>
            )}
          </div>
          <p className="text-xs mt-1 leading-relaxed line-clamp-2" style={{ color: "var(--color-text-subtle)" }}>
            {description}
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
            module.is_published
              ? { background: "var(--color-success-bg)", color: "var(--color-success)", border: "1px solid rgba(22,163,74,0.2)" }
              : { background: "var(--color-surface-secondary)", color: "var(--color-text-subtle)", border: "1px solid var(--color-border)" }
          }
        >
          {publishing
            ? <Loader2 size={11} className="animate-spin" />
            : module.is_published
              ? <><Globe size={11} /> Published</>
              : <><EyeOff size={11} /> Unpublished</>
          }
        </button>

        {/* Actions */}
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
            style={{ color: "var(--color-text-muted)" }}
            title="Edit name"
            onMouseEnter={e => { e.currentTarget.style.background = "var(--color-surface-hover)"; e.currentTarget.style.color = "var(--color-text)"; }}
            onMouseLeave={e => { e.currentTarget.style.background = "transparent"; e.currentTarget.style.color = "var(--color-text-muted)"; }}
          >
            <Pencil size={14} />
          </button>

          {/* System modules are protected — no delete */}
          {!module.is_system && (
            <button
              onClick={onDelete}
              className="w-8 h-8 rounded-[var(--radius-md)] flex items-center justify-center transition-colors cursor-pointer"
              style={{ color: "var(--color-text-muted)" }}
              title="Delete module"
              onMouseEnter={e => { e.currentTarget.style.background = "var(--color-danger-bg)"; e.currentTarget.style.color = "var(--color-danger)"; }}
              onMouseLeave={e => { e.currentTarget.style.background = "transparent"; e.currentTarget.style.color = "var(--color-text-muted)"; }}
            >
              <Trash2 size={14} />
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────
export default function AdminResourcesPage() {
  const router = useRouter();
  const toast  = useToast();
  const { copy: copyLink, copiedId } = useCopyLink();

  const [modules,    setModules]    = useState<ResourceModule[]>([]);
  const [loading,    setLoading]    = useState(true);
  const [modal,      setModal]      = useState<null | "add" | { mode: "edit"; module: ResourceModule }>(null);
  const [modalName,  setModalName]  = useState("");
  const [modalError, setModalError] = useState("");
  const [saving,     setSaving]     = useState(false);
  const [publishing, setPublishing] = useState<string | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<ResourceModule | null>(null);
  const [deleting,     setDeleting]     = useState(false);

  // ── Load ───────────────────────────────────────────────────────────────────
  useEffect(() => {
    api.get("/resources/modules/")
      .then(res => setModules(res.data.data))
      .catch(() => toast.error("Failed to load modules."))
      .finally(() => setLoading(false));
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // ── Modal helpers ──────────────────────────────────────────────────────────
  function openAdd() {
    setModalName(""); setModalError(""); setModal("add");
  }
  function openEdit(m: ResourceModule) {
    setModalName(m.name); setModalError(""); setModal({ mode: "edit", module: m });
  }
  function closeModal() {
    setModal(null); setModalName(""); setModalError("");
  }

  async function handleModalSubmit() {
    const name = modalName.trim();
    if (!name) { setModalError("Name is required."); return; }
    setSaving(true); setModalError("");
    try {
      if (modal === "add") {
        const res = await api.post<ApiSuccess<ResourceModule>>("/resources/modules/", { name });
        setModules(prev => [...prev, res.data.data]);
        toast.success("Module created.");
      } else if (modal !== null) {
        const res = await api.patch<ApiSuccess<ResourceModule>>(
          `/resources/modules/${modal.module.id}/`, { name }
        );
        setModules(prev => prev.map(m => m.id === modal.module.id ? res.data.data : m));
        toast.success("Module updated.");
      }
      closeModal();
    } catch (err) {
      setModalError(getErrorMessage(err));
    } finally {
      setSaving(false);
    }
  }

  // ── Toggle publish ─────────────────────────────────────────────────────────
  async function handleTogglePublish(module: ResourceModule) {
    setPublishing(module.id);
    try {
      const res = await api.patch<ApiSuccess<ResourceModule>>(
        `/resources/modules/${module.id}/`, { is_published: !module.is_published }
      );
      setModules(prev => prev.map(m => m.id === module.id ? res.data.data : m));
    } catch (err) {
      toast.error(getErrorMessage(err));
    } finally {
      setPublishing(null);
    }
  }

  // ── Delete ─────────────────────────────────────────────────────────────────
  async function handleDelete() {
    if (!deleteTarget) return;
    setDeleting(true);
    try {
      await api.delete(`/resources/modules/${deleteTarget.id}/`);
      setModules(prev => prev.filter(m => m.id !== deleteTarget.id));
      setDeleteTarget(null);
      toast.success("Module deleted.");
    } catch (err) {
      toast.error(getErrorMessage(err));
    } finally {
      setDeleting(false);
    }
  }

  const modalTitle       = modal === "add" ? "New Module"    : "Edit Module";
  const modalSubmitLabel = modal === "add" ? "Create module" : "Save changes";

  return (
    <AdminLayout>
      <PageWrapper className="max-w-5xl">

        <PageHeader
          title="Resources"
          subtitle="Manage all student-facing placement resource modules."
          rightSlot={
            <Button variant="primary" onClick={openAdd}>
              + Add Module
            </Button>
          }
        />

        {/* ── Grid ───────────────────────────────────────────────────────────── */}
        {loading ? (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {[1, 2].map(i => <ResourceItemCardSkeleton key={i} />)}
          </div>
        ) : modules.length === 0 ? (
          <EmptyState
            icon={Layers}
            title="No modules yet"
            subtitle="Create your first module to start organising resources."
            action={{ label: "+ Add Module", onClick: openAdd }}
          />
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {modules.map((module, i) => (
              <ModuleCard
                key={module.id}
                module={module}
                index={i}
                publishing={publishing === module.id}
                isCopied={copiedId === (module.is_system
                  ? `${typeof window !== "undefined" ? window.location.origin : ""}/students/companies`
                  : `${typeof window !== "undefined" ? window.location.origin : ""}/students/resources/${module.id}`
                )}
                onNavigate={() => module.is_system
                  ? router.push("/admin/companies")
                  : router.push(`/admin/resources/${module.id}`)
                }
                onEdit={() => openEdit(module)}
                onDelete={() => setDeleteTarget(module)}
                onTogglePublish={() => handleTogglePublish(module)}
                onCopyLink={() => {
                  const url = module.is_system
                    ? `${window.location.origin}/students/companies`
                    : `${window.location.origin}/students/resources/${module.id}`;
                  copyLink(url);
                  toast.success("Student link copied.");
                }}
              />
            ))}
          </div>
        )}

      </PageWrapper>

      {/* ── Add / Edit Modal ──────────────────────────────────────────────────── */}
      <Modal isOpen={modal !== null} onClose={closeModal} title={modalTitle} maxWidth="sm">
        <form onSubmit={e => { e.preventDefault(); handleModalSubmit(); }}>
          <Input
            label="Module name"
            placeholder="e.g. Interview Prep"
            autoFocus
            value={modalName}
            onChange={e => { setModalName(e.target.value); setModalError(""); }}
            error={modalError}
          />
          <div className="flex justify-end gap-3 mt-5">
            <Button variant="secondary" type="button" onClick={closeModal}>
              Cancel
            </Button>
            <Button type="submit" loading={saving} disabled={!modalName.trim()}>
              {modalSubmitLabel}
            </Button>
          </div>
        </form>
      </Modal>

      {/* ── Delete confirm ────────────────────────────────────────────────────── */}
      <ConfirmDialog
        isOpen={!!deleteTarget}
        onClose={() => setDeleteTarget(null)}
        onConfirm={handleDelete}
        title="Delete module?"
        message={`"${deleteTarget?.name}" will be permanently removed. This cannot be undone.`}
        confirmLabel="Delete"
        confirmVariant="danger"
        loading={deleting}
      />
    </AdminLayout>
  );
}
