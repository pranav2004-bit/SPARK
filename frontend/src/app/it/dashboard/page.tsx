"use client";

import { useEffect, useState } from "react";
import { AlertTriangle, ChevronDown, Gauge } from "lucide-react";
import { ITLayout } from "@/components/layout/ITLayout";
import { PageWrapper } from "@/components/layout/PageWrapper";
import { EmptyState } from "@/components/ui/EmptyState";
import { useToast } from "@/components/ui/Toast";
import api, { getErrorMessage } from "@/lib/api";
import type {
  ApiSuccess, ActiveInactiveCount,
  ITDashboardAuthStats, ITDashboardUserStats, ITDashboardBatchStats,
} from "@/types";

// Everything on this page is fetched fresh on every load, never cached —
// explicit user requirement ("100% accuracy... update automatically every
// time"). Composed from two services' own stats endpoints (each owns its
// own data; no cross-service call at read time, same isolation convention
// used throughout this platform): auth-service for departments/admins/
// super_admins, user-service for students/batches/sections. Department
// breakdowns from each are merged client-side via mergeByDepartment below.

type DeptRow = ActiveInactiveCount & { code: string; name: string; is_active: boolean };

// Merges the official department list (auth-service — has every real
// department, including ones with zero current admins/students) with a
// free-text breakdown (user-service's Student.department, or auth-
// service's own admin-by-department — neither has a FK to Department, same
// cross-service-isolation convention used everywhere in this platform).
// Matched case-insensitively. Anything in the breakdown that doesn't match
// a real department is returned separately as `unmapped` — a genuine data-
// quality signal (a typo'd department string, or one renamed/deleted after
// students/admins were already assigned it) worth surfacing, not hiding.
function mergeByDepartment(
  official: { code: string; name: string; is_active: boolean }[],
  breakdown: (ActiveInactiveCount & { department: string })[],
): { matched: DeptRow[]; unmapped: (ActiveInactiveCount & { department: string })[] } {
  const byCode = new Map(breakdown.map(row => [row.department.trim().toLowerCase(), row]));
  const matched: DeptRow[] = official.map(dept => {
    const key = dept.code.trim().toLowerCase();
    const row = byCode.get(key);
    byCode.delete(key);
    return {
      code: dept.code, name: dept.name, is_active: dept.is_active,
      total: row?.total ?? 0, active: row?.active ?? 0, inactive: row?.inactive ?? 0,
    };
  });
  return { matched, unmapped: Array.from(byCode.values()) };
}

// ── Small building blocks ────────────────────────────────────────────────────

function StatTile({ label, value }: { label: string; value: number }) {
  return (
    <div
      className="flex items-center justify-center p-4 rounded-[var(--radius-xl)]"
      style={{ background: "var(--color-surface)", border: "1px solid var(--color-border)", boxShadow: "var(--shadow-sm)" }}
    >
      <div className="min-w-0 text-center">
        <p className="text-2xl font-bold leading-tight" style={{ color: "var(--color-text)" }}>{value.toLocaleString()}</p>
        <p className="text-sm mt-1" style={{ color: "var(--color-text-subtle)" }}>{label}</p>
      </div>
    </div>
  );
}

function SectionCard({ title, headerRight, children }: { title: string; headerRight?: React.ReactNode; children: React.ReactNode }) {
  return (
    <div
      className="p-5 rounded-[var(--radius-xl)]"
      style={{ background: "var(--color-surface)", border: "1px solid var(--color-border)", boxShadow: "var(--shadow-sm)" }}
    >
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-sm font-semibold uppercase tracking-wide" style={{ color: "var(--color-text-muted)" }}>{title}</h2>
        {headerRight}
      </div>
      {children}
    </div>
  );
}

