"use client";

import { useEffect, useState, useCallback, useMemo } from "react";
import { useRouter } from "next/navigation";
import { useForm } from "react-hook-form";
import { Building2, Pencil, Trash2, Layers, ChevronRight, Link2, Check } from "lucide-react";
import { useCopyLink } from "@/hooks/useCopyLink";
import { AdminLayout } from "@/components/layout/AdminLayout";
import { PageWrapper } from "@/components/layout/PageWrapper";
import { PageHeader } from "@/components/layout/PageHeader";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Modal } from "@/components/ui/Modal";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import { EmptyState } from "@/components/ui/EmptyState";
import { Badge } from "@/components/ui/Badge";
import { CompanyCardSkeleton } from "@/components/ui/Skeleton";
import { SearchInput } from "@/components/ui/SearchInput";
import { useToast } from "@/components/ui/Toast";
import api, { getErrorMessage } from "@/lib/api";
import type { Company, ApiSuccess, PaginatedResponse } from "@/types";

interface CompanyForm {
  company_name: string;
}

export default function CompaniesPage() {
  const router = useRouter();
  const { error: toastError, success: toastSuccess } = useToast();
  const { copy: copyLink, copiedId } = useCopyLink();

  const [companies, setCompanies] = useState<Company[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [editCompany, setEditCompany] = useState<Company | null>(null);
  const [deleteCompany, setDeleteCompany] = useState<Company | null>(null);
  const [showAdd, setShowAdd] = useState(false);
  const [modalLoading, setModalLoading] = useState(false);
  const [deleteLoading, setDeleteLoading] = useState(false);
  const [publishLoading, setPublishLoading] = useState<string | null>(null);

  // Trim whitespace before matching — handles whitespace-only input gracefully
  const searchTerm = search.trim().toLowerCase();
  const filteredCompanies = useMemo(
    () =>
      searchTerm
        ? companies.filter((c) =>
            c.company_name?.toLowerCase().includes(searchTerm)
          )
        : companies,
    [companies, searchTerm]
  );

  const {
    register,
    handleSubmit,
    reset,
    setError,
    formState: { errors },
  } = useForm<CompanyForm>();

  const fetchCompanies = useCallback(async () => {
    try {
      const { data } = await api.get<PaginatedResponse<Company>>(
        "/admin/companies/"
      );
      setCompanies(data.results);
    } catch (err) {
      toastError(getErrorMessage(err));
    } finally {
      setLoading(false);
    }
  }, [toastError]);

  useEffect(() => {
    fetchCompanies();
  }, [fetchCompanies]);

  function openAdd() {
    reset({ company_name: "" });
    setShowAdd(true);
  }

  function openEdit(c: Company) {
    reset({ company_name: c.company_name });
    setEditCompany(c);
  }

  function closeModal() {
    setShowAdd(false);
    setEditCompany(null);
    reset();
  }

  async function onSubmit(data: CompanyForm) {
    setModalLoading(true);
    try {
      if (editCompany) {
        const res = await api.patch<ApiSuccess<Company>>(
          `/admin/companies/${editCompany.id}/`,
          data
        );
        setCompanies((prev) =>
          prev.map((c) => (c.id === editCompany.id ? res.data.data : c))
        );
        toastSuccess("Company updated.");
      } else {
        const res = await api.post<ApiSuccess<Company>>("/admin/companies/", data);
        setCompanies((prev) => [...prev, res.data.data]);
        toastSuccess("Company created.");
      }
      closeModal();
    } catch (err) {
      const msg = getErrorMessage(err);
      setError("company_name", {
        message:
          msg.toLowerCase().includes("unique") ||
          msg.toLowerCase().includes("already")
            ? "A company with this name already exists."
            : msg,
      });
    } finally {
      setModalLoading(false);
    }
  }

  async function handleDelete() {
    if (!deleteCompany) return;
    setDeleteLoading(true);
    try {
      await api.delete(`/admin/companies/${deleteCompany.id}/`);
      setCompanies((prev) => prev.filter((c) => c.id !== deleteCompany.id));
      toastSuccess(`"${deleteCompany.company_name}" deleted.`);
      setDeleteCompany(null);
    } catch (err) {
      toastError(getErrorMessage(err));
      setDeleteCompany(null);
    } finally {
      setDeleteLoading(false);
    }
  }

  async function handleTogglePublish(company: Company) {
    const nextPublished = !company.is_published;

    // Optimistic update — flip immediately so the UI feels instant
    setCompanies((prev) =>
      prev.map((c) =>
        c.id === company.id ? { ...c, is_published: nextPublished } : c
      )
    );
    setPublishLoading(company.id);

    try {
      const res = await api.patch<ApiSuccess<Company>>(
        `/admin/companies/${company.id}/toggle-publish/`
      );
      // Confirm with server state (source of truth)
      setCompanies((prev) =>
        prev.map((c) => (c.id === company.id ? res.data.data : c))
      );
      toastSuccess(nextPublished ? "Company published." : "Company unpublished.");
    } catch (err) {
      // Revert optimistic update on failure
      setCompanies((prev) =>
        prev.map((c) =>
          c.id === company.id ? { ...c, is_published: company.is_published } : c
        )
      );
      toastError(getErrorMessage(err));
    } finally {
      setPublishLoading(null);
    }
  }

  return (
    <AdminLayout>
      <PageWrapper>
        <PageHeader
          title="Company Management"
          backHref="/admin/resources"
          centerSlot={
            !loading && companies.length > 0 ? (
              <div className="flex items-center gap-3 w-full max-w-sm">
                <SearchInput
                  value={search}
                  onChange={setSearch}
                  placeholder="Search companies…"
                  className="flex-1"
                />
                {searchTerm && (
                  <p className="text-xs shrink-0 tabular-nums" style={{ color: "var(--color-text-muted)" }}>
                    {filteredCompanies.length === 0
                      ? "No results"
                      : `${filteredCompanies.length} / ${companies.length}`}
                  </p>
                )}
              </div>
            ) : undefined
          }
          rightSlot={
            <Button variant="primary" onClick={openAdd}>
              + Add Company
            </Button>
          }
        />

        {loading ? (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-5">
            {Array.from({ length: 6 }).map((_, i) => (
              <CompanyCardSkeleton key={i} />
            ))}
          </div>
        ) : companies.length === 0 ? (
          // No companies exist at all
          <EmptyState
            icon={Building2}
            title="No Companies Yet"
            subtitle="Add your first company to start building placement content."
            action={{ label: "+ Add Company", onClick: openAdd }}
          />
        ) : filteredCompanies.length === 0 ? (
          // Companies exist but none match the search query
          <EmptyState
            icon={Building2}
            title="No companies found"
            subtitle={`No companies match "${search.trim()}". Try a different name or clear the search.`}
            action={{ label: "Clear search", onClick: () => setSearch("") }}
          />
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-5">
            {filteredCompanies.map((company) => (
              <div
                key={company.id}
                onClick={() => router.push(`/admin/companies/${company.id}`)}
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
                        <Building2 size={18} style={{ color: "var(--color-accent)" }} />
                      </div>
                      <div className="min-w-0 pt-0.5">
                        <h3 className="font-semibold text-[var(--color-text)] truncate leading-snug">
                          {company.company_name}
                        </h3>
                        <p className="text-sm text-[var(--color-text-muted)] mt-1 flex items-center gap-1.5">
                          <Layers size={12} style={{ color: "var(--color-text-subtle)" }} />
                          {company.section_count ?? 0}{" "}
                          {(company.section_count ?? 0) === 1 ? "section" : "sections"}
                        </p>
                      </div>
                    </div>

                    {/* Badge + action buttons — stop propagation so clicks don't navigate */}
                    <div
                      className="flex items-center gap-0.5 shrink-0"
                      onClick={(e) => e.stopPropagation()}
                    >
                      <Badge variant={company.is_published ? "published" : "unpublished"}>
                        {company.is_published ? "Published" : "Draft"}
                      </Badge>
                      <button
                        onClick={() => openEdit(company)}
                        className="p-1.5 rounded-md transition-colors ml-1"
                        style={{ color: "var(--color-text-subtle)" }}
                        onMouseEnter={(e) => {
                          e.currentTarget.style.background = "var(--color-surface-hover)";
                          e.currentTarget.style.color = "var(--color-text)";
                        }}
                        onMouseLeave={(e) => {
                          e.currentTarget.style.background = "transparent";
                          e.currentTarget.style.color = "var(--color-text-subtle)";
                        }}
                        aria-label="Edit company"
                      >
                        <Pencil size={14} />
                      </button>
                      <button
                        onClick={() => setDeleteCompany(company)}
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
                        aria-label="Delete company"
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
                  <Button
                    variant={company.is_published ? "secondary" : "success"}
                    size="sm"
                    loading={publishLoading === company.id}
                    onClick={() => handleTogglePublish(company)}
                  >
                    {company.is_published ? "Unpublish" : "Publish"}
                  </Button>
                  <div className="flex items-center gap-2">
                    {/* Copy student link — only when published (students can't reach unpublished pages) */}
                    {company.is_published && (() => {
                      const isCopied = copiedId?.endsWith(company.id) ?? false;
                      return (
                        <button
                          onClick={() =>
                            copyLink(`${window.location.origin}/students/companies/${company.id}`)
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
                    <span
                      className="text-xs font-medium"
                      style={{ color: "var(--color-text-muted)" }}
                    >
                      View sections
                    </span>
                    <ChevronRight size={13} style={{ color: "var(--color-text-muted)" }} />
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </PageWrapper>

      {/* Add / Edit Modal */}
      <Modal
        isOpen={showAdd || !!editCompany}
        onClose={closeModal}
        title={editCompany ? "Edit Company" : "Add Company"}
        maxWidth="sm"
      >
        <form onSubmit={handleSubmit(onSubmit)}>
          <Input
            label="Company name"
            placeholder="e.g. Infosys"
            autoFocus
            error={errors.company_name?.message}
            {...register("company_name", {
              required: "Company name is required.",
            })}
          />
          <div className="flex justify-end gap-3 mt-5">
            <Button variant="secondary" type="button" onClick={closeModal}>
              Cancel
            </Button>
            <Button type="submit" loading={modalLoading}>
              {editCompany ? "Save changes" : "Create company"}
            </Button>
          </div>
        </form>
      </Modal>

      {/* Delete ConfirmDialog */}
      <ConfirmDialog
        isOpen={!!deleteCompany}
        onClose={() => setDeleteCompany(null)}
        onConfirm={handleDelete}
        title="Delete Company"
        message={`Delete "${deleteCompany?.company_name}"? This will also delete all sections and uploads. This cannot be undone.`}
        confirmLabel="Delete company"
        loading={deleteLoading}
      />
    </AdminLayout>
  );
}
