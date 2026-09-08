"use client";

import { useEffect, useState, useCallback } from "react";
import { useSearchParams } from "next/navigation";
import { GraduationCap, ChevronDown } from "lucide-react";
import { PageWrapper } from "@/components/layout/PageWrapper";
import { PageHeader } from "@/components/layout/PageHeader";
import { EmptyState } from "@/components/ui/EmptyState";
import { SearchInput } from "@/components/ui/SearchInput";
import { Pagination } from "@/components/ui/Pagination";
import api, { getErrorMessage } from "@/lib/api";
import { useDepartments } from "@/lib/departmentsContext";
import type { PaginatedResponse, Batch } from "@/types";

// ── Types ──────────────────────────────────────────────────────────────────────

interface StudentRecord {
  id: string;
  student_id: string;
  fullname: string;
  college_email_id: string;
  department: string;
  batch_name?: string;
  batch_id?: string;
  created_at: string;
}

// ── Skeleton ───────────────────────────────────────────────────────────────────

function TableSkeleton() {
  return (
    <div className="animate-pulse space-y-3">
      {Array.from({ length: 8 }).map((_, i) => (
        <div
          key={i}
          className="h-14 rounded-xl"
          style={{ background: "var(--color-surface-secondary)" }}
        />
      ))}
    </div>
  );
}

// ── Page ───────────────────────────────────────────────────────────────────────

