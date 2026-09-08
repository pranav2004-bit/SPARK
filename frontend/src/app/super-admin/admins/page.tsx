"use client";

import { useEffect, useState, useCallback } from "react";
import { Users, ChevronDown } from "lucide-react";
import { PageWrapper } from "@/components/layout/PageWrapper";
import { PageHeader } from "@/components/layout/PageHeader";
import { EmptyState } from "@/components/ui/EmptyState";
import { SearchInput } from "@/components/ui/SearchInput";
import { listenAdminChannel } from "@/lib/adminChannel";
import api, { getErrorMessage } from "@/lib/api";

// Read/query-only (2026-08-19) — admin account creation, editing, status
// toggling, password reset, and deletion are IT-exclusive; see /it/admins
// for the management interface. Admin account management was placed in the
// IT role the same day, with full parity validated live before Super Admin
// was restricted here — same treatment as Batches.

// ── Types ──────────────────────────────────────────────────────────────────────

interface AdminRecord {
  id: string;
  email: string;
  name: string;
  department?: string;
  is_active: boolean;
  created_at: string;
}

// ── UI helpers ─────────────────────────────────────────────────────────────────

function TableSkeleton() {
  return (
    <div className="animate-pulse space-y-3">
      {Array.from({ length: 5 }).map((_, i) => (
        <div key={i} className="h-14 rounded-xl" style={{ background: "var(--color-surface-secondary)" }} />
      ))}
    </div>
  );
}

function StatusBadge({ active }: { active: boolean }) {
  return (
    <span
      className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-semibold"
      style={{
        background: active ? "var(--color-success-bg)" : "var(--color-surface-secondary)",
        color: active ? "var(--color-success)" : "var(--color-text-muted)",
        border: `1px solid ${active ? "var(--color-success)30" : "var(--color-border)"}`,
      }}
    >
      {active ? "Active" : "Inactive"}
    </span>
  );
}

// ── Page ───────────────────────────────────────────────────────────────────────

