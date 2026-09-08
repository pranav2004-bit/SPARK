"use client";

import { useEffect, useState, useCallback } from "react";
import { useParams } from "next/navigation";
import { ChevronDown } from "lucide-react";
import { PageWrapper } from "@/components/layout/PageWrapper";
import { PageHeader } from "@/components/layout/PageHeader";
import { SearchInput } from "@/components/ui/SearchInput";
import { StudentTable } from "@/components/admin/StudentTable";
import { useToast } from "@/components/ui/Toast";
import api, { getErrorMessage } from "@/lib/api";
import { useDepartments } from "@/lib/departmentsContext";
import type { Batch, Student, PaginatedResponse, ApiSuccess } from "@/types";

// Students module removed from Super Admin (2026-08-19) — mirrors
// admin/batch/[batch_id]/page.tsx exactly: a batch's own roster stays part
// of the read-only Batches module (AdminBatchStudentsView, unaffected by
// the Students removal). No layout wrapper here — super-admin/* uses the
// file-based layout.tsx (Pattern B), unlike admin/* (Pattern A).

export default function SuperAdminBatchDetailPage() {
  const { batch_id } = useParams<{ batch_id: string }>();
  const { error: toastError } = useToast();
  const { departments } = useDepartments();
  const DEPT_OPTIONS = [
    { value: "", label: "All departments" },
    ...departments.map((d) => ({ value: d.code, label: d.name || d.code })),
  ];

  const [batch, setBatch] = useState<Batch | null>(null);
  const [students, setStudents] = useState<Student[]>([]);
  const [totalCount, setTotalCount] = useState(0);
  const [totalPages, setTotalPages] = useState(1);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState(false);
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState("");
  const [department, setDepartment] = useState("");

  const fetchStudents = useCallback(async () => {
    setLoading(true);
    setLoadError(false);
    try {
      const params = new URLSearchParams();
      params.set("page", String(page));
      if (search) params.set("search", search);
      if (department) params.set("department", department);

      const { data } = await api.get<PaginatedResponse<Student>>(
        `/users/batches/${batch_id}/students/?${params}`
      );
      setStudents(data.results);
      setTotalCount(data.count);
      setTotalPages(data.total_pages ?? Math.ceil(data.count / 50));
    } catch (err) {
      toastError(getErrorMessage(err));
      setLoadError(true);
    } finally {
      setLoading(false);
    }
  }, [batch_id, page, search, department, toastError]);

  // Fetch batch name once
  useEffect(() => {
    api
      .get<ApiSuccess<Batch>>(`/users/batches/${batch_id}/`)
      .then(({ data }) => setBatch(data.data))
      .catch(() => {});
  }, [batch_id]);

  useEffect(() => {
    fetchStudents();
  }, [fetchStudents]);

  function handleSearch(val: string) {
    setSearch(val);
    setPage(1);
  }

  function handleDeptChange(e: React.ChangeEvent<HTMLSelectElement>) {
    setDepartment(e.target.value);
    setPage(1);
  }

  return (
    <PageWrapper>
      <PageHeader
        title={batch?.batch_name ?? "Batch"}
        subtitle={`${totalCount} ${totalCount === 1 ? "student" : "students"} · Read only`}
        backHref="/super-admin/batches"
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
            style={{
              borderColor: "var(--color-border)",
              color: "var(--color-text)",
              width: 176,
            }}
          >
            {DEPT_OPTIONS.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </select>
          <ChevronDown
            size={14}
            className="absolute right-2.5 top-1/2 -translate-y-1/2 pointer-events-none"
            style={{ color: "var(--color-text-muted)" }}
          />
        </div>

        {/* Clear filters — only when active */}
        {(search || department) && (
          <button
            onClick={() => { setSearch(""); setDepartment(""); setPage(1); }}
            className="ml-auto text-xs font-medium px-3 py-1.5 rounded-lg transition-colors"
            style={{
              color: "var(--color-text-muted)",
              background: "var(--color-surface-secondary)",
              border: "1px solid var(--color-border)",
            }}
            onMouseEnter={e => {
              (e.currentTarget as HTMLButtonElement).style.color = "var(--color-danger)";
              (e.currentTarget as HTMLButtonElement).style.borderColor = "var(--color-danger)";
            }}
            onMouseLeave={e => {
              (e.currentTarget as HTMLButtonElement).style.color = "var(--color-text-muted)";
              (e.currentTarget as HTMLButtonElement).style.borderColor = "var(--color-border)";
            }}
          >
            Clear filters
          </button>
        )}
      </div>

      <StudentTable
        students={students}
        loading={loading}
        loadError={loadError}
        onRetry={fetchStudents}
        totalCount={totalCount}
        totalPages={totalPages}
        page={page}
        onPageChange={setPage}
        onStudentUpdated={() => {}}
        onStudentDeleted={() => {}}
        showBatchColumn={false}
        readOnly
      />
    </PageWrapper>
  );
}
