"use client";

import { useEffect, useState, useCallback } from "react";
import { useParams, useRouter } from "next/navigation";
import { Download, ShieldAlert, Copy } from "lucide-react";
import { AdminLayout } from "@/components/layout/AdminLayout";
import { PageWrapper } from "@/components/layout/PageWrapper";
import { PageHeader } from "@/components/layout/PageHeader";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { SearchInput } from "@/components/ui/SearchInput";
import { Pagination } from "@/components/ui/Pagination";
import { Skeleton, TableRowSkeleton } from "@/components/ui/Skeleton";
import { EmptyState } from "@/components/ui/EmptyState";
import { useToast } from "@/components/ui/Toast";
import api, { getErrorMessage } from "@/lib/api";
import type { ApiSuccess, PaginatedResponse, EssayAssignment, EssayResultRow, EssayResultExamStatus } from "@/types";

const EXAM_STATUS_STYLES: Record<EssayResultExamStatus, { bg: string; color: string; label: string }> = {
  pending:    { bg: "#F3F4F6", color: "#6B7280", label: "Not started" },
  writing:    { bg: "#EFF6FF", color: "#2563EB", label: "Writing" },
  processing: { bg: "#EFF6FF", color: "#2563EB", label: "Processing" },
  completed:  { bg: "#F0FDF4", color: "#16A34A", label: "Scored" },
  failed:     { bg: "#FEF2F2", color: "#DC2626", label: "Failed" },
};

function ExamStatusPill({ status }: { status: EssayResultExamStatus }) {
  const s = EXAM_STATUS_STYLES[status] ?? EXAM_STATUS_STYLES.pending;
  return (
    <span className="text-[11px] font-semibold px-2 py-0.5 rounded-full" style={{ background: s.bg, color: s.color }}>
      {s.label}
    </span>
  );
}

function formatDateTime(iso: string | null): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
}

