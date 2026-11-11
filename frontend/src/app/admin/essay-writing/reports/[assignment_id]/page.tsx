"use client";

import { useEffect, useState, useCallback } from "react";
import { useParams } from "next/navigation";
import { Download, Send, RefreshCcw, FileOutput, Mail } from "lucide-react";
import { AdminLayout } from "@/components/layout/AdminLayout";
import { PageWrapper } from "@/components/layout/PageWrapper";
import { PageHeader } from "@/components/layout/PageHeader";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Select } from "@/components/ui/Select";
import { SearchInput } from "@/components/ui/SearchInput";
import { Modal } from "@/components/ui/Modal";
import { Pagination } from "@/components/ui/Pagination";
import { Skeleton, TableRowSkeleton } from "@/components/ui/Skeleton";
import { EmptyState } from "@/components/ui/EmptyState";
import { useToast } from "@/components/ui/Toast";
import api, { getErrorMessage } from "@/lib/api";
import type {
  ApiSuccess, PaginatedResponse, EssayAssignment, EssayReportRow, EssayBulkResendResult,
} from "@/types";

const STATUS_STYLES: Record<string, { bg: string; color: string; label: string }> = {
  PENDING:            { bg: "#F3F4F6", color: "#6B7280", label: "Pending" },
  LLM_PROCESSING:     { bg: "#EFF6FF", color: "#2563EB", label: "Evaluating" },
  LLM_COMPLETE:       { bg: "#EFF6FF", color: "#2563EB", label: "Awaiting report" },
  REPORT_GENERATING:  { bg: "#EFF6FF", color: "#2563EB", label: "Generating report" },
  REPORT_READY:       { bg: "#F0FDF4", color: "#16A34A", label: "Report ready" },
  LLM_FAILED:         { bg: "#FEF2F2", color: "#DC2626", label: "Failed" },
};

const DELIVERY_STYLES: Record<string, { bg: string; color: string; label: string }> = {
  pending:   { bg: "#F3F4F6", color: "#6B7280", label: "Not sent" },
  sent:      { bg: "#F0FDF4", color: "#16A34A", label: "Sent" },
  bounced:   { bg: "#FEF2F2", color: "#DC2626", label: "Bounced" },
  complaint: { bg: "#FEF2F2", color: "#DC2626", label: "Complaint" },
};

const STATUS_FILTER_OPTIONS: { value: string; label: string }[] = [
  { value: "", label: "All statuses" },
  { value: "pending", label: "Pending" },
  { value: "processing", label: "Processing" },
  { value: "completed", label: "Completed" },
  { value: "failed", label: "Failed" },
];

function Pill({ bg, color, label }: { bg: string; color: string; label: string }) {
  return (
    <span className="text-[11px] font-semibold px-2 py-0.5 rounded-full" style={{ background: bg, color }}>
      {label}
    </span>
  );
}

function formatDateTime(iso: string | null): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
}

// Same "no dedicated Textarea component" reasoning as
// submissions/[submission_id]/page.tsx's own ReasonField — kept local
// rather than extracted since each page's own copy is this small.
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

