"use client";

import { useEffect, useState } from "react";
import {
  Users, ShieldCheck, Crown, LayoutDashboard, Building2,
  AlertTriangle, ChevronDown, Gauge,
} from "lucide-react";
import { ITLayout } from "@/components/layout/ITLayout";
import { PageWrapper } from "@/components/layout/PageWrapper";
import { PageHeader } from "@/components/layout/PageHeader";
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

function StatTile({ icon: Icon, label, value }: { icon: React.ElementType; label: string; value: number }) {
  return (
    <div
      className="flex items-center gap-3 p-4 rounded-[var(--radius-xl)]"
      style={{ background: "var(--color-surface)", border: "1px solid var(--color-border)", boxShadow: "var(--shadow-sm)" }}
    >
      <div className="w-10 h-10 rounded-full flex items-center justify-center shrink-0" style={{ background: "var(--color-primary-light)" }}>
        <Icon size={18} style={{ color: "var(--color-primary)" }} />
      </div>
      <div className="min-w-0">
        <p className="text-xl font-bold leading-tight" style={{ color: "var(--color-text)" }}>{value.toLocaleString()}</p>
        <p className="text-xs mt-0.5" style={{ color: "var(--color-text-subtle)" }}>{label}</p>
      </div>
    </div>
  );
}

// Total/active/inactive as three short labeled numbers in a row — active
// and inactive always use the same two colors as this app's existing
// Active/Inactive StatusBadge (it/admins, it/departments, etc.), so this
// reads consistently with every other page rather than inventing a new
// status palette.
function ActiveInactiveStrip({ counts }: { counts: ActiveInactiveCount }) {
  return (
    <div className="flex items-center gap-5">
      <div>
        <p className="text-2xl font-bold" style={{ color: "var(--color-text)" }}>{counts.total}</p>
        <p className="text-xs" style={{ color: "var(--color-text-subtle)" }}>Total</p>
      </div>
      <div>
        <p className="text-2xl font-bold" style={{ color: "var(--color-success)" }}>{counts.active}</p>
        <p className="text-xs" style={{ color: "var(--color-text-subtle)" }}>Active</p>
      </div>
      <div>
        <p className="text-2xl font-bold" style={{ color: "var(--color-text-muted)" }}>{counts.inactive}</p>
        <p className="text-xs" style={{ color: "var(--color-text-subtle)" }}>Inactive</p>
      </div>
    </div>
  );
}

function SectionCard({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div
      className="p-5 rounded-[var(--radius-xl)]"
      style={{ background: "var(--color-surface)", border: "1px solid var(--color-border)", boxShadow: "var(--shadow-sm)" }}
    >
      <h2 className="text-sm font-semibold uppercase tracking-wide mb-4" style={{ color: "var(--color-text-muted)" }}>{title}</h2>
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

function BatchRow({ batch, expanded, onToggle }: { batch: ITDashboardBatchStats; expanded: boolean; onToggle: () => void }) {
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
            <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
              <div>
                <p className="text-xs font-semibold uppercase tracking-wide mb-2" style={{ color: "var(--color-text-subtle)" }}>By department</p>
                <BreakdownTable
                  keyLabel="Department"
                  rows={batch.by_department.map(r => ({ ...r, label: r.department || "(none)" }))}
                />
              </div>
              <div>
                <p className="text-xs font-semibold uppercase tracking-wide mb-2" style={{ color: "var(--color-text-subtle)" }}>By section</p>
                <BreakdownTable
                  keyLabel="Section"
                  rows={batch.by_section.map(r => ({ ...r, label: r.section || "(none)" }))}
                />
              </div>
            </div>
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
  const students = ready ? mergeByDepartment(authStats!.departments.list, userStats!.students.by_department) : null;

  return (
    <ITLayout>
      <PageWrapper>
        <PageHeader
          title="Dashboard"
          subtitle="Live institution-wide numbers — recomputed from the real data on every visit, never cached."
        />

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
            <div className="grid gap-4" style={{ gridTemplateColumns: "repeat(auto-fill, minmax(220px, 1fr))" }}>
              <StatTile icon={Users} label="Students" value={userStats!.students.total} />
              <StatTile icon={ShieldCheck} label="Admins" value={authStats!.admins.total} />
              <StatTile icon={Crown} label="Super Admins" value={authStats!.super_admins.total} />
              <StatTile icon={LayoutDashboard} label="Batches" value={userStats!.batches.length} />
              <StatTile icon={Building2} label="Departments" value={authStats!.departments.total} />
            </div>

            {/* ── Departments ────────────────────────────────────────────────── */}
            <SectionCard title="Departments">
              <ActiveInactiveStrip counts={authStats!.departments} />
            </SectionCard>

            {/* ── Super Admins ───────────────────────────────────────────────── */}
            <SectionCard title="Super Admins">
              <ActiveInactiveStrip counts={authStats!.super_admins} />
            </SectionCard>

            {/* ── Admins ─────────────────────────────────────────────────────── */}
            <SectionCard title="Admins">
              <div className="mb-5"><ActiveInactiveStrip counts={authStats!.admins} /></div>
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
            <SectionCard title="Students">
              <div className="mb-5"><ActiveInactiveStrip counts={userStats!.students} /></div>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                <div>
                  <p className="text-xs font-semibold uppercase tracking-wide mb-2" style={{ color: "var(--color-text-subtle)" }}>By department</p>
                  <BreakdownTable keyLabel="Department" rows={students!.matched.map(r => ({ ...r, label: r.name || r.code }))} />
                  {students!.unmapped.length > 0 && (
                    <p className="text-xs mt-3 flex items-center gap-1.5" style={{ color: "var(--color-warning)" }}>
                      <AlertTriangle size={12} />
                      {students!.unmapped.length} student group{students!.unmapped.length === 1 ? "" : "s"} under a department that no longer exists: {students!.unmapped.map(r => `"${r.department || "(blank)"}" (${r.total})`).join(", ")}.
                    </p>
                  )}
                </div>
                <div>
                  <p className="text-xs font-semibold uppercase tracking-wide mb-2" style={{ color: "var(--color-text-subtle)" }}>By section</p>
                  <BreakdownTable
                    keyLabel="Section"
                    rows={userStats!.students.by_section.map(r => ({ ...r, label: r.section || "(none)" }))}
                  />
                </div>
              </div>
            </SectionCard>

            {/* ── Sections per department ────────────────────────────────────── */}
            <SectionCard title="Sections per department">
              {userStats!.sections_per_department.length === 0 ? (
                <p className="text-xs italic" style={{ color: "var(--color-text-subtle)" }}>No students assigned to any section yet.</p>
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr style={{ borderBottom: "1px solid var(--color-border)" }}>
                        {["Department", "Section count", "Sections"].map(h => (
                          <th key={h} className="text-left px-3 py-2 text-xs font-semibold uppercase tracking-wider whitespace-nowrap"
                            style={{ color: "var(--color-text-subtle)" }}>{h}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {userStats!.sections_per_department.map(row => (
                        <tr key={row.department} style={{ borderBottom: "1px solid var(--color-border)" }}>
                          <td className="px-3 py-2 font-medium" style={{ color: "var(--color-text)" }}>{row.department || "(none)"}</td>
                          <td className="px-3 py-2" style={{ color: "var(--color-text)" }}>{row.section_count}</td>
                          <td className="px-3 py-2" style={{ color: "var(--color-text-muted)" }}>{row.sections.join(", ")}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
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
                          onToggle={() => setExpandedBatchId(prev => prev === batch.id ? null : batch.id)}
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
