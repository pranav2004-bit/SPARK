"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { Layers, ChevronRight, ChevronUp, ChevronDown, Pencil, Trash2, ListChecks } from "lucide-react";
import { AdminLayout } from "@/components/layout/AdminLayout";
import { PageWrapper } from "@/components/layout/PageWrapper";
import { PageHeader } from "@/components/layout/PageHeader";
import { Button } from "@/components/ui/Button";
import { Modal } from "@/components/ui/Modal";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import { EmptyState } from "@/components/ui/EmptyState";
import { ResourceItemCardSkeleton, Skeleton } from "@/components/ui/Skeleton";
import { useToast } from "@/components/ui/Toast";
import api, { getErrorMessage } from "@/lib/api";
import type { QuestionPaper, QuestionSet, QuestionSection, ApiSuccess } from "@/types";

const T = {
  text: "var(--color-text)", muted: "var(--color-text-muted)", subtle: "var(--color-text-subtle)",
  border: "var(--color-border)",
};

interface SetSections {
  set:      QuestionSet;
  paper:    QuestionPaper;
  sections: QuestionSection[];
}

// ── Create/rename section modal ──────────────────────────────────────────────
function SectionFormModal({ isOpen, onClose, section, onCreated, onUpdated }: {
  isOpen: boolean; onClose: () => void;
  section: QuestionSection | null; // null = creating new
  onCreated: (s: QuestionSection) => void;
  onUpdated: (s: QuestionSection) => void;
}) {
  const { set_id } = useParams<{ set_id: string }>();
  const toast = useToast();
  const [title, setTitle] = useState("");
  const [saving, setSaving] = useState(false);

  useEffect(() => { if (isOpen) setTitle(section?.title ?? ""); }, [isOpen, section]);

  async function handleSave() {
    if (!title.trim()) return;
    setSaving(true);
    try {
      if (section) {
        const res = await api.patch<ApiSuccess<QuestionSection>>(`/assessments/admin/sections/${section.id}/`, {
          title: title.trim(),
        });
        onUpdated(res.data.data);
        toast.success("Section renamed.");
      } else {
        const res = await api.post<ApiSuccess<QuestionSection>>(`/assessments/admin/sets/${set_id}/sections/`, {
          title: title.trim(),
        });
        onCreated(res.data.data);
        toast.success("Section created.");
      }
      onClose();
    } catch (err) {
      toast.error(getErrorMessage(err));
    } finally {
      setSaving(false);
    }
  }

  return (
    <Modal
      isOpen={isOpen} onClose={onClose} title={section ? "Rename Section" : "New Section"} maxWidth="sm"
      headerAction={
        <Button variant="primary" size="sm" onClick={handleSave} loading={saving} disabled={!title.trim()}>
          {section ? "Save" : "Create Section"}
        </Button>
      }
    >
      <div>
        <label className="block text-xs font-semibold mb-1.5" style={{ color: T.muted }}>Section Name</label>
        <input
          autoFocus
          value={title}
          onChange={e => setTitle(e.target.value)}
          onKeyDown={e => { if (e.key === "Enter" && title.trim()) handleSave(); }}
          placeholder="e.g. Quantitative Aptitude"
          className="w-full text-sm rounded-[var(--radius-md)] px-3.5 py-2.5 outline-none"
          style={{ background: "var(--color-surface)", border: `1px solid ${T.border}`, color: T.text }}
        />
      </div>
    </Modal>
  );
}

