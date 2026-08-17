"use client";

import { useEffect, useState, useCallback } from "react";
import { useRouter, useParams } from "next/navigation";
import { useForm } from "react-hook-form";
import { Layers, Pencil, Trash2, Upload, ChevronRight, Link2, Check, AlertTriangle } from "lucide-react";
import { useCopyLink } from "@/hooks/useCopyLink";
import { AdminLayout } from "@/components/layout/AdminLayout";
import { PageWrapper } from "@/components/layout/PageWrapper";
import { PageHeader } from "@/components/layout/PageHeader";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Modal } from "@/components/ui/Modal";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import { EmptyState } from "@/components/ui/EmptyState";
import { SectionCardSkeleton, Skeleton } from "@/components/ui/Skeleton";
import { useToast } from "@/components/ui/Toast";
import api, { getErrorMessage } from "@/lib/api";
import type { Company, Section, ApiSuccess, PaginatedResponse } from "@/types";

interface SectionForm {
  section_name: string;
}

export default function SectionsPage() {
  const router = useRouter();
  const { company_id } = useParams<{ company_id: string }>();
  const { error: toastError, success: toastSuccess } = useToast();
  const { copy: copyLink, copiedId } = useCopyLink();

  const [company, setCompany] = useState<Company | null>(null);
  const [sections, setSections] = useState<Section[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState(false);
  const [editSection, setEditSection] = useState<Section | null>(null);
  const [deleteSection, setDeleteSection] = useState<Section | null>(null);
  const [showAdd, setShowAdd] = useState(false);
  const [modalLoading, setModalLoading] = useState(false);
  const [deleteLoading, setDeleteLoading] = useState(false);

  const {
    register,
    handleSubmit,
    reset,
    setError,
    formState: { errors },
  } = useForm<SectionForm>();

  const fetchSections = useCallback(async () => {
    setLoading(true);
    setLoadError(false);
    try {
      const [companyRes, sectionsRes] = await Promise.all([
        api.get<ApiSuccess<Company>>(`/resources/companies/${company_id}/`),
        api.get<PaginatedResponse<Section>>(
          `/resources/companies/${company_id}/sections/`
        ),
      ]);
      setCompany(companyRes.data.data);
      setSections(sectionsRes.data.results);
    } catch (err) {
      toastError(getErrorMessage(err));
      setLoadError(true);
    } finally {
      setLoading(false);
    }
  }, [company_id, toastError]);

  useEffect(() => {
    fetchSections();
  }, [fetchSections]);

  function openAdd() {
    reset({ section_name: "" });
    setShowAdd(true);
  }

  function openEdit(s: Section) {
    reset({ section_name: s.section_name });
    setEditSection(s);
  }

  function closeModal() {
    setShowAdd(false);
    setEditSection(null);
    reset();
  }

  async function onSubmit(data: SectionForm) {
    setModalLoading(true);
    try {
      if (editSection) {
        const res = await api.patch<ApiSuccess<Section>>(
          `/resources/companies/${company_id}/sections/${editSection.id}/`,
          data
        );
        setSections((prev) =>
          prev.map((s) => (s.id === editSection.id ? res.data.data : s))
        );
        toastSuccess("Section updated.");
      } else {
        const res = await api.post<ApiSuccess<Section>>(
          `/resources/companies/${company_id}/sections/`,
          data
        );
        setSections((prev) => [...prev, res.data.data]);
        toastSuccess("Section created.");
      }
      closeModal();
    } catch (err) {
      const msg = getErrorMessage(err);
      setError("section_name", {
        message:
          msg.toLowerCase().includes("unique") ||
          msg.toLowerCase().includes("already")
            ? "A section with this name already exists in this company."
            : msg,
      });
    } finally {
      setModalLoading(false);
    }
  }

  async function handleDelete() {
    if (!deleteSection) return;
    setDeleteLoading(true);
    try {
      await api.delete(
        `/resources/companies/${company_id}/sections/${deleteSection.id}/`
      );
      setSections((prev) => prev.filter((s) => s.id !== deleteSection.id));
      toastSuccess(`Section "${deleteSection.section_name}" deleted.`);
      setDeleteSection(null);
    } catch (err) {
      toastError(getErrorMessage(err));
      setDeleteSection(null);
    } finally {
      setDeleteLoading(false);
    }
  }

  const navigateToSection = (section: Section) =>
    router.push(`/admin/companies/${company_id}/${section.id}`);

  return (
    <AdminLayout>
      <PageWrapper>
        <PageHeader
          title={company?.company_name ?? ""}
          titleSkeleton={loading ? <Skeleton className="h-7 w-44" /> : undefined}
          subtitle={
            !loading
              ? `${sections.length} ${sections.length === 1 ? "section" : "sections"}`
              : undefined
          }
          backHref="/admin/companies"
          rightSlot={
            <Button variant="primary" onClick={openAdd}>
              + Add Section
            </Button>
          }
        />

        {loading ? (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-5">
            {Array.from({ length: 3 }).map((_, i) => (
              <SectionCardSkeleton key={i} />
            ))}
          </div>
        ) : loadError ? (
          <EmptyState
            icon={AlertTriangle}
            title="Couldn't load sections"
            subtitle="Something went wrong fetching this data — it may be temporary. Try again in a moment."
            action={{ label: "Retry", onClick: fetchSections }}
          />
        ) : sections.length === 0 ? (
          <EmptyState
            icon={Layers}
            title="No Sections Yet"
            subtitle="Add sections to organise the content for this company."
            action={{ label: "+ Add Section", onClick: openAdd }}
          />
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-5">
            {sections.map((section) => {
              const uploadCount = section.upload_count ?? 0;
              const hasUploads = uploadCount > 0;

              return (
                <div
                  key={section.id}
                  onClick={() => navigateToSection(section)}
                  className="bg-white border border-[var(--color-border)] rounded-xl cursor-pointer hover:shadow-[var(--shadow-md)] hover:border-[var(--color-border-strong)] transition-all duration-200 overflow-hidden"
                >
                  {/* Card body */}
                  <div className="p-5">
                    <div className="flex items-start justify-between gap-3">

                      {/* Icon + info */}
                      <div className="flex items-start gap-3 min-w-0">
                        <div
                          className="w-10 h-10 rounded-lg flex items-center justify-center shrink-0"
                          style={{ background: "var(--color-accent-light)" }}
                        >
                          <Layers size={18} style={{ color: "var(--color-accent)" }} />
                        </div>
                        <div className="min-w-0 pt-0.5">
                          <h3 className="font-semibold text-[var(--color-text)] truncate leading-snug">
                            {section.section_name}
                          </h3>
                          <p className="text-sm text-[var(--color-text-muted)] mt-1 flex items-center gap-1.5">
                            <Upload
                              size={12}
                              style={{ color: "var(--color-text-subtle)" }}
                            />
                            <span
                              style={{
                                color: hasUploads
                                  ? "var(--color-text)"
                                  : "var(--color-text-muted)",
                                fontWeight: hasUploads ? 500 : 400,
                              }}
                            >
                              {uploadCount}{" "}
                              {uploadCount === 1 ? "upload" : "uploads"}
                            </span>
                          </p>
                        </div>
                      </div>

                      {/* Actions — always visible, stop card click propagation */}
                      <div
                        className="flex items-center gap-0.5 shrink-0"
                        onClick={(e) => e.stopPropagation()}
                      >
                        <button
                          onClick={() => openEdit(section)}
                          className="p-1.5 rounded-md transition-colors"
                          style={{ color: "var(--color-text-subtle)" }}
                          onMouseEnter={(e) => {
                            e.currentTarget.style.background = "var(--color-surface-hover)";
                            e.currentTarget.style.color = "var(--color-text)";
                          }}
                          onMouseLeave={(e) => {
                            e.currentTarget.style.background = "transparent";
                            e.currentTarget.style.color = "var(--color-text-subtle)";
                          }}
                          aria-label="Edit section"
                        >
                          <Pencil size={14} />
                        </button>
                        <button
                          onClick={() => setDeleteSection(section)}
                          className="p-1.5 rounded-md transition-colors"
                          style={{ color: "var(--color-text-subtle)" }}
                          onMouseEnter={(e) => {
                            e.currentTarget.style.background = "var(--color-danger-bg)";
                            e.currentTarget.style.color = "var(--color-danger)";
                          }}
                          onMouseLeave={(e) => {
                            e.currentTarget.style.background = "transparent";
                            e.currentTarget.style.color = "var(--color-text-subtle)";
                          }}
                          aria-label="Delete section"
                        >
                          <Trash2 size={14} />
                        </button>
                      </div>
                    </div>
                  </div>

                  {/* Card footer */}
                  <div
                    className="px-5 py-2.5 flex items-center justify-between"
                    style={{
                      borderTop: "1px solid var(--color-border)",
                      background: "var(--color-primary-light)",
                    }}
                    onClick={(e) => e.stopPropagation()}
                  >
                    {/* Copy student link — only when parent company is published */}
                    {company?.is_published && (() => {
                      const isCopied = copiedId?.endsWith(section.id) ?? false;
                      return (
                        <button
                          onClick={() =>
                            copyLink(`${window.location.origin}/students/sections/${section.id}`)
                          }
                          title="Copy student link"
                          className="flex items-center gap-1.5 px-2 py-1 rounded-md text-xs font-medium transition-colors"
                          style={{
                            color: isCopied ? "#16A34A" : "var(--color-text-muted)",
                            background: "transparent",
                          }}
                          onMouseEnter={(e) => (e.currentTarget.style.background = "var(--color-surface-hover)")}
                          onMouseLeave={(e) => (e.currentTarget.style.background = "transparent")}
                        >
                          {isCopied ? <Check size={12} /> : <Link2 size={12} />}
                          {isCopied ? "Copied!" : "Copy link"}
                        </button>
                      );
                    })()}
                    <div className="flex items-center gap-1.5 ml-auto">
                      <span
                        className="text-xs font-medium"
                        style={{ color: "var(--color-text-muted)" }}
                      >
                        View uploads
                      </span>
                      <ChevronRight size={13} style={{ color: "var(--color-text-muted)" }} />
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </PageWrapper>

      <Modal
        isOpen={showAdd || !!editSection}
        onClose={closeModal}
        title={editSection ? "Edit Section" : "Add Section"}
        maxWidth="sm"
      >
        <form onSubmit={handleSubmit(onSubmit)}>
          <Input
            label="Section name"
            placeholder="e.g. Aptitude, Technical, HR"
            autoFocus
            error={errors.section_name?.message}
            {...register("section_name", {
              required: "Section name is required.",
            })}
          />
          <div className="flex justify-end gap-3 mt-5">
            <Button variant="secondary" type="button" onClick={closeModal}>
              Cancel
            </Button>
            <Button type="submit" loading={modalLoading}>
              {editSection ? "Save changes" : "Create section"}
            </Button>
          </div>
        </form>
      </Modal>

      <ConfirmDialog
        isOpen={!!deleteSection}
        onClose={() => setDeleteSection(null)}
        onConfirm={handleDelete}
        title="Delete Section"
        message={`Delete "${deleteSection?.section_name}"? All uploads in this section will also be deleted. This cannot be undone.`}
        confirmLabel="Delete section"
        loading={deleteLoading}
      />
    </AdminLayout>
  );
}
