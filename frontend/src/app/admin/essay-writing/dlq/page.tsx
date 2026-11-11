"use client";

import { useEffect, useState, useCallback } from "react";
import { useRouter } from "next/navigation";
import { RefreshCcw, CheckCircle2, AlertTriangle, Eye } from "lucide-react";
import { AdminLayout } from "@/components/layout/AdminLayout";
import { PageWrapper } from "@/components/layout/PageWrapper";
import { PageHeader } from "@/components/layout/PageHeader";
import { Button } from "@/components/ui/Button";
import { Select } from "@/components/ui/Select";
import { Modal } from "@/components/ui/Modal";
import { Pagination } from "@/components/ui/Pagination";
import { Skeleton, TableRowSkeleton } from "@/components/ui/Skeleton";
import { EmptyState } from "@/components/ui/EmptyState";
import { useToast } from "@/components/ui/Toast";
import api, { getErrorMessage } from "@/lib/api";
import type { ApiSuccess, PaginatedResponse, EssayDLQEntryRow, EssayDLQBulkRetryResult } from "@/types";

const RESOLVED_FILTER_OPTIONS = [
  { value: "false", label: "Unresolved" },
  { value: "true", label: "Resolved" },
  { value: "all", label: "All" },
];

function StatusPill({ resolved }: { resolved: boolean }) {
  return resolved ? (
    <span className="text-[11px] font-semibold px-2 py-0.5 rounded-full" style={{ background: "#F3F4F6", color: "#6B7280" }}>
      Resolved
    </span>
  ) : (
    <span className="text-[11px] font-semibold px-2 py-0.5 rounded-full" style={{ background: "#FEF2F2", color: "#DC2626" }}>
      Unresolved
    </span>
  );
}

function formatDateTime(iso: string | null): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
}

// Same "no dedicated Textarea component" reasoning as every other
// mandatory-reason modal in this module (Reports, Submissions detail) —
// kept local since each page's own copy is this small.
function ReasonField({ value, onChange, placeholder }: { value: string; onChange: (v: string) => void; placeholder?: string }) {
  return (
    <textarea
      value={value}
      onChange={e => onChange(e.target.value)}
      placeholder={placeholder}
      rows={3}
      className="w-full rounded-[var(--radius-md)] border px-3 py-2 text-sm outline-none transition-colors resize-none"
      style={{ borderColor: "var(--color-border)", color: "var(--color-text)" }}
    />
  );
}

