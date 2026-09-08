"use client";

import { useEffect, useState, useCallback } from "react";
import { useRouter } from "next/navigation";
import { LayoutDashboard, Users, ChevronRight } from "lucide-react";
import { PageWrapper } from "@/components/layout/PageWrapper";
import { PageHeader } from "@/components/layout/PageHeader";
import { EmptyState } from "@/components/ui/EmptyState";
import { CardSkeleton } from "@/components/ui/Skeleton";
import { Pagination } from "@/components/ui/Pagination";
import api, { getErrorMessage } from "@/lib/api";
import type { ApiSuccess } from "@/types";

// Card-grid layout (2026-08-19) — matches the Batches interface Admin and IT
// already use (admin/batch/page.tsx, it/batch/page.tsx), for a consistent
// look across every read-only or full-CRUD Batches view in the app. This
// replaced an older table layout whose Department/Assigned Admin columns
// never had real data behind them (Batch has no such fields — department
// lives on Student) and whose department filter was consequently dead code.
// "View students" routes into super-admin/batches/[batch_id] — a batch's
// roster stays part of the read-only Batches module now that the standalone
// Students module was removed from Super Admin (2026-08-19), same reasoning
// as Admin.

interface BatchRecord {
  id: string;
  batch_name: string;
  student_count: number;
  created_at: string;
}

const PAGE_SIZE = 50;

export default function SuperAdminBatchesPage() {
  const router = useRouter();
  const [allBatches, setAllBatches] = useState<BatchRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [page, setPage] = useState(1);

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

  const totalCount = allBatches.length;
  const totalPages = Math.max(1, Math.ceil(totalCount / PAGE_SIZE));
  const batches = allBatches.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE);

  return (
    <PageWrapper>
      <PageHeader
        title="Batches"
        subtitle={`${totalCount.toLocaleString()} ${totalCount === 1 ? "batch" : "batches"} · Read only`}
      />

      {error && !loading ? (
        <EmptyState
          icon={LayoutDashboard}
          title="Couldn't load batches"
          subtitle={error}
          action={{ label: "Retry", onClick: fetchBatches }}
        />
      ) : loading ? (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {Array.from({ length: 6 }).map((_, i) => (
            <CardSkeleton key={i} />
          ))}
        </div>
      ) : batches.length === 0 ? (
        <EmptyState
          icon={LayoutDashboard}
          title="No Batches Yet"
          subtitle="No batches have been created yet."
        />
      ) : (
        <>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-5">
            {batches.map((batch) => (
              <div
                key={batch.id}
                onClick={() => router.push(`/super-admin/batches/${batch.id}`)}
                className="bg-white border border-[var(--color-border)] rounded-xl cursor-pointer hover:shadow-[var(--shadow-md)] hover:border-[var(--color-border-strong)] transition-all duration-200 overflow-hidden"
              >
                {/* Card body */}
                <div className="p-5">
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

          {totalPages > 1 && (
            <div className="mt-5">
              <Pagination
                page={page}
                totalPages={totalPages}
                onPageChange={setPage}
                totalCount={totalCount}
                pageSize={PAGE_SIZE}
              />
            </div>
          )}
        </>
      )}
    </PageWrapper>
  );
}
