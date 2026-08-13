"use client";

import { useState } from "react";
import { useForm } from "react-hook-form";
import { Pencil, Trash2, UserCheck, UserX, KeyRound } from "lucide-react";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Modal } from "@/components/ui/Modal";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import { Select } from "@/components/ui/Select";
import { TableRowSkeleton } from "@/components/ui/Skeleton";
import { Pagination } from "@/components/ui/Pagination";
import { useToast } from "@/components/ui/Toast";
import api, { getErrorMessage } from "@/lib/api";
import { DEPARTMENTS } from "@/lib/constants";
import type { Student, Batch, ApiSuccess } from "@/types";

interface StudentTableProps {
  students: Student[];
  loading: boolean;
  totalCount: number;
  totalPages?: number;
  page: number;
  onPageChange: (page: number) => void;
  onStudentUpdated: (updated: Student) => void;
  onStudentDeleted: (id: string) => void;
  showBatchColumn?: boolean;
  batches?: Batch[];
}

interface EditForm {
  department: string;
  batch_id: string;
}

const PAGE_SIZE = 50;

export function StudentTable({
  students,
  loading,
  totalCount,
  totalPages: totalPagesProp,
  page,
  onPageChange,
  onStudentUpdated,
  onStudentDeleted,
  showBatchColumn = false,
  batches = [],
}: StudentTableProps) {
  const { error: toastError, success: toastSuccess } = useToast();
  const [editStudent, setEditStudent] = useState<Student | null>(null);
  const [deleteStudent, setDeleteStudent] = useState<Student | null>(null);
  const [resetStudent, setResetStudent] = useState<Student | null>(null);
  const [actionLoading, setActionLoading] = useState<string | null>(null);

  const {
    register,
    handleSubmit,
    reset,
    formState: { errors },
  } = useForm<EditForm>();

  const totalPages = totalPagesProp ?? Math.ceil(totalCount / PAGE_SIZE);

  function openEdit(s: Student) {
    reset({
      department: s.department,
      batch_id: s.batch_id,
    });
    setEditStudent(s);
  }

  async function onEditSubmit(data: EditForm) {
    if (!editStudent) return;
    setActionLoading("edit");
    try {
      const res = await api.patch<ApiSuccess<Student>>(
        `/users/students/${editStudent.id}/`,
        data
      );
      onStudentUpdated(res.data.data);
      toastSuccess("Student updated.");
      setEditStudent(null);
    } catch (err) {
      toastError(getErrorMessage(err));
    } finally {
      setActionLoading(null);
    }
  }

  async function handleToggleActive(student: Student) {
    setActionLoading(student.id);
    try {
      const res = await api.patch<ApiSuccess<{ is_active: boolean }>>(
        `/users/students/${student.id}/toggle-status/`
      );
      onStudentUpdated({ ...student, is_active: res.data.data.is_active });
      toastSuccess(
        res.data.data.is_active ? "Student enabled." : "Student disabled."
      );
    } catch (err) {
      toastError(getErrorMessage(err));
    } finally {
      setActionLoading(null);
    }
  }

  async function handleResetPassword() {
    if (!resetStudent) return;
    setActionLoading("reset");
    try {
      await api.post(`/auth/student/${resetStudent.student_id}/reset-password/`);
      toastSuccess(
        `Password reset to ANITS@123 for ${resetStudent.student_id}.`
      );
      setResetStudent(null);
    } catch (err) {
      toastError(getErrorMessage(err));
      setResetStudent(null);
    } finally {
      setActionLoading(null);
    }
  }

  async function handleDelete() {
    if (!deleteStudent) return;
    setActionLoading("delete");
    try {
      await api.delete(`/users/students/${deleteStudent.id}/`);
      onStudentDeleted(deleteStudent.id);
      toastSuccess("Student deleted.");
      setDeleteStudent(null);
    } catch (err) {
      toastError(getErrorMessage(err));
      setDeleteStudent(null);
    } finally {
      setActionLoading(null);
    }
  }

  const deptOptions = DEPARTMENTS.map((d) => ({ value: d, label: d }));
  const batchOptions = batches.map((b) => ({
    value: b.id,
    label: b.batch_name,
  }));

  return (
    <>
      <div
        className="rounded-xl overflow-hidden"
        style={{
          border: "1px solid var(--color-border)",
          boxShadow: "var(--shadow-sm)",
        }}
      >
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            {/* ── Table header ───────────────────────────────────────────── */}
            <thead>
              <tr
                style={{
                  borderBottom: "1px solid var(--color-border)",
                  background: "var(--color-surface-secondary)",
                }}
              >
                <th className="text-left px-5 py-3 text-[11px] font-semibold uppercase tracking-[0.07em]"
                  style={{ color: "var(--color-text-subtle)", width: 130 }}>
                  Student ID
                </th>
                <th className="text-left px-5 py-3 text-[11px] font-semibold uppercase tracking-[0.07em]"
                  style={{ color: "var(--color-text-subtle)" }}>
                  Name
                </th>
                <th className="text-left px-5 py-3 text-[11px] font-semibold uppercase tracking-[0.07em]"
                  style={{ color: "var(--color-text-subtle)" }}>
                  Email
                </th>
                <th className="text-left px-5 py-3 text-[11px] font-semibold uppercase tracking-[0.07em]"
                  style={{ color: "var(--color-text-subtle)", width: 90 }}>
                  Dept
                </th>
                {showBatchColumn && (
                  <th className="text-left px-5 py-3 text-[11px] font-semibold uppercase tracking-[0.07em]"
                    style={{ color: "var(--color-text-subtle)" }}>
                    Batch
                  </th>
                )}
                <th className="text-left px-5 py-3 text-[11px] font-semibold uppercase tracking-[0.07em]"
                  style={{ color: "var(--color-text-subtle)", width: 90 }}>
                  Status
                </th>
                <th className="px-5 py-3" style={{ width: 140 }} aria-label="Actions" />
              </tr>
            </thead>

            {/* ── Table body ─────────────────────────────────────────────── */}
            <tbody
              style={{ background: "#fff" }}
            >
              {loading ? (
                Array.from({ length: 5 }).map((_, i) => (
                  <TableRowSkeleton key={i} cols={showBatchColumn ? 7 : 6} />
                ))
              ) : students.length === 0 ? (
                <tr>
                  <td
                    colSpan={showBatchColumn ? 7 : 6}
                    className="text-center py-14 text-sm"
                    style={{ color: "var(--color-text-muted)" }}
                  >
                    No students found.
                  </td>
                </tr>
              ) : (
                students.map((student) => (
                  <tr
                    key={student.id}
                    className="transition-colors"
                    style={{ borderTop: "1px solid var(--color-border)" }}
                    onMouseEnter={e =>
                      (e.currentTarget.style.background = "var(--color-primary-light)")
                    }
                    onMouseLeave={e =>
                      (e.currentTarget.style.background = "#fff")
                    }
                  >
                    {/* Student ID — styled badge */}
                    <td className="px-5 py-3.5">
                      <span
                        className="inline-flex items-center px-2.5 py-0.5 rounded-md font-mono text-xs font-semibold tracking-wide"
                        style={{
                          background: "var(--color-primary-light)",
                          color: "var(--color-primary)",
                          letterSpacing: "0.06em",
                        }}
                      >
                        {student.student_id}
                      </span>
                    </td>

                    {/* Name — with avatar initial */}
                    <td className="px-5 py-3.5">
                      <div className="flex items-center gap-2.5">
                        <span
                          className="inline-flex items-center justify-center rounded-full text-[11px] font-bold shrink-0"
                          style={{
                            width: 28,
                            height: 28,
                            background: "var(--color-accent-light)",
                            color: "var(--color-accent)",
                          }}
                        >
                          {student.fullname?.charAt(0).toUpperCase() ?? "?"}
                        </span>
                        <span
                          className="font-medium text-sm"
                          style={{ color: "var(--color-text)" }}
                        >
                          {student.fullname}
                        </span>
                      </div>
                    </td>

                    {/* Email */}
                    <td className="px-5 py-3.5 text-sm" style={{ color: "var(--color-text-muted)" }}>
                      {student.college_email_id || (
                        <span style={{ color: "var(--color-text-subtle)" }}>—</span>
                      )}
                    </td>

                    {/* Department — pill tag */}
                    <td className="px-5 py-3.5">
                      <span
                        className="inline-flex items-center px-2 py-0.5 rounded-md text-xs font-medium"
                        style={{
                          background: "var(--color-surface-secondary)",
                          color: "var(--color-text-muted)",
                          border: "1px solid var(--color-border)",
                        }}
                      >
                        {student.department}
                      </span>
                    </td>

                    {/* Batch column (optional) */}
                    {showBatchColumn && (
                      <td className="px-5 py-3.5 text-sm" style={{ color: "var(--color-text-muted)" }}>
                        {student.batch_name ?? "—"}
                      </td>
                    )}

                    {/* Status badge */}
                    <td className="px-5 py-3.5">
                      <Badge variant={student.is_active ? "active" : "disabled"}>
                        {student.is_active ? "Active" : "Disabled"}
                      </Badge>
                    </td>

                    {/* Actions */}
                    <td className="px-5 py-3.5">
                      <div
                        className="flex items-center gap-0.5 justify-end"
                        style={{
                          borderLeft: "1px solid var(--color-border)",
                          paddingLeft: 12,
                        }}
                      >
                        <button
                          onClick={() => openEdit(student)}
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
                          title="Edit student"
                        >
                          <Pencil size={14} />
                        </button>
                        <button
                          onClick={() => handleToggleActive(student)}
                          disabled={actionLoading === student.id}
                          className="p-1.5 rounded-md transition-colors"
                          style={{ color: "var(--color-text-subtle)" }}
                          onMouseEnter={e => {
                            e.currentTarget.style.background = student.is_active
                              ? "var(--color-warning-bg)"
                              : "var(--color-success-bg)";
                            e.currentTarget.style.color = student.is_active
                              ? "var(--color-warning)"
                              : "var(--color-success)";
                          }}
                          onMouseLeave={e => {
                            e.currentTarget.style.background = "transparent";
                            e.currentTarget.style.color = "var(--color-text-subtle)";
                          }}
                          title={student.is_active ? "Disable student" : "Enable student"}
                        >
                          {student.is_active ? <UserX size={14} /> : <UserCheck size={14} />}
                        </button>
                        <button
                          onClick={() => setResetStudent(student)}
                          className="p-1.5 rounded-md transition-colors"
                          style={{ color: "var(--color-text-subtle)" }}
                          onMouseEnter={e => {
                            e.currentTarget.style.background = "var(--color-info-bg)";
                            e.currentTarget.style.color = "var(--color-info)";
                          }}
                          onMouseLeave={e => {
                            e.currentTarget.style.background = "transparent";
                            e.currentTarget.style.color = "var(--color-text-subtle)";
                          }}
                          title="Reset password"
                        >
                          <KeyRound size={14} />
                        </button>
                        <button
                          onClick={() => setDeleteStudent(student)}
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
                          title="Delete student"
                        >
                          <Trash2 size={14} />
                        </button>
                      </div>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>

        <Pagination
          page={page}
          totalPages={totalPages}
          onPageChange={onPageChange}
          totalCount={totalCount}
          pageSize={PAGE_SIZE}
        />
      </div>

      {/* Edit Modal */}
      <Modal
        isOpen={!!editStudent}
        onClose={() => setEditStudent(null)}
        title="Edit Student"
      >
        <form onSubmit={handleSubmit(onEditSubmit)}>
          <div className="space-y-4">
            {/* Editable: department */}
            <Select
              label="Department"
              options={deptOptions}
              error={errors.department?.message}
              {...register("department", { required: "Department is required." })}
            />
            {/* Editable: batch */}
            {showBatchColumn && (
              <Select
                label="Batch"
                options={batchOptions}
                placeholder="Select batch"
                error={errors.batch_id?.message}
                {...register("batch_id", { required: "Batch is required." })}
              />
            )}
          </div>
          <div className="flex justify-end gap-3 mt-4">
            <Button variant="secondary" type="button" onClick={() => setEditStudent(null)}>
              Cancel
            </Button>
            <Button type="submit" loading={actionLoading === "edit"}>
              Save changes
            </Button>
          </div>
        </form>
      </Modal>

      {/* Reset password dialog */}
      <ConfirmDialog
        isOpen={!!resetStudent}
        onClose={() => setResetStudent(null)}
        onConfirm={handleResetPassword}
        title="Reset Password"
        message={`Reset password for ${resetStudent?.student_id} (${resetStudent?.fullname})? Their password will be set to ANITS@123.`}
        confirmLabel="Reset password"
        confirmVariant="primary"
        loading={actionLoading === "reset"}
      />

      {/* Delete dialog */}
      <ConfirmDialog
        isOpen={!!deleteStudent}
        onClose={() => setDeleteStudent(null)}
        onConfirm={handleDelete}
        title="Delete Student"
        message={`This will permanently delete ${deleteStudent?.student_id}${deleteStudent?.fullname ? ` (${deleteStudent.fullname})` : ""} and their login access. This cannot be undone.`}
        confirmLabel="Permanently Delete"
        loading={actionLoading === "delete"}
      />
    </>
  );
}