export default function AdminDLQPage() {
  const router = useRouter();
  const toast = useToast();

  const [rows, setRows] = useState<EssayDLQEntryRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState(false);
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  const [totalCount, setTotalCount] = useState(0);

  const [resolvedFilter, setResolvedFilter] = useState("false");

  const [actionTarget, setActionTarget] = useState<{ row: EssayDLQEntryRow; kind: "retry" | "resolve" } | null>(null);
  const [actionReason, setActionReason] = useState("");
  const [actionSubmitting, setActionSubmitting] = useState(false);

  const [bulkOpen, setBulkOpen] = useState(false);
  const [bulkPreview, setBulkPreview] = useState<EssayDLQBulkRetryResult | null>(null);
  const [bulkPreviewLoading, setBulkPreviewLoading] = useState(false);
  const [bulkReason, setBulkReason] = useState("");
  const [bulkSending, setBulkSending] = useState(false);

  const loadRows = useCallback(() => {
    setLoading(true);
    setLoadError(false);
    const params = new URLSearchParams({ page: String(page), resolved: resolvedFilter });
    api.get<PaginatedResponse<EssayDLQEntryRow>>(`/essay/admin/dlq/?${params}`)
      .then(res => {
        setRows(res.data.results);
        setTotalPages(res.data.total_pages);
        setTotalCount(res.data.count);
      })
      .catch(err => { toast.error(getErrorMessage(err)); setLoadError(true); })
      .finally(() => setLoading(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [page, resolvedFilter]);

  useEffect(loadRows, [loadRows]);
  useEffect(() => { setPage(1); }, [resolvedFilter]);

  function openAction(row: EssayDLQEntryRow, kind: "retry" | "resolve") {
    setActionTarget({ row, kind });
    setActionReason("");
  }

  async function submitAction() {
    if (!actionTarget) return;
    if (!actionReason.trim()) {
      toast.error(`A reason is required to ${actionTarget.kind} a DLQ entry.`);
      return;
    }
    setActionSubmitting(true);
    try {
      const path = actionTarget.kind === "retry"
        ? `/essay/admin/dlq/${actionTarget.row.id}/retry/`
        : `/essay/admin/dlq/${actionTarget.row.id}/resolve/`;
      const res = await api.post<ApiSuccess<null>>(path, { reason: actionReason.trim() });
      toast.success(res.data.message ?? "Done.");
      setActionTarget(null);
      loadRows();
    } catch (err) {
      toast.error(getErrorMessage(err));
    } finally {
      setActionSubmitting(false);
    }
  }

  function openBulkRetry() {
    setBulkOpen(true);
    setBulkPreview(null);
    setBulkReason("");
    setBulkPreviewLoading(true);
    api.post<ApiSuccess<EssayDLQBulkRetryResult>>("/essay/admin/dlq/bulk-retry/", { dry_run: true })
      .then(res => setBulkPreview(res.data.data))
      .catch(err => { toast.error(getErrorMessage(err)); setBulkOpen(false); })
      .finally(() => setBulkPreviewLoading(false));
  }

  async function confirmBulkRetry() {
    if (!bulkReason.trim()) {
      toast.error("A reason is required to bulk-retry DLQ entries.");
      return;
    }
    setBulkSending(true);
    try {
      const res = await api.post<ApiSuccess<EssayDLQBulkRetryResult>>(
        "/essay/admin/dlq/bulk-retry/", { dry_run: false, reason: bulkReason.trim() },
      );
      toast.success(`Retried ${res.data.data.dispatched_count ?? 0} entrie(s).`);
      setBulkOpen(false);
      loadRows();
    } catch (err) {
      toast.error(getErrorMessage(err));
    } finally {
      setBulkSending(false);
    }
  }

  return (
    <AdminLayout>
      <PageWrapper>
        <PageHeader
          title="DLQ"
          subtitle="Failed background jobs — LLM evaluation, report generation, and more — awaiting retry or manual resolution."
          backHref="/admin/essay-writing"
          rightSlot={
            <Button variant="secondary" leftIcon={<RefreshCcw size={14} />} onClick={openBulkRetry}>
              Bulk retry
            </Button>
          }
        />

        <div className="mb-4 max-w-xs">
          <Select
            value={resolvedFilter}
            onChange={e => setResolvedFilter(e.target.value)}
            options={RESOLVED_FILTER_OPTIONS}
          />
        </div>

        <div className="rounded-[var(--radius-xl)] overflow-hidden" style={{ background: "var(--color-surface)", border: "1px solid var(--color-border)" }}>
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b" style={{ borderColor: "var(--color-border)" }}>
                <th className="text-left px-4 py-3 font-semibold text-xs" style={{ color: "var(--color-text-subtle)" }}>Task</th>
                <th className="text-left px-4 py-3 font-semibold text-xs" style={{ color: "var(--color-text-subtle)" }}>Error</th>
                <th className="text-left px-4 py-3 font-semibold text-xs" style={{ color: "var(--color-text-subtle)" }}>Attempts</th>
                <th className="text-left px-4 py-3 font-semibold text-xs" style={{ color: "var(--color-text-subtle)" }}>Created</th>
                <th className="text-left px-4 py-3 font-semibold text-xs" style={{ color: "var(--color-text-subtle)" }}>Status</th>
                <th className="text-right px-4 py-3 font-semibold text-xs" style={{ color: "var(--color-text-subtle)" }}>Actions</th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                Array.from({ length: 6 }).map((_, i) => <TableRowSkeleton key={i} cols={6} />)
              ) : rows.length === 0 && !loadError ? (
                <tr>
                  <td colSpan={6}>
                    <EmptyState icon={CheckCircle2} title="No DLQ entries" subtitle="Nothing is stuck right now." />
                  </td>
                </tr>
              ) : loadError ? (
                <tr>
                  <td colSpan={6}>
                    <EmptyState icon={AlertTriangle} title="Couldn't load the DLQ" subtitle="Please try again." />
                  </td>
                </tr>
              ) : (
                rows.map(row => (
                  <tr
                    key={row.id}
                    onClick={() => router.push(`/admin/essay-writing/dlq/${row.id}`)}
                    className="border-b last:border-b-0 cursor-pointer"
                    style={{ borderColor: "var(--color-border)" }}
                    onMouseEnter={e => { e.currentTarget.style.background = "var(--color-surface-subtle)"; }}
                    onMouseLeave={e => { e.currentTarget.style.background = ""; }}
                  >
                    <td className="px-4 py-3 font-mono text-xs" style={{ color: "var(--color-text)" }}>{row.task_name}</td>
                    <td className="px-4 py-3 truncate max-w-xs" style={{ color: "var(--color-text-subtle)" }}>{row.error}</td>
                    <td className="px-4 py-3" style={{ color: "var(--color-text)" }}>{row.attempts}</td>
                    <td className="px-4 py-3 text-xs" style={{ color: "var(--color-text-subtle)" }}>{formatDateTime(row.created_at)}</td>
                    <td className="px-4 py-3"><StatusPill resolved={row.resolved} /></td>
                    <td className="px-4 py-3" onClick={e => e.stopPropagation()}>
                      <div className="flex items-center justify-end gap-1.5">
                        <Button variant="ghost" size="sm" leftIcon={<Eye size={12} />} onClick={() => router.push(`/admin/essay-writing/dlq/${row.id}`)}>
                          View
                        </Button>
                        <Button
                          variant="ghost" size="sm" leftIcon={<RefreshCcw size={12} />}
                          disabled={row.resolved}
                          onClick={() => openAction(row, "retry")}
                        >
                          Retry
                        </Button>
                        <Button
                          variant="ghost" size="sm" leftIcon={<CheckCircle2 size={12} />}
                          disabled={row.resolved}
                          onClick={() => openAction(row, "resolve")}
                        >
                          Resolve
                        </Button>
                      </div>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
          <Pagination page={page} totalPages={totalPages} onPageChange={setPage} totalCount={totalCount} pageSize={30} />
        </div>

        {/* Retry/Resolve modal — mandatory reason, matching every other
            admin action modal in this service (Retrigger, Override,
            Regenerate). */}
        <Modal
          isOpen={!!actionTarget}
          onClose={() => !actionSubmitting && setActionTarget(null)}
          title={actionTarget?.kind === "retry" ? "Retry DLQ Entry" : "Resolve DLQ Entry"}
          maxWidth="sm"
        >
          <div className="space-y-3">
            <p className="text-sm" style={{ color: "var(--color-text-subtle)" }}>
              {actionTarget?.kind === "retry"
                ? "This re-dispatches the exact original task. A reason is required for the audit log."
                : "This marks the entry done WITHOUT retrying — use this once you've handled it another way. A reason is required for the audit log."}
            </p>
            <ReasonField value={actionReason} onChange={setActionReason} placeholder="Why?" />
            <div className="flex justify-end gap-2 pt-2">
              <Button variant="secondary" size="sm" onClick={() => setActionTarget(null)} disabled={actionSubmitting}>Cancel</Button>
              <Button variant="primary" size="sm" loading={actionSubmitting} onClick={submitAction}>
                {actionTarget?.kind === "retry" ? "Retry" : "Resolve"}
              </Button>
            </div>
          </div>
        </Modal>

        {/* Bulk retry modal — dry-run preview shown first (Task 11.2's
            own default-safe pattern, explicitly named for reuse here too),
            a real retry only ever happens after this explicit second
            confirmation, with its own mandatory reason. */}
        <Modal isOpen={bulkOpen} onClose={() => !bulkSending && setBulkOpen(false)} title="Bulk Retry DLQ Entries" maxWidth="sm">
          <div className="space-y-3">
            {bulkPreviewLoading || !bulkPreview ? (
              <Skeleton className="h-20 w-full" />
            ) : (
              <>
                <p className="text-sm" style={{ color: "var(--color-text)" }}>
                  This will retry <strong>{bulkPreview.would_dispatch_count ?? 0}</strong> unresolved entrie(s)
                  {bulkPreview.capped && <> (capped from {bulkPreview.total_matching} matching)</>}, oldest first.
                </p>
                {bulkPreview.sample && bulkPreview.sample.length > 0 && (
                  <ul className="text-xs space-y-0.5 max-h-32 overflow-y-auto" style={{ color: "var(--color-text-subtle)" }}>
                    {bulkPreview.sample.map(s => <li key={s.id} className="font-mono">{s.task_name}</li>)}
                  </ul>
                )}
                <ReasonField value={bulkReason} onChange={setBulkReason} placeholder="Why are these being bulk-retried?" />
                <div className="flex justify-end gap-2 pt-2">
                  <Button variant="secondary" size="sm" onClick={() => setBulkOpen(false)} disabled={bulkSending}>Cancel</Button>
                  <Button
                    variant="primary" size="sm" loading={bulkSending}
                    disabled={(bulkPreview.would_dispatch_count ?? 0) === 0}
                    onClick={confirmBulkRetry}
                  >
                    Retry {bulkPreview.would_dispatch_count ?? 0} entrie(s)
                  </Button>
                </div>
              </>
            )}
          </div>
        </Modal>
      </PageWrapper>
    </AdminLayout>
  );
}
