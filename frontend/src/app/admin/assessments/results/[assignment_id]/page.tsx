"use client";

import { useEffect, useState, useCallback } from "react";
import { useParams, useRouter } from "next/navigation";
import {
  Download, FileText, ShieldAlert, CheckCircle2, XCircle, Clock, ChevronRight,
} from "lucide-react";
import { AdminLayout } from "@/components/layout/AdminLayout";
import { PageWrapper } from "@/components/layout/PageWrapper";
import { PageHeader } from "@/components/layout/PageHeader";
import { Button } from "@/components/ui/Button";
import { Select } from "@/components/ui/Select";
import { Modal } from "@/components/ui/Modal";
import { Pagination } from "@/components/ui/Pagination";
import { TableRowSkeleton } from "@/components/ui/Skeleton";
import { EmptyState } from "@/components/ui/EmptyState";
import { useToast } from "@/components/ui/Toast";
import api, { getErrorMessage } from "@/lib/api";
import { DEPARTMENTS } from "@/lib/constants";
import type {
  ApiSuccess, PaginatedResponse, AdminResultRow, AdminResultResponsesData, AdminResultLogsData,
} from "@/types";

function formatDateTime(iso: string | null): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
}

function formatDuration(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return `${m}m ${s}s`;
}

export default function AdminAssessmentResultsPage() {
  const { assignment_id } = useParams<{ assignment_id: string }>();
  const router = useRouter();
  const toast = useToast();

  const [rows, setRows] = useState<AdminResultRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  const [totalCount, setTotalCount] = useState(0);

  const [department, setDepartment] = useState("");
  const [flaggedOnly, setFlaggedOnly] = useState(false);
  const [sort, setSort] = useState("-ended_at");

  const [responsesModal, setResponsesModal] = useState<AdminResultResponsesData | null>(null);
  const [logsModal, setLogsModal] = useState<AdminResultLogsData | null>(null);
  const [detailLoading, setDetailLoading] = useState<string | null>(null);
  const [exporting, setExporting] = useState(false);

  const buildParams = useCallback(() => {
    const params = new URLSearchParams({ page: String(page), sort });
    if (department) params.set("department", department);
    if (flaggedOnly) params.set("flagged_only", "true");
    return params;
  }, [page, sort, department, flaggedOnly]);

  const load = useCallback(() => {
    setLoading(true);
    api.get<PaginatedResponse<AdminResultRow>>(
      `/assessments/admin/assignments/${assignment_id}/results/?${buildParams()}`
    )
      .then(res => {
        setRows(res.data.results);
        setTotalPages(res.data.total_pages);
        setTotalCount(res.data.count);
      })
      .catch(err => toast.error(getErrorMessage(err)))
      .finally(() => setLoading(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [assignment_id, buildParams]);

  useEffect(load, [load]);

  useEffect(() => { setPage(1); }, [department, flaggedOnly, sort]);

  async function openResponses(resultId: string) {
    setDetailLoading(resultId + ":responses");
    try {
      const res = await api.get<ApiSuccess<AdminResultResponsesData>>(`/assessments/admin/results/${resultId}/responses/`);
      setResponsesModal(res.data.data);
    } catch (err) {
      toast.error(getErrorMessage(err));
    } finally {
      setDetailLoading(null);
    }
  }

  async function openLogs(resultId: string) {
    setDetailLoading(resultId + ":logs");
    try {
      // page_size=200 (Task 11.1's pagination audit added real pagination
      // to this endpoint, which was previously unbounded): generous enough
      // that realistic malpractice-review sessions still see everything in
      // one page — the modal below notes if a session's log count exceeds
      // even that.
      const res = await api.get<ApiSuccess<AdminResultLogsData>>(`/assessments/admin/results/${resultId}/logs/?page_size=200`);
      setLogsModal(res.data.data);
    } catch (err) {
      toast.error(getErrorMessage(err));
    } finally {
      setDetailLoading(null);
    }
  }

  async function handleExport() {
    setExporting(true);
    try {
      const res = await api.get(`/assessments/admin/assignments/${assignment_id}/results/export/?${buildParams()}`, {
        responseType: "blob",
      });
      const blob = new Blob([res.data], { type: "text/csv;charset=utf-8;" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `results_${assignment_id}.csv`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    } catch (err) {
      toast.error(getErrorMessage(err));
    } finally {
      setExporting(false);
    }
  }

  const isEmpty = !loading && rows.length === 0;

  return (
    <AdminLayout>
      <PageWrapper className="max-w-6xl">
        <PageHeader
          title="Results"
          subtitle="Review submitted responses, activity logs, and export data for this assessment."
          backHref="/admin/assessments/papers"
          rightSlot={
            <Button variant="secondary" leftIcon={<Download size={14} />} loading={exporting} onClick={handleExport}>
              Export CSV
            </Button>
          }
        />

        {/* Filters */}
        <div className="flex flex-wrap items-end gap-3 mb-4">
          <div className="w-48">
            <Select
              label="Department"
              value={department}
              onChange={e => setDepartment(e.target.value)}
              options={[{ value: "", label: "All departments" }, ...DEPARTMENTS.map(d => ({ value: d, label: d }))]}
            />
          </div>
          <div className="w-48">
            <Select
              label="Sort by"
              value={sort}
              onChange={e => setSort(e.target.value)}
              options={[
                { value: "-ended_at", label: "Most recent" },
                { value: "-percentage", label: "Highest score" },
                { value: "percentage", label: "Lowest score" },
                { value: "-duration_seconds", label: "Longest duration" },
                { value: "duration_seconds", label: "Shortest duration" },
              ]}
            />
          </div>
          <label className="flex items-center gap-2 h-9 px-3 rounded-[var(--radius-md)] text-sm cursor-pointer"
            style={{ border: "1px solid var(--color-border)", color: "var(--color-text)" }}>
            <input type="checkbox" checked={flaggedOnly} onChange={e => setFlaggedOnly(e.target.checked)} />
            Flagged only
          </label>
        </div>

        {/* Table */}
        <div className="rounded-[var(--radius-xl)] overflow-hidden" style={{ border: "1px solid var(--color-border)", background: "var(--color-surface)" }}>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr style={{ borderBottom: "1px solid var(--color-border)" }}>
                  {["Student", "Dept", "Duration", "Score", "%", "Status", "Flagged", ""].map(h => (
                    <th key={h} className="text-left px-4 py-3 text-xs font-semibold uppercase tracking-wider whitespace-nowrap"
                      style={{ color: "var(--color-text-subtle)" }}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {loading ? (
                  Array.from({ length: 5 }).map((_, i) => <TableRowSkeleton key={i} cols={8} />)
                ) : rows.map(r => (
                  <tr key={r.result_id} style={{ borderBottom: "1px solid var(--color-border)" }}>
                    <td className="px-4 py-3 whitespace-nowrap">
                      <p className="font-medium" style={{ color: "var(--color-text)" }}>{r.student_name}</p>
                      <p className="text-xs" style={{ color: "var(--color-text-subtle)" }}>{r.student_roll_id}</p>
                    </td>
                    <td className="px-4 py-3 whitespace-nowrap">{r.department}</td>
                    <td className="px-4 py-3 whitespace-nowrap">
                      <span className="inline-flex items-center gap-1"><Clock size={11} />{formatDuration(r.duration_seconds)}</span>
                    </td>
                    <td className="px-4 py-3 whitespace-nowrap">{r.score}/{r.total_marks}</td>
                    <td className="px-4 py-3 whitespace-nowrap font-semibold">{r.percentage}%</td>
                    <td className="px-4 py-3 whitespace-nowrap">{r.status}</td>
                    <td className="px-4 py-3 whitespace-nowrap">
                      {r.malpractice_flag ? (
                        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-semibold"
                          style={{ background: "#FEF2F2", color: "#DC2626" }}>
                          <ShieldAlert size={11} /> Flagged
                        </span>
                      ) : (
                        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-semibold"
                          style={{ background: "#F0FDF4", color: "#16A34A" }}>
                          <CheckCircle2 size={11} /> Clean
                        </span>
                      )}
                    </td>
                    <td className="px-4 py-3 whitespace-nowrap">
                      <div className="flex items-center gap-1.5">
                        <Button variant="ghost" size="sm" loading={detailLoading === r.result_id + ":responses"}
                          onClick={() => openResponses(r.result_id)}>
                          Responses
                        </Button>
                        <Button variant="ghost" size="sm" loading={detailLoading === r.result_id + ":logs"}
                          onClick={() => openLogs(r.result_id)}>
                          Logs
                        </Button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {isEmpty && (
            <EmptyState icon={FileText} title="No results yet" subtitle="Results appear here once students submit." />
          )}

          {!isEmpty && (
            <Pagination page={page} totalPages={totalPages} totalCount={totalCount} onPageChange={setPage} />
          )}
        </div>
      </PageWrapper>

      {/* Responses modal */}
      <Modal isOpen={!!responsesModal} onClose={() => setResponsesModal(null)} title="Submitted Responses" maxWidth="lg">
        <div className="space-y-4 max-h-[60vh] overflow-y-auto">
          {responsesModal?.questions.map(q => (
            <div key={q.question_id} className="rounded-[var(--radius-lg)] p-4" style={{ border: "1px solid var(--color-border)" }}>
              <p className="text-xs font-semibold uppercase tracking-wider mb-2" style={{ color: "var(--color-text-subtle)" }}>
                Question {q.question_number} · {q.marks_awarded}/{q.marks} marks
              </p>
              <p className="text-sm mb-3" style={{ color: "var(--color-text)" }}>{q.question_text}</p>
              {!q.answered && (
                <p className="text-xs italic mb-2" style={{ color: "var(--color-text-subtle)" }}>Not answered</p>
              )}
              <div className="space-y-1.5">
                {q.options.map(opt => {
                  const selected = q.selected_option_ids.includes(opt.id);
                  const style = opt.is_correct
                    ? { background: "#F0FDF4", border: "1px solid #BBF7D0", color: "#166534" }
                    : selected
                      ? { background: "#FEF2F2", border: "1px solid #FECACA", color: "#991B1B" }
                      : { background: "#fff", border: "1px solid var(--color-border)", color: "var(--color-text-muted)" };
                  return (
                    <div key={opt.id} className="flex items-center gap-2 px-3 py-2 rounded-[var(--radius-md)] text-sm" style={style}>
                      {opt.is_correct ? <CheckCircle2 size={13} /> : selected ? <XCircle size={13} /> : null}
                      <span className="font-semibold">{opt.label}.</span> {opt.text}
                      {selected && <span className="text-xs ml-auto">(selected)</span>}
                    </div>
                  );
                })}
              </div>
            </div>
          ))}
        </div>
      </Modal>

      {/* Logs modal */}
      <Modal isOpen={!!logsModal} onClose={() => setLogsModal(null)} title="Activity Log" maxWidth="md">
        <div>
          {logsModal?.malpractice_flag && (
            <div className="flex items-start gap-2 px-4 py-3 rounded-[var(--radius-lg)] mb-4"
              style={{ background: "#FEF2F2", border: "1px solid #FECACA" }}>
              <ShieldAlert size={16} style={{ color: "#DC2626", flexShrink: 0, marginTop: 1 }} />
              <div>
                <p className="text-sm font-semibold" style={{ color: "#991B1B" }}>Flagged for review</p>
                <p className="text-xs mt-1" style={{ color: "#991B1B" }}>
                  Threshold(s) tripped: {logsModal.malpractice_reasons.join(", ")}
                </p>
              </div>
            </div>
          )}
          <div className="space-y-2 max-h-[50vh] overflow-y-auto">
            {logsModal?.logs.length === 0 && (
              <p className="text-sm italic" style={{ color: "var(--color-text-subtle)" }}>No activity events recorded.</p>
            )}
            {logsModal?.logs.map((log, i) => (
              <div key={i} className="flex items-center gap-3 px-3 py-2 rounded-[var(--radius-md)]" style={{ background: "var(--color-surface-secondary)" }}>
                <ChevronRight size={12} style={{ color: "var(--color-text-subtle)" }} />
                <span className="text-sm font-medium" style={{ color: "var(--color-text)" }}>{log.event_type}</span>
                <span className="text-xs ml-auto" style={{ color: "var(--color-text-subtle)" }}>{formatDateTime(log.occurred_at)}</span>
              </div>
            ))}
          </div>
          {logsModal && logsModal.count > logsModal.logs.length && (
            <p className="text-xs mt-3 italic" style={{ color: "var(--color-text-subtle)" }}>
              Showing the first {logsModal.logs.length} of {logsModal.count} events.
            </p>
          )}
        </div>
      </Modal>
    </AdminLayout>
  );
}
