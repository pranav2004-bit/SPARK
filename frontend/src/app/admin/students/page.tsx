"use client";

import { useEffect, useState, useCallback } from "react";
import { useForm } from "react-hook-form";
import { Users, ChevronDown, Upload } from "lucide-react";
import { AdminLayout } from "@/components/layout/AdminLayout";
import { PageWrapper } from "@/components/layout/PageWrapper";
import { PageHeader } from "@/components/layout/PageHeader";
import { SearchInput } from "@/components/ui/SearchInput";
import { Select } from "@/components/ui/Select";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Modal } from "@/components/ui/Modal";
import { EmptyState } from "@/components/ui/EmptyState";
import { StudentTable } from "@/components/admin/StudentTable";
import { BulkImportModal } from "@/components/admin/BulkImportModal";
import { useToast } from "@/components/ui/Toast";
import api, { getErrorMessage } from "@/lib/api";
import { DEPARTMENTS } from "@/lib/constants";
import type { Student, Batch, PaginatedResponse, ApiSuccess } from "@/types";

const DEPT_OPTIONS = [
  { value: "", label: "All departments" },
  ...DEPARTMENTS.map((d) => ({ value: d, label: d })),
];

interface AddStudentForm {
  student_id: string;
  department: string;
  batch_id: string;
}

