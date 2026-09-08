"use client";

import { useEffect, useState, useCallback } from "react";
import { useRouter } from "next/navigation";
import { LayoutDashboard, Users, ChevronRight, AlertTriangle } from "lucide-react";
import { AdminLayout } from "@/components/layout/AdminLayout";
import { PageWrapper } from "@/components/layout/PageWrapper";
import { PageHeader } from "@/components/layout/PageHeader";
import { EmptyState } from "@/components/ui/EmptyState";
import { CardSkeleton } from "@/components/ui/Skeleton";
import { useToast } from "@/components/ui/Toast";
import api, { getErrorMessage } from "@/lib/api";
import type { Batch, ApiSuccess } from "@/types";

// Read/query-only (2026-08-19) — batch creation, editing, and deletion are
// IT-exclusive; see /it/batch for the management interface.

export default function BatchPage() {
  const router = useRouter();
  const { error: toastError } = useToast();

  const [batches, setBatches] = useState<Batch[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState(false);

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

  return (
    <AdminLayout>
      <PageWrapper>
        <PageHeader title="Batch Management" subtitle="View only — managed by IT" />

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
            subtitle="Batches are created by IT — none exist yet."
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
        )}
      </PageWrapper>
    </AdminLayout>
  );
}