// ── Main page ─────────────────────────────────────────────────────────────────
export default function AdminAssessmentSetSectionsPage() {
  const { paper_id, set_id } = useParams<{ paper_id: string; set_id: string }>();
  const router = useRouter();
  const toast  = useToast();

  const [detail,  setDetail]  = useState<SetSections | null>(null);
  const [loading, setLoading] = useState(true);
  const [formSection, setFormSection] = useState<QuestionSection | null | "new">(null);
  const [deleteTarget, setDeleteTarget] = useState<QuestionSection | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [reordering, setReordering] = useState(false);

  const load = () => {
    api.get<ApiSuccess<SetSections>>(`/assessments/admin/sets/${set_id}/sections/`)
      .then(res => setDetail(res.data.data))
      .catch(err => { toast.error(getErrorMessage(err)); router.push(`/admin/assessments/papers/${paper_id}`); })
      .finally(() => setLoading(false));
  };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(load, [set_id]);

  function handleCreated(s: QuestionSection) {
    setDetail(prev => prev ? { ...prev, sections: [...prev.sections, s] } : prev);
  }
  function handleUpdated(s: QuestionSection) {
    setDetail(prev => prev ? { ...prev, sections: prev.sections.map(x => x.id === s.id ? s : x) } : prev);
  }

  async function handleDelete() {
    if (!deleteTarget) return;
    setDeleting(true);
    try {
      await api.delete(`/assessments/admin/sections/${deleteTarget.id}/`);
      setDetail(prev => prev ? { ...prev, sections: prev.sections.filter(s => s.id !== deleteTarget.id) } : prev);
      setDeleteTarget(null);
      toast.success("Section deleted.");
    } catch (err) { toast.error(getErrorMessage(err)); }
    finally { setDeleting(false); }
  }

  // Swaps this section's order with its neighbor's — two PATCHes rather
  // than a dedicated bulk-reorder endpoint (mirrors admin/scroll's move(),
  // but sections don't have that endpoint, so this does it directly).
  async function handleMove(index: number, dir: -1 | 1) {
    if (!detail) return;
    const target = index + dir;
    if (target < 0 || target >= detail.sections.length) return;
    const a = detail.sections[index];
    const b = detail.sections[target];

    const reordered = [...detail.sections];
    [reordered[index], reordered[target]] = [reordered[target], reordered[index]];
    setDetail(prev => prev ? { ...prev, sections: reordered } : prev);

    setReordering(true);
    try {
      await Promise.all([
        api.patch(`/assessments/admin/sections/${a.id}/`, { order: b.order }),
        api.patch(`/assessments/admin/sections/${b.id}/`, { order: a.order }),
      ]);
      setDetail(prev => prev ? {
        ...prev,
        sections: prev.sections.map(s =>
          s.id === a.id ? { ...s, order: b.order } : s.id === b.id ? { ...s, order: a.order } : s
        ),
      } : prev);
    } catch (err) {
      toast.error(getErrorMessage(err));
      setDetail(prev => prev ? { ...prev, sections: detail.sections } : prev); // rollback
    } finally {
      setReordering(false);
    }
  }

  const set = detail?.set;
  const isEmpty = !loading && (detail?.sections.length ?? 0) === 0;

  return (
    <AdminLayout>
      <PageWrapper>

        <PageHeader
          title={set?.label ?? ""}
          titleSkeleton={loading ? <Skeleton className="h-8 w-40" /> : undefined}
          subtitle={detail ? `${detail.paper.title} — ${detail.sections.length} section${detail.sections.length === 1 ? "" : "s"}` : undefined}
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
            <Button variant="primary" onClick={() => setFormSection("new")}>+ Section</Button>
          }
        />

        {loading ? (
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            {[1, 2].map(i => <ResourceItemCardSkeleton key={i} />)}
          </div>
        ) : isEmpty ? (
          <EmptyState icon={Layers} title="No sections yet" subtitle="Create a section to start adding questions to this set."
            action={{ label: "+ Section", onClick: () => setFormSection("new") }} />
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            {detail!.sections.map((s, idx) => (
              <div key={s.id}
                className="flex items-start justify-between gap-3 p-4 rounded-[var(--radius-lg)] cursor-pointer transition-shadow hover:shadow-[var(--shadow-sm)]"
                style={{ background: "var(--color-surface)", border: "1px solid var(--color-border)" }}
                onClick={() => router.push(`/admin/assessments/papers/${paper_id}/sets/${set_id}/sections/${s.id}`)}
              >
                <div className="min-w-0 flex-1">
                  <div className="w-9 h-9 rounded-[var(--radius-md)] flex items-center justify-center mb-3"
                    style={{ background: "#EFF6FF" }}>
                    <ListChecks size={16} style={{ color: "#2563EB" }} />
                  </div>
                  <p className="text-sm font-semibold truncate" style={{ color: T.text }}>{s.title}</p>
                  <p className="text-xs mt-0.5" style={{ color: T.subtle }}>
                    {s.question_count} question{s.question_count === 1 ? "" : "s"}
                  </p>
                </div>
                <div className="flex flex-col items-center gap-1 shrink-0">
                  <div className="flex gap-0.5">
                    <button onClick={e => { e.stopPropagation(); handleMove(idx, -1); }}
                      disabled={idx === 0 || reordering}
                      className="w-7 h-7 rounded-[var(--radius-md)] flex items-center justify-center transition-colors disabled:opacity-30"
                      style={{ color: T.subtle }} aria-label="Move up">
                      <ChevronUp size={13} />
                    </button>
                    <button onClick={e => { e.stopPropagation(); handleMove(idx, 1); }}
                      disabled={idx === detail!.sections.length - 1 || reordering}
                      className="w-7 h-7 rounded-[var(--radius-md)] flex items-center justify-center transition-colors disabled:opacity-30"
                      style={{ color: T.subtle }} aria-label="Move down">
                      <ChevronDown size={13} />
                    </button>
                  </div>
                  <div className="flex gap-0.5">
                    <button onClick={e => { e.stopPropagation(); setFormSection(s); }}
                      className="w-7 h-7 rounded-[var(--radius-md)] flex items-center justify-center transition-colors"
                      style={{ color: T.subtle }} aria-label="Rename section">
                      <Pencil size={13} />
                    </button>
                    <button onClick={e => { e.stopPropagation(); setDeleteTarget(s); }}
                      className="w-7 h-7 rounded-[var(--radius-md)] flex items-center justify-center transition-colors"
                      style={{ color: T.subtle }} aria-label="Delete section">
                      <Trash2 size={13} />
                    </button>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}

      </PageWrapper>

      <SectionFormModal
        isOpen={formSection !== null}
        onClose={() => setFormSection(null)}
        section={formSection === "new" ? null : formSection}
        onCreated={handleCreated}
        onUpdated={handleUpdated}
      />

      <ConfirmDialog
        isOpen={!!deleteTarget}
        onClose={() => setDeleteTarget(null)}
        onConfirm={handleDelete}
        title="Delete section?"
        message={
          deleteTarget && deleteTarget.question_count > 0
            ? `"${deleteTarget.title}" and its ${deleteTarget.question_count} question${deleteTarget.question_count === 1 ? "" : "s"} will be permanently removed. This cannot be undone.`
            : `"${deleteTarget?.title}" will be permanently removed. This cannot be undone.`
        }
        confirmLabel="Delete"
        confirmVariant="danger"
        loading={deleting}
      />
    </AdminLayout>
  );
}
