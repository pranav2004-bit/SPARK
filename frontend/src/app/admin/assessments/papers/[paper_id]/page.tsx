"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import {
  HelpCircle, Pencil, Trash2, ChevronRight, ScrollText,
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
import type { QuestionPaper, QuestionSet, ApiSuccess } from "@/types";

// Small icon button with a black/white hover tooltip showing its label —
// Edit/Delete here are icon-only with no visible text, so on-hover
// identification matters. Mirrors the same component in the sibling
// sets/[set_id] page.
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

interface PaperDetail {
  paper: QuestionPaper;
  sets:  QuestionSet[];
}

export default function AdminAssessmentPaperPage() {
  const { paper_id } = useParams<{ paper_id: string }>();
  const router = useRouter();
  const toast  = useToast();

  const [detail,  setDetail]  = useState<PaperDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [modal,   setModal]   = useState<null | "add" | { mode: "edit"; item: QuestionSet }>(null);
  const [modalLabel, setModalLabel] = useState("");
  const [modalError, setModalError] = useState("");
  const [saving,     setSaving]     = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<{ id: string; label: string } | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [showSetExitConfirm, setShowSetExitConfirm] = useState(false);

  const [rulesOpen, setRulesOpen] = useState(false);
  const [rulesText, setRulesText] = useState("");
  const [rulesSaving, setRulesSaving] = useState(false);

  const load = () => {
    api.get<ApiSuccess<PaperDetail>>(`/assessments/admin/papers/${paper_id}/`)
      .then(res => setDetail(res.data.data))
      .catch(err => { toast.error(getErrorMessage(err)); router.push("/admin/assessments/papers"); })
      .finally(() => setLoading(false));
  };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(load, [paper_id]);

  function openModal(state: NonNullable<typeof modal>) {
    setModalLabel(typeof state === "object" ? state.item.label : "");
    setModalError(""); setModal(state);
  }
  function closeModal() { setModal(null); setModalLabel(""); setModalError(""); setShowSetExitConfirm(false); }

  // Original label for the set being edited ("" while adding, since there's
  // nothing to compare against) — lets the header Save button light up only
  // once the field actually differs from what's saved, instead of being
  // clickable (and closeable-without-warning) the whole time.
  const originalSetLabel = modal !== null && typeof modal === "object" ? modal.item.label : "";
  const isSetLabelDirty = modalLabel.trim() !== originalSetLabel.trim();
  const canSubmitSetModal = !!modalLabel.trim() && isSetLabelDirty;

  function handleAttemptCloseSetModal() {
    if (isSetLabelDirty) setShowSetExitConfirm(true);
    else closeModal();
  }

  async function handleSaveChangesFromExitConfirm() {
    setShowSetExitConfirm(false);
    await handleModalSubmit();
  }

  async function handleModalSubmit() {
    const label = modalLabel.trim();
    if (!label) { setModalError("Set label is required."); return; }
    setSaving(true); setModalError("");
    try {
      if (modal === "add") {
        const res = await api.post<ApiSuccess<QuestionSet>>(`/assessments/admin/papers/${paper_id}/sets/`, { label });
        setDetail(prev => prev ? { ...prev, sets: [...prev.sets, res.data.data] } : prev);
        toast.success("Set created.");
      } else if (modal !== null && typeof modal === "object" && modal.mode === "edit") {
        const res = await api.patch<ApiSuccess<QuestionSet>>(`/assessments/admin/sets/${modal.item.id}/`, { label });
        setDetail(prev => prev ? { ...prev, sets: prev.sets.map(s => s.id === modal.item.id ? res.data.data : s) } : prev);
        toast.success("Set updated.");
      }
      closeModal();
    } catch (err) { setModalError(getErrorMessage(err)); }
    finally { setSaving(false); }
  }

  function openRules() {
    setRulesText(detail?.paper.instructions ?? "");
    setRulesOpen(true);
  }

  async function handleSaveRules() {
    setRulesSaving(true);
    try {
      const res = await api.patch<ApiSuccess<QuestionPaper>>(
        `/assessments/admin/papers/${paper_id}/instructions/`, { instructions: rulesText },
      );
      setDetail(prev => prev ? { ...prev, paper: res.data.data } : prev);
      toast.success("Rules saved.");
      setRulesOpen(false);
    } catch (err) { toast.error(getErrorMessage(err)); }
    finally { setRulesSaving(false); }
  }

  async function handleDelete() {
    if (!deleteTarget) return;
    setDeleting(true);
    try {
      await api.delete(`/assessments/admin/sets/${deleteTarget.id}/`);
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
          subtitle="Sets are equivalent alternates distributed among students for anti-cheating — keep total marks equal across sets."
          backHref="/admin/assessments/papers"
          breadcrumb={
            <span className="cursor-pointer hover:underline" onClick={() => router.push("/admin/assessments/papers")}>
              Assessments
            </span>
          }
          rightSlot={
            <div className="flex items-center gap-2">
              <Button variant="secondary" leftIcon={<ScrollText size={14} />} onClick={openRules}>
                Rules
              </Button>
              <Button variant="primary" onClick={() => openModal("add")}>+ Add Set</Button>
            </div>
          }
        />

        {loading ? (
          <div className="grid gap-4" style={{ gridTemplateColumns: "repeat(auto-fill, minmax(260px, 1fr))" }}>
            {[1, 2, 3].map(i => <ResourceItemCardSkeleton key={i} />)}
          </div>
        ) : isEmpty ? (
          <EmptyState
            icon={HelpCircle}
            title="No sets yet"
            subtitle="Add at least one set (e.g. Set A) to start authoring questions."
          />
        ) : (
          // auto-fill + minmax, not a fixed column count — a row with few
          // cards keeps each card at its own natural width instead of
          // stretching to fill its grid cell (same fix as the Section
          // cards one level down, sets/[set_id]/page.tsx).
          <div className="grid gap-4" style={{ gridTemplateColumns: "repeat(auto-fill, minmax(260px, 1fr))" }}>
            {detail!.sets.map((s) => {
              return (
                <div
                  key={s.id}
                  className="flex items-center justify-between gap-3 p-4 rounded-[var(--radius-xl)] cursor-pointer transition-shadow duration-150 hover:shadow-[var(--shadow-md)] group/card"
                  style={{ background: "var(--color-surface)", border: "1px solid var(--color-border)", boxShadow: "var(--shadow-sm)" }}
                  onClick={() => router.push(`/admin/assessments/papers/${paper_id}/sets/${s.id}`)}
                >
                  <div className="min-w-0 flex-1">
                    <p className="text-base font-semibold leading-snug truncate" style={{ color: "var(--color-text)" }}>{s.label}</p>
                    <p className="text-sm mt-1 flex items-center gap-2" style={{ color: "var(--color-text-subtle)" }}>
                      <span>{s.question_count} question{s.question_count === 1 ? "" : "s"}</span>
                      <span>·</span>
                      <span>{s.total_marks} mark{s.total_marks === 1 ? "" : "s"}</span>
                    </p>
                  </div>
                  <div className="flex items-center gap-0.5 shrink-0">
                    <ChevronRight size={16} style={{ color: "var(--color-text-subtle)" }}
                      className="transition-transform duration-150 group-hover/card:translate-x-0.5" />
                    <span className="w-px h-5 mx-1" style={{ background: "var(--color-border)" }} />
                    <IconActionButton label="Edit" color="#2563EB"
                      onClick={e => { e.stopPropagation(); openModal({ mode: "edit", item: s }); }}>
                      <Pencil size={14} />
                    </IconActionButton>
                    <IconActionButton label="Delete" color="var(--color-danger)"
                      onClick={e => { e.stopPropagation(); setDeleteTarget({ id: s.id, label: s.label }); }}>
                      <Trash2 size={14} />
                    </IconActionButton>
                  </div>
                </div>
              );
            })}
          </div>
        )}

      </PageWrapper>

      <Modal isOpen={rulesOpen} onClose={() => setRulesOpen(false)} title="Exam Rules" maxWidth="lg">
        <p className="text-xs mb-3" style={{ color: "var(--color-text-subtle)" }}>
          Shown to students before they can start this exam — they must tick "I have read all the instructions" to proceed.
        </p>
        <textarea
          autoFocus
          rows={10}
          placeholder="Paste the exam instructions here…"
          value={rulesText}
          onChange={e => setRulesText(e.target.value)}
          className="w-full text-sm rounded-[var(--radius-md)] px-3.5 py-2.5 outline-none leading-relaxed resize-y border bg-white text-[var(--color-text)] placeholder:text-[var(--color-text-subtle)] border-[var(--color-border)] hover:border-[var(--color-border-strong)] focus:ring-2 focus:ring-[var(--color-accent)]"
        />
        <div className="flex justify-end gap-3 mt-5">
          <Button variant="secondary" type="button" onClick={() => setRulesOpen(false)}>Cancel</Button>
          <Button type="button" loading={rulesSaving} onClick={handleSaveRules}>Save</Button>
        </div>
      </Modal>

      <Modal
        isOpen={modal !== null}
        onClose={handleAttemptCloseSetModal}
        title={modal === "add" ? "New Set" : "Edit Set"}
        maxWidth="sm"
        headerAction={
          <Button
            size="sm"
            loading={saving}
            disabled={!canSubmitSetModal}
            onClick={handleModalSubmit}
          >
            {modal === "add" ? "Create" : "Save changes"}
          </Button>
        }
      >
        <form onSubmit={e => { e.preventDefault(); handleModalSubmit(); }}>
          <Input
            label="Set label"
            placeholder="e.g. Set A"
            autoFocus
            value={modalLabel}
            onChange={e => { setModalLabel(e.target.value); setModalError(""); }}
            error={modalError}
          />
        </form>
      </Modal>

      {/* Closing (X / backdrop) with an unsaved label change — asks before
          the edit is silently lost, same shape as the question editor's
          exit-confirm. */}
      <ConfirmDialog
        isOpen={showSetExitConfirm}
        onClose={() => setShowSetExitConfirm(false)}
        onConfirm={handleSaveChangesFromExitConfirm}
        title="Unsaved changes"
        message="You've changed this set's label but haven't saved it yet. Leaving now will discard the change."
        confirmLabel={modal === "add" ? "Create" : "Save changes"}
        confirmVariant="primary"
        confirmDisabled={!canSubmitSetModal}
        loading={saving}
      />

      <ConfirmDialog
        isOpen={!!deleteTarget}
        onClose={() => setDeleteTarget(null)}
        onConfirm={handleDelete}
        title="Delete set?"
        message={`"${deleteTarget?.label}" and all its questions will be permanently removed. This cannot be undone.`}
        confirmLabel="Delete"
        confirmVariant="danger"
        loading={deleting}
      />
    </AdminLayout>
  );
}