function BreakdownTable({ rows, keyLabel }: { rows: (ActiveInactiveCount & { [k: string]: unknown })[]; keyLabel: string }) {
  if (rows.length === 0) {
    return <p className="text-xs italic" style={{ color: "var(--color-text-subtle)" }}>No data yet.</p>;
  }
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr style={{ borderBottom: "1px solid var(--color-border)" }}>
            {[keyLabel, "Total", "Active", "Inactive"].map(h => (
              <th key={h} className="text-left px-3 py-2 text-xs font-semibold uppercase tracking-wider whitespace-nowrap"
                style={{ color: "var(--color-text-subtle)" }}>{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, i) => (
            <tr key={i} style={{ borderBottom: "1px solid var(--color-border)" }}>
              <td className="px-3 py-2 font-medium" style={{ color: "var(--color-text)" }}>{String(row.label ?? row.name)}</td>
              <td className="px-3 py-2" style={{ color: "var(--color-text)" }}>{row.total}</td>
              <td className="px-3 py-2" style={{ color: "var(--color-success)" }}>{row.active}</td>
              <td className="px-3 py-2" style={{ color: "var(--color-text-muted)" }}>{row.inactive}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// A department row nested inside an expanded batch — clicking it reveals
// that department's own section counts WITHIN this batch (not a flat
// cross-department tally).
function BatchDepartmentRow({ row, expanded, onToggle }: {
  row: ITDashboardBatchStats["by_department"][number];
  expanded: boolean;
  onToggle: () => void;
}) {
  return (
    <>
      <tr
        onClick={onToggle}
        className="cursor-pointer"
        style={{ borderBottom: expanded ? "none" : "1px solid var(--color-border)" }}
      >
        <td className="px-3 py-2">
          <span className="flex items-center gap-2 font-medium" style={{ color: "var(--color-text)" }}>
            <ChevronDown size={12} style={{ color: "var(--color-text-subtle)", transform: expanded ? "rotate(180deg)" : "none", transition: "transform 150ms" }} />
            {row.department || "(none)"}
          </span>
        </td>
        <td className="px-3 py-2" style={{ color: "var(--color-text)" }}>{row.total}</td>
        <td className="px-3 py-2" style={{ color: "var(--color-success)" }}>{row.active}</td>
        <td className="px-3 py-2" style={{ color: "var(--color-text-muted)" }}>{row.inactive}</td>
      </tr>
      {expanded && (
        <tr style={{ borderBottom: "1px solid var(--color-border)" }}>
          <td colSpan={4} className="px-4 py-3" style={{ background: "var(--color-surface)" }}>
            <BreakdownTable
              keyLabel="Section"
              rows={row.sections.map(r => ({ ...r, label: r.section || "(none)" }))}
            />
          </td>
        </tr>
      )}
    </>
  );
}

function BatchRow({ batch, expanded, onToggle, expandedDept, onToggleDept }: {
  batch: ITDashboardBatchStats;
  expanded: boolean;
  onToggle: () => void;
  expandedDept: string | null;
  onToggleDept: (department: string) => void;
}) {
  return (
    <>
      <tr
        onClick={onToggle}
        className="cursor-pointer"
        style={{ borderBottom: expanded ? "none" : "1px solid var(--color-border)" }}
      >
        <td className="px-3 py-3">
          <span className="flex items-center gap-2 font-medium" style={{ color: "var(--color-text)" }}>
            <ChevronDown size={14} style={{ color: "var(--color-text-subtle)", transform: expanded ? "rotate(180deg)" : "none", transition: "transform 150ms" }} />
            {batch.batch_name}
          </span>
        </td>
        <td className="px-3 py-3" style={{ color: "var(--color-text)" }}>{batch.total}</td>
        <td className="px-3 py-3" style={{ color: "var(--color-success)" }}>{batch.active}</td>
        <td className="px-3 py-3" style={{ color: "var(--color-text-muted)" }}>{batch.inactive}</td>
      </tr>
      {expanded && (
        <tr style={{ borderBottom: "1px solid var(--color-border)" }}>
          <td colSpan={4} className="px-4 py-4" style={{ background: "var(--color-surface-secondary)" }}>
            <p className="text-xs font-semibold uppercase tracking-wide mb-2" style={{ color: "var(--color-text-subtle)" }}>By department</p>
            {batch.by_department.length === 0 ? (
              <p className="text-xs italic" style={{ color: "var(--color-text-subtle)" }}>No data yet.</p>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr style={{ borderBottom: "1px solid var(--color-border)" }}>
                      {["Department", "Total", "Active", "Inactive"].map(h => (
                        <th key={h} className="text-left px-3 py-2 text-xs font-semibold uppercase tracking-wider whitespace-nowrap"
                          style={{ color: "var(--color-text-subtle)" }}>{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {batch.by_department.map(row => (
                      <BatchDepartmentRow
                        key={row.department}
                        row={row}
                        expanded={expandedDept === row.department}
                        onToggle={() => onToggleDept(row.department)}
                      />
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </td>
        </tr>
      )}
    </>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function ITDashboardPage() {
  const toast = useToast();

  const [authStats, setAuthStats] = useState<ITDashboardAuthStats | null>(null);
  const [userStats, setUserStats] = useState<ITDashboardUserStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState(false);
  const [expandedBatchId, setExpandedBatchId] = useState<string | null>(null);
  const [expandedBatchDept, setExpandedBatchDept] = useState<string | null>(null);
  const [studentsBatchFilter, setStudentsBatchFilter] = useState("");

  function load() {
    setLoading(true);
    setLoadError(false);
    Promise.all([
      api.get<ApiSuccess<ITDashboardAuthStats>>("/auth/dashboard-stats/"),
      api.get<ApiSuccess<ITDashboardUserStats>>("/users/it/dashboard-stats/"),
    ])
      .then(([authRes, userRes]) => {
        setAuthStats(authRes.data.data);
        setUserStats(userRes.data.data);
      })
      .catch(err => { toast.error(getErrorMessage(err)); setLoadError(true); })
      .finally(() => setLoading(false));
  }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(load, []);

  const ready = authStats && userStats && !loading;

  const admins = ready ? mergeByDepartment(authStats!.departments.list, authStats!.admins.by_department) : null;

  // Scoped to one batch when a filter is picked — reuses that batch's own
  // by_department breakdown (already computed server-side) instead of the
  // institution-wide one, same merge-against-the-official-list treatment
  // either way so a department with zero students in that batch still
  // shows as a real 0 row rather than being omitted.
  const selectedBatch = ready ? userStats!.batches.find(b => b.id === studentsBatchFilter) : undefined;
  const studentsByDepartmentSource = selectedBatch ? selectedBatch.by_department : (ready ? userStats!.students.by_department : []);
  const students = ready ? mergeByDepartment(authStats!.departments.list, studentsByDepartmentSource) : null;

  return (
    <ITLayout>
      <PageWrapper>
        {loading ? (
          <div className="grid gap-4" style={{ gridTemplateColumns: "repeat(auto-fill, minmax(220px, 1fr))" }}>
            {Array.from({ length: 5 }).map((_, i) => (
              <div key={i} className="h-20 rounded-[var(--radius-xl)] animate-pulse" style={{ background: "var(--color-surface-secondary)" }} />
            ))}
          </div>
        ) : loadError ? (
          <EmptyState
            icon={AlertTriangle}
            title="Couldn't load the dashboard"
            subtitle="Something went wrong fetching this data — it may be temporary. Try again in a moment."
            action={{ label: "Retry", onClick: load }}
          />
        ) : ready && (
          <div className="space-y-6">
            {/* ── Overview ───────────────────────────────────────────────────── */}
            <div className="grid gap-4" style={{ gridTemplateColumns: "repeat(5, minmax(0, 1fr))" }}>
              <StatTile label="Students" value={userStats!.students.total} />
              <StatTile label="Admins" value={authStats!.admins.total} />
              <StatTile label="Batches" value={userStats!.batches.length} />
              <StatTile label="Departments" value={authStats!.departments.total} />
              <StatTile label="Super Admins" value={authStats!.super_admins.total} />
            </div>

            {/* ── Admins ─────────────────────────────────────────────────────── */}
            <SectionCard title="Admins">
              <p className="text-xs font-semibold uppercase tracking-wide mb-2" style={{ color: "var(--color-text-subtle)" }}>By department</p>
              <BreakdownTable keyLabel="Department" rows={admins!.matched.map(r => ({ ...r, label: r.name || r.code }))} />
              {admins!.unmapped.length > 0 && (
                <p className="text-xs mt-3 flex items-center gap-1.5" style={{ color: "var(--color-warning)" }}>
                  <AlertTriangle size={12} />
                  {admins!.unmapped.length} admin{admins!.unmapped.length === 1 ? "" : "s"} listed under a department that no longer exists: {admins!.unmapped.map(r => `"${r.department || "(blank)"}" (${r.total})`).join(", ")}.
                </p>
              )}
            </SectionCard>

            {/* ── Students ───────────────────────────────────────────────────── */}
            <SectionCard
              title="Students"
              headerRight={
                <div className="flex items-center gap-2 shrink-0">
                  <span className="text-xs font-semibold uppercase tracking-wide" style={{ color: "var(--color-text-subtle)" }}>Batch</span>
                  <div className="relative shrink-0">
                    <select
                      value={studentsBatchFilter}
                      onChange={(e) => setStudentsBatchFilter(e.target.value)}
                      className="h-9 pl-3 pr-8 text-sm rounded-[var(--radius-md)] border bg-white appearance-none cursor-pointer focus:outline-none focus:ring-2 focus:ring-[var(--color-accent)]"
                      style={{
                        borderColor: selectedBatch ? "var(--color-accent)" : "var(--color-border)",
                        color: "var(--color-text)",
                        fontWeight: selectedBatch ? 600 : 400,
                        width: 170,
                      }}
                    >
                      <option value="">All batches</option>
                      {userStats!.batches.map((b) => (
                        <option key={b.id} value={b.id}>{b.batch_name}</option>
                      ))}
                    </select>
                    <ChevronDown size={14} className="absolute right-2.5 top-1/2 -translate-y-1/2 pointer-events-none" style={{ color: selectedBatch ? "var(--color-accent)" : "var(--color-text-muted)" }} />
                  </div>
                </div>
              }
            >
              <p className="text-xs font-semibold uppercase tracking-wide mb-2" style={{ color: "var(--color-text-subtle)" }}>
                By department{selectedBatch ? ` — ${selectedBatch.batch_name}` : ""}
              </p>
              <BreakdownTable keyLabel="Department" rows={students!.matched.map(r => ({ ...r, label: r.name || r.code }))} />
              {students!.unmapped.length > 0 && (
                <p className="text-xs mt-3 flex items-center gap-1.5" style={{ color: "var(--color-warning)" }}>
                  <AlertTriangle size={12} />
                  {students!.unmapped.length} student group{students!.unmapped.length === 1 ? "" : "s"} under a department that no longer exists: {students!.unmapped.map(r => `"${r.department || "(blank)"}" (${r.total})`).join(", ")}.
                </p>
              )}
            </SectionCard>

            {/* ── Batches ────────────────────────────────────────────────────── */}
            <SectionCard title="Batches">
              {userStats!.batches.length === 0 ? (
                <p className="text-xs italic" style={{ color: "var(--color-text-subtle)" }}>No batches created yet.</p>
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr style={{ borderBottom: "1px solid var(--color-border)" }}>
                        {["Batch", "Total", "Active", "Inactive"].map(h => (
                          <th key={h} className="text-left px-3 py-2 text-xs font-semibold uppercase tracking-wider whitespace-nowrap"
                            style={{ color: "var(--color-text-subtle)" }}>{h}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {userStats!.batches.map(batch => (
                        <BatchRow
                          key={batch.id}
                          batch={batch}
                          expanded={expandedBatchId === batch.id}
                          onToggle={() => {
                            setExpandedBatchId(prev => prev === batch.id ? null : batch.id);
                            setExpandedBatchDept(null);
                          }}
                          expandedDept={expandedBatchDept}
                          onToggleDept={(department) => setExpandedBatchDept(prev => prev === department ? null : department)}
                        />
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
              <p className="text-xs mt-3 flex items-center gap-1.5" style={{ color: "var(--color-text-subtle)" }}>
                <Gauge size={12} /> Click a batch to see its own department and section breakdown.
              </p>
            </SectionCard>
          </div>
        )}
      </PageWrapper>
    </ITLayout>
  );
}
