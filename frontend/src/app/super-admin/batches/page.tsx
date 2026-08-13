"use client";

import { useEffect, useState, useCallback } from "react";
import { Layers, ChevronDown } from "lucide-react";
import { PageWrapper } from "@/components/layout/PageWrapper";
import { PageHeader } from "@/components/layout/PageHeader";
import { EmptyState } from "@/components/ui/EmptyState";
import { Pagination } from "@/components/ui/Pagination";
import api, { getErrorMessage } from "@/lib/api";
import { DEPARTMENTS } from "@/lib/constants";
import type { ApiSuccess } from "@/types";

// ── Types ──────────────────────────────────────────────────────────────────────

interface BatchRecord {
  id: string;
  batch_name: string;
  department: string;
  student_count: number;
  assigned_admin_name?: string;
  created_at: string;
}

const PAGE_SIZE = 50;

// ── Skeleton ───────────────────────────────────────────────────────────────────

function TableSkeleton() {
  return (
    <div className="animate-pulse space-y-3">
      {Array.from({ length: 6 }).map((_, i) => (
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

export default function SuperAdminBatchesPage() {
  const [allBatches, setAllBatches] = useState<BatchRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [page, setPage] = useState(1);
  const [department, setDepartment] = useState("");

  const fetchBatches = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const res = await api.get<ApiSuccess<BatchRecord[]>>("/users/batches/");
      setAllBatches(res.data.data);
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchBatches(); }, [fetchBatches]);

  const filtered = department
    ? allBatches.filter((b) => b.department === department)
    : allBatches;

  const totalCount = filtered.length;
  const totalPages = Math.max(1, Math.ceil(totalCount / PAGE_SIZE));
  const batches = filtered.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE);

  function handleDeptChange(e: React.ChangeEvent<HTMLSelectElement>) {
    setDepartment(e.target.value);
    setPage(1);
  }

  function handlePageChange(p: number) {
    setPage(p);
  }

  return (
    <PageWrapper>
      <PageHeader
        title="Batches"
        subtitle={`${totalCount.toLocaleString()} ${totalCount === 1 ? "batch" : "batches"} · Read only`}
      />

      {/* Filter toolbar */}
      <div
        className="flex flex-wrap items-center gap-3 rounded-xl px-4 py-3 mb-5"
        style={{ background: "#fff", border: "1px solid var(--color-border)", boxShadow: "var(--shadow-sm)" }}
      >
        <div className="relative">
          <select
            value={department}
            onChange={handleDeptChange}
            className="h-9 pl-3 pr-8 text-sm rounded-[var(--radius-md)] border bg-white appearance-none cursor-pointer focus:outline-none focus:ring-2 focus:ring-[var(--color-accent)]"
            style={{ borderColor: "var(--color-border)", color: "var(--color-text)", minWidth: 180 }}
          >
            <option value="">All departments</option>
            {DEPARTMENTS.map((d) => (
              <option key={d} value={d}>{d}</option>
            ))}
          </select>
          <ChevronDown size={14} className="absolute right-2.5 top-1/2 -translate-y-1/2 pointer-events-none" style={{ color: "var(--color-text-muted)" }} />
        </div>

        {department && (
          <button
            onClick={() => { setDepartment(""); setPage(1); }}
            className="text-xs font-medium px-3 py-1.5 rounded-lg transition-colors"
            style={{ color: "var(--color-text-muted)", background: "var(--color-surface-secondary)", border: "1px solid var(--color-border)" }}
          >
            Clear filter
          </button>
        )}
      </div>

      {/* Error */}
      {error && !loading && (
        <div
          className="rounded-2xl p-5 flex items-center justify-between mb-5"
          style={{ background: "var(--color-danger-bg)", border: "1px solid var(--color-danger)20" }}
        >
          <p className="text-sm" style={{ color: "var(--color-danger)" }}>{error}</p>
          <button
            onClick={fetchBatches}
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
      ) : batches.length === 0 && !error ? (
        <EmptyState
          icon={Layers}
          title="No Batches Found"
          subtitle={department ? `No batches in the ${department} department.` : "No batches have been created yet."}
        />
      ) : (
        <div
          className="rounded-2xl overflow-hidden"
          style={{ background: "#fff", border: "1px solid var(--color-border)", boxShadow: "var(--shadow-sm)" }}
        >
          <table className="w-full">
            <thead>
              <tr style={{ borderBottom: "1px solid var(--color-border)", background: "var(--color-surface-secondary)" }}>
                {["Batch Name", "Department", "Students", "Assigned Admin"].map((h) => (
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
              {batches.map((batch, idx) => (
                <tr
                  key={batch.id}
                  style={{
                    borderBottom: idx < batches.length - 1 ? "1px solid var(--color-border)" : "none",
                  }}
                >
                  <td className="px-5 py-4">
                    <span className="text-sm font-semibold" style={{ color: "var(--color-text)" }}>
                      {batch.batch_name}
                    </span>
                  </td>
                  <td className="px-5 py-4">
                    <span
                      className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium"
                      style={{
                        background: "var(--color-primary-light)",
                        color: "var(--color-primary)",
                      }}
                    >
                      {batch.department || "—"}
                    </span>
                  </td>
                  <td className="px-5 py-4 text-sm" style={{ color: "var(--color-text-muted)" }}>
                    {(batch.student_count ?? 0).toLocaleString()}
                  </td>
                  <td className="px-5 py-4 text-sm" style={{ color: "var(--color-text-muted)" }}>
                    {batch.assigned_admin_name ?? "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>

          <Pagination
            page={page}
            totalPages={totalPages}
            onPageChange={handlePageChange}
            totalCount={totalCount}
          />
        </div>
      )}
    </PageWrapper>
  );
}