export default function AdminEssayReportsPage() {
  const { assignment_id } = useParams<{ assignment_id: string }>();
  const toast = useToast();

  const [assignment, setAssignment] = useState<EssayAssignment | null>(null);
  const [rows, setRows] = useState<EssayReportRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState(false);
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  const [totalCount, setTotalCount] = useState(0);

  const [statusFilter, setStatusFilter] = useState("");
  const [department, setDepartment] = useState("");
  const [studentSearch, setStudentSearch] = useState("");

  const [regenerateTarget, setRegenerateTarget] = useState<EssayReportRow | null>(null);
  const [regenerateReason, setRegenerateReason] = useState("");
  const [regenerating, setRegenerating] = useState(false);

  const [resendingId, setResendingId] = useState<string | null>(null);
  const [downloading, setDownloading] = useState(false);

  const [bulkOpen, setBulkOpen] = useState(false);
  const [bulkPreview, setBulkPreview] = useState<EssayBulkResendResult | null>(null);
  const [bulkPreviewLoading, setBulkPreviewLoading] = useState(false);
  const [bulkSending, setBulkSending] = useState(false);

  useEffect(() => {
    api.get<ApiSuccess<EssayAssignment>>(`/essay/admin/assignments/${assignment_id}/`)
      .then(res => setAssignment(res.data.data))
      .catch(() => { /* header title falls back to a generic label — the table below has its own load error handling */ });
  }, [assignment_id]);

  const buildParams = useCallback((extra?: Record<string, string>) => {
    const params = new URLSearchParams({ page: String(page), ...extra });
    if (statusFilter) params.set("status", statusFilter);
    if (department.trim()) params.set("department", department.trim());
    if (studentSearch.trim()) params.set("student_search", studentSearch.trim());
    return params;
  }, [page, statusFilter, department, studentSearch]);

  const loadRows = useCallback(() => {
    setLoading(true);
    setLoadError(false);
    api.get<PaginatedResponse<EssayReportRow>>(`/essay/admin/assignments/${assignment_id}/reports/?${buildParams()}`)
      .then(res => {
        setRows(res.data.results);
        setTotalPages(res.data.total_pages);
        setTotalCount(res.data.count);
      })
      .catch(err => { toast.error(getErrorMessage(err)); setLoadError(true); })
      .finally(() => setLoading(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [buildParams]);

  useEffect(loadRows, [loadRows]);
  useEffect(() => { setPage(1); }, [statusFilter, department, studentSearch]);

  function openRegenerate(row: EssayReportRow) {
    setRegenerateTarget(row);
    setRegenerateReason("");
  }

  async function submitRegenerate() {
    if (!regenerateTarget) return;
    if (!regenerateReason.trim()) {
      toast.error("A reason is required to regenerate a report.");
      return;
    }
    setRegenerating(true);
    try {
      await api.post(`/essay/admin/submissions/${regenerateTarget.submission_id}/regenerate-report/`, {
        reason: regenerateReason.trim(),
      });
      toast.success("Report regeneration dispatched.");
      setRegenerateTarget(null);
      loadRows();
    } catch (err) {
      toast.error(getErrorMessage(err));
    } finally {
      setRegenerating(false);
    }
  }

  async function handleResend(row: EssayReportRow) {
    setResendingId(row.submission_id);
    try {
      const res = await api.post<ApiSuccess<null>>(`/essay/admin/submissions/${row.submission_id}/resend-report/`);
      toast.success(res.data.message ?? "Report email dispatched.");
      loadRows();
    } catch (err) {
      toast.error(getErrorMessage(err));
    } finally {
      setResendingId(null);
    }
  }

  async function handleBulkDownload() {
    setDownloading(true);
    try {
      const res = await api.get(`/essay/admin/assignments/${assignment_id}/reports/bulk-download/?${buildParams()}`, {
        responseType: "blob",
      });
      const blob = new Blob([res.data], { type: "application/zip" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `essay_reports_${assignment_id}.zip`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    } catch (err) {
      toast.error(getErrorMessage(err));
    } finally {
      setDownloading(false);
    }
  }

  function openBulkResend() {
    setBulkOpen(true);
    setBulkPreview(null);
    setBulkPreviewLoading(true);
    api.post<ApiSuccess<EssayBulkResendResult>>(
      `/essay/admin/assignments/${assignment_id}/reports/bulk-resend/?${buildParams()}`, { dry_run: true },
    )
      .then(res => setBulkPreview(res.data.data))
      .catch(err => { toast.error(getErrorMessage(err)); setBulkOpen(false); })
      .finally(() => setBulkPreviewLoading(false));
  }

  async function confirmBulkResend() {
    setBulkSending(true);
    try {
      const res = await api.post<ApiSuccess<EssayBulkResendResult>>(
        `/essay/admin/assignments/${assignment_id}/reports/bulk-resend/?${buildParams()}`, { dry_run: false },
      );
      toast.success(`Dispatched ${res.data.data.dispatched_count ?? 0} report email(s).`);
      setBulkOpen(false);
      loadRows();
    } catch (err) {
      toast.error(getErrorMessage(err));
    } finally {
      setBulkSending(false);
    }
  }

  const hasActiveFilters = !!(statusFilter || department.trim() || studentSearch.trim());

  return (
    <AdminLayout>
      <PageWrapper>
        <PageHeader
          title={assignment?.paper_title ?? "Reports"}
          subtitle="Per-student report generation and delivery status for this assignment."
          backHref="/admin/essay-writing/reports"
          rightSlot={
            <div className="flex items-center gap-2">
              <Button variant="secondary" leftIcon={<Send size={14} />} onClick={openBulkResend}>
                Bulk resend
              </Button>
              <Button variant="secondary" leftIcon={<Download size={14} />} loading={downloading} onClick={handleBulkDownload}>
                Bulk download
              </Button>
            </div>
          }
        />

        {/* Filters */}
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 mb-4">
          <SearchInput
            value={studentSearch}
            onChange={setStudentSearch}
            placeholder="Search by email, roll number, or name..."
          />
          <Input
            placeholder="Department..."
            value={department}
            onChange={e => setDepartment(e.target.value)}
          />
          <Select
            value={statusFilter}
            onChange={e => setStatusFilter(e.target.value)}
            options={STATUS_FILTER_OPTIONS.map(o => ({ value: o.value, label: o.label }))}
          />
        </div>

        <div className="rounded-[var(--radius-xl)] overflow-hidden" style={{ background: "var(--color-surface)", border: "1px solid var(--color-border)" }}>
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b" style={{ borderColor: "var(--color-border)" }}>
                <th className="text-left px-4 py-3 font-semibold text-xs" style={{ color: "var(--color-text-subtle)" }}>Student</th>
                <th className="text-left px-4 py-3 font-semibold text-xs" style={{ color: "var(--color-text-subtle)" }}>Department</th>
                <th className="text-left px-4 py-3 font-semibold text-xs" style={{ color: "var(--color-text-subtle)" }}>Status</th>
                <th className="text-left px-4 py-3 font-semibold text-xs" style={{ color: "var(--color-text-subtle)" }}>Score</th>
                <th className="text-left px-4 py-3 font-semibold text-xs" style={{ color: "var(--color-text-subtle)" }}>Delivery</th>
                <th className="text-left px-4 py-3 font-semibold text-xs" style={{ color: "var(--color-text-subtle)" }}>Sent</th>
                <th className="text-right px-4 py-3 font-semibold text-xs" style={{ color: "var(--color-text-subtle)" }}>Actions</th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                Array.from({ length: 6 }).map((_, i) => <TableRowSkeleton key={i} cols={7} />)
              ) : rows.length === 0 && !loadError ? (
                <tr>
                  <td colSpan={7}>
                    <EmptyState
                      icon={FileOutput}
                      title="No reports found"
                      subtitle={hasActiveFilters ? "Try adjusting your filters." : "No submissions exist for this assignment yet."}
                    />
                  </td>
                </tr>
              ) : loadError ? (
                <tr>
                  <td colSpan={7}>
                    <EmptyState icon={FileOutput} title="Couldn't load reports" subtitle="Please try again." />
                  </td>
                </tr>
              ) : (
                rows.map(row => {
                  const status = STATUS_STYLES[row.status] ?? STATUS_STYLES.PENDING;
                  const delivery = DELIVERY_STYLES[row.delivery_status] ?? DELIVERY_STYLES.pending;
                  return (
                    <tr key={row.submission_id} className="border-b last:border-b-0" style={{ borderColor: "var(--color-border)" }}>
                      <td className="px-4 py-3" style={{ color: "var(--color-text)" }}>
                        <div className="font-medium">{row.student_name}</div>
                        <div className="text-xs" style={{ color: "var(--color-text-subtle)" }}>{row.student_email || "no email on file"}</div>
                      </td>
                      <td className="px-4 py-3" style={{ color: "var(--color-text-subtle)" }}>{row.department || "—"}</td>
                      <td className="px-4 py-3"><Pill bg={status.bg} color={status.color} label={status.label} /></td>
                      <td className="px-4 py-3" style={{ color: "var(--color-text)" }}>{row.score !== null ? `${row.score}/10` : "—"}</td>
                      <td className="px-4 py-3"><Pill bg={delivery.bg} color={delivery.color} label={delivery.label} /></td>
                      <td className="px-4 py-3 text-xs" style={{ color: "var(--color-text-subtle)" }}>{formatDateTime(row.email_sent_at)}</td>
                      <td className="px-4 py-3">
                        <div className="flex items-center justify-end gap-1.5">
                          <Button
                            variant="ghost" size="sm" leftIcon={<RefreshCcw size={12} />}
                            disabled={row.status !== "REPORT_READY"}
                            onClick={() => openRegenerate(row)}
                            title={row.status !== "REPORT_READY" ? "Only a ready report can be regenerated." : "Regenerate report"}
                          >
                            Regenerate
                          </Button>
                          <Button
                            variant="ghost" size="sm" leftIcon={<Mail size={12} />}
                            disabled={!row.has_report}
                            loading={resendingId === row.submission_id}
                            onClick={() => handleResend(row)}
                            title={!row.has_report ? "No report yet to send." : "Resend report email"}
                          >
                            Resend
                          </Button>
                        </div>
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
          <Pagination page={page} totalPages={totalPages} onPageChange={setPage} totalCount={totalCount} pageSize={30} />
        </div>

        {/* Regenerate modal — mandatory reason, matching the retrigger/
            override modals' own established convention
            (submissions/[submission_id]/page.tsx). */}
        <Modal isOpen={!!regenerateTarget} onClose={() => !regenerating && setRegenerateTarget(null)} title="Regenerate Report" maxWidth="sm">
          <div className="space-y-3">
            <p className="text-sm" style={{ color: "var(--color-text-subtle)" }}>
              This clears the existing report and any "sent" marker, then re-renders it from the current score and feedback. A reason is required for the audit log.
            </p>
            <ReasonField value={regenerateReason} onChange={setRegenerateReason} placeholder="Why is this report being regenerated?" />
            <div className="flex justify-end gap-2 pt-2">
              <Button variant="secondary" size="sm" onClick={() => setRegenerateTarget(null)} disabled={regenerating}>Cancel</Button>
              <Button variant="primary" size="sm" loading={regenerating} onClick={submitRegenerate}>Regenerate</Button>
            </div>
          </div>
        </Modal>

        {/* Bulk resend modal — dry-run preview shown first (Task 11.2's
            own default-safe pattern), a real send only ever happens after
            this explicit second confirmation. */}
        <Modal isOpen={bulkOpen} onClose={() => !bulkSending && setBulkOpen(false)} title="Bulk Resend Reports" maxWidth="sm">
          <div className="space-y-3">
            {bulkPreviewLoading || !bulkPreview ? (
              <Skeleton className="h-20 w-full" />
            ) : (
              <>
                <p className="text-sm" style={{ color: "var(--color-text)" }}>
                  This will send <strong>{bulkPreview.would_dispatch_count ?? 0}</strong> report email(s)
                  {bulkPreview.capped && <> (capped from {bulkPreview.total_matching} matching)</>}, matching the current filters.
                </p>
                {bulkPreview.sample && bulkPreview.sample.length > 0 && (
                  <ul className="text-xs space-y-0.5 max-h-32 overflow-y-auto" style={{ color: "var(--color-text-subtle)" }}>
                    {bulkPreview.sample.map(s => <li key={s.submission_id}>{s.student_email}</li>)}
                  </ul>
                )}
                <div className="flex justify-end gap-2 pt-2">
                  <Button variant="secondary" size="sm" onClick={() => setBulkOpen(false)} disabled={bulkSending}>Cancel</Button>
                  <Button
                    variant="primary" size="sm" loading={bulkSending}
                    disabled={(bulkPreview.would_dispatch_count ?? 0) === 0}
                    onClick={confirmBulkResend}
                  >
                    Send {bulkPreview.would_dispatch_count ?? 0} email(s)
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
