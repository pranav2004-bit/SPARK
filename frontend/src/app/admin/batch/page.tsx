"use client";

import { useEffect, useState, useCallback } from "react";
import { useRouter } from "next/navigation";
import { useForm } from "react-hook-form";
import { LayoutDashboard, Pencil, Trash2, Users, ChevronRight, AlertTriangle } from "lucide-react";
import { AdminLayout } from "@/components/layout/AdminLayout";
import { PageWrapper } from "@/components/layout/PageWrapper";
import { PageHeader } from "@/components/layout/PageHeader";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Modal } from "@/components/ui/Modal";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import { EmptyState } from "@/components/ui/EmptyState";
import { CardSkeleton } from "@/components/ui/Skeleton";
import { useToast } from "@/components/ui/Toast";
import api, { getErrorMessage } from "@/lib/api";
import type { Batch, ApiSuccess } from "@/types";

interface BatchForm {
  batch_name: string;
}

export default function BatchPage() {
  const router = useRouter();
  const { error: toastError, success: toastSuccess } = useToast();

  const [batches, setBatches] = useState<Batch[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState(false);
  const [editBatch, setEditBatch] = useState<Batch | null>(null);
  const [deleteBatch, setDeleteBatch] = useState<Batch | null>(null);
  const [showAddModal, setShowAddModal] = useState(false);
  const [modalLoading, setModalLoading] = useState(false);
  const [deleteLoading, setDeleteLoading] = useState(false);

  const {
    register,
    handleSubmit,
    reset,
    setError,
    formState: { errors },
  } = useForm<BatchForm>();

  const fetchBatches = useCallback(async () => {
    setLoading(true);
    setLoadError(false);
    try {
      const { data } = await api.get<ApiSuccess<Batch[]>>("/users/batches/");
      setBatches(data.data);
    } catch (err) {
      toastError(getErrorMessage(err));
      setLoadError(true);
    } finally {
      setLoading(false);
    }
  }, [toastError]);

  useEffect(() => {
    fetchBatches();
  }, [fetchBatches]);

  function openAdd() {
    reset({ batch_name: "" });
    setShowAddModal(true);
  }

  function openEdit(batch: Batch) {
    reset({ batch_name: batch.batch_name });
    setEditBatch(batch);
  }

  function closeModal() {
    setShowAddModal(false);
    setEditBatch(null);
    reset();
  }

  async function onSubmit(data: BatchForm) {
    setModalLoading(true);
    try {
      if (editBatch) {
        const res = await api.patch<ApiSuccess<Batch>>(
          `/users/batches/${editBatch.id}/`,
          data
        );
        setBatches((prev) =>
          prev.map((b) => (b.id === editBatch.id ? res.data.data : b))
        );
        toastSuccess("Batch updated.");
      } else {
        const res = await api.post<ApiSuccess<Batch>>("/users/batches/", data);
        setBatches((prev) => [...prev, res.data.data]);
        toastSuccess("Batch created.");
      }
      closeModal();
    } catch (err) {
      const msg = getErrorMessage(err);
      if (msg.toLowerCase().includes("batch_name") || msg.toLowerCase().includes("unique") || msg.toLowerCase().includes("already")) {
        setError("batch_name", { message: "A batch with this name already exists." });
      } else {
        setError("batch_name", { message: msg });
      }
    } finally {
      setModalLoading(false);
    }
  }

  async function handleDelete() {
    if (!deleteBatch) return;
    setDeleteLoading(true);
    try {
      await api.delete(`/users/batches/${deleteBatch.id}/`);
      setBatches((prev) => prev.filter((b) => b.id !== deleteBatch.id));
      toastSuccess(`Batch "${deleteBatch.batch_name}" deleted.`);
      setDeleteBatch(null);
    } catch (err) {
      const msg = getErrorMessage(err);
      if (msg.toLowerCase().includes("student")) {
        toastError("Cannot delete a batch that has students.");
      } else {
        toastError(msg);
      }
      setDeleteBatch(null);
    } finally {
      setDeleteLoading(false);
    }
  }

  return (
    <AdminLayout>
      <PageWrapper>
        <PageHeader
          title="Batch Management"
          rightSlot={
            <Button variant="primary" onClick={openAdd}>
              + Add Batch
            </Button>
          }
        />

        {loading ? (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {Array.from({ length: 6 }).map((_, i) => (
              <CardSkeleton key={i} />
            ))}
          </div>
        ) : loadError ? (
          <EmptyState
            icon={AlertTriangle}
            title="Couldn't load batches"
            subtitle="Something went wrong fetching this data — it may be temporary. Try again in a moment."
            action={{ label: "Retry", onClick: fetchBatches }}
          />
        ) : batches.length === 0 ? (
          <EmptyState
            icon={LayoutDashboard}
            title="No Batches Yet"
            subtitle="Create your first batch to start adding students."
            action={{ label: "+ Add Batch", onClick: openAdd }}
          />
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-5">
            {batches.map((batch) => (
              <div
                key={batch.id}
                onClick={() => router.push(`/admin/batch/${batch.id}`)}
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
                        <LayoutDashboard size={18} style={{ color: "var(--color-accent)" }} />
                      </div>
                      <div className="min-w-0 pt-0.5">
                        <h3 className="font-semibold text-[var(--color-text)] truncate leading-snug">
                          {batch.batch_name}
                        </h3>
                        <p className="text-sm text-[var(--color-text-muted)] mt-1 flex items-center gap-1.5">
                          <Users size={12} style={{ color: "var(--color-text-subtle)" }} />
                          {batch.student_count ?? 0}{" "}
                          {(batch.student_count ?? 0) === 1 ? "student" : "students"}
                        </p>
                      </div>
                    </div>

                    {/* Action buttons — always visible */}
                    <div
                      className="flex items-center gap-0.5 shrink-0"
                      onClick={(e) => e.stopPropagation()}
                    >
                      <button
                        onClick={() => openEdit(batch)}
                        className="p-1.5 rounded-md transition-colors"
                        style={{ color: "var(--color-text-subtle)" }}
                        onMouseEnter={e => {
                          e.currentTarget.style.background = "var(--color-surface-hover)";
                          e.currentTarget.style.color = "var(--color-text)";
                        }}
                        onMouseLeave={e => {
                          e.currentTarget.style.background = "transparent";
                          e.currentTarget.style.color = "var(--color-text-subtle)";
                        }}
                        aria-label="Edit batch"
                      >
                        <Pencil size={14} />
                      </button>
                      <button
                        onClick={() => setDeleteBatch(batch)}
                        className="p-1.5 rounded-md transition-colors"
                        style={{ color: "var(--color-text-subtle)" }}
                        onMouseEnter={e => {
                          e.currentTarget.style.background = "var(--color-danger-bg)";
                          e.currentTarget.style.color = "var(--color-danger)";
                        }}
                        onMouseLeave={e => {
                          e.currentTarget.style.background = "transparent";
                          e.currentTarget.style.color = "var(--color-text-subtle)";
                        }}
                        aria-label="Delete batch"
                      >
                        <Trash2 size={14} />
                      </button>
                    </div>
                  </div>
                </div>

                {/* Card footer — navigation affordance */}
                <div
                  className="px-5 py-2.5 flex items-center justify-between"
                  style={{
                    borderTop: "1px solid var(--color-border)",
                    background: "var(--color-primary-light)",
                  }}
                >
                  <span
                    className="text-xs font-medium"
                    style={{ color: "var(--color-text-muted)" }}
                  >
                    View students
                  </span>
                  <ChevronRight size={13} style={{ color: "var(--color-text-muted)" }} />
                </div>
              </div>
            ))}
          </div>
        )}
      </PageWrapper>

      {/* Add / Edit Modal */}
      <Modal
        isOpen={showAddModal || !!editBatch}
        onClose={closeModal}
        title={editBatch ? "Edit Batch" : "Add Batch"}
        maxWidth="sm"
      >
        <form onSubmit={handleSubmit(onSubmit)}>
          <Input
            label="Batch name"
            placeholder="e.g. CSE-2025"
            autoFocus
            error={errors.batch_name?.message}
            {...register("batch_name", {
              required: "Batch name is required.",
            })}
          />
          <div className="flex justify-end gap-3 mt-5">
            <Button variant="secondary" type="button" onClick={closeModal}>
              Cancel
            </Button>
            <Button type="submit" loading={modalLoading}>
              {editBatch ? "Save changes" : "Create batch"}
            </Button>
          </div>
        </form>
      </Modal>

      {/* Delete ConfirmDialog */}
      <ConfirmDialog
        isOpen={!!deleteBatch}
        onClose={() => setDeleteBatch(null)}
        onConfirm={handleDelete}
        title="Delete Batch"
        message={`Delete "${deleteBatch?.batch_name}"? This cannot be undone.`}
        confirmLabel="Delete"
        loading={deleteLoading}
      />
    </AdminLayout>
  );
}