export default function SuperAdminStudentsPage() {
  const { departments } = useDepartments();
  const searchParams = useSearchParams();
  const [students, setStudents] = useState<StudentRecord[]>([]);
  const [batches, setBatches] = useState<Batch[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [totalCount, setTotalCount] = useState(0);
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  const [search, setSearch] = useState("");
  const [department, setDepartment] = useState("");
  // Pre-filled when arriving from a Batches card's "View students" link
  // (/super-admin/students?batch_id=<id>) — read once on mount, same as
  // any other initial-state seed; the filter dropdown remains fully
  // interactive afterwards.
  const [batchFilter, setBatchFilter] = useState(() => searchParams.get("batch_id") ?? "");

  // Fetch batches for filter dropdown
  useEffect(() => {
    api
      .get<{ data: Batch[] }>("/users/batches/")
      .then(({ data }) => setBatches(data.data ?? []))
      .catch(() => {});
  }, []);

  const fetchStudents = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const params = new URLSearchParams();
      params.set("page", String(page));
      if (search) params.set("search", search);
      if (department) params.set("department", department);
      if (batchFilter) params.set("batch_id", batchFilter);

      const res = await api.get<PaginatedResponse<StudentRecord>>(
        `/users/students/?${params}`
      );
      setStudents(res.data.results);
      setTotalCount(res.data.count);
      setTotalPages(res.data.total_pages ?? Math.ceil(res.data.count / 50));
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setLoading(false);
    }
  }, [page, search, department, batchFilter]);

  useEffect(() => { fetchStudents(); }, [fetchStudents]);

  // SearchInput component handles 300ms debounce internally
  function handleSearch(val: string) {
    setSearch(val);
    setPage(1);
  }

  function handleDeptChange(e: React.ChangeEvent<HTMLSelectElement>) {
    setDepartment(e.target.value);
    setPage(1);
  }

  function handleBatchChange(e: React.ChangeEvent<HTMLSelectElement>) {
    setBatchFilter(e.target.value);
    setPage(1);
  }

  const hasFilters = !!(search || department || batchFilter);

  return (
    <PageWrapper>
      <PageHeader
        title="Students"
        subtitle={`${totalCount.toLocaleString()} ${totalCount === 1 ? "student" : "students"} · Read only`}
      />

      {/* Filter toolbar */}
      <div
        className="flex flex-wrap items-center gap-3 rounded-xl px-4 py-3 mb-5"
        style={{ background: "#fff", border: "1px solid var(--color-border)", boxShadow: "var(--shadow-sm)" }}
      >
        <SearchInput
          value={search}
          placeholder="Search by name or email..."
          onChange={handleSearch}
          className="w-64 shrink-0"
        />

        <div className="hidden sm:block self-stretch w-px" style={{ background: "var(--color-border)" }} />

        {/* Department filter */}
        <div className="relative shrink-0">
          <select
            value={department}
            onChange={handleDeptChange}
            className="h-9 pl-3 pr-8 text-sm rounded-[var(--radius-md)] border bg-white appearance-none cursor-pointer focus:outline-none focus:ring-2 focus:ring-[var(--color-accent)]"
            style={{ borderColor: "var(--color-border)", color: "var(--color-text)", width: 170 }}
          >
            <option value="">All departments</option>
            {departments.map((d) => (
              <option key={d.id} value={d.code}>{d.name || d.code}</option>
            ))}
          </select>
          <ChevronDown size={14} className="absolute right-2.5 top-1/2 -translate-y-1/2 pointer-events-none" style={{ color: "var(--color-text-muted)" }} />
        </div>

        <div className="hidden sm:block self-stretch w-px" style={{ background: "var(--color-border)" }} />

        {/* Batch filter */}
        <div className="relative shrink-0">
          <select
            value={batchFilter}
            onChange={handleBatchChange}
            className="h-9 pl-3 pr-8 text-sm rounded-[var(--radius-md)] border bg-white appearance-none cursor-pointer focus:outline-none focus:ring-2 focus:ring-[var(--color-accent)]"
            style={{ borderColor: "var(--color-border)", color: "var(--color-text)", width: 170 }}
          >
            <option value="">All batches</option>
            {batches.map((b) => (
              <option key={b.id} value={b.id}>{b.batch_name}</option>
            ))}
          </select>
          <ChevronDown size={14} className="absolute right-2.5 top-1/2 -translate-y-1/2 pointer-events-none" style={{ color: "var(--color-text-muted)" }} />
        </div>

        {/* Always rendered — visibility toggle prevents toolbar reflow */}
        <button
          onClick={() => { setSearch(""); setDepartment(""); setBatchFilter(""); setPage(1); }}
          className="ml-auto text-xs font-medium px-3 py-1.5 rounded-lg transition-colors"
          style={{
            color: "var(--color-text-muted)",
            background: "var(--color-surface-secondary)",
            border: "1px solid var(--color-border)",
            visibility: hasFilters ? "visible" : "hidden",
            pointerEvents: hasFilters ? "auto" : "none",
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
      </div>

      {/* Error */}
      {error && !loading && (
        <div
          className="rounded-2xl p-5 flex items-center justify-between mb-5"
          style={{ background: "var(--color-danger-bg)", border: "1px solid var(--color-danger)20" }}
        >
          <p className="text-sm" style={{ color: "var(--color-danger)" }}>{error}</p>
          <button
            onClick={fetchStudents}
            className="text-sm font-semibold px-4 py-2 rounded-lg"
            style={{ background: "var(--color-danger)", color: "#fff" }}
          >
            Retry
          </button>
        </div>
      )}

      {/* Table */}
      {loading ? (
        <TableSkeleton />
      ) : students.length === 0 && !error ? (
        <EmptyState
          icon={GraduationCap}
          title="No Students Found"
          subtitle={
            hasFilters
              ? "No students match the current filters."
              : "No students have been added yet."
          }
        />
      ) : (
        <div
          className="rounded-2xl overflow-hidden"
          style={{ background: "#fff", border: "1px solid var(--color-border)", boxShadow: "var(--shadow-sm)" }}
        >
          <table className="w-full">
            <thead>
              <tr style={{ borderBottom: "1px solid var(--color-border)", background: "var(--color-surface-secondary)" }}>
                {["Name", "Email", "Batch", "Department", "Enrolled"].map((h) => (
                  <th
                    key={h}
                    className="px-5 py-3 text-left text-xs font-semibold tracking-wide"
                    style={{ color: "var(--color-text-muted)" }}
                  >
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {students.map((student, idx) => (
                <tr
                  key={student.id}
                  style={{
                    borderBottom: idx < students.length - 1 ? "1px solid var(--color-border)" : "none",
                  }}
                >
                  <td className="px-5 py-4">
                    <div className="flex items-center gap-3">
                      <span
                        className="flex items-center justify-center rounded-full text-xs font-bold shrink-0"
                        style={{
                          width: 30,
                          height: 30,
                          background: "var(--color-accent-light)",
                          color: "var(--color-accent)",
                        }}
                      >
                        {(student.fullname || student.student_id).charAt(0).toUpperCase()}
                      </span>
                      <div>
                        <p className="text-sm font-semibold" style={{ color: "var(--color-text)" }}>
                          {student.fullname || "—"}
                        </p>
                        <p className="text-xs" style={{ color: "var(--color-text-subtle)" }}>
                          {student.student_id}
                        </p>
                      </div>
                    </div>
                  </td>
                  <td className="px-5 py-4 text-sm max-w-[200px] truncate" style={{ color: "var(--color-text-muted)" }}>
                    {student.college_email_id || "—"}
                  </td>
                  <td className="px-5 py-4 text-sm" style={{ color: "var(--color-text-muted)" }}>
                    {student.batch_name || "—"}
                  </td>
                  <td className="px-5 py-4">
                    <span
                      className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium"
                      style={{ background: "var(--color-primary-light)", color: "var(--color-primary)" }}
                    >
                      {student.department || "—"}
                    </span>
                  </td>
                  <td className="px-5 py-4 text-sm" style={{ color: "var(--color-text-muted)" }}>
                    {student.created_at
                      ? new Date(student.created_at).toLocaleDateString("en-IN", {
                          day: "2-digit",
                          month: "short",
                          year: "numeric",
                        })
                      : "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>

          <Pagination
            page={page}
            totalPages={totalPages}
            onPageChange={setPage}
            totalCount={totalCount}
          />
        </div>
      )}
    </PageWrapper>
  );
}