export default function AdminEssayResultsPage() {
  const { assignment_id } = useParams<{ assignment_id: string }>();
  const router = useRouter();
  const toast = useToast();

  const [assignment, setAssignment] = useState<EssayAssignment | null>(null);
  const [rows, setRows] = useState<EssayResultRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState(false);
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  const [totalCount, setTotalCount] = useState(0);
  const [exporting, setExporting] = useState(false);

  const [studentSearch, setStudentSearch] = useState("");
  const [department, setDepartment] = useState("");
  const [flaggedOnly, setFlaggedOnly] = useState(false);

  useEffect(() => {
    api.get<ApiSuccess<EssayAssignment>>(`/essay/admin/assignments/${assignment_id}/`)
      .then(res => setAssignment(res.data.data))
      .catch(() => { /* the header title/subtitle just falls back to a generic label below — the table itself has its own load error handling */ });
  }, [assignment_id]);

  const buildParams = useCallback(() => {
    const params = new URLSearchParams({ page: String(page) });
    const trimmedSearch = studentSearch.trim();
    if (trimmedSearch) params.set("student_search", trimmedSearch);
    if (department.trim()) params.set("department", department.trim());
    if (flaggedOnly) params.set("flagged", "true");
    return params;
  }, [page, studentSearch, department, flaggedOnly]);

  const loadRows = useCallback(() => {
    setLoading(true);
    setLoadError(false);
    api.get<PaginatedResponse<EssayResultRow>>(`/essay/admin/assignments/${assignment_id}/results/?${buildParams()}`)
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
  useEffect(() => { setPage(1); }, [studentSearch, department, flaggedOnly]);

  async function handleExport() {
    setExporting(true);
    try {
      const res = await api.get(`/essay/admin/assignments/${assignment_id}/results/export/?${buildParams()}`, {
        responseType: "blob",
      });
      const blob = new Blob([res.data], { type: "text/csv;charset=utf-8;" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `essay_results_${assignment_id}.csv`;
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

  const hasActiveFilters = !!(studentSearch.trim() || department.trim() || flaggedOnly);

  return (
    <AdminLayout>
      <PageWrapper>
        <PageHeader
          title={assignment?.paper_title ?? "Results"}
          subtitle="Per-student scores and LLM feedback for this assignment."
          backHref="/admin/essay-writing/results"
          rightSlot={
            <Button variant="secondary" leftIcon={<Download size={14} />} loading={exporting} onClick={handleExport}>
              Export CSV
            </Button>
          }
        />

        {/* Filters */}
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 mb-4">
          <SearchInput
            value={studentSearch}
            onChange={setStudentSearch}
            placeholder="Search by roll number or name..."
          />
          <Input
            placeholder="Department..."
            value={department}
            onChange={e => setDepartment(e.target.value)}
          />
          <button
            onClick={() => setFlaggedOnly(v => !v)}
            className="flex items-center gap-2 px-3 rounded-[var(--radius-md)] text-sm cursor-pointer transition-colors"
            style={{
              border: flaggedOnly ? "1.5px solid #DC2626" : "1px solid var(--color-border)",
              background: flaggedOnly ? "#FEF2F2" : "var(--color-surface)",
              color: flaggedOnly ? "#DC2626" : "var(--color-text-subtle)",
            }}
          >
            <ShieldAlert size={14} /> Flagged only
          </button>
        </div>

        <div className="rounded-[var(--radius-xl)] overflow-hidden" style={{ background: "var(--color-surface)", border: "1px solid var(--color-border)" }}>
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b" style={{ borderColor: "var(--color-border)" }}>
                <th className="text-left px-4 py-3 font-semibold text-xs" style={{ color: "var(--color-text-subtle)" }}>Student</th>
                <th className="text-left px-4 py-3 font-semibold text-xs" style={{ color: "var(--color-text-subtle)" }}>Department</th>
                <th className="text-left px-4 py-3 font-semibold text-xs" style={{ color: "var(--color-text-subtle)" }}>Set</th>
                <th className="text-left px-4 py-3 font-semibold text-xs" style={{ color: "var(--color-text-subtle)" }}>Status</th>
                <th className="text-left px-4 py-3 font-semibold text-xs" style={{ color: "var(--color-text-subtle)" }}>Score</th>
                <th className="text-left px-4 py-3 font-semibold text-xs" style={{ color: "var(--color-text-subtle)" }}>Flags</th>
                <th className="text-left px-4 py-3 font-semibold text-xs" style={{ color: "var(--color-text-subtle)" }}>Submitted</th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                Array.from({ length: 6 }).map((_, i) => <TableRowSkeleton key={i} cols={7} />)
              ) : rows.length === 0 && !loadError ? (
                <tr>
                  <td colSpan={7}>
                    <EmptyState
                      icon={Copy}
                      title="No students found"
                      subtitle={hasActiveFilters ? "Try adjusting your filters." : "No students are allocated to this assignment yet."}
                    />
                  </td>
                </tr>
              ) : loadError ? (
                <tr>
                  <td colSpan={7}>
                    <EmptyState icon={ShieldAlert} title="Couldn't load results" subtitle="Please try again." />
                  </td>
                </tr>
              ) : (
                rows.map(row => (
                  <tr
                    key={row.student_user_id}
                    onClick={() => row.submission_id && router.push(`/admin/essay-writing/submissions/${row.submission_id}`)}
                    className="border-b last:border-b-0"
                    style={{
                      borderColor: "var(--color-border)",
                      cursor: row.submission_id ? "pointer" : "default",
                    }}
                    onMouseEnter={e => { if (row.submission_id) e.currentTarget.style.background = "var(--color-surface-subtle)"; }}
                    onMouseLeave={e => { e.currentTarget.style.background = ""; }}
                  >
                    <td className="px-4 py-3" style={{ color: "var(--color-text)" }}>
                      <div className="font-medium">{row.student_name}</div>
                      <div className="text-xs font-mono" style={{ color: "var(--color-text-subtle)" }}>{row.student_roll_id || row.student_user_id.slice(0, 8)}</div>
                    </td>
                    <td className="px-4 py-3" style={{ color: "var(--color-text-subtle)" }}>{row.department || "—"}</td>
                    <td className="px-4 py-3" style={{ color: "var(--color-text-subtle)" }}>{row.set_label}</td>
                    <td className="px-4 py-3"><ExamStatusPill status={row.exam_status} /></td>
                    <td className="px-4 py-3" style={{ color: "var(--color-text)" }}>{row.score !== null ? `${row.score}/10` : "—"}</td>
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-1.5">
                        {row.malpractice_flag && <span title="Malpractice flagged"><ShieldAlert size={14} style={{ color: "#DC2626" }} /></span>}
                        {row.plagiarism_flag && <span title="Plagiarism flagged"><Copy size={14} style={{ color: "#D97706" }} /></span>}
                      </div>
                    </td>
                    <td className="px-4 py-3 text-xs" style={{ color: "var(--color-text-subtle)" }}>{formatDateTime(row.submitted_at)}</td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
          <Pagination page={page} totalPages={totalPages} onPageChange={setPage} totalCount={totalCount} pageSize={30} />
        </div>
      </PageWrapper>
    </AdminLayout>
  );
}
