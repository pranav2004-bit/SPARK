"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import {
  Layers, HelpCircle, Pencil, Trash2, ChevronRight, FileEdit, CheckCircle2,
} from "lucide-react";
import { AdminLayout } from "@/components/layout/AdminLayout";
import { PageWrapper } from "@/components/layout/PageWrapper";
import { PageHeader } from "@/components/layout/PageHeader";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Modal } from "@/components/ui/Modal";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import { EmptyState } from "@/components/ui/EmptyState";
import { ResourceItemCardSkeleton, Skeleton } from "@/components/ui/Skeleton";
import { useToast } from "@/components/ui/Toast";
import api, { getErrorMessage } from "@/lib/api";
import type { EssayPaper, EssaySet, ApiSuccess } from "@/types";

const PALETTE = [
  { bg: "#EFF6FF", color: "#2563EB" },
  { bg: "#F0FDF4", color: "#16A34A" },
  { bg: "#FDF4FF", color: "#9333EA" },
  { bg: "#FFF4E6", color: "#E8820C" },
];
const palette = (i: number) => PALETTE[i % PALETTE.length];

interface PaperDetail {
  paper: EssayPaper;
  sets:  EssaySet[];
}

export default function AdminEssayPaperPage() {
  const { paper_id } = useParams<{ paper_id: string }>();
  const router = useRouter();
  const toast  = useToast();

  const [detail,  setDetail]  = useState<PaperDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [modal,   setModal]   = useState<null | "add" | { mode: "edit"; item: EssaySet }>(null);
  const [modalLabel, setModalLabel] = useState("");
  const [modalError, setModalError] = useState("");
  const [saving,     setSaving]     = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<{ id: string; label: string } | null>(null);
  const [deleting, setDeleting] = useState(false);

  const load = () => {
    api.get<ApiSuccess<PaperDetail>>(`/essay/admin/papers/${paper_id}/`)
      .then(res => setDetail(res.data.data))
      .catch(err => { toast.error(getErrorMessage(err)); router.push("/admin/essay-writing/papers"); })
      .finally(() => setLoading(false));
  };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(load, [paper_id]);

  function openModal(state: NonNullable<typeof modal>) {
    setModalLabel(typeof state === "object" ? state.item.label : "");
    setModalError(""); setModal(state);
  }
  function closeModal() { setModal(null); setModalLabel(""); setModalError(""); }

  async function handleModalSubmit() {
    const label = modalLabel.trim();
    if (!label) { setModalError("Set label is required."); return; }
    setSaving(true); setModalError("");
    try {
      if (modal === "add") {
        const res = await api.post<ApiSuccess<EssaySet>>(`/essay/admin/papers/${paper_id}/sets/`, { label });
        setDetail(prev => prev ? { ...prev, sets: [...prev.sets, res.data.data] } : prev);
        toast.success("Set created.");
      } else if (modal !== null && typeof modal === "object" && modal.mode === "edit") {
        const res = await api.patch<ApiSuccess<EssaySet>>(`/essay/admin/sets/${modal.item.id}/`, { label });
        setDetail(prev => prev ? { ...prev, sets: prev.sets.map(s => s.id === modal.item.id ? res.data.data : s) } : prev);
        toast.success("Set updated.");
      }
      closeModal();
    } catch (err) { setModalError(getErrorMessage(err)); }
    finally { setSaving(false); }
  }

  async function handleDelete() {
    if (!deleteTarget) return;
    setDeleting(true);
    try {
      await api.delete(`/essay/admin/sets/${deleteTarget.id}/`);
      setDetail(prev => prev ? { ...prev, sets: prev.sets.filter(s => s.id !== deleteTarget.id) } : prev);
      setDeleteTarget(null);
      toast.success("Set deleted.");
    } catch (err) { toast.error(getErrorMessage(err)); }
    finally { setDeleting(false); }
  }

  const paper = detail?.paper;
  const isEmpty = !loading && (detail?.sets.length ?? 0) === 0;

  return (
    <AdminLayout>
      <PageWrapper>

        <PageHeader
          title={paper?.title ?? ""}
          titleSkeleton={loading ? <Skeleton className="h-8 w-52" /> : undefined}
          subtitle="Sets are equivalent alternates distributed among students for anti-cheating — each set holds exactly one writing prompt."
          backHref="/admin/essay-writing/papers"
          breadcrumb={
            <span className="cursor-pointer hover:underline" onClick={() => router.push("/admin/essay-writing/papers")}>
              Essay Writing
            </span>
          }
          rightSlot={
            <Button variant="primary" onClick={() => openModal("add")}>+ Add Set</Button>
          }
        />

        {loading ? (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {[1, 2, 3].map(i => <ResourceItemCardSkeleton key={i} />)}
          </div>
        ) : isEmpty ? (
          <EmptyState
            icon={HelpCircle}
            title="No sets yet"
            subtitle="Add at least one set (e.g. Set A) to start authoring its writing prompt."
          />
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {detail!.sets.map((s, i) => {
              const { bg, color } = palette(i);
              return (
                <div
                  key={s.id}
                  className="rounded-[var(--radius-xl)] overflow-hidden transition-shadow duration-150 hover:shadow-[var(--shadow-md)]"
                  style={{ background: "var(--color-surface)", border: "1px solid var(--color-border)", boxShadow: "var(--shadow-sm)" }}
                >
                  <button
                    onClick={() => router.push(`/admin/essay-writing/papers/${paper_id}/sets/${s.id}`)}
                    className="w-full text-left px-5 pt-5 pb-4 group cursor-pointer"
                  >
                    <div className="flex items-start justify-between gap-3">
                      <div className="w-11 h-11 rounded-[var(--radius-lg)] flex items-center justify-center shrink-0" style={{ background: bg }}>
                        <Layers size={20} style={{ color }} />
                      </div>
                      <ChevronRight size={16} style={{ color: "var(--color-text-subtle)", marginTop: 2, flexShrink: 0 }}
                        className="transition-transform duration-150 group-hover:translate-x-0.5" />
                    </div>
                    <div className="mt-3">
                      <p className="text-[15px] font-semibold leading-snug" style={{ color: "var(--color-text)" }}>{s.label}</p>
                      <p className="text-xs mt-1 flex items-center gap-1.5" style={{ color: "var(--color-text-subtle)" }}>
                        {s.has_question ? (
                          <><CheckCircle2 size={11} style={{ color: "#16A34A" }} /> Prompt authored</>
                        ) : (
                          <><FileEdit size={11} /> No prompt yet</>
                        )}
                      </p>
                    </div>
                  </button>

                  <div className="flex items-center justify-end px-4 py-3 gap-1" style={{ borderTop: "1px solid var(--color-border)" }}>
                    <button onClick={() => openModal({ mode: "edit", item: s })}
                      className="w-8 h-8 rounded-[var(--radius-md)] flex items-center justify-center transition-colors cursor-pointer"
                      style={{ color: "var(--color-text-subtle)" }} aria-label="Edit"
                      onMouseEnter={e => { e.currentTarget.style.background = "var(--color-surface-hover)"; e.currentTarget.style.color = "var(--color-text)"; }}
                      onMouseLeave={e => { e.currentTarget.style.background = "transparent"; e.currentTarget.style.color = "var(--color-text-subtle)"; }}
                    >
                      <Pencil size={14} />
                    </button>
                    <button onClick={() => setDeleteTarget({ id: s.id, label: s.label })}
                      className="w-8 h-8 rounded-[var(--radius-md)] flex items-center justify-center transition-colors cursor-pointer"
                      style={{ color: "var(--color-text-subtle)" }} aria-label="Delete"
                      onMouseEnter={e => { e.currentTarget.style.background = "var(--color-danger-bg)"; e.currentTarget.style.color = "var(--color-danger)"; }}
                      onMouseLeave={e => { e.currentTarget.style.background = "transparent"; e.currentTarget.style.color = "var(--color-text-subtle)"; }}
                    >
                      <Trash2 size={14} />
                    </button>
                  </div>
                </div>
              );
            })}
          </div>
        )}

      </PageWrapper>

      <Modal isOpen={modal !== null} onClose={closeModal} title={modal === "add" ? "New Set" : "Edit Set"} maxWidth="sm">
        <form onSubmit={e => { e.preventDefault(); handleModalSubmit(); }}>
          <Input
            label="Set label"
            placeholder="e.g. Set A"
            autoFocus
            value={modalLabel}
            onChange={e => { setModalLabel(e.target.value); setModalError(""); }}
            error={modalError}
          />
          <div className="flex justify-end gap-3 mt-5">
            <Button variant="secondary" type="button" onClick={closeModal}>Cancel</Button>
            <Button type="submit" loading={saving} disabled={!modalLabel.trim()}>
              {modal === "add" ? "Create" : "Save changes"}
            </Button>
          </div>
        </form>
      </Modal>

      <ConfirmDialog
        isOpen={!!deleteTarget}
        onClose={() => setDeleteTarget(null)}
        onConfirm={handleDelete}
        title="Delete set?"
        message={`"${deleteTarget?.label}" and its prompt (if authored) will be permanently removed. This cannot be undone.`}
        confirmLabel="Delete"
        confirmVariant="danger"
        loading={deleting}
      />
    </AdminLayout>
  );
}