export default function StudentsPage() {
  const { error: toastError, success: toastSuccess } = useToast();

  const [students, setStudents] = useState<Student[]>([]);
  const [batches, setBatches] = useState<Batch[]>([]);
  const [totalCount, setTotalCount] = useState(0);
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  const [search, setSearch] = useState("");
  const [department, setDepartment] = useState("");
  const [batchFilter, setBatchFilter] = useState("");
  const [showAdd, setShowAdd] = useState(false);
  const [addLoading, setAddLoading] = useState(false);
  const [showBulkImport, setShowBulkImport] = useState(false);

  const {
    register,
    handleSubmit,
    reset,
    setError,
    formState: { errors },
  } = useForm<AddStudentForm>();

  const fetchStudents = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      params.set("page", String(page));
      if (search) params.set("search", search);
      if (department) params.set("department", department);
      if (batchFilter) params.set("batch_id", batchFilter);

      const { data } = await api.get<PaginatedResponse<Student>>(
        `/users/students/?${params}`
      );
      setStudents(data.results);
      setTotalCount(data.count);
      setTotalPages(data.total_pages ?? Math.ceil(data.count / 50));
    } catch (err) {
      toastError(getErrorMessage(err));
    } finally {
      setLoading(false);
    }
  }, [page, search, department, batchFilter, toastError]);

  useEffect(() => {
    fetchStudents();
  }, [fetchStudents]);

  // Fetch batches for dropdown
  useEffect(() => {
    api
      .get<ApiSuccess<Batch[]>>("/users/batches/")
      .then(({ data }) => setBatches(data.data))
      .catch(() => {});
  }, []);

  function handleSearch(val: string) {
    setSearch(val);
    setPage(1);
  }

  function handleDeptChange(e: React.ChangeEvent<HTMLSelectElement>) {
    setDepartment(e.target.value);
    setPage(1);
  }

  function handleBatchFilterChange(e: React.ChangeEvent<HTMLSelectElement>) {
    setBatchFilter(e.target.value);
    setPage(1);
  }

  function openAdd() {
    reset();
    setShowAdd(true);
  }

  async function onAddSubmit(data: AddStudentForm) {
    setAddLoading(true);
    try {
      const res = await api.post<ApiSuccess<Student>>("/users/students/", data);
      setStudents((prev) => [res.data.data, ...prev]);
      setTotalCount((c) => c + 1);
      toastSuccess("Student created.");
      setShowAdd(false);
    } catch (err) {
      const msg = getErrorMessage(err);
      if (
        msg.toLowerCase().includes("student_id") ||
        msg.toLowerCase().includes("unique") ||
        msg.toLowerCase().includes("already")
      ) {
        setError("student_id", {
          message: "A student with this ID already exists.",
        });
      } else {
        setError("student_id", { message: msg });
      }
    } finally {
      setAddLoading(false);
    }
  }

  const batchOptions = batches.map((b) => ({
    value: b.id,
    label: b.batch_name,
  }));

  return (
    <AdminLayout>
      <PageWrapper>
        <PageHeader
          title="Student Management"
          subtitle={`${totalCount} ${totalCount === 1 ? "student" : "students"} total`}
          rightSlot={
            <div className="flex items-center gap-2">
              <button
                onClick={() => setShowBulkImport(true)}
                className="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-lg text-sm font-semibold transition-all"
                style={{
                  background: "var(--color-surface-secondary)",
                  color: "var(--color-text-muted)",
                  border: "1px solid var(--color-border)",
                }}
                onMouseEnter={e => {
                  (e.currentTarget as HTMLButtonElement).style.background = "var(--color-primary)";
                  (e.currentTarget as HTMLButtonElement).style.color = "#fff";
                  (e.currentTarget as HTMLButtonElement).style.borderColor = "var(--color-primary)";
                }}
                onMouseLeave={e => {
                  (e.currentTarget as HTMLButtonElement).style.background = "var(--color-surface-secondary)";
                  (e.currentTarget as HTMLButtonElement).style.color = "var(--color-text-muted)";
                  (e.currentTarget as HTMLButtonElement).style.borderColor = "var(--color-border)";
                }}
              >
                <Upload size={14} />
                Import CSV
              </button>
              <Button variant="primary" onClick={openAdd}>
                + Add Student
              </Button>
            </div>
          }
        />

        {/* Filter toolbar */}
        <div
          className="flex flex-wrap items-center gap-3 rounded-xl px-4 py-3 mb-5"
          style={{
            background: "#fff",
            border: "1px solid var(--color-border)",
            boxShadow: "var(--shadow-sm)",
          }}
        >
          <SearchInput
            value={search}
            onChange={handleSearch}
            placeholder="Search by name or student ID..."
            className="w-64 shrink-0"
          />

          {/* Divider */}
          <div className="hidden sm:block self-stretch w-px" style={{ background: "var(--color-border)" }} />

          {/* Department filter */}
          <div className="relative shrink-0">
            <select
              value={department}
              onChange={handleDeptChange}
              className="h-9 pl-3 pr-8 text-sm rounded-[var(--radius-md)] border bg-white appearance-none cursor-pointer focus:outline-none focus:ring-2 focus:ring-[var(--color-accent)]"
              style={{ borderColor: "var(--color-border)", color: "var(--color-text)", width: 160 }}
            >
              {DEPT_OPTIONS.map((opt) => (
                <option key={opt.value} value={opt.value}>{opt.label}</option>
              ))}
            </select>
            <ChevronDown size={14} className="absolute right-2.5 top-1/2 -translate-y-1/2 pointer-events-none" style={{ color: "var(--color-text-muted)" }} />
          </div>

          {/* Divider */}
          <div className="hidden sm:block self-stretch w-px" style={{ background: "var(--color-border)" }} />

          {/* Batch filter */}
          <div className="relative shrink-0">
            <select
              value={batchFilter}
              onChange={handleBatchFilterChange}
              className="h-9 pl-3 pr-8 text-sm rounded-[var(--radius-md)] border bg-white appearance-none cursor-pointer focus:outline-none focus:ring-2 focus:ring-[var(--color-accent)]"
              style={{ borderColor: "var(--color-border)", color: "var(--color-text)", width: 160 }}
            >
              <option value="">All batches</option>
              {batches.map((b) => (
                <option key={b.id} value={b.id}>{b.batch_name}</option>
              ))}
            </select>
            <ChevronDown size={14} className="absolute right-2.5 top-1/2 -translate-y-1/2 pointer-events-none" style={{ color: "var(--color-text-muted)" }} />
          </div>

          {(search || department || batchFilter) && (
            <button
              onClick={() => { setSearch(""); setDepartment(""); setBatchFilter(""); setPage(1); }}
              className="ml-auto text-xs font-medium px-3 py-1.5 rounded-lg transition-colors"
              style={{ color: "var(--color-text-muted)", background: "var(--color-surface-secondary)", border: "1px solid var(--color-border)" }}
              onMouseEnter={e => { (e.currentTarget as HTMLButtonElement).style.color = "var(--color-danger)"; (e.currentTarget as HTMLButtonElement).style.borderColor = "var(--color-danger)"; }}
              onMouseLeave={e => { (e.currentTarget as HTMLButtonElement).style.color = "var(--color-text-muted)"; (e.currentTarget as HTMLButtonElement).style.borderColor = "var(--color-border)"; }}
            >
              Clear filters
            </button>
          )}
        </div>

        {!loading && totalCount === 0 && !search && !department ? (
          <EmptyState
            icon={Users}
            title="No Students Yet"
            subtitle="Add students to get started."
            action={{ label: "+ Add Student", onClick: openAdd }}
          />
        ) : (
          <StudentTable
            students={students}
            loading={loading}
            totalCount={totalCount}
            page={page}
            onPageChange={setPage}
            onStudentUpdated={(updated) =>
              setStudents((prev) =>
                prev.map((s) => (s.id === updated.id ? updated : s))
              )
            }
            onStudentDeleted={(id) => {
              setStudents((prev) => prev.filter((s) => s.id !== id));
              setTotalCount((c) => c - 1);
            }}
            showBatchColumn
            batches={batches}
            totalPages={totalPages}
          />
        )}
      </PageWrapper>

      {/* Bulk Import Modal */}
      <BulkImportModal
        isOpen={showBulkImport}
        onClose={() => setShowBulkImport(false)}
        onImportComplete={fetchStudents}
        batches={batches}
      />

      {/* Add Student Modal */}
      <Modal
        isOpen={showAdd}
        onClose={() => setShowAdd(false)}
        title="Add Student"
      >
        <form onSubmit={handleSubmit(onAddSubmit)}>
          <div className="space-y-4">
            <Input
              label="Student ID"
              placeholder="e.g. A23126551030"
              error={errors.student_id?.message}
              {...register("student_id", {
                required: "Student ID is required.",
              })}
            />
            <Select
              label="Department"
              placeholder="Select department"
              options={DEPARTMENTS.map((d) => ({ value: d, label: d }))}
              error={errors.department?.message}
              {...register("department", {
                required: "Department is required.",
              })}
            />
            <Select
              label="Batch"
              placeholder="Select batch"
              options={batchOptions}
              error={errors.batch_id?.message}
              {...register("batch_id", { required: "Batch is required." })}
            />
          </div>
          <div className="flex justify-end gap-3 mt-5">
            <Button
              variant="secondary"
              type="button"
              onClick={() => setShowAdd(false)}
            >
              Cancel
            </Button>
            <Button type="submit" loading={addLoading}>
              Create student
            </Button>
          </div>
        </form>
      </Modal>
    </AdminLayout>
  );
}