export default function SuperAdminAdminsPage() {
  const [admins, setAdmins] = useState<AdminRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [pageError, setPageError] = useState("");
  const [searchQuery, setSearchQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState<"" | "active" | "inactive">("");

  // ── Fetch ─────────────────────────────────────────────────────────────────────
  const fetchAdmins = useCallback(async () => {
    setLoading(true);
    setPageError("");
    try {
      const res = await api.get<{ data: AdminRecord[] }>("/auth/admins/");
      setAdmins(res.data.data ?? []);
    } catch (err) {
      setPageError(getErrorMessage(err));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchAdmins(); }, [fetchAdmins]);

  // ── Cross-tab sync: react to admin profile self-updates ───────────────────────
  useEffect(() => {
    const cleanup = listenAdminChannel((event) => {
      if (event.type === "PROFILE_UPDATED") {
        setAdmins((prev) =>
          prev.map((a) => a.id === event.id ? { ...a, name: event.name } : a)
        );
      }
    });
    return cleanup;
  }, []);

  // ── Filtered list (client-side) ───────────────────────────────────────────────
  const q = searchQuery.trim().toLowerCase();
  const filteredAdmins = admins.filter((a) => {
    const matchesSearch = q
      ? a.name.toLowerCase().includes(q) || a.email.toLowerCase().includes(q)
      : true;
    const matchesStatus =
      statusFilter === "active"
        ? a.is_active
        : statusFilter === "inactive"
        ? !a.is_active
        : true;
    return matchesSearch && matchesStatus;
  });

  const isFiltered = q || statusFilter;
  const subtitleText = isFiltered
    ? `${filteredAdmins.length} of ${admins.length} ${admins.length === 1 ? "admin" : "admins"} · Read only`
    : `${admins.length} ${admins.length === 1 ? "admin" : "admins"} · Read only`;

  // ── Render ────────────────────────────────────────────────────────────────────
  return (
    <PageWrapper>
      <PageHeader title="Admins" subtitle={subtitleText} />

      {/* Filter toolbar */}
      {!loading && admins.length > 0 && (
        <div
          className="flex flex-wrap items-center gap-3 rounded-xl px-4 py-3 mb-5"
          style={{ background: "#fff", border: "1px solid var(--color-border)", boxShadow: "var(--shadow-sm)" }}
        >
          <SearchInput
            value={searchQuery}
            onChange={(val) => { setSearchQuery(val); }}
            placeholder="Search by name or email…"
            className="w-64 shrink-0"
          />

          {/* Divider */}
          <div className="hidden sm:block self-stretch w-px" style={{ background: "var(--color-border)" }} />

          {/* Status filter */}
          <div className="relative shrink-0">
            <select
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value as "" | "active" | "inactive")}
              className="h-9 pl-3 pr-8 text-sm rounded-[var(--radius-md)] border bg-white appearance-none cursor-pointer focus:outline-none focus:ring-2 focus:ring-[var(--color-accent)]"
              style={{ borderColor: "var(--color-border)", color: "var(--color-text)", minWidth: 140 }}
            >
              <option value="">All statuses</option>
              <option value="active">Active</option>
              <option value="inactive">Inactive</option>
            </select>
            <ChevronDown size={14} className="absolute right-2.5 top-1/2 -translate-y-1/2 pointer-events-none" style={{ color: "var(--color-text-muted)" }} />
          </div>

          {/* Always rendered — visibility toggle prevents toolbar reflow */}
          <button
            onClick={() => { setSearchQuery(""); setStatusFilter(""); }}
            className="ml-auto text-xs font-medium px-3 py-1.5 rounded-lg transition-colors shrink-0"
            style={{
              color: "var(--color-text-muted)",
              background: "var(--color-surface-secondary)",
              border: "1px solid var(--color-border)",
              visibility: isFiltered ? "visible" : "hidden",
              pointerEvents: isFiltered ? "auto" : "none",
            }}
            onMouseEnter={e => { (e.currentTarget as HTMLButtonElement).style.color = "var(--color-danger)"; (e.currentTarget as HTMLButtonElement).style.borderColor = "var(--color-danger)"; }}
            onMouseLeave={e => { (e.currentTarget as HTMLButtonElement).style.color = "var(--color-text-muted)"; (e.currentTarget as HTMLButtonElement).style.borderColor = "var(--color-border)"; }}
          >
            Clear filters
          </button>
        </div>
      )}

      {/* Page-level error */}
      {pageError && !loading && (
        <div className="rounded-2xl p-5 flex items-center justify-between mb-5"
          style={{ background: "var(--color-danger-bg)", border: "1px solid var(--color-danger)20" }}>
          <p className="text-sm" style={{ color: "var(--color-danger)" }}>{pageError}</p>
          <button onClick={fetchAdmins} className="text-sm font-semibold px-4 py-2 rounded-lg"
            style={{ background: "var(--color-danger)", color: "#fff" }}>Retry</button>
        </div>
      )}

      {/* Table */}
      {loading ? (
        <TableSkeleton />
      ) : admins.length === 0 && !pageError ? (
        <EmptyState icon={Users} title="No Admins Yet"
          subtitle="Admin accounts are created by IT — none exist yet." />
      ) : filteredAdmins.length === 0 ? (
        <EmptyState icon={Users} title="No results"
          subtitle={`No admins match "${searchQuery}". Try a different name or email.`} />
      ) : (
        <div className="rounded-2xl overflow-hidden"
          style={{ background: "#fff", border: "1px solid var(--color-border)", boxShadow: "var(--shadow-sm)" }}>
          <table className="w-full">
            <thead>
              <tr style={{ borderBottom: "1px solid var(--color-border)", background: "var(--color-surface-secondary)" }}>
                {["Name", "Email", "Status"].map((h) => (
                  <th key={h} className="px-5 py-3 text-left text-xs font-semibold tracking-wide"
                    style={{ color: "var(--color-text-muted)" }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {filteredAdmins.map((admin, idx) => (
                <tr key={admin.id} style={{ borderBottom: idx < filteredAdmins.length - 1 ? "1px solid var(--color-border)" : "none" }}>
                  <td className="px-5 py-4">
                    <div className="flex items-center gap-3">
                      <span className="flex items-center justify-center rounded-full text-xs font-bold shrink-0"
                        style={{ width: 32, height: 32, background: "var(--color-primary-light)", color: "var(--color-primary)" }}>
                        {(admin.name || admin.email).charAt(0).toUpperCase()}
                      </span>
                      <span className="text-sm font-semibold" style={{ color: "var(--color-text)" }}>
                        {admin.name || <span style={{ color: "var(--color-text-muted)", fontStyle: "italic" }}>No name</span>}
                      </span>
                    </div>
                  </td>
                  <td className="px-5 py-4 text-sm" style={{ color: "var(--color-text-muted)" }}>{admin.email}</td>
                  <td className="px-5 py-4"><StatusBadge active={admin.is_active} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </PageWrapper>
  );
}
